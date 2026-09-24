from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from family_finance_hub.documents.processors.ports import OcrResult
from family_finance_hub.documents.processors.pdf import PdfDocumentProcessor
from family_finance_hub.documents.processors.ports import DocumentProcessingError, ProcessingContext, ProcessingRequest


def make_pdf(password=None):
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def request(content):
    return ProcessingRequest(
        content=content,
        context=ProcessingContext(filename="synthetic-statement.pdf", content_type="application/pdf"),
    )


class FakeOcrProvider:
    def __init__(self, result=None, error=None):
        self.result = result or OcrResult("OCR synthetic statement text", "completed")
        self.error = error
        self.calls = []

    def extract_pdf_text(self, content, *, page_count):
        self.calls.append((content, page_count))
        if self.error:
            raise self.error
        return self.result


def test_pdf_processor_returns_unencrypted_preview_without_mutating_original():
    original = make_pdf()

    result = PdfDocumentProcessor().process(request(original))

    assert result.preview_bytes == original
    assert result.was_encrypted is False
    assert result.page_count == 1
    assert result.ocr_required is True
    assert not PdfReader(BytesIO(original)).is_encrypted


def test_encrypted_pdf_requires_password_and_reports_wrong_password_separately():
    original = make_pdf("synthetic-pass")
    processor = PdfDocumentProcessor()

    with pytest.raises(DocumentProcessingError) as missing:
        processor.process(request(original))
    assert missing.value.code == "pdf_password_required"

    with pytest.raises(DocumentProcessingError) as wrong:
        processor.process(request(original), password_candidates=("wrong-pass",))
    assert wrong.value.code == "pdf_wrong_password"
    assert PdfReader(BytesIO(original)).is_encrypted


def test_encrypted_pdf_decrypts_only_to_separate_in_memory_preview():
    original = make_pdf("synthetic-pass")
    result = PdfDocumentProcessor().process(request(original), password_candidates=("synthetic-pass",))

    assert result.was_encrypted is True
    assert result.page_count == 1
    assert result.preview_bytes != original
    assert not PdfReader(BytesIO(result.preview_bytes)).is_encrypted
    assert PdfReader(BytesIO(original)).is_encrypted


def test_ocr_runs_only_after_decryption_when_native_text_is_insufficient():
    original = make_pdf("synthetic-pass")
    ocr = FakeOcrProvider()

    result = PdfDocumentProcessor(ocr).process(
        request(original), password_candidates=("synthetic-pass",)
    )

    assert result.ocr_status == "completed"
    assert result.ocr_required is False
    assert result.extracted_text == "OCR synthetic statement text"
    assert len(ocr.calls) == 1
    ocr_input, page_count = ocr.calls[0]
    assert not PdfReader(BytesIO(ocr_input)).is_encrypted
    assert page_count == 1
    assert PdfReader(BytesIO(original)).is_encrypted


def test_ocr_failure_does_not_block_pdf_preview_or_expose_error():
    ocr = FakeOcrProvider(error=RuntimeError("sensitive OCR detail"))
    original = make_pdf()

    result = PdfDocumentProcessor(ocr).process(request(original))

    assert result.ocr_status == "failed"
    assert result.ocr_required is True
    assert result.preview_bytes == original
    assert "sensitive OCR detail" not in result.extracted_text


def test_pdf_processor_caps_password_candidates_and_sanitizes_malformed_errors():
    original = make_pdf("correct-fourth")
    candidates = ("wrong-1", "wrong-2", "wrong-3", "correct-fourth")

    with pytest.raises(DocumentProcessingError) as capped:
        PdfDocumentProcessor().process(request(original), password_candidates=candidates)
    assert capped.value.code == "pdf_wrong_password"

    with pytest.raises(DocumentProcessingError) as malformed:
        PdfDocumentProcessor().process(request(b"not a pdf"))
    assert malformed.value.code == "pdf_malformed"
    assert "not a pdf" not in str(malformed.value)
