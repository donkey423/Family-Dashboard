from contextlib import asynccontextmanager
import asyncio
import re
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal, cast as typing_cast
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from .application.use_cases import ImportDocumentUseCase, ImportFinanceCsvUseCase
from .application.codex_mcp_import import CodexMcpGmailImportCommand, CodexMcpGmailImportUseCase
from .application.document_lifecycle import DocumentImpactChanged, DocumentLifecycleUseCase, DocumentNotFound
from .application.pdf_processing import (
    PdfPreviewCommand,
    PdfPreviewDocumentNotFound,
    PdfPreviewProfileNotFound,
    PdfPreviewSecretProfileNotFound,
    PdfPreviewUnsupportedDocument,
    PdfPreviewUseCase,
)
from .application.statement_import import StatementAnalysisCommand, StatementImportError, StatementImportUseCase
from .config import Settings
from .database import Base, make_engine, make_session_factory
from .documents.service import DocumentService
from .documents.processors.ocr import TesseractOcrProvider
from .documents.processors.pdf import PdfDocumentProcessor
from .documents.processors.ports import DocumentProcessingError
from .finance.service import FinanceCsvImportService
from .finance.queries import active_transaction_filter, transaction_totals
from .finance.statements.contracts import BankStatementParser, StatementData, resolve_transaction_date
from .finance.statements.taiwan_credit_cards import TaiwanCreditCardStatementParser
from .exports.ports import WorkbookWriter
from .exports.service import WorkbookExportBusy, WorkbookExportService
from .exports.xlsx import XlsxWorkbookWriter
from .models import AIProviderProfile, Document, DocumentSourceRecord, FinanceTransaction, GmailConnection, ImportJob, Statement, StatementAccount, utc_now
from .documents.sources import DocumentSourceRegistry, LocalFileDocumentSource
from .documents.sources.ports import DocumentSourceUnavailable
from .models import DocumentSecurityProfile, PasswordRuleRecord, SecretProfile
from .security.secrets import KeyringSecretStore, SecretStore, SecretStoreUnavailable
from .security.secrets.service import PERSONAL_UNLOCK_ID, SecretProfileService
from .security.password_rules import PasswordInstructionContext, PasswordInstructionExtractor
from .security.password_rules.ports import PasswordRuleInterpreter, PasswordRuleInterpreterUnavailable
from .security.password_rules.provider_service import AIProviderService
from .security.password_rules.service import PasswordRuleService
from .storage.local_filesystem import LocalFilesystemStorage
from .integrations.gmail import GmailOAuthService, GmailSyncScheduler, GmailSyncUseCase
from .integrations.gmail.client import GmailClient, GmailUnavailable
from .integrations.gmail.oauth import GmailAuthorizationUnavailable
from .integrations.gmail.scheduler import SYNC_INTERVAL
from .integrations.gmail.source import GmailAttachmentDocumentSource


class SecretProfileInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    national_id: str = Field(min_length=1, max_length=64)
    birthday: date


class PersonalUnlockInput(BaseModel):
    national_id: str | None = Field(default=None, max_length=64)
    birthday: date | None = None


class DocumentSecurityProfileInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    institution: str = Field(min_length=1, max_length=100)
    sender_pattern: str | None = Field(default=None, max_length=255)
    secret_profile_id: str


class AIProviderInput(BaseModel):
    provider: Literal["groq", "openai"] = "openai"
    api_key: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)


class PasswordRuleAnalysisInput(BaseModel):
    document_security_profile_id: str | None = None
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=20_000)
    sender: str = Field(default="", max_length=255)
    filename: str = Field(default="", max_length=255)


class PdfPreviewInput(PasswordRuleAnalysisInput):
    allow_ai_analysis: bool = False


class StatementAnalysisInput(PasswordRuleAnalysisInput):
    allow_ai_analysis: bool = False
    statement_account_id: str | None = Field(default=None, max_length=36)


class StatementConfirmInput(BaseModel):
    review_version: int = Field(ge=1)


