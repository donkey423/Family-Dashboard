from contextlib import asynccontextmanager
import asyncio
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any, Callable, Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from .application.use_cases import ImportDocumentUseCase, ImportFinanceCsvUseCase
from .application.document_lifecycle import DocumentImpactChanged, DocumentLifecycleUseCase, DocumentNotFound
from .config import Settings
from .database import Base, make_engine, make_session_factory
from .documents.service import DocumentService
from .documents.processors.ocr import TesseractOcrProvider
from .documents.processors.pdf import PdfDocumentProcessor
from .documents.processors.ports import DocumentProcessingError, ProcessingContext, ProcessingRequest
from .finance.service import FinanceCsvImportService
from .finance.queries import active_transaction_filter, transaction_totals
from .models import AIProviderProfile, Document, DocumentSourceRecord, FinanceTransaction, GmailConnection, ImportJob, utc_now
from .documents.sources import DocumentSourceRegistry, LocalFileDocumentSource
from .documents.sources.ports import DocumentSourceUnavailable
from .models import DocumentSecurityProfile, PasswordRuleRecord, SecretProfile
from .security.secrets import KeyringSecretStore, SecretStore, SecretStoreUnavailable
from .security.secrets.service import SecretProfileService
from .security.password_rules import PasswordComposer, PasswordInstructionContext, PasswordInstructionExtractor
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


class DocumentSecurityProfileInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    institution: str = Field(min_length=1, max_length=100)
    sender_pattern: str | None = Field(default=None, max_length=255)
    secret_profile_id: str


class AIProviderInput(BaseModel):
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


class GmailOAuthClientInput(BaseModel):
    config: dict[str, Any]


class GmailSyncInput(BaseModel):
    query: str | None = Field(default=None, max_length=500)


class GmailScheduleInput(BaseModel):
    enabled: bool


class DocumentLifecycleInput(BaseModel):
    impact_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(default="", max_length=200)


