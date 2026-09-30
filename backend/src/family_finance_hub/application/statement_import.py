"""Analyze statement PDFs and confirm their rows into Finance.

The use case deliberately separates PDF processing, parser output, review, and
transaction creation.  No extracted PDF text or password material is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..finance.statements.contracts import BankStatementParser, StatementData
from ..finance.statements.normalization import normalize_statement
from ..models import Document, FinanceTransaction, ImportJob, Statement, StatementAccount
from .pdf_processing import PdfPreviewCommand, PdfPreviewUseCase


class StatementImportError(Exception):
    """A user-safe, non-sensitive statement workflow error."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class StatementAnalysisCommand:
    pdf: PdfPreviewCommand
    statement_account_id: str | None = None


class StatementImportUseCase:
    def __init__(self, pdf_preview: PdfPreviewUseCase, parser: BankStatementParser | None = None):
        self.pdf_preview = pdf_preview
        self.parser = parser

    @property
    def parser_ready(self) -> bool:
        return self.parser is not None

    def analyze(
        self,
        session: Session,
        document_id: str,
        command: StatementAnalysisCommand,
    ) -> dict:
        self._validate_document(session, document_id)

        # Reuse the existing unlock flow.  The returned text remains in memory
        # and is passed only to the injected parser.
        preview = self.pdf_preview.execute(session, document_id, command.pdf)
        if self.parser is None:
            return self._save_pending(
                session,
                document_id,
                reason_code="parser_not_configured",
                parser_id=None,
                parser_version=None,
            )

        try:
            parsed = self.parser.parse(
                preview.processed.extracted_text,
                page_count=preview.processed.page_count,
            )
        except Exception:
            return self._save_pending(
                session,
                document_id,
                reason_code="parser_failed",
                parser_id=getattr(self.parser, "bank_id", None),
                parser_version=getattr(self.parser, "format_version", None),
            )

        if parsed.status == "unsupported":
            return self._save_pending(
                session,
                document_id,
                reason_code=parsed.reason_code or "unsupported_statement",
                parser_id=getattr(self.parser, "bank_id", None),
                parser_version=getattr(self.parser, "format_version", None),
            )
        if parsed.statement is None:
            return self._save_pending(
                session,
                document_id,
                reason_code="parser_missing_statement",
                parser_id=getattr(self.parser, "bank_id", None),
                parser_version=getattr(self.parser, "format_version", None),
            )

        return self._save_parsed(
            session,
            document_id,
            parsed.statement,
            command.statement_account_id,
            parser_id=getattr(self.parser, "bank_id", parsed.statement.bank_id),
            parser_version=getattr(self.parser, "format_version", parsed.statement.format_version),
        )

    def confirm(self, session: Session, statement_id: str, review_version: int) -> dict:
        with session.begin():
            statement = session.get(Statement, statement_id)
            if statement is None:
                raise StatementImportError("statement_not_found", "找不到帳單分析結果")

            if statement.status == "imported":
                transaction_ids = session.scalars(
                    select(FinanceTransaction.id)
                    .where(FinanceTransaction.statement_id == statement.id)
                    .order_by(FinanceTransaction.statement_line_index, FinanceTransaction.id)
                ).all()
                return self._confirmation_payload(statement, tuple(transaction_ids), reused=True)
            if statement.status != "ready":
                raise StatementImportError("statement_not_ready", "帳單仍需補充資料或人工核對，尚未可入帳")
            if statement.review_version != review_version:
                raise StatementImportError("statement_review_changed", "帳單內容已更新，請重新載入後再確認")

            document = session.get(Document, statement.document_id)
            if document is None:
                raise StatementImportError("document_not_found", "找不到帳單文件")
            if document.revoked_at is not None:
                raise StatementImportError("document_revoked", "帳單文件已撤銷，不能入帳")
            if statement.statement_account_id is None or statement.period_start is None or statement.period_end is None:
                raise StatementImportError("statement_identity_missing", "帳單缺少帳戶或期間，不能入帳")
            if not statement.statement_json:
                raise StatementImportError("statement_data_missing", "帳單解析資料不存在，不能入帳")

            duplicate = session.scalar(
                select(Statement)
                .where(
                    Statement.id != statement.id,
                    Statement.status == "imported",
                    Statement.statement_account_id == statement.statement_account_id,
                    Statement.period_start == statement.period_start,
                    Statement.period_end == statement.period_end,
                )
                .limit(1)
            )
            if duplicate is not None:
                raise StatementImportError("statement_period_already_imported", "同一帳戶與帳單期間已經入帳")

            try:
                statement_data = StatementData.model_validate(statement.statement_json)
                normalized = normalize_statement(statement_data, statement_id=statement.id)
            except (TypeError, ValueError):
                raise StatementImportError("statement_invalid", "帳單解析結果無法驗證，未建立交易") from None
            if not normalized.can_import:
                raise StatementImportError("statement_not_ready", "帳單仍需人工核對，未建立交易")

            transaction_ids: list[str] = []
            for line in normalized.lines:
                existing = session.scalar(
                    select(FinanceTransaction).where(FinanceTransaction.row_hash == line.row_hash)
                )
                if existing is not None:
                    if existing.statement_id != statement.id or existing.statement_line_index != line.line_index:
                        raise StatementImportError("transaction_identity_conflict", "交易識別衝突，未建立交易")
                    transaction_ids.append(existing.id)
                    continue
                transaction = FinanceTransaction(
                    id=str(uuid4()),
                    source_document_id=statement.document_id,
                    row_hash=line.row_hash,
                    transaction_date=line.transaction_date,
                    description=line.description,
                    amount=line.amount,
                    currency=line.currency,
                    raw_json=json.dumps(
                        {
                            "line_index": line.line_index,
                            "page_number": line.page_number,
                            "source_sequence": line.source_sequence,
                            "transaction_date": line.transaction_date,
                            "source_transaction_date": line.source_transaction_date,
                            "transaction_date_basis": line.transaction_date_basis,
                            "posting_date": line.posting_date,
                            "description": line.description,
                            "transaction_kind": line.transaction_kind,
                            "amount": line.amount,
                            "currency": line.currency,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                    statement_id=statement.id,
                    posting_date=line.posting_date,
                    transaction_kind=line.transaction_kind,
                    statement_line_index=line.line_index,
                )
                session.add(transaction)
                transaction_ids.append(transaction.id)

            statement.status = "imported"
            statement.reason_code = None
            statement.imported_at = datetime.now(timezone.utc)
            statement.review_version += 1
            session.add(ImportJob(
                id=str(uuid4()),
                document_id=statement.document_id,
                source_type="statement_pdf",
                target_module="finance",
                status="completed",
                summary=f"信用卡帳單已確認，新增 {len(transaction_ids)} 筆交易",
            ))
            return self._confirmation_payload(statement, tuple(transaction_ids), reused=False)

    def _validate_document(self, session: Session, document_id: str) -> None:
        document = session.get(Document, document_id)
        if document is None:
            raise StatementImportError("document_not_found", "找不到帳單文件")
        if document.revoked_at is not None:
            raise StatementImportError("document_revoked", "帳單文件已撤銷，不能分析")
        if document.content_type != "application/pdf" and not document.filename.lower().endswith(".pdf"):
            raise StatementImportError("unsupported_document", "目前只支援 PDF 帳單分析")
        session.rollback()

    def _save_pending(
        self,
        session: Session,
        document_id: str,
        *,
        reason_code: str,
        parser_id: str | None,
        parser_version: str | None,
    ) -> dict:
        with session.begin():
            statement = session.scalar(select(Statement).where(Statement.document_id == document_id))
            if statement is None:
                statement = Statement(
                    id=str(uuid4()),
                    document_id=document_id,
                    bank_id=parser_id or "unclassified",
                    format_version=parser_version or "pending",
                )
                session.add(statement)
            elif statement.status == "imported":
                return self._statement_payload(session, statement)
            else:
                statement.review_version += 1
            statement.statement_account_id = None
            statement.bank_id = parser_id or statement.bank_id or "unclassified"
            statement.format_version = parser_version or statement.format_version or "pending"
            statement.parser_id = parser_id
            statement.parser_version = parser_version
            statement.period_start = None
            statement.period_end = None
            statement.statement_json = None
            statement.status = "pending"
            statement.reason_code = reason_code
            session.add(ImportJob(
                id=str(uuid4()),
                document_id=document_id,
                source_type="statement_pdf",
                target_module="finance",
                status="pending",
                summary=f"帳單分析待處理：{reason_code}",
            ))
            session.flush()
            return self._statement_payload(session, statement)

    def _save_parsed(
        self,
        session: Session,
        document_id: str,
        statement_data: StatementData,
        statement_account_id: str | None,
        *,
        parser_id: str,
        parser_version: str,
    ) -> dict:
        with session.begin():
            statement = session.scalar(select(Statement).where(Statement.document_id == document_id))
            if statement is None:
                statement = Statement(
                    id=str(uuid4()),
                    document_id=document_id,
                    bank_id=statement_data.bank_id,
                    format_version=statement_data.format_version,
                )
                session.add(statement)
            elif statement.status == "imported":
                return self._statement_payload(session, statement)
            else:
                statement.review_version += 1

            account, account_reason = self._resolve_account(
                session,
                statement_data.bank_id,
                statement_account_id,
                account_hint=statement_data.account_hint,
            )
            normalized = normalize_statement(statement_data, statement_id=statement.id)
            reasons = list(normalized.reason_codes)
            if account_reason:
                reasons.append(account_reason)
            status = "ready" if normalized.can_import and account is not None else "pending"

            statement.statement_account_id = account.id if account else None
            statement.bank_id = statement_data.bank_id
            statement.format_version = statement_data.format_version
            statement.parser_id = parser_id
            statement.parser_version = parser_version
            statement.period_start = statement_data.period_start
            statement.period_end = statement_data.period_end
            statement.statement_json = statement_data.model_dump(mode="json")
            statement.status = status
            statement.reason_code = ",".join(reasons) or None
            session.add(ImportJob(
                id=str(uuid4()),
                document_id=document_id,
                source_type="statement_pdf",
                target_module="finance",
                status=status,
                summary=f"帳單分析完成：{len(normalized.lines)} 筆候選，狀態 {status}",
            ))
            session.flush()
            return self._statement_payload(session, statement, line_count=len(normalized.lines))

    def _resolve_account(
        self,
        session: Session,
        bank_id: str,
        statement_account_id: str | None,
        *,
        account_hint: str | None = None,
    ) -> tuple[StatementAccount | None, str | None]:
        if statement_account_id:
            account = session.get(StatementAccount, statement_account_id)
            if account is None:
                raise StatementImportError("statement_account_not_found", "找不到帳單帳戶")
            if account.bank_id != bank_id:
                raise StatementImportError("statement_account_mismatch", "帳單帳戶與解析出的機構不一致")
            return account, None

        candidates = session.scalars(
            select(StatementAccount).where(StatementAccount.bank_id == bank_id).order_by(StatementAccount.created_at)
        ).all()
        if len(candidates) == 1:
            return candidates[0], None
        if not candidates:
            default_names = {
                "ctbc": "中國信託信用卡",
                "taishin": "台新信用卡",
                "cathay": "國泰世華信用卡",
                "sinopac": "永豐信用卡",
            }
            default_name = default_names.get(bank_id)
            if default_name:
                account = StatementAccount(
                    id=str(uuid4()),
                    bank_id=bank_id,
                    display_name=default_name,
                    account_hint=account_hint,
                )
                session.add(account)
                session.flush()
                return account, None
            return None, "statement_account_required"
        return None, "statement_account_ambiguous"

    @staticmethod
    def _statement_payload(session: Session, statement: Statement, *, line_count: int | None = None) -> dict:
        if line_count is None and statement.statement_json:
            line_count = len(statement.statement_json.get("lines", []))
        transaction_count = session.scalar(
            select(func.count(FinanceTransaction.id)).where(FinanceTransaction.statement_id == statement.id)
        ) or 0
        return {
            "statement_id": statement.id,
            "document_id": statement.document_id,
            "statement_account_id": statement.statement_account_id,
            "bank_id": statement.bank_id,
            "format_version": statement.format_version,
            "period_start": statement.period_start,
            "period_end": statement.period_end,
            "status": statement.status,
            "reason_code": statement.reason_code,
            "review_version": statement.review_version,
            "line_count": line_count or 0,
            "transaction_count": transaction_count,
            "imported_at": statement.imported_at,
        }

    @staticmethod
    def _confirmation_payload(statement: Statement, transaction_ids: tuple[str, ...], *, reused: bool) -> dict:
        return {
            "statement_id": statement.id,
            "document_id": statement.document_id,
            "status": statement.status,
            "review_version": statement.review_version,
            "transaction_ids": list(transaction_ids),
            "transaction_count": len(transaction_ids),
            "reused": reused,
        }
