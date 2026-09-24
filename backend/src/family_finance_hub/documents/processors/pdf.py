from dataclasses import dataclass
from io import BytesIO
from typing import Sequence

from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError

from .ports import DocumentProcessingError, DocumentProcessor, OcrProvider, ProcessingRequest

MAX_PDF_PAGES = 1000
MAX_EXTRACTED_TEXT_CHARS = 1_000_000
MAX_PASSWORD_CANDIDATES = 3


@dataclass(frozen=True)
class ProcessedPdf:
    preview_bytes: bytes
    extracted_text: str
    page_count: int
    was_encrypted: bool
    ocr_required: bool
    ocr_status: str
    successful_candidate_index: int | None


class PdfDocumentProcessor(DocumentProcessor[ProcessedPdf]):
    def __init__(self, ocr_provider: OcrProvider | None = None):
        self.ocr_provider = ocr_provider

    def process(
        self,
        request: ProcessingRequest,
        *,
        password_candidates: Sequence[str] = (),
    ) -> ProcessedPdf:
        if request.context.content_type != "application/pdf" and not request.context.filename.lower().endswith(".pdf"):
            raise DocumentProcessingError("pdf_malformed", "檔案不是 PDF")
        try:
            reader = PdfReader(BytesIO(request.content), strict=True)
            was_encrypted = reader.is_encrypted
        except Exception:
            raise DocumentProcessingError("pdf_malformed", "PDF 無法讀取") from None

        successful_candidate_index = None
        if was_encrypted:
            if not password_candidates:
                raise DocumentProcessingError("pdf_password_required", "PDF 需要密碼")
            decrypted = False
            try:
                for index, password in enumerate(tuple(password_candidates)[:MAX_PASSWORD_CANDIDATES]):
                    if reader.decrypt(password):
                        decrypted = True
                        successful_candidate_index = index
                        break
            except (DependencyError, NotImplementedError):
                raise DocumentProcessingError("pdf_unsupported_encryption", "此 PDF 加密方式不受支援") from None
            except Exception:
                raise DocumentProcessingError("pdf_malformed", "PDF 無法解密") from None
            if not decrypted:
                raise DocumentProcessingError("pdf_wrong_password", "提供的密碼規則無法開啟 PDF")

        try:
            page_count = len(reader.pages)
            if page_count > MAX_PDF_PAGES:
                raise DocumentProcessingError("pdf_processing_limit", "PDF 頁數超過處理限制")
            text_parts: list[str] = []
            total_chars = 0
            for page in reader.pages:
                if total_chars >= MAX_EXTRACTED_TEXT_CHARS:
                    break
                text = page.extract_text() or ""
                remaining = MAX_EXTRACTED_TEXT_CHARS - total_chars
                text_parts.append(text[:remaining])
                total_chars += min(len(text), remaining)
            writer = PdfWriter()
            writer.append_pages_from_reader(reader)
            output = BytesIO()
            writer.write(output)
        except DocumentProcessingError:
            raise
        except Exception:
            raise DocumentProcessingError("pdf_malformed", "PDF 內容無法處理") from None

        extracted_text = "\n".join(text_parts)
        ocr_status = "available"
        if len(extracted_text.strip()) < 12:
            if self.ocr_provider is None:
                ocr_status = "unavailable"
            else:
                try:
                    ocr_result = self.ocr_provider.extract_pdf_text(
                        output.getvalue(), page_count=page_count
                    )
                    if ocr_result.text:
                        extracted_text = "\n".join(filter(None, (extracted_text, ocr_result.text)))
                    ocr_status = ocr_result.status
                except Exception:
                    ocr_status = "failed"
        if ocr_status == "completed" and len(extracted_text.strip()) < 12:
            ocr_status = "insufficient"
        return ProcessedPdf(
            preview_bytes=output.getvalue(),
            extracted_text=extracted_text,
            page_count=page_count,
            was_encrypted=was_encrypted,
            ocr_required=len(extracted_text.strip()) < 12,
            ocr_status=ocr_status,
            successful_candidate_index=successful_candidate_index,
        )
