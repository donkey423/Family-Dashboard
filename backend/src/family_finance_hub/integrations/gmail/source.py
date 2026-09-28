from __future__ import annotations

from email.header import decode_header, make_header
from email.message import Message
from typing import Callable, Any

from ...documents.sources.ports import (
    DocumentSource,
    DocumentSourceReference,
    DocumentSourceUnavailable,
    SourceMessageContext,
)
from .client import GmailUnavailable, decode_base64url

MAX_MESSAGE_TEXT_BYTES = 32_000


class GmailAttachmentDocumentSource(DocumentSource):
    source_type = "gmail_attachment"

    def __init__(self, client_factory: Callable[[], Any], max_bytes: int):
        self.client_factory = client_factory
        self.max_bytes = max_bytes

    def read(self, reference: DocumentSourceReference) -> bytes:
        metadata = reference.metadata or {}
        message_id = metadata.get("message_id")
        attachment_id = metadata.get("attachment_id")
        part_id = metadata.get("part_id")
        if not message_id:
            raise DocumentSourceUnavailable("Gmail 來源參照不完整")
        try:
            client = self.client_factory()
            if attachment_id:
                content = client.get_attachment(message_id, attachment_id)
            else:
                message = client.get_message(message_id)
                part = _find_part(message.get("payload", {}), part_id)
                if not part:
                    raise DocumentSourceUnavailable("Gmail 原始附件已不存在")
                content = decode_base64url(part.get("body", {}).get("data", ""))
        except (GmailUnavailable, KeyError, TypeError):
            raise DocumentSourceUnavailable("Gmail 附件目前無法取得") from None
        if len(content) > self.max_bytes:
            raise DocumentSourceUnavailable("Gmail 附件超過處理大小限制")
        return content

    def read_message_context(self, reference: dict[str, Any]) -> SourceMessageContext:
        message_id = reference.get("message_id")
        if not message_id:
            return SourceMessageContext("", "", "")
        try:
            message = self.client_factory().get_message(str(message_id))
        except GmailUnavailable:
            raise DocumentSourceUnavailable("Gmail 郵件目前無法取得") from None
        headers = {
            str(item.get("name", "")).casefold(): _decode_header(str(item.get("value", "")))
            for item in message.get("payload", {}).get("headers", [])
        }
        plain_parts, html_parts = _text_parts(message.get("payload", {}))
        body = "\n".join(plain_parts or html_parts)[:MAX_MESSAGE_TEXT_BYTES]
        return SourceMessageContext(
            subject=headers.get("subject", "")[:500],
            sender=headers.get("from", "")[:255],
            body=body,
        )


def _find_part(payload: dict[str, Any], part_id: str | None) -> dict[str, Any] | None:
    if part_id is not None and str(payload.get("partId", "")) == str(part_id):
        return payload
    for part in payload.get("parts", []):
        found = _find_part(part, part_id)
        if found:
            return found
    return None


def _text_parts(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    plain: list[str] = []
    html: list[str] = []
    filename = payload.get("filename")
    mime_type = str(payload.get("mimeType", "")).casefold()
    body = payload.get("body", {})
    encoded = body.get("data") if isinstance(body, dict) else None
    if not filename and mime_type in {"text/plain", "text/html"} and isinstance(encoded, str):
        if len(encoded) <= MAX_MESSAGE_TEXT_BYTES * 2:
            content = decode_base64url(encoded)[:MAX_MESSAGE_TEXT_BYTES]
            charset = _charset(payload.get("headers", []))
            try:
                text = content.decode(charset, errors="replace")
            except LookupError:
                text = content.decode("utf-8", errors="replace")
            (plain if mime_type == "text/plain" else html).append(text)
    for part in payload.get("parts", []):
        if isinstance(part, dict):
            child_plain, child_html = _text_parts(part)
            plain.extend(child_plain)
            html.extend(child_html)
    return plain, html


def _decode_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError, ValueError):
        return value


def _charset(headers: list[dict[str, Any]]) -> str:
    content_type = next((
        str(item.get("value", ""))
        for item in headers
        if str(item.get("name", "")).casefold() == "content-type"
    ), "")
    message = Message()
    try:
        message["Content-Type"] = content_type
        return message.get_content_charset() or "utf-8"
    except (LookupError, ValueError):
        return "utf-8"
