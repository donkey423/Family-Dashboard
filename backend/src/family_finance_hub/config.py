from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/family-finance-hub.db"
    storage_root: Path = Path("./data/documents")
    max_upload_bytes: int = 25 * 1024 * 1024
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    tesseract_executable: str | None = None
    ocr_languages: str = "chi_tra+eng"
    excel_output_path: Path | None = None
    legacy_gmail_oauth_enabled: bool = False
    builtin_category_rules_enabled: bool = True

    @property
    def workbook_path(self) -> Path:
        return self.excel_output_path or self.storage_root.parent / "exports" / "家庭收支記錄.xlsx"

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "FAMILY_FINANCE_HUB_DATABASE_URL",
                "sqlite:///./data/family-finance-hub.db",
            ),
            storage_root=Path(os.getenv("FAMILY_FINANCE_HUB_STORAGE_ROOT", "./data/documents")),
            max_upload_bytes=int(os.getenv("FAMILY_FINANCE_HUB_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))),
            cors_origins=tuple(filter(None, os.getenv(
                "FAMILY_FINANCE_HUB_CORS_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173",
            ).split(","))),
            tesseract_executable=os.getenv("FAMILY_FINANCE_HUB_TESSERACT") or None,
            ocr_languages=os.getenv("FAMILY_FINANCE_HUB_OCR_LANG", "chi_tra+eng"),
            excel_output_path=Path(os.environ["FAMILY_FINANCE_HUB_EXCEL_PATH"]) if os.getenv("FAMILY_FINANCE_HUB_EXCEL_PATH") else None,
            legacy_gmail_oauth_enabled=os.getenv(
                "FAMILY_FINANCE_HUB_LEGACY_GMAIL_OAUTH",
                "false",
            ).strip().casefold() in {"1", "true", "yes", "on"},
            builtin_category_rules_enabled=os.getenv(
                "FAMILY_FINANCE_HUB_BUILTIN_CATEGORY_RULES", "true",
            ).strip().casefold() in {"1", "true", "yes", "on"},
        )
