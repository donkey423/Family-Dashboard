from io import BytesIO
import math
import shutil
import subprocess
import time

from .ports import OcrResult

MAX_OCR_PAGES = 20
MAX_OCR_PIXELS = 8_000_000
MAX_OCR_SIDE = 4_000
MAX_OCR_TEXT_CHARS = 1_000_000
OCR_TIMEOUT_SECONDS = 120
OCR_PAGE_TIMEOUT_SECONDS = 20
OCR_LANGUAGE_PROBE_TIMEOUT_SECONDS = 10


class TesseractOcrProvider:
    def __init__(self, executable: str | None = None, languages: str = "chi_tra+eng"):
        self.executable = executable
        self.languages = languages

    def extract_pdf_text(self, content: bytes, *, page_count: int) -> OcrResult:
        executable = self.executable or shutil.which("tesseract")
        if not executable:
            return OcrResult("", "unavailable")
        try:
            import pypdfium2 as pdfium
        except (ImportError, OSError):
            return OcrResult("", "unavailable")

        try:
            language_result = subprocess.run(
                [executable, "--list-langs"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=OCR_LANGUAGE_PROBE_TIMEOUT_SECONDS,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return OcrResult("", "unavailable")
        if language_result.returncode != 0:
            return OcrResult("", "unavailable")

        available_languages = {
            line.strip()
            for line in language_result.stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        }
        required_languages = {language.strip() for language in self.languages.split("+") if language.strip()}
        if not required_languages or not required_languages.issubset(available_languages):
            return OcrResult("", "language_unavailable")

        try:
            pdf = pdfium.PdfDocument(content)
        except Exception:
            return OcrResult("", "failed")

        text_parts: list[str] = []
        total_chars = 0
        processed_pages = 0
        deadline = time.monotonic() + OCR_TIMEOUT_SECONDS
        page_limit = min(page_count, len(pdf), MAX_OCR_PAGES)
        status = "partial" if page_count > page_limit else "completed"
        try:
            for index in range(page_limit):
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    status = "partial" if text_parts else "failed"
                    break
                page = pdf[index]
                try:
                    width, height = page.get_size()
                    if width <= 0 or height <= 0:
                        status = "partial" if text_parts else "failed"
                        break
                    scale = min(
                        2.0,
                        MAX_OCR_SIDE / max(width, height),
                        math.sqrt(MAX_OCR_PIXELS / (width * height)),
                    )
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                        try:
                            image_buffer = BytesIO()
                            image.save(image_buffer, format="PNG")
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                except Exception:
                    status = "partial" if text_parts else "failed"
                    break
                finally:
                    page.close()

                image_bytes = image_buffer.getvalue()
                image_buffer.close()
                timeout = min(OCR_PAGE_TIMEOUT_SECONDS, remaining_time)
                try:
                    result = subprocess.run(
                        [executable, "stdin", "stdout", "-l", self.languages],
                        input=image_bytes,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        timeout=timeout,
                        check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except subprocess.TimeoutExpired:
                    status = "partial" if text_parts else "failed"
                    break
                except OSError:
                    status = "unavailable" if not text_parts else "partial"
                    break
                if result.returncode != 0:
                    status = "unavailable" if not text_parts else "partial"
                    break

                text = result.stdout.decode("utf-8", errors="replace")
                remaining_chars = MAX_OCR_TEXT_CHARS - total_chars
                if remaining_chars <= 0:
                    status = "partial"
                    break
                text_parts.append(text[:remaining_chars])
                total_chars += min(len(text), remaining_chars)
                processed_pages += 1
        finally:
            pdf.close()

        if processed_pages < page_limit and status == "completed":
            status = "partial" if text_parts else "failed"
        return OcrResult("\n".join(text_parts).strip(), status)
