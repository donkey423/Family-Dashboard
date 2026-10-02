from __future__ import annotations

from ..contracts import DocumentIR, PasswordRule, SourceDocument
from ..errors import UnlockNeedsReview
from ..unlock.pdf import open_pdf_reader
from ..unlock.ports import SecretStore
from ..unlock.rules import compose_candidates, rule_fingerprint
from .native_pdf import extract_native


def extract_document(
    source: SourceDocument,
    content: bytes,
    *,
    rule: PasswordRule | None = None,
    secret_store: SecretStore | None = None,
    national_id_ref: str | None = None,
    birthday_ref: str | None = None,
) -> DocumentIR:
    candidates: tuple[str, ...] = ()
    fingerprint = None
    if rule is not None:
        if secret_store is None:
            raise UnlockNeedsReview("password rule requires a local secret store")
        candidates = compose_candidates(
            rule,
            secret_store,
            national_id_ref=national_id_ref,
            birthday_ref=birthday_ref,
        )
        fingerprint = rule_fingerprint(rule)
    reader, unlock = open_pdf_reader(content, candidates=candidates, rule_fingerprint=fingerprint)
    extraction, pages = extract_native(reader)
    return DocumentIR(
        document_id=source.document_id,
        source_sha256=source.sha256,
        mime_type=source.mime_type,
        page_count=len(pages),
        unlock=unlock,
        extraction=extraction,
        pages=pages,
    )
