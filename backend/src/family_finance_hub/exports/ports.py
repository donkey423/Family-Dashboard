from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ExportTransaction:
    id: str
    document_id: str
    transaction_date: date | None
    description: str
    amount: Decimal
    currency: str
    source_filename: str


@dataclass(frozen=True)
class ExportDocument:
    id: str
    filename: str
    state: str
    transaction_count: int


@dataclass(frozen=True)
class WorkbookSnapshot:
    """Caller supplies active transactions and active/pending/revoked documents."""

    transactions: tuple[ExportTransaction, ...]
    documents: tuple[ExportDocument, ...]


class WorkbookWriteError(RuntimeError):
    """Workbook output failed; messages never include source content or paths."""


class WorkbookOwnershipError(WorkbookWriteError):
    """The destination is not a recognized generated workbook."""


class WorkbookWriter(Protocol):
    """Project one snapshot; the caller owns filtering, locking and retries.

    Ownership/content errors use WorkbookWriteError; IO failures retain
    PermissionError/OSError with sanitized messages.
    """

    def write(self, snapshot: WorkbookSnapshot, destination: Path) -> None: ...