def create_app(
    settings: Settings | None = None,
    *,
    create_schema: bool = False,
    secret_store: SecretStore | None = None,
    password_interpreter: PasswordRuleInterpreter | None = None,
    pdf_processor: PdfDocumentProcessor | None = None,
    gmail_client_factory: Callable[[], GmailClient] | None = None,
) -> FastAPI:
    config = settings or Settings.from_environment()
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

    def make_gmail_client() -> GmailClient:
        if gmail_client_factory is not None:
            return gmail_client_factory()
        try:
            with session_factory() as gmail_session:
                return GmailOAuthService(get_secret_store()).authorized_client(gmail_session)
        except HTTPException:
            raise GmailAuthorizationUnavailable("Gmail 授權目前無法使用") from None

    gmail_source = GmailAttachmentDocumentSource(make_gmail_client, config.max_upload_bytes)
    document_sources = DocumentSourceRegistry((LocalFileDocumentSource(storage), gmail_source))
    document_import = ImportDocumentUseCase(documents)
    finance_service = FinanceCsvImportService(documents, document_sources)
    finance_import = ImportFinanceCsvUseCase(finance_service)
    document_lifecycle = DocumentLifecycleUseCase()
    gmail_sync = GmailSyncUseCase(documents, finance_service, config.max_upload_bytes)
    gmail_sync_lock = Lock()

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
        scheduler_task = asyncio.create_task(gmail_scheduler.run(stop_scheduler))
        try:
            yield
        finally:
            stop_scheduler.set()
            await scheduler_task
        engine.dispose()

    app = FastAPI(title="家庭收支記錄 API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.settings = config
    app.state.gmail_sync_scheduler = gmail_scheduler
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-FamilyHub-Text-Extraction"],
    )

    def get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "product": "家庭收支記錄"}

    @app.get("/api/security/profiles")
    def list_secret_profiles(session: Session = Depends(get_session)):
        return [
            {"id": row.id, "display_name": row.display_name, "has_credentials": True}
            for row in session.query(SecretProfile).order_by(SecretProfile.created_at.desc()).all()
        ]

    @app.get("/api/gmail/status")
    def gmail_status(session: Session = Depends(get_session)):
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

    @app.get("/api/security/ai-provider")
    def get_ai_provider(session: Session = Depends(get_session)):
        profile = session.get(AIProviderProfile, "openai")
        return {
            "configured": profile is not None,
            "provider": profile.provider if profile else None,
            "model": profile.model if profile else None,
        }

    @app.post("/api/security/ai-provider", status_code=201)
    def configure_ai_provider(body: AIProviderInput, session: Session = Depends(get_session)):
        try:
            profile = AIProviderService(get_secret_store()).configure(session, body.api_key, body.model)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="無法安全保存 AI 設定，請確認 Windows Credential Manager") from None
        return {"configured": True, "provider": profile.provider, "model": profile.model}

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
            raise HTTPException(status_code=422, detail="請填寫 profile 名稱與機構名稱")
        with session.begin():
            if session.get(SecretProfile, body.secret_profile_id) is None:
                raise HTTPException(status_code=404, detail="找不到家庭成員安全 profile")
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
        if not body.document_security_profile_id:
            raise HTTPException(status_code=422, detail="請先選擇文件安全 profile")
        profile = session.get(DocumentSecurityProfile, body.document_security_profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="找不到文件安全 profile")
        secret_profile = session.get(SecretProfile, profile.secret_profile_id)
        if secret_profile is None:
            raise HTTPException(status_code=404, detail="找不到家庭成員安全 profile")
        try:
            national_id, birthday = get_secret_service().get_values(secret_profile)
            instruction = instruction_extractor.extract(
                PasswordInstructionContext(body.subject, body.body, body.sender, body.filename),
                (value for value in (national_id, birthday) if value),
            )
            if not instruction:
                raise HTTPException(status_code=422, detail="郵件中找不到可辨識的密碼規則說明")
            context = {"institution": profile.institution, "document_type": "PDF statement"}
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
            raise HTTPException(status_code=503, detail=str(error)) from None
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
            with session.begin():
                document = session.get(Document, document_id)
                if document is None:
                    raise HTTPException(status_code=404, detail="找不到文件")
                if document.content_type != "application/pdf" and not document.filename.lower().endswith(".pdf"):
                    raise HTTPException(status_code=415, detail="目前只支援 PDF 預覽")
                try:
                    content = document_sources.read(document)
                except DocumentSourceUnavailable:
                    content = None
                gmail_references = session.scalars(select(DocumentSourceRecord).where(
                    DocumentSourceRecord.document_id == document_id,
                    DocumentSourceRecord.source_type == "gmail_attachment",
                )).all()
                profile = session.get(DocumentSecurityProfile, body.document_security_profile_id) if body.document_security_profile_id else None
                if body.document_security_profile_id and profile is None:
                    raise HTTPException(status_code=404, detail="找不到文件安全 profile")
                secret_profile = session.get(SecretProfile, profile.secret_profile_id) if profile else None
                if profile and secret_profile is None:
                    raise HTTPException(status_code=404, detail="找不到家庭成員安全 profile")
            if content is None:
                raise DocumentSourceUnavailable("document source unavailable")

            request = ProcessingRequest(
                content=content,
                context=ProcessingContext(
                    filename=document.filename,
                    content_type=document.content_type,
                    document_security_profile_id=profile.id if profile else None,
                ),
            )
            rule = None
            fingerprint = ""
            processed = None
            try:
                processed = active_pdf_processor.process(request)
            except DocumentProcessingError as initial_error:
                if initial_error.code != "pdf_password_required" or not profile or not secret_profile:
                    raise
                gmail_context = None
                for source in gmail_references:
                    try:
                        gmail_context = gmail_source.read_message_context(source.source_reference or {})
                        break
                    except GmailUnavailable:
                        continue
                national_id, birthday = get_secret_service().get_values(secret_profile)
                instruction = instruction_extractor.extract(
                    PasswordInstructionContext(
                        "\n".join(filter(None, (
                            gmail_context.subject if gmail_context else "",
                            body.subject,
                        ))),
                        "\n".join(filter(None, (
                            gmail_context.body if gmail_context else "",
                            body.body,
                        ))),
                        gmail_context.sender if gmail_context else body.sender,
                        body.filename or document.filename,
                    ),
                    (value for value in (national_id, birthday) if value),
                )
                if not instruction:
                    raise initial_error
                context = {"institution": profile.institution, "document_type": "PDF statement"}
                fingerprint = password_rules.fingerprint(instruction, context)
                rule = password_rules.get_verified(session, profile.id, fingerprint)
                session.commit()
                candidates = PasswordComposer(get_secret_store()).compose(
                    rule, secret_profile.national_id_credential_ref, secret_profile.birthday_credential_ref
                ) if rule else ()
                if candidates:
                    try:
                        processed = active_pdf_processor.process(request, password_candidates=candidates)
                    except DocumentProcessingError as cached_error:
                        if cached_error.code != "pdf_wrong_password" or not body.allow_ai_analysis:
                            raise
                        rule = None
                else:
                    rule = None

                if processed is None:
                    if not body.allow_ai_analysis:
                        raise DocumentProcessingError("pdf_password_required", "尚無已驗證的密碼規則") from None
                    interpreter = password_interpreter or AIProviderService(get_secret_store()).interpreter(session)
                    rule = interpreter.interpret(instruction, context)
                    candidates = PasswordComposer(get_secret_store()).compose(
                        rule, secret_profile.national_id_credential_ref, secret_profile.birthday_credential_ref
                    )
                    if not candidates:
                        raise DocumentProcessingError("pdf_password_required", "密碼規則不明確或無法使用") from None
                    processed = active_pdf_processor.process(request, password_candidates=candidates)
            if processed is None:
                raise DocumentProcessingError("pdf_malformed", "PDF 無法處理") from None
            if processed.was_encrypted and rule is not None and fingerprint:
                if rule.status == "ambiguous" and processed.successful_candidate_index is not None:
                    selected = rule.candidates[processed.successful_candidate_index]
                    rule = rule.model_copy(update={"status": "resolved", "candidates": [selected]})
                if rule.status == "resolved" and profile:
                    password_rules.save_verified(session, profile.id, fingerprint, rule)
                    session.commit()
        except HTTPException:
            raise
        except DocumentSourceUnavailable:
            raise HTTPException(status_code=503, detail="目前無法取得文件來源") from None
        except DocumentProcessingError as error:
            messages = {
                "pdf_password_required": "PDF 需要密碼規則，請選擇文件安全 profile 並提供郵件說明。",
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
            raise HTTPException(status_code=503, detail=str(error)) from None
        except SecretStoreUnavailable:
            raise HTTPException(status_code=503, detail="Windows 安全資料保管庫目前無法使用") from None
        except Exception:
            raise HTTPException(status_code=503, detail="PDF 預覽處理失敗") from None
        return Response(
            content=processed.preview_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(document.filename)}",
                "Cache-Control": "private, no-store, max-age=0",
                "X-FamilyHub-Text-Extraction": processed.ocr_status,
            },
        )

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
        session: Session = Depends(get_session),
    ):
        filters = [active_transaction_filter()]
        if month:
            try:
                if len(month) != 7 or month[4] != "-" or not month[:4].isdigit() or not month[5:].isdigit():
                    raise ValueError
                year, month_number = int(month[:4]), int(month[5:])
                start = date(year, month_number, 1)
                end = date(year + 1, 1, 1) if month_number == 12 else date(year, month_number + 1, 1)
            except ValueError as error:
                raise HTTPException(status_code=422, detail="月份格式無效，請使用 YYYY-MM") from error
            filters.extend([
                FinanceTransaction.transaction_date >= start,
                FinanceTransaction.transaction_date < end,
            ])
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
    def dashboard(session: Session = Depends(get_session)):
        return transaction_totals(session)

    @app.get("/api/search")
    def search(q: str = Query(min_length=1, max_length=200), session: Session = Depends(get_session)):
        pattern = f"%{q.strip()}%"
        documents = session.scalars(select(Document).where(Document.revoked_at.is_(None), Document.filename.ilike(pattern)).limit(50)).all()
        transactions = session.scalars(select(FinanceTransaction).where(active_transaction_filter(), or_(FinanceTransaction.description.ilike(pattern), cast(FinanceTransaction.amount, String).ilike(pattern))).limit(50)).all()
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
        }

    @app.get("/api/jobs")
    def list_jobs(session: Session = Depends(get_session)):
        rows = session.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(100)).all()
        return [{"id": row.id, "document_id": row.document_id, "source_type": row.source_type, "target_module": row.target_module, "status": row.status, "summary": row.summary, "created_at": row.created_at} for row in rows]

    return app


app = create_app()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
