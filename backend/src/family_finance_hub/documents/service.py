from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Document, DocumentSourceRecord, ImportJob, utc_now
from ..storage.ports import StoragePort

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".csv"}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".csv": "text/csv",
}


@dataclass(frozen=True)
class ImportedDocument:
    document: Document
    duplicate: bool
    duplicate_source: bool = False


class DocumentService:
    def __init__(self, storage: StoragePort):
        self.storage = storage

    def import_bytes(self, session: Session, filename: str, content: bytes, target_module: str) -> ImportedDocument:
        safe_name = PurePath(filename.replace("\\", "/")).name[:255]
        extension = PurePath(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("僅支援 PDF、JPG、PNG 與 CSV")
        digest = sha256(content).hexdigest()
        document = session.scalar(select(Document).where(Document.sha256 == digest))
        duplicate = document is not None
        storage_key = f"{digest[:2]}/{digest}{extension}"
        if document is None:
            document_id = str(uuid4())
            self.storage.put(storage_key, content)
            document = Document(
                id=document_id,
                sha256=digest,
                filename=safe_name,
                content_type=CONTENT_TYPES[extension],
                size_bytes=len(content),
            )
            source = self._local_source(document_id, storage_key)
            try:
                with session.begin_nested():
                    session.add(document)
                    session.add(source)
                    session.flush()
            except IntegrityError:
                document = session.scalar(select(Document).where(Document.sha256 == digest))
                if document is None:
                    raise
                duplicate = True
                self._ensure_local_source(session, document.id, storage_key)
        else:
            self.storage.put(storage_key, content)
            self._ensure_local_source(session, document.id, storage_key)

        job = ImportJob(
            id=str(uuid4()),
            document_id=document.id,
            source_type="upload",
            target_module=target_module,
            status="duplicate" if duplicate else "completed",
            summary="內容已存在，沿用既有文件" if duplicate else "文件已匯入",
        )
        session.add(job)
        return ImportedDocument(document=document, duplicate=duplicate)

    def import_remote_bytes(
        self,
        session: Session,
        filename: str,
        content: bytes,
        source_type: str,
        source_key: str,
        source_reference: dict[str, str],
    ) -> ImportedDocument:
        safe_name = PurePath(filename.replace("\\", "/")).name[:255]
        extension = PurePath(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("僅支援 PDF、JPG、PNG 與 CSV")
        digest = sha256(content).hexdigest()
        document = session.scalar(select(Document).where(Document.sha256 == digest))
        duplicate = document is not None
        if document is None:
            document = Document(
                id=str(uuid4()),
                sha256=digest,
                filename=safe_name,
                content_type=CONTENT_TYPES[extension],
                size_bytes=len(content),
            )
            try:
                with session.begin_nested():
                    session.add(document)
                    session.flush()
            except IntegrityError:
                document = session.scalar(select(Document).where(Document.sha256 == digest))
                if document is None:
                    raise
                duplicate = True

        existing_source = session.scalar(
            select(DocumentSourceRecord).where(
                DocumentSourceRecord.source_type == source_type,
                DocumentSourceRecord.source_key == source_key,
            )
        )
        if existing_source is not None:
            existing_source.availability_status = "available"
            existing_source.last_verified_at = utc_now()
            return ImportedDocument(document=document, duplicate=True, duplicate_source=True)

        source = DocumentSourceRecord(
            id=str(uuid4()),
            document_id=document.id,
            source_type=source_type,
            source_key=source_key,
            source_reference=source_reference,
            availability_status="available",
            last_verified_at=utc_now(),
        )
        try:
            with session.begin_nested():
                session.add(source)
                session.flush()
        except IntegrityError:
            existing_source = session.scalar(
                select(DocumentSourceRecord).where(
                    DocumentSourceRecord.source_type == source_type,
                    DocumentSourceRecord.source_key == source_key,
                )
            )
            if existing_source is None:
                raise
            existing_source.availability_status = "available"
            existing_source.last_verified_at = utc_now()
            return ImportedDocument(document=document, duplicate=True, duplicate_source=True)
        return ImportedDocument(document=document, duplicate=duplicate)

    @staticmethod
    def _local_source(document_id: str, storage_key: str) -> DocumentSourceRecord:
        return DocumentSourceRecord(
            id=str(uuid4()),
            document_id=document_id,
            source_type="local_file",
            source_key=storage_key,
            storage_key=storage_key,
            availability_status="available",
            last_verified_at=utc_now(),
        )

    def _ensure_local_source(self, session: Session, document_id: str, storage_key: str) -> None:
        source = session.scalar(
            select(DocumentSourceRecord).where(
                DocumentSourceRecord.source_type == "local_file",
                DocumentSourceRecord.source_key == storage_key,
            )
        )
        if source is not None:
            source.availability_status = "available"
            source.last_verified_at = utc_now()
            return

        source = self._local_source(document_id, storage_key)
        try:
            with session.begin_nested():
                session.add(source)
                session.flush()
        except IntegrityError:
            source = session.scalar(
                select(DocumentSourceRecord).where(
                    DocumentSourceRecord.source_type == "local_file",
                    DocumentSourceRecord.source_key == storage_key,
                )
            )
            if source is None:
                raise
            source.availability_status = "available"
            source.last_verified_at = utc_now()