class StatementAccountInput(BaseModel):
    bank_id: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=100)
    account_hint: str | None = Field(default=None, max_length=80)

    @field_validator("account_hint")
    @classmethod
    def account_hint_must_be_masked(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(character for character in value if character.isdigit())
        masked = any(marker in value for marker in ("*", "•", "●")) or "xx" in value.casefold()
        if any(len(run) > 4 for run in re.findall(r"\d+", value)):
            raise ValueError("帳戶提示只能保存遮罩後資訊")
        if len(digits) > 4 and not masked:
            raise ValueError("帳戶提示只能保存遮罩後資訊")
        return value.strip()


class StatementAccountPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    account_hint: str | None = Field(default=None, max_length=80)

    @field_validator("account_hint")
    @classmethod
    def account_hint_must_be_masked(cls, value: str | None) -> str | None:
        return StatementAccountInput.account_hint_must_be_masked(value)


class GmailOAuthClientInput(BaseModel):
    config: dict[str, Any]


class GmailSyncInput(BaseModel):
    query: str | None = Field(default=None, max_length=500)


class GmailScheduleInput(BaseModel):
    enabled: bool


class WorkbookExportInput(BaseModel):
    enabled: bool


class DocumentLifecycleInput(BaseModel):
    impact_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(default="", max_length=200)


_DEFAULT_STATEMENT_PARSER = object()


def _month_range(value: str | None) -> tuple[date, date] | None:
    if not value:
        return None
    try:
        if len(value) != 7 or value[4] != "-" or not value[:4].isdigit() or not value[5:].isdigit():
            raise ValueError
        year, month = int(value[:4]), int(value[5:])
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return start, end
    except ValueError as error:
        raise HTTPException(status_code=422, detail="月份格式無效，請使用 YYYY-MM") from error


def _currency_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise HTTPException(status_code=422, detail="幣別格式無效，請使用三碼英文字母")
    return normalized


def _raise_ai_provider_error(error: PasswordRuleInterpreterUnavailable) -> None:
    status_codes = {
        "ai_auth_failed": 401,
        "ai_rate_limited": 429,
        "ai_quota_unavailable": 429,
        "ai_model_unavailable": 422,
        "ai_schema_invalid": 502,
        "ai_timeout": 504,
        "ai_service_unavailable": 503,
    }
    reason_code = error.reason_code
    raise HTTPException(
        status_code=status_codes.get(reason_code, 503),
        detail={"code": reason_code, "message": str(error)},
        headers={"X-FamilyHub-Error": reason_code},
    ) from None


def create_app(
    settings: Settings | None = None,
    *,
    create_schema: bool = False,
    secret_store: SecretStore | None = None,
    password_interpreter: PasswordRuleInterpreter | None = None,
    pdf_processor: PdfDocumentProcessor | None = None,
    statement_parser: BankStatementParser | None | object = _DEFAULT_STATEMENT_PARSER,
    gmail_client_factory: Callable[[], GmailClient] | None = None,
    workbook_writer: WorkbookWriter | None = None,
) -> FastAPI:
    config = settings or Settings.from_environment()
    legacy_gmail_enabled = config.legacy_gmail_oauth_enabled or gmail_client_factory is not None
    engine = make_engine(config.database_url)
    session_factory = make_session_factory(engine)
    storage = LocalFilesystemStorage(config.storage_root)
    documents = DocumentService(storage)
    active_secret_store = secret_store
    password_rules = PasswordRuleService()
    instruction_extractor = PasswordInstructionExtractor()
    active_pdf_processor = pdf_processor or PdfDocumentProcessor(TesseractOcrProvider(
        config.tesseract_executable,
        config.ocr_languages,
    ))

    def get_secret_store() -> SecretStore:
        nonlocal active_secret_store
        if active_secret_store is None:
            try:
                active_secret_store = KeyringSecretStore()
            except SecretStoreUnavailable as error:
                raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from error
        return active_secret_store

    def get_pdf_secret_store() -> SecretStore:
        try:
            return get_secret_store()
        except HTTPException as error:
            raise SecretStoreUnavailable("Windows 安全資料保管庫目前無法使用") from error

    def get_pdf_interpreter(session: Session) -> PasswordRuleInterpreter:
        return password_interpreter or AIProviderService(get_pdf_secret_store()).interpreter(session)

    def make_gmail_client() -> GmailClient:
        if not legacy_gmail_enabled:
            raise GmailUnavailable("網站內建 Gmail OAuth 已停用")
        if gmail_client_factory is not None:
            return gmail_client_factory()
        try:
            with session_factory() as gmail_session:
                return GmailOAuthService(get_secret_store()).authorized_client(gmail_session)
        except HTTPException:
            raise GmailAuthorizationUnavailable("Gmail 授權目前無法使用") from None

    gmail_source = GmailAttachmentDocumentSource(make_gmail_client, config.max_upload_bytes)
    document_sources = DocumentSourceRegistry((LocalFileDocumentSource(storage), gmail_source))
    pdf_preview = PdfPreviewUseCase(
        document_sources,
        gmail_source,
        active_pdf_processor,
        instruction_extractor,
        password_rules,
        get_pdf_secret_store,
        get_pdf_interpreter,
    )
    active_statement_parser = (
        TaiwanCreditCardStatementParser()
        if statement_parser is _DEFAULT_STATEMENT_PARSER
        else typing_cast(BankStatementParser | None, statement_parser)
    )
    statement_import = StatementImportUseCase(pdf_preview, active_statement_parser)
    document_import = ImportDocumentUseCase(documents)
    codex_mcp_import = CodexMcpGmailImportUseCase(documents, instruction_extractor)
    finance_service = FinanceCsvImportService(documents, document_sources)
    finance_import = ImportFinanceCsvUseCase(finance_service)
    document_lifecycle = DocumentLifecycleUseCase()
    gmail_sync = GmailSyncUseCase(documents, finance_service, config.max_upload_bytes)
    gmail_sync_lock = Lock()
    workbook_export = WorkbookExportService(
        session_factory,
        workbook_writer or XlsxWorkbookWriter(),
        config.workbook_path,
        pdf_transaction_parser_ready=active_statement_parser is not None,
    )

    def get_secret_service() -> SecretProfileService:
        return SecretProfileService(get_secret_store())

    gmail_scheduler = GmailSyncScheduler(
        session_factory,
        gmail_sync,
        make_gmail_client,
        gmail_sync_lock,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.storage_root.mkdir(parents=True, exist_ok=True)
        if create_schema:
            Base.metadata.create_all(engine)
        stop_scheduler = asyncio.Event()
        scheduler_task = (
            asyncio.create_task(gmail_scheduler.run(stop_scheduler))
            if legacy_gmail_enabled
            else None
        )
        export_task = asyncio.create_task(workbook_export.run(stop_scheduler))
        try:
            yield
        finally:
            stop_scheduler.set()
            if scheduler_task is not None:
                await scheduler_task
            await export_task
        engine.dispose()

    app = FastAPI(title="家庭收支記錄 API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.settings = config
    app.state.gmail_sync_scheduler = gmail_scheduler if legacy_gmail_enabled else None
    app.state.workbook_export = workbook_export
    app.state.statement_import = statement_import
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
        expose_headers=["X-FamilyHub-Text-Extraction", "X-FamilyHub-Error"],
    )

    def get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def require_legacy_gmail() -> None:
        if not legacy_gmail_enabled:
            raise HTTPException(
                status_code=410,
                detail="網站內建 Gmail OAuth 已停用；Gmail 帳單由 Codex MCP 自動化收錄",
            )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "product": "家庭收支記錄"}

    @app.get("/api/exports/excel/status")
    def workbook_export_status():
        return workbook_export.status()

    @app.post("/api/exports/excel/settings")
    def configure_workbook_export(body: WorkbookExportInput):
        try:
            return workbook_export.configure(body.enabled)
        except WorkbookExportBusy:
            raise HTTPException(status_code=409, detail="Excel 正在更新，請稍後重試") from None

    @app.post("/api/exports/excel/refresh")
    def refresh_workbook_export():
        try:
            workbook_export.refresh(force=True)
        except WorkbookExportBusy:
            raise HTTPException(status_code=409, detail="Excel 正在更新，請稍後重試") from None
        return workbook_export.status()

    @app.get("/api/exports/excel/content")
    def download_workbook():
        try:
            content = workbook_export.read_workbook()
        except FileNotFoundError:
            raise HTTPException(status_code=409, detail="Excel 尚未更新，請先完成更新再下載") from None
        except OSError:
            raise HTTPException(status_code=503, detail="Excel 檔案目前無法讀取") from None
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(config.workbook_path.name)}",
            "Cache-Control": "private, no-store",
        })

    @app.get("/api/security/profiles")
    def list_secret_profiles(session: Session = Depends(get_session)):
        return [
            {"id": row.id, "display_name": row.display_name, "has_credentials": True}
            for row in session.query(SecretProfile).order_by(SecretProfile.created_at.desc()).all()
        ]

    @app.get("/api/security/personal-unlock")
    def get_personal_unlock(session: Session = Depends(get_session)):
        profile = session.get(SecretProfile, PERSONAL_UNLOCK_ID)
        if profile is None:
            return {"has_national_id": False, "has_birthday": False}
        try:
            national_id, birthday = get_secret_service().get_values(profile)
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        return {"has_national_id": bool(national_id), "has_birthday": bool(birthday)}

    @app.get("/api/gmail/status")
    def gmail_status(session: Session = Depends(get_session)):
        require_legacy_gmail()
        from .models import GmailSyncState

        connection = session.get(GmailConnection, "gmail")
        sync_state = session.get(GmailSyncState, "gmail")
        authorized = False
        if connection is not None:
            try:
                authorized = bool(get_secret_store().get(connection.token_credential_ref))
            except SecretStoreUnavailable:
                raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        return {
            "configured": connection is not None,
            "authorized": authorized,
            "scope": "gmail.readonly" if authorized else None,
            "last_sync_status": sync_state.status if sync_state else "never",
            "last_successful_sync": sync_state.last_successful_at if sync_state else None,
            "last_error_summary": sync_state.last_error_summary if sync_state else None,
            "full_sync_in_progress": sync_state.full_sync_in_progress if sync_state else False,
            "auto_sync_enabled": connection.auto_sync_enabled if connection else False,
            "next_sync_at": _as_utc(connection.next_scheduled_sync_at) if connection and connection.next_scheduled_sync_at else None,
            "sync_interval_minutes": int(SYNC_INTERVAL.total_seconds() // 60),
        }

    @app.post("/api/gmail/schedule")
    def configure_gmail_schedule(body: GmailScheduleInput, session: Session = Depends(get_session)):
        require_legacy_gmail()
        with session.begin():
            connection = session.get(GmailConnection, "gmail")
            if connection is None:
                raise HTTPException(status_code=409, detail="請先連接 Gmail 帳戶")
            if body.enabled:
                try:
                    authorized = bool(get_secret_store().get(connection.token_credential_ref))
                except SecretStoreUnavailable:
                    raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
                if not authorized:
                    raise HTTPException(status_code=409, detail="請先完成 Gmail 唯讀授權")
            was_enabled = connection.auto_sync_enabled
            connection.auto_sync_enabled = body.enabled
            if body.enabled:
                if not was_enabled or connection.next_scheduled_sync_at is None:
                    connection.next_scheduled_sync_at = utc_now() + SYNC_INTERVAL
            else:
                connection.next_scheduled_sync_at = None
        return {
            "auto_sync_enabled": connection.auto_sync_enabled,
            "next_sync_at": _as_utc(connection.next_scheduled_sync_at) if connection.next_scheduled_sync_at else None,
            "sync_interval_minutes": int(SYNC_INTERVAL.total_seconds() // 60),
        }

    @app.post("/api/gmail/oauth-client", status_code=201)
    def configure_gmail_oauth(body: GmailOAuthClientInput, session: Session = Depends(get_session)):
        require_legacy_gmail()
        try:
            GmailOAuthService(get_secret_store()).configure_client(session, body.config)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="無法安全保存 Gmail 設定，請確認 Windows Credential Manager") from None
        return {"configured": True}

    @app.post("/api/gmail/authorize")
    def authorize_gmail(session: Session = Depends(get_session)):
        require_legacy_gmail()
        try:
            GmailOAuthService(get_secret_store()).authorize(session)
        except GmailAuthorizationUnavailable as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="Gmail 授權未完成") from None
        return {"authorized": True, "scope": "gmail.readonly"}

    @app.post("/api/gmail/sync")
    def sync_gmail(body: GmailSyncInput, session: Session = Depends(get_session)):
        require_legacy_gmail()
        query = body.query or "in:anywhere has:attachment {filename:pdf filename:csv}"
        if not gmail_sync_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Gmail 同步正在進行")
        try:
            client = make_gmail_client()
            result = gmail_sync.execute(session, client, query)
            with session.begin():
                connection = session.get(GmailConnection, "gmail")
                if connection and connection.auto_sync_enabled:
                    connection.next_scheduled_sync_at = utc_now() + SYNC_INTERVAL
            return result
        except GmailAuthorizationUnavailable as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except GmailUnavailable:
            raise HTTPException(status_code=503, detail="Gmail 目前無法連線，請檢查授權與網路") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except Exception:
            raise HTTPException(status_code=503, detail="Gmail 同步未完成") from None
        finally:
            gmail_sync_lock.release()

    @app.post("/api/security/profiles", status_code=201)
    def create_secret_profile(body: SecretProfileInput, session: Session = Depends(get_session)):
        try:
            profile = get_secret_service().create_profile(
                session,
                body.display_name,
                body.national_id,
                body.birthday,
            )
        except SecretStoreUnavailable as error:
            raise HTTPException(status_code=503, detail="無法安全保存資料，請確認 Windows Credential Manager") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception:
            raise HTTPException(status_code=503, detail="無法安全保存資料，請稍後重試") from None
        return {"id": profile.id, "display_name": profile.display_name, "has_credentials": True}

    @app.put("/api/security/personal-unlock")
    def save_personal_unlock(body: PersonalUnlockInput, session: Session = Depends(get_session)):
        try:
            service = get_secret_service()
            profile = service.save_personal_unlock(session, body.national_id, body.birthday)
            national_id, birthday = service.get_values(profile)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        except Exception:
            raise HTTPException(status_code=503, detail="無法安全保存解鎖資料") from None
        return {"has_national_id": bool(national_id), "has_birthday": bool(birthday)}

    @app.get("/api/security/ai-provider")
    def get_ai_provider(session: Session = Depends(get_session)):
        profile = session.get(AIProviderProfile, "openai")
        credential_available = False
        if profile is not None:
            try:
                credential_available = bool(get_secret_store().get(profile.api_key_credential_ref))
            except SecretStoreUnavailable:
                raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        return {
            "configured": profile is not None,
            "credential_available": credential_available,
            "provider": profile.provider if profile else None,
            "model": profile.model if profile else None,
        }

    @app.post("/api/security/ai-provider/test")
    def test_ai_provider(body: AIProviderInput):
        try:
            AIProviderService(get_secret_store()).test_connection(
                body.api_key,
                body.model,
                provider=body.provider,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except PasswordRuleInterpreterUnavailable as error:
            _raise_ai_provider_error(error)
        except HTTPException:
            raise
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        return {"ok": True, "provider": body.provider, "model": body.model.strip()}

    @app.post("/api/security/ai-provider", status_code=201)
    def configure_ai_provider(body: AIProviderInput, session: Session = Depends(get_session)):
        try:
            profile = AIProviderService(get_secret_store()).configure(
                session,
                body.api_key,
                body.model,
                provider=body.provider,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except PasswordRuleInterpreterUnavailable as error:
            _raise_ai_provider_error(error)
        except HTTPException:
            raise
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        except Exception:
            raise HTTPException(status_code=503, detail="無法安全保存 AI 設定，請確認 Windows Credential Manager") from None
        return {
            "configured": True,
            "credential_available": True,
            "provider": profile.provider,
            "model": profile.model,
        }

    @app.get("/api/security/document-profiles")
    def list_document_security_profiles(session: Session = Depends(get_session)):
        rows = session.query(DocumentSecurityProfile).order_by(DocumentSecurityProfile.created_at.desc()).all()
        return [{
            "id": row.id,
            "display_name": row.display_name,
            "institution": row.institution,
            "sender_pattern": row.sender_pattern,
            "secret_profile_id": row.secret_profile_id,
        } for row in rows]

    @app.post("/api/security/document-profiles", status_code=201)
    def create_document_security_profile(body: DocumentSecurityProfileInput, session: Session = Depends(get_session)):
        if not body.display_name.strip() or not body.institution.strip():
            raise HTTPException(status_code=422, detail="請填寫文件解鎖設定名稱與機構名稱")
        with session.begin():
            if session.get(SecretProfile, body.secret_profile_id) is None:
                raise HTTPException(status_code=404, detail="找不到家庭成員安全資料")
            profile = DocumentSecurityProfile(
                id=str(uuid4()),
                display_name=body.display_name.strip(),
                institution=body.institution.strip(),
                sender_pattern=(body.sender_pattern or "").strip() or None,
                secret_profile_id=body.secret_profile_id,
            )
            session.add(profile)
        return {
            "id": profile.id,
            "display_name": profile.display_name,
            "institution": profile.institution,
            "sender_pattern": profile.sender_pattern,
            "secret_profile_id": profile.secret_profile_id,
        }

    @app.post("/api/security/password-rules/analyze")
    def analyze_password_rule(body: PasswordRuleAnalysisInput, session: Session = Depends(get_session)):
        profile_id = body.document_security_profile_id or PERSONAL_UNLOCK_ID
        profile = session.get(DocumentSecurityProfile, profile_id)
        if profile is None:
            raise HTTPException(status_code=422, detail="請先保存個人解鎖資料")
        secret_profile = session.get(SecretProfile, profile.secret_profile_id)
        if secret_profile is None:
            raise HTTPException(status_code=404, detail="找不到家庭成員安全資料")
        try:
            national_id, birthday = get_secret_service().get_values(secret_profile)
            instruction = instruction_extractor.extract(
                PasswordInstructionContext(body.subject, body.body, body.sender, body.filename),
                (value for value in (national_id, birthday) if value),
            )
            if not instruction:
                raise HTTPException(status_code=422, detail="郵件中找不到可辨識的密碼規則說明")
            context = (
                {"document_type": "PDF"}
                if profile.id == PERSONAL_UNLOCK_ID
                else {"institution": profile.institution, "document_type": "PDF statement"}
            )
            fingerprint = password_rules.fingerprint(instruction, context)
            rule = password_rules.get_verified(session, profile.id, fingerprint)
            reused = rule is not None
            session.commit()
            if rule is None:
                interpreter = password_interpreter or AIProviderService(get_secret_store()).interpreter(session)
                rule = interpreter.interpret(instruction, context)
        except HTTPException:
            raise
        except PasswordRuleInterpreterUnavailable as error:
            _raise_ai_provider_error(error)
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        except Exception:
            raise HTTPException(status_code=503, detail="目前無法分析密碼規則") from None
        return {
            "status": rule.status,
            "rule": rule.model_dump(mode="json"),
            "reused_verified_rule": reused,
            "instruction_fingerprint": fingerprint,
        }

    @app.post("/api/documents/{document_id}/preview")
    def preview_document(
        document_id: str,
        body: PdfPreviewInput,
        session: Session = Depends(get_session),
    ):
        try:
            result = pdf_preview.execute(
                session,
                document_id,
                PdfPreviewCommand(
                    document_security_profile_id=body.document_security_profile_id,
                    subject=body.subject,
                    body=body.body,
                    sender=body.sender,
                    filename=body.filename,
                    allow_ai_analysis=body.allow_ai_analysis,
                ),
            )
        except PdfPreviewDocumentNotFound:
            raise HTTPException(status_code=404, detail="找不到文件") from None
        except PdfPreviewProfileNotFound:
            raise HTTPException(status_code=404, detail="找不到文件解鎖設定") from None
        except PdfPreviewSecretProfileNotFound:
            raise HTTPException(status_code=404, detail="找不到家庭成員安全資料") from None
        except PdfPreviewUnsupportedDocument:
            raise HTTPException(status_code=415, detail="目前只支援 PDF 預覽") from None
        except HTTPException:
            raise
        except DocumentSourceUnavailable:
            raise HTTPException(
                status_code=503,
                detail="目前無法取得文件來源",
                headers={"X-FamilyHub-Error": "document_source_unavailable"},
            ) from None
        except DocumentProcessingError as error:
            messages = {
                "pdf_password_required": "PDF 需要解鎖資料與郵件中的密碼提示。請至設定保存身分資料後重試。",
                "pdf_wrong_password": "目前的密碼規則無法開啟這份 PDF。",
                "pdf_unsupported_encryption": "此 PDF 使用不支援的加密方式。",
                "pdf_malformed": "PDF 無法讀取或內容格式不正確。",
                "pdf_processing_limit": "PDF 超過目前的處理限制。",
            }
            raise HTTPException(
                status_code=422,
                detail=messages.get(error.code, "PDF 處理失敗"),
                headers={"X-FamilyHub-Error": error.code},
            ) from None
        except PasswordRuleInterpreterUnavailable as error:
            _raise_ai_provider_error(error)
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        except Exception:
            raise HTTPException(status_code=503, detail="PDF 預覽處理失敗") from None
        processed = result.processed
        return Response(
            content=processed.preview_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(result.filename)}",
                "Cache-Control": "private, no-store, max-age=0",
                "X-FamilyHub-Text-Extraction": processed.ocr_status,
            },
        )

    def _raise_statement_error(error: StatementImportError) -> None:
        status_codes = {
            "document_not_found": 404,
            "statement_not_found": 404,
            "statement_account_not_found": 404,
            "unsupported_document": 415,
            "document_revoked": 409,
            "statement_not_ready": 409,
            "statement_review_changed": 409,
            "statement_period_already_imported": 409,
            "transaction_identity_conflict": 409,
            "statement_account_mismatch": 422,
            "statement_account_required": 422,
            "statement_account_ambiguous": 422,
            "statement_identity_missing": 422,
            "statement_invalid": 422,
        }
        raise HTTPException(status_code=status_codes.get(error.code, 503), detail=error.detail) from None

    def _statement_detail_payload(statement: Statement, session: Session, *, include_lines: bool) -> dict:
        data = None
        if statement.statement_json:
            try:
                data = StatementData.model_validate(statement.statement_json)
            except ValueError:
                data = None
        transaction_count = session.scalar(
            select(func.count(FinanceTransaction.id)).where(FinanceTransaction.statement_id == statement.id)
        ) or 0
        account = session.get(StatementAccount, statement.statement_account_id) if statement.statement_account_id else None
        payload = {
            "statement_id": statement.id,
            "document_id": statement.document_id,
            "statement_account_id": statement.statement_account_id,
            "account_name": account.display_name if account else None,
            "bank_id": statement.bank_id,
            "format_version": statement.format_version,
            "parser_id": statement.parser_id,
            "parser_version": statement.parser_version,
            "period_start": statement.period_start,
            "period_end": statement.period_end,
            "closing_date": data.closing_date if data else None,
            "status": statement.status,
            "reason_code": statement.reason_code,
            "review_version": statement.review_version,
            "line_count": len(data.lines) if data else 0,
            "transaction_count": transaction_count,
            "reconciliation": data.reconciliation.model_dump(mode="json") if data else None,
            "created_at": statement.created_at,
            "updated_at": statement.updated_at,
            "imported_at": statement.imported_at,
        }
        if include_lines and data:
            payload["lines"] = []
            for line in data.lines:
                effective_date, date_basis = resolve_transaction_date(line, data.closing_date)
                payload["lines"].append({
                    **line.model_dump(mode="json"),
                    "effective_transaction_date": effective_date,
                    "transaction_date_basis": date_basis,
                })
        return payload

    @app.get("/api/statement-accounts")
    def list_statement_accounts(session: Session = Depends(get_session)):
        rows = session.scalars(select(StatementAccount).order_by(StatementAccount.display_name, StatementAccount.id)).all()
        return [{
            "id": row.id,
            "bank_id": row.bank_id,
            "display_name": row.display_name,
            "account_hint": row.account_hint,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        } for row in rows]

    @app.post("/api/statement-accounts")
    def create_statement_account(body: StatementAccountInput, session: Session = Depends(get_session)):
        with session.begin():
            account = StatementAccount(
                id=str(uuid4()),
                bank_id=body.bank_id.strip(),
                display_name=body.display_name.strip(),
                account_hint=body.account_hint,
            )
            session.add(account)
        return {
            "id": account.id,
            "bank_id": account.bank_id,
            "display_name": account.display_name,
            "account_hint": account.account_hint,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }

    @app.patch("/api/statement-accounts/{account_id}")
    def update_statement_account(account_id: str, body: StatementAccountPatch, session: Session = Depends(get_session)):
        if body.display_name is None and body.account_hint is None:
            raise HTTPException(status_code=422, detail="至少要提供一個要更新的欄位")
        with session.begin():
            account = session.get(StatementAccount, account_id)
            if account is None:
                raise HTTPException(status_code=404, detail="找不到帳單帳戶")
            if body.display_name is not None:
                account.display_name = body.display_name.strip()
            if body.account_hint is not None:
                account.account_hint = body.account_hint
        return {
            "id": account.id,
            "bank_id": account.bank_id,
            "display_name": account.display_name,
            "account_hint": account.account_hint,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }

    @app.post("/api/documents/{document_id}/statement-analysis")
    def analyze_statement(
        document_id: str,
        body: StatementAnalysisInput,
        session: Session = Depends(get_session),
    ):
        try:
            return statement_import.analyze(
                session,
                document_id,
                StatementAnalysisCommand(
                    pdf=PdfPreviewCommand(
                        document_security_profile_id=body.document_security_profile_id,
                        subject=body.subject,
                        body=body.body,
                        sender=body.sender,
                        filename=body.filename,
                        allow_ai_analysis=body.allow_ai_analysis,
                    ),
                    statement_account_id=body.statement_account_id,
                ),
            )
        except StatementImportError as error:
            _raise_statement_error(error)
        except PdfPreviewDocumentNotFound:
            raise HTTPException(status_code=404, detail="找不到文件") from None
        except PdfPreviewProfileNotFound:
            raise HTTPException(status_code=404, detail="找不到文件解鎖設定") from None
        except PdfPreviewSecretProfileNotFound:
            raise HTTPException(status_code=404, detail="找不到文件解鎖安全資料") from None
        except PdfPreviewUnsupportedDocument:
            raise HTTPException(status_code=415, detail="目前只支援 PDF 帳單分析") from None
        except DocumentSourceUnavailable:
            raise HTTPException(status_code=503, detail="目前無法取得文件來源") from None
        except DocumentProcessingError as error:
            messages = {
                "pdf_password_required": "PDF 需要解鎖資料與郵件中的密碼提示。",
                "pdf_wrong_password": "目前的密碼規則無法開啟這份 PDF。",
                "pdf_unsupported_encryption": "此 PDF 使用不支援的加密方式。",
                "pdf_malformed": "PDF 無法讀取或內容格式不正確。",
                "pdf_processing_limit": "PDF 超過目前的處理限制。",
            }
            raise HTTPException(status_code=422, detail=messages.get(error.code, "PDF 處理失敗")) from None
        except PasswordRuleInterpreterUnavailable as error:
            _raise_ai_provider_error(error)
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        except Exception:
            raise HTTPException(status_code=503, detail="帳單分析處理失敗") from None

    @app.get("/api/statements")
    def list_statements(
        status: Literal["pending", "ready", "imported"] | None = Query(default=None),
        session: Session = Depends(get_session),
    ):
        query = select(Statement)
        if status:
            query = query.where(Statement.status == status)
        rows = session.scalars(query.order_by(Statement.created_at.desc(), Statement.id)).all()
        return [_statement_detail_payload(row, session, include_lines=False) for row in rows]

    @app.post("/api/statements/{statement_id}/confirm")
    def confirm_statement(statement_id: str, body: StatementConfirmInput, session: Session = Depends(get_session)):
        try:
            return statement_import.confirm(session, statement_id, body.review_version)
        except StatementImportError as error:
            _raise_statement_error(error)

    @app.get("/api/statements/{statement_id}")
    def get_statement(statement_id: str, session: Session = Depends(get_session)):
        statement = session.get(Statement, statement_id)
        if statement is None:
            raise HTTPException(status_code=404, detail="找不到帳單分析結果")
        return _statement_detail_payload(statement, session, include_lines=True)

    @app.get("/api/integrations/codex-mcp/status")
    def codex_mcp_status(session: Session = Depends(get_session)):
        latest = session.scalar(
            select(ImportJob)
            .where(ImportJob.source_type == "codex_mcp")
            .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
        )
        return {
            "mode": "codex_mcp",
            "legacy_gmail_oauth_enabled": legacy_gmail_enabled,
            "last_import_at": latest.created_at if latest else None,
            "last_import_status": latest.status if latest else None,
        }

    @app.post("/api/integrations/codex-mcp/gmail/import", status_code=201)
    async def import_codex_mcp_gmail_attachment(
        file: UploadFile = File(...),
        message_id: str = Form(..., max_length=512),
        attachment_id: str = Form(..., max_length=512),
        subject: str = Form(default="", max_length=500),
        sender: str = Form(default="", max_length=255),
        password_instruction: str = Form(default="", max_length=20_000),
        session: Session = Depends(get_session),
    ):
        content = await file.read(config.max_upload_bytes + 1)
        if len(content) > config.max_upload_bytes:
            raise HTTPException(status_code=413, detail="文件超過上傳大小限制")
        try:
            imported, instruction_detected = codex_mcp_import.execute(session, CodexMcpGmailImportCommand(
                filename=file.filename or "statement.pdf",
                content=content,
                message_id=message_id,
                attachment_id=attachment_id,
                subject=subject,
                sender=sender,
                password_instruction=password_instruction,
            ))
        except ValueError as error:
            status_code = 409 if str(error) == "來源識別碼已對應不同內容" else 400
            raise HTTPException(status_code=status_code, detail=str(error)) from error
        return {
            "document_id": imported.document.id,
            "filename": imported.document.filename,
            "sha256": imported.document.sha256,
            "duplicate": imported.duplicate,
            "duplicate_source": imported.duplicate_source,
            "instruction_detected": instruction_detected,
            "skipped_revoked": imported.document.revoked_at is not None,
        }

    @app.post("/api/documents")
    async def upload_document(file: UploadFile = File(...), session: Session = Depends(get_session)):
        content = await file.read(config.max_upload_bytes + 1)
        if len(content) > config.max_upload_bytes:
            raise HTTPException(status_code=413, detail="文件超過上傳大小限制")
        try:
            result = document_import.execute(session, file.filename or "upload", content, "documents")
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"id": result.document.id, "filename": result.document.filename, "sha256": result.document.sha256, "duplicate": result.duplicate, "skipped_revoked": result.document.revoked_at is not None}

    @app.get("/api/documents")
    def list_documents(state: Literal["active", "revoked", "all"] = "active", session: Session = Depends(get_session)):
        statement = select(Document)
        if state != "all":
            statement = statement.where(Document.revoked_at.is_(None) if state == "active" else Document.revoked_at.is_not(None))
        rows = session.scalars(statement.order_by(Document.created_at.desc())).all()
        return [{
            "id": row.id,
            "filename": row.filename,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "created_at": row.created_at,
            "revoked_at": row.revoked_at,
            "revocation_reason": row.revocation_reason,
            "sources": [{"type": source.source_type, "availability": source.availability_status} for source in row.sources],
        } for row in rows]

    @app.get("/api/documents/{document_id}/detail")
    def document_detail(document_id: str, session: Session = Depends(get_session)):
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="找不到文件")
        transactions = session.scalars(
            select(FinanceTransaction).where(FinanceTransaction.source_document_id == document_id).order_by(
                case((FinanceTransaction.transaction_date.is_(None), 1), else_=0),
                FinanceTransaction.transaction_date.desc(),
                FinanceTransaction.created_at.desc(),
                FinanceTransaction.id,
            )
        ).all()
        jobs = session.scalars(select(ImportJob).where(ImportJob.document_id == document_id).order_by(ImportJob.created_at.desc())).all()
        return {
            "document": {
                "id": document.id,
                "filename": document.filename,
                "content_type": document.content_type,
                "size_bytes": document.size_bytes,
                "created_at": document.created_at,
                "revoked_at": document.revoked_at,
                "revocation_reason": document.revocation_reason,
                "sources": [{"type": source.source_type, "availability": source.availability_status} for source in document.sources],
            },
            "sources": [{
                "type": source.source_type,
                "availability": source.availability_status,
                "has_local_copy": source.source_type == "local_file" and source.storage_key is not None,
                "last_verified_at": source.last_verified_at,
            } for source in document.sources],
            "transactions": [{
                "id": row.id,
                "source_document_id": row.source_document_id,
                "date": row.transaction_date,
                "description": row.description,
                "amount": str(row.amount),
                "currency": row.currency,
            } for row in transactions],
            "jobs": [{
                "id": row.id,
                "document_id": row.document_id,
                "source_type": row.source_type,
                "target_module": row.target_module,
                "status": row.status,
                "summary": row.summary,
                "created_at": row.created_at,
            } for row in jobs],
        }

    @app.get("/api/documents/{document_id}/import-impact")
    def document_import_impact(document_id: str, session: Session = Depends(get_session)):
        try:
            return document_lifecycle.preview(session, document_id)
        except DocumentNotFound:
            raise HTTPException(status_code=404, detail="找不到文件") from None

    @app.post("/api/documents/{document_id}/revoke")
    def revoke_document(document_id: str, body: DocumentLifecycleInput, session: Session = Depends(get_session)):
        return change_document_state(document_id, body, True, session)

    @app.post("/api/documents/{document_id}/restore")
    def restore_document(document_id: str, body: DocumentLifecycleInput, session: Session = Depends(get_session)):
        return change_document_state(document_id, body, False, session)

    def change_document_state(document_id: str, body: DocumentLifecycleInput, revoked: bool, session: Session):
        try:
            return document_lifecycle.execute(session, document_id, revoked=revoked, impact_token=body.impact_token, reason=body.reason)
        except DocumentNotFound:
            raise HTTPException(status_code=404, detail="找不到文件") from None
        except DocumentImpactChanged:
            raise HTTPException(status_code=409, detail="文件或交易已變更，請重新檢視影響後再確認") from None

    @app.post("/api/documents/{document_id}/save-local")
    def save_document_locally(document_id: str, session: Session = Depends(get_session)):
        try:
            with session.begin():
                document = session.get(Document, document_id)
                if document is None:
                    raise HTTPException(status_code=404, detail="找不到文件")
                content = document_sources.read(document)
                if len(content) > config.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="文件超過本機保存大小限制")
                saved = documents.import_bytes(session, document.filename, content, "documents")
        except HTTPException:
            raise
        except DocumentSourceUnavailable:
            raise HTTPException(status_code=503, detail="目前無法取得原始文件") from None
        return {"id": saved.document.id, "saved_locally": True}

    @app.get("/api/documents/{document_id}/content")
    def get_document_content(document_id: str, session: Session = Depends(get_session)):
        unavailable = False
        with session.begin():
            document = session.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="找不到文件")
            try:
                content = document_sources.read(document)
            except DocumentSourceUnavailable:
                unavailable = True
                content = b""
        if unavailable:
            raise HTTPException(status_code=503, detail="目前無法取得文件來源")
        return Response(
            content=content,
            media_type=document.content_type,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(document.filename)}",
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/finance/import-csv")
    async def import_finance_csv(file: UploadFile = File(...), session: Session = Depends(get_session)):
        content = await file.read(config.max_upload_bytes + 1)
        if len(content) > config.max_upload_bytes:
            raise HTTPException(status_code=413, detail="文件超過上傳大小限制")
        try:
            return finance_import.execute(session, file.filename or "upload.csv", content)
        except (ValueError, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/finance/transactions")
    def list_transactions(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        month: str | None = Query(default=None, max_length=7),
        currency: str | None = Query(default=None, max_length=3),
        session: Session = Depends(get_session),
    ):
        filters = [active_transaction_filter()]
        month_range = _month_range(month)
        if month_range:
            filters.extend([
                FinanceTransaction.transaction_date >= month_range[0],
                FinanceTransaction.transaction_date < month_range[1],
            ])
        currency_code = _currency_code(currency)
        if currency_code:
            filters.append(FinanceTransaction.currency == currency_code)
        statement = select(FinanceTransaction).where(*filters)
        total = session.scalar(select(func.count(FinanceTransaction.id)).where(*filters)) or 0
        rows = session.scalars(
            statement.order_by(
                case((FinanceTransaction.transaction_date.is_(None), 1), else_=0),
                FinanceTransaction.transaction_date.desc(),
                FinanceTransaction.created_at.desc(),
            ).offset(offset).limit(limit)
        ).all()
        return {
            "items": [{"id": row.id, "source_document_id": row.source_document_id, "date": row.transaction_date, "description": row.description, "amount": str(row.amount), "currency": row.currency} for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/dashboard")
    def dashboard(
        month: str | None = Query(default=None, max_length=7),
        currency: str | None = Query(default=None, max_length=3),
        session: Session = Depends(get_session),
    ):
        month_range = _month_range(month)
        currency_code = _currency_code(currency)
        totals = transaction_totals(
            session,
            start_date=month_range[0] if month_range else None,
            end_date=month_range[1] if month_range else None,
            currency=currency_code,
        )
        available_currencies = session.scalars(
            select(FinanceTransaction.currency)
            .join(Document, FinanceTransaction.source_document_id == Document.id)
            .where(active_transaction_filter())
            .distinct()
            .order_by(FinanceTransaction.currency)
        ).all()
        return {**totals, "available_currencies": available_currencies}

    @app.get("/api/search")
    def search(
        q: str = Query(min_length=1, max_length=200),
        document_limit: int = Query(default=10, ge=1, le=100),
        document_offset: int = Query(default=0, ge=0),
        transaction_limit: int = Query(default=10, ge=1, le=100),
        transaction_offset: int = Query(default=0, ge=0),
        session: Session = Depends(get_session),
    ):
        query = q.strip()
        if not query:
            raise HTTPException(status_code=422, detail="搜尋文字不可為空")
        pattern = f"%{query}%"
        document_filters = [Document.revoked_at.is_(None), Document.filename.ilike(pattern)]
        transaction_filters = [active_transaction_filter(), or_(FinanceTransaction.description.ilike(pattern), cast(FinanceTransaction.amount, String).ilike(pattern))]
        document_total = session.scalar(select(func.count(Document.id)).where(*document_filters)) or 0
        transaction_total = session.scalar(select(func.count(FinanceTransaction.id)).where(*transaction_filters)) or 0
        documents = session.scalars(
            select(Document).where(*document_filters).order_by(Document.created_at.desc(), Document.id).offset(document_offset).limit(document_limit)
        ).all()
        transactions = session.scalars(
            select(FinanceTransaction).where(*transaction_filters).order_by(
                case((FinanceTransaction.transaction_date.is_(None), 1), else_=0),
                FinanceTransaction.transaction_date.desc(),
                FinanceTransaction.created_at.desc(),
                FinanceTransaction.id,
            ).offset(transaction_offset).limit(transaction_limit)
        ).all()
        return {
            "documents": [{
                "id": row.id,
                "filename": row.filename,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "created_at": row.created_at,
                "revoked_at": row.revoked_at,
                "revocation_reason": row.revocation_reason,
                "sources": [{"type": source.source_type, "availability": source.availability_status} for source in row.sources],
            } for row in documents],
            "transactions": [{"id": row.id, "source_document_id": row.source_document_id, "date": row.transaction_date, "description": row.description, "amount": str(row.amount), "currency": row.currency} for row in transactions],
            "document_total": document_total,
            "transaction_total": transaction_total,
            "document_limit": document_limit,
            "document_offset": document_offset,
            "transaction_limit": transaction_limit,
            "transaction_offset": transaction_offset,
        }

    @app.get("/api/jobs")
    def list_jobs(session: Session = Depends(get_session)):
        rows = session.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(100)).all()
        return [{"id": row.id, "document_id": row.document_id, "source_type": row.source_type, "target_module": row.target_module, "status": row.status, "summary": row.summary, "created_at": row.created_at} for row in rows]

    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
