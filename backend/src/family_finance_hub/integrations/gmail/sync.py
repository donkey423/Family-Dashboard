from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...documents.service import DocumentService
from ...finance.service import FinanceCsvImportService
from ...models import DocumentSourceRecord, GmailSyncState, ImportJob, utc_now
from .client import GmailClient, GmailHistoryExpired

DEFAULT_GMAIL_QUERY = "in:anywhere has:attachment {filename:pdf filename:csv}"
MAX_MESSAGES_PER_SYNC = 10_000


class GmailSyncUseCase:
    def __init__(
        self,
        documents: DocumentService,
        finance_import: FinanceCsvImportService,
        max_attachment_bytes: int,
    ):
        self.documents = documents
        self.finance_import = finance_import
        self.max_attachment_bytes = max_attachment_bytes

    def execute(self, session: Session, client: GmailClient, query: str = DEFAULT_GMAIL_QUERY) -> dict[str, int | str]:
        if not query.strip() or len(query) > 500:
            raise ValueError("Gmail 搜尋條件無效")
        new_attachments = csv_files = transactions = duplicates = failures = retryable_failures = scanned_messages = 0
        truncated = False
        full_sync = False
        mode = "incremental"
        changed_message_ids: list[str] = []
        next_history_id: str | None = None
        with session.begin():
            state = session.get(GmailSyncState, "gmail")
            if state is None:
                state = GmailSyncState(id="gmail", status="running")
                session.add(state)
                session.flush()
            state.last_attempt_at = utc_now()

            if state.full_sync_in_progress:
                if state.full_sync_query != query:
                    raise ValueError("完整同步尚未完成，請沿用原搜尋條件")
                full_sync = True
                mode = "full-resume"
                baseline_history_id = state.full_sync_baseline_history_id
                page_token = state.full_sync_page_token
            elif state.history_id:
                page_token = None
                history_page_token = None
                try:
                    while True:
                        history = client.list_history(state.history_id, history_page_token)
                        next_history_id = history.get("historyId") or next_history_id
                        for record in history.get("history", []):
                            for added in record.get("messagesAdded", []):
                                message_id = added.get("message", {}).get("id")
                                if message_id:
                                    changed_message_ids.append(str(message_id))
                        history_page_token = history.get("nextPageToken")
                        if not history_page_token:
                            break
                except GmailHistoryExpired:
                    full_sync = True
                    mode = "full-fallback"
                    baseline_history_id = _profile_history_id(client.get_profile())
                    page_token = None
            else:
                full_sync = True
                mode = "full"
                baseline_history_id = _profile_history_id(client.get_profile())
                page_token = None

            if full_sync:
                current_page_token = page_token
                while scanned_messages < MAX_MESSAGES_PER_SYNC:
                    page = client.list_messages(query, current_page_token)
                    message_ids = [str(item["id"]) for item in page.get("messages", []) if item.get("id")]
                    for message_id in message_ids:
                        scanned_messages += 1
                        stats, message_failures, message_retryable_failures = self._process_message(session, client, message_id)
                        failures += message_failures
                        retryable_failures += message_retryable_failures
                        new_attachments += stats["new"]
                        csv_files += stats["csv"]
                        transactions += stats["transactions"]
                        duplicates += stats["duplicates"]
                    next_page_token = page.get("nextPageToken")
                    if retryable_failures or not next_page_token:
                        current_page_token = current_page_token if retryable_failures else None
                        truncated = bool(next_page_token and not retryable_failures)
                        if truncated:
                            current_page_token = next_page_token
                        break
                    current_page_token = next_page_token
                    if scanned_messages >= MAX_MESSAGES_PER_SYNC:
                        truncated = True
                        break

                state.full_sync_in_progress = truncated or retryable_failures > 0
                state.full_sync_query = query if state.full_sync_in_progress else None
                state.full_sync_page_token = current_page_token if state.full_sync_in_progress else None
                state.full_sync_baseline_history_id = baseline_history_id if state.full_sync_in_progress else None
                if not state.full_sync_in_progress:
                    state.history_id = baseline_history_id
                    state.last_successful_at = utc_now()
            else:
                for message_id in dict.fromkeys(changed_message_ids):
                    scanned_messages += 1
                    stats, message_failures, message_retryable_failures = self._process_message(session, client, message_id)
                    failures += message_failures
                    retryable_failures += message_retryable_failures
                    new_attachments += stats["new"]
                    csv_files += stats["csv"]
                    transactions += stats["transactions"]
                    duplicates += stats["duplicates"]
                truncated = False
                if retryable_failures == 0:
                    state.history_id = next_history_id or state.history_id
                    state.last_successful_at = utc_now()

            if new_attachments or failures:
                session.add(ImportJob(
                    id=str(uuid4()),
                    document_id=None,
                    source_type="gmail_sync",
                    target_module="documents",
                    status="partial" if failures else "completed",
                    summary=f"新增附件 {new_attachments} 份、CSV {csv_files} 份、新增交易 {transactions} 筆、略過重複 {duplicates} 份、失敗 {failures} 件",
                ))
            state.status = "partial" if failures or truncated else "completed"
            state.last_error_summary = "部分郵件或附件無法處理" if failures else "完整同步分批進行中" if truncated else None

        return {
            "scanned_messages": scanned_messages,
            "new_attachments": new_attachments,
            "csv_files": csv_files,
            "created_transactions": transactions,
            "duplicates": duplicates,
            "failures": failures,
            "truncated": int(truncated),
            "sync_mode": mode,
        }

    def _process_message(self, session: Session, client: GmailClient, message_id: str) -> tuple[dict[str, int], int, int]:
        failures = retryable_failures = 0
        stats = _attachment_counts()
        try:
            message = client.get_message(message_id)
            parts = list(_attachment_parts(message.get("payload", {})))
        except Exception:
            return stats, 1, 1

        for part in parts:
            filename = str(part.get("filename", ""))[:255]
            if not filename.lower().endswith((".pdf", ".csv")):
                continue
            try:
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")
                part_id = str(part.get("partId", ""))
                source_key = f"{message_id}:{part_id or attachment_id}"
                existing = session.scalar(select(DocumentSourceRecord.id).where(
                    DocumentSourceRecord.source_type == "gmail_attachment",
                    DocumentSourceRecord.source_key == source_key,
                ))
                if existing:
                    stats["duplicates"] += 1
                    continue
                content = (
                    client.get_attachment(message_id, attachment_id)
                    if attachment_id
                    else _decode_inline(body.get("data", ""))
                )
                if len(content) > self.max_attachment_bytes:
                    failures += 1
                    session.add(ImportJob(
                        id=str(uuid4()),
                        document_id=None,
                        source_type="gmail_attachment",
                        target_module="documents",
                        status="failed",
                        summary="Gmail 附件超過上傳大小限制",
                    ))
                    continue
                content_type = str(part.get("mimeType") or (
                    "text/csv" if filename.lower().endswith(".csv") else "application/pdf"
                ))[:128]
                reference = {
                    "message_id": message_id,
                    "part_id": part_id,
                    "filename": filename,
                    "content_type": content_type,
                }
                if attachment_id:
                    reference["attachment_id"] = str(attachment_id)
                if filename.lower().endswith(".csv"):
                    try:
                        imported = self.finance_import.import_remote_csv(session, filename, content, source_key, reference)
                    except (ValueError, UnicodeDecodeError):
                        stats["new"] += 1
                        stats["csv"] += 1
                        failures += 1
                        continue
                    if imported.get("duplicate_source"):
                        stats["duplicates"] += 1
                        continue
                    stats["csv"] += 1
                    stats["transactions"] += int(imported["created_transactions"])
                else:
                    imported = self.documents.import_remote_bytes(
                        session, filename, content, "gmail_attachment", source_key, reference
                    )
                    if imported.duplicate_source:
                        stats["duplicates"] += 1
                        continue
                stats["new"] += 1
                del content
            except Exception:
                failures += 1
                retryable_failures += 1
        return stats, failures, retryable_failures


def _attachment_counts() -> dict[str, int]:
    return {"new": 0, "csv": 0, "transactions": 0, "duplicates": 0}

def _profile_history_id(profile: dict[str, Any]) -> str:
    history_id = profile.get("historyId")
    if not history_id:
        raise ValueError("Gmail 未提供同步 history ID")
    return str(history_id)


def _attachment_parts(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if payload.get("filename"):
        yield payload
    for part in payload.get("parts", []):
        yield from _attachment_parts(part)


def _decode_inline(value: str) -> bytes:
    from .client import decode_base64url

    try:
        return decode_base64url(value)
    except Exception:
        raise ValueError("Gmail 附件格式無效") from None
