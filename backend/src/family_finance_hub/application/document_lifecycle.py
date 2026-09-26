from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from ..documents.service import DocumentService
from ..finance.queries import transaction_totals
from ..models import Document, ImportJob


class DocumentNotFound(Exception):
    pass


class DocumentImpactChanged(Exception):
    pass


class DocumentLifecycleUseCase:
    def preview(self, session: Session, document_id: str) -> dict:
        document = session.get(Document, document_id)
        if document is None:
            raise DocumentNotFound
        totals = transaction_totals(session, document_id=document_id)
        snapshot = {"id": document.id, "version": document.lifecycle_version, **totals}
        token = sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        return {
            "document_id": document.id,
            "filename": document.filename,
            "revoked_at": document.revoked_at,
            "revocation_reason": document.revocation_reason,
            "impact_token": token,
            **totals,
        }

    def execute(self, session: Session, document_id: str, *, revoked: bool, impact_token: str, reason: str) -> dict:
        with session.begin():
            impact = self.preview(session, document_id)
            document = session.get(Document, document_id)
            if (document.revoked_at is not None) == revoked:
                return {**impact, "changed": False}
            if impact_token != impact["impact_token"]:
                raise DocumentImpactChanged
            if not DocumentService.set_revoked(session, document, revoked, reason.strip()):
                raise DocumentImpactChanged
            label = "撤銷" if revoked else "恢復"
            session.add(ImportJob(
                id=str(uuid4()), document_id=document_id,
                source_type="document_lifecycle", target_module="documents",
                status="revoked" if revoked else "restored",
                summary=f"{label}文件匯入，關聯 {impact['transaction_count']} 筆交易" + (f"；原因：{reason.strip()}" if reason.strip() else ""),
            ))
            session.flush()
            return {**self.preview(session, document_id), "changed": True}
