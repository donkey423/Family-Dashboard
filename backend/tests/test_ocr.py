import sys
from types import ModuleType, SimpleNamespace

from family_finance_hub.config import Settings
from family_finance_hub.documents.processors.ocr import TesseractOcrProvider


class FakeImage:
    def save(self, buffer, *, format):
        assert format == "PNG"
        buffer.write(b"synthetic-png")

    def close(self):
        pass


class FakeBitmap:
    def to_pil(self):
        return FakeImage()

    def close(self):
        pass


class FakePage:
    def get_size(self):
        return (300, 400)

    def render(self, *, scale):
        assert scale > 0
        return FakeBitmap()

    def close(self):
        pass


class FakePdf:
    def __init__(self, content):
        assert content == b"decrypted-synthetic-pdf"

    def __len__(self):
        return 1

    def __getitem__(self, index):
        assert index == 0
        return FakePage()

    def close(self):
        pass


def test_tesseract_provider_renders_and_streams_image_without_files(monkeypatch):
    pdfium = ModuleType("pypdfium2")
    pdfium.PdfDocument = FakePdf
    monkeypatch.setitem(sys.modules, "pypdfium2", pdfium)
    monkeypatch.setattr("family_finance_hub.documents.processors.ocr.shutil.which", lambda _: None)

    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1] == "--list-langs":
            return SimpleNamespace(
                returncode=0,
                stdout=b'List of available languages in "tessdata" (2):\nchi_tra\neng\n',
            )
        return SimpleNamespace(returncode=0, stdout="合成帳單".encode("utf-8"))

    monkeypatch.setattr("family_finance_hub.documents.processors.ocr.subprocess.run", run)
    provider = TesseractOcrProvider(executable="tesseract-test", languages="chi_tra+eng")

    result = provider.extract_pdf_text(b"decrypted-synthetic-pdf", page_count=1)

    assert result.status == "completed"
    assert result.text == "合成帳單"
    probe_command, probe_options = calls[0]
    assert probe_command == ["tesseract-test", "--list-langs"]
    assert probe_options["stdout"] is not None
    command, options = calls[1]
    assert command == ["tesseract-test", "stdin", "stdout", "-l", "chi_tra+eng"]
    assert options["input"] == b"synthetic-png"
    assert options["stdout"] is not None
    assert options["stderr"] is not None


def test_tesseract_provider_reports_missing_language_data_before_rendering(monkeypatch):
    pdfium = ModuleType("pypdfium2")

    def open_pdf(_content):
        raise AssertionError("PDF must not be opened when required language data is missing")

    pdfium.PdfDocument = open_pdf
    monkeypatch.setitem(sys.modules, "pypdfium2", pdfium)
    monkeypatch.setattr("family_finance_hub.documents.processors.ocr.shutil.which", lambda _: None)

    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"List of available languages (1):\nchi_tra\n")

    monkeypatch.setattr("family_finance_hub.documents.processors.ocr.subprocess.run", run)

    result = TesseractOcrProvider(executable="tesseract-test", languages="chi_tra+eng").extract_pdf_text(
        b"decrypted-synthetic-pdf", page_count=1
    )

    assert result.status == "language_unavailable"
    assert result.text == ""
    assert len(calls) == 1
    assert calls[0][0] == ["tesseract-test", "--list-langs"]


def test_tesseract_provider_reports_missing_executable_without_processing(monkeypatch):
    monkeypatch.setattr("family_finance_hub.documents.processors.ocr.shutil.which", lambda _: None)

    result = TesseractOcrProvider().extract_pdf_text(b"synthetic-pdf", page_count=1)

    assert result.status == "unavailable"
    assert result.text == ""


def test_ocr_settings_can_select_local_engine_and_languages(monkeypatch):
    monkeypatch.setenv("FAMILY_FINANCE_HUB_TESSERACT", "C:/Tools/tesseract.exe")
    monkeypatch.setenv("FAMILY_FINANCE_HUB_OCR_LANG", "chi_tra+eng")

    settings = Settings.from_environment()

    assert settings.tesseract_executable == "C:/Tools/tesseract.exe"
    assert settings.ocr_languages == "chi_tra+eng"
