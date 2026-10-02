from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from ..contracts import UnlockResult
from ..errors import ExtractionFailed, UnlockNeedsReview


def open_pdf_reader(content: bytes, *, candidates: tuple[str, ...] = (), rule_fingerprint: str | None = None) -> tuple[PdfReader, UnlockResult]:
    try:
        initial = PdfReader(BytesIO(content), strict=False)
    except Exception as error:
        raise ExtractionFailed("PDF cannot be opened") from error

    if not initial.is_encrypted:
        return initial, UnlockResult(status="not_needed", was_encrypted=False, candidate_count=0)

    if not candidates:
        raise UnlockNeedsReview("encrypted PDF requires a local password rule/candidate")
    if len(candidates) > 3:
        raise UnlockNeedsReview("password candidate limit exceeded")

    for candidate in candidates:
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            result = reader.decrypt(candidate)
            if result:
                # Touch the first page to force decryption failures now.
                if len(reader.pages):
                    _ = reader.pages[0].mediabox
                return reader, UnlockResult(
                    status="unlocked",
                    was_encrypted=True,
                    candidate_count=len(candidates),
                    rule_fingerprint=rule_fingerprint,
                )
        except Exception:
            continue
    raise UnlockNeedsReview("none of the allowed local password candidates unlocked the PDF")
