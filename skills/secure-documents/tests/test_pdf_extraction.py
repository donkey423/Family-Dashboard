from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from secure_documents.acquisition.local_file import read_local_pdf
from secure_documents.contracts import PasswordRule
from secure_documents.extraction.service import extract_document
from secure_documents.unlock.stores import MemorySecretStore


def _plain_pdf(path: Path, text: str = "Secure document hello") -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, text)
    c.save()


def _encrypted_copy(source: Path, target: Path, password: str) -> None:
    reader = PdfReader(source)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    with target.open("wb") as handle:
        writer.write(handle)


def test_unencrypted_pdf_to_document_ir(tmp_path):
    pdf = tmp_path / "plain.pdf"
    _plain_pdf(pdf)
    source, content = read_local_pdf(pdf)
    ir = extract_document(source, content)
    assert ir.page_count == 1
    assert ir.unlock.was_encrypted is False
    assert "Secure document hello" in ir.pages[0].text
    assert ir.pages[0].blocks


def test_encrypted_pdf_unlocks_without_exposing_password(tmp_path):
    plain = tmp_path / "plain.pdf"
    encrypted = tmp_path / "encrypted.pdf"
    _plain_pdf(plain, "Encrypted content")
    _encrypted_copy(plain, encrypted, "A123456789")

    source, content = read_local_pdf(encrypted)
    store = MemorySecretStore({"id-ref": "A123456789"})
    rule = PasswordRule.model_validate({
        "status": "resolved",
        "candidates": [{"segments": [{"kind": "secret", "secret": "national_id", "transform": "upper"}]}],
    })
    ir = extract_document(source, content, rule=rule, secret_store=store, national_id_ref="id-ref")
    payload = ir.model_dump_json()
    assert ir.unlock.was_encrypted is True
    assert ir.unlock.status == "unlocked"
    assert "Encrypted content" in ir.pages[0].text
    assert "A123456789" not in payload
