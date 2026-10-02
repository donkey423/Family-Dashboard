from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ..contracts import SourceDocument
from ..errors import UnsupportedDocument


def read_local_pdf(path: Path) -> tuple[SourceDocument, bytes]:
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".pdf":
        raise UnsupportedDocument("PDF adapter only accepts .pdf files")
    content = path.read_bytes()
    if not content.startswith(b"%PDF-"):
        raise UnsupportedDocument("file does not have a PDF header")
    digest = sha256(content).hexdigest()
    return (
        SourceDocument(
            document_id=f"doc-{uuid4()}",
            sha256=digest,
            filename=path.name,
            mime_type="application/pdf",
            size_bytes=len(content),
        ),
        content,
    )
