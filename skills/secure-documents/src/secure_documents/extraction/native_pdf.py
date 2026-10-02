from __future__ import annotations

from pypdf import PdfReader

from ..contracts import ExtractionMetadata, PageIR, TextBlock
from ..errors import ExtractionFailed

EXTRACTOR_VERSION = "0.1.0"


def extract_native(reader: PdfReader) -> tuple[ExtractionMetadata, tuple[PageIR, ...]]:
    pages: list[PageIR] = []
    warnings: list[str] = []
    try:
        for page_index, page in enumerate(reader.pages, start=1):
            blocks: list[TextBlock] = []

            def visitor(text, _cm, tm, _font_dict, font_size):
                normalized = str(text or "")
                if not normalized.strip():
                    return
                x = float(tm[4]) if tm and len(tm) > 5 else None
                y = float(tm[5]) if tm and len(tm) > 5 else None
                blocks.append(TextBlock(
                    block_id=f"p{page_index}-b{len(blocks)+1}",
                    text=normalized,
                    x=x,
                    y=y,
                    font_size=float(font_size) if font_size is not None else None,
                ))

            text = page.extract_text(visitor_text=visitor) or ""
            if not text.strip():
                warnings.append(f"page_{page_index}_native_text_empty")
            pages.append(PageIR(page_number=page_index, text=text, blocks=tuple(blocks)))
    except Exception as error:
        raise ExtractionFailed("native PDF extraction failed") from error

    metadata = ExtractionMetadata(
        extractor="pypdf",
        extractor_version=EXTRACTOR_VERSION,
        method="native_layout",
        warnings=tuple(warnings),
    )
    return metadata, tuple(pages)
