from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..documents.service import DocumentService, ImportedDocument
from ..models import Document, DocumentSourceRecord
from ..security.password_rules import PasswordInstructionContext, PasswordInstructionExtractor


CODEX_MCP_GMAIL_SOURCE = "codex_mcp_gmail"


@dataclass(frozen=True)
class CodexMcpGmailImportCommand:
    filename: str
    content: bytes
    message_id: str
    attachment_id: str
    subject: str = ""
    sender: str = ""
    password_instruction: str = ""


class CodexMcpGmailImportUseCase:
    def __init__(self, documents: DocumentService, extractor: PasswordInstructionExtractor):
        self.documents = documents
        self.extractor = extractor

    def execute(self, session: Session, command: CodexMcpGmailImportCommand) -> tuple[ImportedDocument, bool]:
        message_id = _source_identifier(command.message_id, "message_id")
        attachment_id = _source_identifier(command.attachment_id, "attachment_id")
        sanitized_instruction = self.extractor.extract(PasswordInstructionContext(
            subject=command.subject[:500],
            body=command.password_instruction[:20_000],
            sender=command.sender[:255],
            filename=command.filename,
        ))
        source_key = sha256(f"{message_id}\0{attachment_id}".encode("utf-8")).hexdigest()
        source_reference = {
            "transport": "gmail_mcp",
            "password_instruction": sanitized_instruction,
        }

        with session.begin():
            existing_hash = session.scalar(
                select(Document.sha256)
                .join(DocumentSourceRecord, DocumentSourceRecord.document_id == Document.id)
                .where(
                    DocumentSourceRecord.source_type == CODEX_MCP_GMAIL_SOURCE,
                    DocumentSourceRecord.source_key == source_key,
                )
            )
            if existing_hash is not None and existing_hash != sha256(command.content).hexdigest():
                raise ValueError("來源識別碼已對應不同內容")
            imported = self.documents.import_bytes(
                session,
                command.filename,
                command.content,
                "documents",
                source_type="codex_mcp",
            )
            duplicate_source = self.documents.attach_source(
                session,
                imported.document,
                CODEX_MCP_GMAIL_SOURCE,
                source_key,
                source_reference,
            )
        return ImportedDocument(
            document=imported.document,
            duplicate=imported.duplicate,
            duplicate_source=duplicate_source,
        ), bool(sanitized_instruction)


def _source_identifier(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 512 or "\r" in normalized or "\n" in normalized:
        raise ValueError(f"{field} 格式不正確")
    return normalized
