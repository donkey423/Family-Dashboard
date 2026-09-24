from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..documents.processors.csv import CsvDocumentProcessor, ParsedCsv
from ..documents.processors.ports import DocumentProcessor, ProcessingContext, ProcessingRequest
from ..documents.service import DocumentService
from ..documents.sources.registry import DocumentSourceRegistry
from ..models import FinanceTransaction, ImportJob


def _date_value(value: str | None) -> date | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None


def _field(row: dict[str | None, str | None], *names: str) -> str:
    normalized = {str(key or "").strip().casefold(): (value or "").strip() for key, value in row.items()}
    return next((normalized[name] for name in names if normalized.get(name)), "")


class FinanceCsvImportService:
    def __init__(
        self,
        documents: DocumentService,
        document_sources: DocumentSourceRegistry,
        processor: DocumentProcessor[ParsedCsv] | None = None,
    ):
        self.documents = documents
        self.document_sources = document_sources
        self.processor = processor or CsvDocumentProcessor()

    def import_csv(self, session: Session, filename: str, content: bytes) -> dict[str, int | str | bool]:
        if not filename.lower().endswith(".csv"):
            raise ValueError("財務匯入僅接受 CSV 檔案")
        imported = self.documents.import_bytes(session, filename, content, "finance")
        parsed = self.processor.process(ProcessingRequest(
            content=self.document_sources.read(imported.document),
            context=ProcessingContext(filename=filename, content_type=imported.document.content_type),
        ))
        return self._import_parsed(session, imported.document.id, parsed, imported.duplicate, "csv")

    def import_remote_csv(
        self,
        session: Session,
        filename: str,
        content: bytes,
        source_key: str,
        source_reference: dict[str, str],
    ) -> dict[str, int | str | bool]:
        if not filename.lower().endswith(".csv"):
            raise ValueError("財務匯入僅接受 CSV 檔案")
        parsed = self.processor.process(ProcessingRequest(
            content=content,
            context=ProcessingContext(filename=filename, content_type="text/csv"),
        ))
        imported = self.documents.import_remote_bytes(
            session,
            filename,
            content,
            "gmail_attachment",
            source_key,
            source_reference,
        )
        if imported.duplicate_source:
            return {
                "document_id": imported.document.id,
                "duplicate_document": True,
                "duplicate_source": True,
                "created_transactions": 0,
            }
        return self._import_parsed(session, imported.document.id, parsed, imported.duplicate, "gmail_attachment")

    def _import_parsed(
        self,
        session: Session,
        document_id: str,
        parsed: ParsedCsv,
        duplicate_document: bool,
        source_type: str,
    ) -> dict[str, int | str | bool]:
        headers = {header.strip().casefold() for header in parsed.headers if header}
        if not ({"amount", "transaction amount"} & headers) and not ({"debit", "withdrawal", "credit", "deposit"} & headers):
            raise ValueError("CSV 需要 amount 欄位，或 debit/credit 欄位")

        created = 0
        for row_number, row in enumerate(parsed.rows, start=1):
            description = _field(row, "description", "memo", "name", "payee", "merchant")
            amount_text = _field(row, "amount", "transaction amount")
            if amount_text:
                amount_text = amount_text.replace(",", "").replace("$", "")
                try:
                    amount = Decimal(amount_text)
                except InvalidOperation as error:
                    raise ValueError(f"第 {row_number} 筆金額格式無效") from error
            else:
                debit = _field(row, "debit", "withdrawal")
                credit = _field(row, "credit", "deposit")
                if not debit and not credit:
                    raise ValueError("CSV 需要 amount 欄位，或 debit/credit 欄位")
                try:
                    amount = -Decimal(debit.replace(",", "").replace("$", "") or "0")
                    amount += Decimal(credit.replace(",", "").replace("$", "") or "0")
                except InvalidOperation as error:
                    raise ValueError(f"第 {row_number} 筆金額格式無效") from error

            normalized_row = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            row_hash = sha256(f"{document_id}:{row_number}:{normalized_row}".encode("utf-8")).hexdigest()
            if session.scalar(select(FinanceTransaction.id).where(FinanceTransaction.row_hash == row_hash)):
                continue
            transaction = FinanceTransaction(
                id=str(uuid4()),
                source_document_id=document_id,
                row_hash=row_hash,
                transaction_date=_date_value(_field(row, "date", "posted_at", "transaction_date")),
                description=description or f"CSV 第 {row_number} 筆",
                amount=amount,
                currency=(_field(row, "currency") or "TWD").upper()[:8],
                raw_json=normalized_row,
            )
            session.add(transaction)
            created += 1

        job = ImportJob(
            id=str(uuid4()),
            document_id=document_id,
            source_type=source_type,
            target_module="finance",
            status="completed",
            summary=f"新增 {created} 筆交易" + ("；文件內容已存在" if duplicate_document else ""),
        )
        session.add(job)
        return {"document_id": document_id, "duplicate_document": duplicate_document, "created_transactions": created}
