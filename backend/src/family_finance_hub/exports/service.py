from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import timezone
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..finance.queries import active_transaction_filter
from ..models import Document, FinanceTransaction, ImportJob, WorkbookExportState, utc_now
from .ports import ExportDocument, ExportTransaction, WorkbookOwnershipError, WorkbookSnapshot, WorkbookWriter

EXPORT_ID = "excel"
POLL_SECONDS = 30
ERROR_MESSAGES = {
    "file_in_use": "Excel 檔案正在使用中或沒有寫入權限；請關閉檔案後重試。",
    "unowned_workbook": "目標已有其他 Excel 檔案，未覆寫；請改用新的輸出位置。",
    "write_failed": "Excel 更新失敗，上一版仍保留；請確認磁碟空間與輸出位置。",
}


class WorkbookExportBusy(Exception):
    pass


def read_snapshot(session: Session) -> WorkbookSnapshot:
    transactions = tuple(
        ExportTransaction(row.id, row.source_document_id, row.transaction_date,
                          row.description, row.amount, row.currency, filename)
        for row, filename in session.execute(
            select(FinanceTransaction, Document.filename)
            .join(Document, FinanceTransaction.source_document_id == Document.id)
            .where(active_transaction_filter())
            .order_by(FinanceTransaction.transaction_date, FinanceTransaction.id)
        )
    )
    counts = dict(session.execute(select(
        FinanceTransaction.source_document_id, func.count(FinanceTransaction.id),
    ).group_by(FinanceTransaction.source_document_id)).all())
    documents = tuple(
        ExportDocument(row.id, row.filename,
                       "revoked" if row.revoked_at else "active" if counts.get(row.id) else "pending",
                       counts.get(row.id, 0))
        for row in session.scalars(select(Document).order_by(Document.id))
    )
    return WorkbookSnapshot(transactions, documents)


class WorkbookExportService:
    def __init__(self, session_factory: sessionmaker, writer: WorkbookWriter, destination: Path):
        self.session_factory = session_factory
        self.writer = writer
        self.destination = destination.resolve()
        if self.destination.suffix.lower() != ".xlsx":
            raise ValueError("Excel output path must end in .xlsx")
        self.lock = Lock()

    def status(self) -> dict:
        with self.session_factory() as session:
            state = session.get(WorkbookExportState, EXPORT_ID)
            snapshot = read_snapshot(session)
            output_matches = self._output_matches(state)
            current_hash = self._fingerprint(snapshot)
            pending_pdfs = sum(
                row.state == "pending" and row.filename.lower().endswith(".pdf")
                for row in snapshot.documents
            )
            return {
                "enabled": bool(state and state.enabled),
                "status": state.status if state else "never",
                "output_path": str(self.destination),
                "file_available": output_matches and bool(state and state.last_successful_at),
                "last_successful_at": state.last_successful_at.replace(tzinfo=timezone.utc) if state and state.last_successful_at else None,
                "last_error": ERROR_MESSAGES.get(state.last_error_code) if state else None,
                "last_error_code": state.last_error_code if state else None,
                "exported_transactions": state.transaction_count if state else 0,
                "current_transactions": len(snapshot.transactions),
                "pending_pdf_documents": pending_pdfs,
                "needs_update": not output_matches or state is None or state.snapshot_hash != current_hash or state.status == "failed",
                "check_interval_seconds": POLL_SECONDS,
                "pdf_transaction_parser_ready": False,
            }

    def configure(self, enabled: bool) -> dict:
        with self.lock, self.session_factory() as session, session.begin():
            state = session.get(WorkbookExportState, EXPORT_ID)
            if state is None:
                state = WorkbookExportState(id=EXPORT_ID)
                session.add(state)
            state.enabled = enabled
        if enabled:
            self.refresh()
        return self.status()

    def refresh(self, *, scheduled: bool = False, force: bool = False) -> bool:
        if not self.lock.acquire(blocking=False):
            if scheduled:
                return False
            raise WorkbookExportBusy()
        try:
            with self.session_factory() as session:
                state = session.get(WorkbookExportState, EXPORT_ID)
                if scheduled and (state is None or not state.enabled):
                    return False
                snapshot = read_snapshot(session)
                fingerprint = self._fingerprint(snapshot)
                if (
                    not force
                    and state
                    and state.status == "completed"
                    and state.snapshot_hash == fingerprint
                    and self._output_matches(state)
                ):
                    return False
            # Read a committed snapshot, then release SQLite before filesystem I/O.
            try:
                self.writer.write(snapshot, self.destination)
                output_sha256 = self._file_sha256()
            except WorkbookOwnershipError:
                self._record_failure("unowned_workbook")
                return False
            except PermissionError:
                self._record_failure("file_in_use")
                return False
            except Exception:
                self._record_failure("write_failed")
                return False
            with self.session_factory() as session, session.begin():
                state = session.get(WorkbookExportState, EXPORT_ID)
                if state is None:
                    state = WorkbookExportState(id=EXPORT_ID)
                    session.add(state)
                state.snapshot_hash = fingerprint
                state.output_sha256 = output_sha256
                state.status = "completed"
                state.last_successful_at = utc_now()
                state.last_error_code = None
                state.transaction_count = len(snapshot.transactions)
                session.add(ImportJob(
                    id=str(uuid4()), document_id=None, source_type="excel_export",
                    target_module="finance", status="completed",
                    summary=f"Excel 已更新，共 {len(snapshot.transactions)} 筆有效交易",
                ))
            return True
        finally:
            self.lock.release()

    def read_workbook(self) -> bytes:
        with self.lock, self.session_factory() as session:
            state = session.get(WorkbookExportState, EXPORT_ID)
            # Never serve an unrelated file merely because it exists at the target path.
            snapshot = read_snapshot(session)
            if state is None or state.snapshot_hash != self._fingerprint(snapshot) or state.status != "completed":
                raise FileNotFoundError()
            try:
                content = self.destination.read_bytes()
            except OSError:
                raise FileNotFoundError() from None
            if not state.output_sha256 or sha256(content).hexdigest() != state.output_sha256:
                raise FileNotFoundError()
            return content

    def _fingerprint(self, snapshot: WorkbookSnapshot) -> str:
        value = {"format_version": 1, "destination": str(self.destination), "data": asdict(snapshot)}
        return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()

    def _file_sha256(self) -> str:
        digest = sha256()
        with self.destination.open("rb") as workbook:
            for chunk in iter(lambda: workbook.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _output_matches(self, state: WorkbookExportState | None) -> bool:
        if state is None or not state.output_sha256:
            return False
        try:
            return self._file_sha256() == state.output_sha256
        except OSError:
            return False

    def _record_failure(self, code: str) -> None:
        with self.session_factory() as session, session.begin():
            state = session.get(WorkbookExportState, EXPORT_ID)
            if state is None:
                state = WorkbookExportState(id=EXPORT_ID)
                session.add(state)
            if state.status != "failed" or state.last_error_code != code:
                session.add(ImportJob(
                    id=str(uuid4()), document_id=None, source_type="excel_export",
                    target_module="finance", status="failed", summary=ERROR_MESSAGES[code],
                ))
            state.status = "failed"
            state.last_error_code = code

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(self.refresh, scheduled=True)
            except Exception:
                # A temporary database failure must not terminate the background worker.
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=POLL_SECONDS)
            except asyncio.TimeoutError:
                continue
