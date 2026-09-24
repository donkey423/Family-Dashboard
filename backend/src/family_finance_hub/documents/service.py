from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Document, ImportJob
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
        if document is None:
            document_id = str(uuid4())
            storage_key = f"{digest[:2]}/{digest}{extension}"
            self.storage.put(storage_key, content)
            document = Document(
                id=document_id,
                sha256=digest,
                filename=safe_name,
                content_type=CONTENT_TYPES[extension],
                size_bytes=len(content),
                storage_key=storage_key,
                source_type="local_file",
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
