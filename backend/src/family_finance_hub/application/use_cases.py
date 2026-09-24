from uuid import uuid4

from sqlalchemy.orm import Session

from ..documents.service import DocumentService
from ..finance.service import FinanceCsvImportService
from ..models import ImportJob


class ImportDocumentUseCase:
    def __init__(self, documents: DocumentService):
        self.documents = documents

    def execute(self, session: Session, filename: str, content: bytes, target_module: str):
        with session.begin():
            return self.documents.import_bytes(session, filename, content, target_module)


class ImportFinanceCsvUseCase:
    def __init__(self, importer: FinanceCsvImportService):
        self.importer = importer

    def execute(self, session: Session, filename: str, content: bytes) -> dict[str, int | str | bool]:
        try:
            with session.begin():
                return self.importer.import_csv(session, filename, content)
        except (ValueError, UnicodeDecodeError) as error:
            with session.begin():
                document_id = None
                try:
                    imported = self.importer.documents.import_bytes(session, filename, content, "finance")
                    document_id = imported.document.id
                except ValueError:
                    pass
                session.add(ImportJob(
                    id=str(uuid4()),
                    document_id=document_id,
                    source_type="csv",
                    target_module="finance",
                    status="failed",
                    summary=str(error)[:500],
                ))
            raise
