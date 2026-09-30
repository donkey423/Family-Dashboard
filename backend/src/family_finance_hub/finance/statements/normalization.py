"""Normalize parsed statement lines before persistence or transaction creation.

This module deliberately knows nothing about a bank's PDF layout or storage. It
only turns the validated statement contract into stable, importable rows and
blocks rows that still need human review.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from .contracts import StatementData, StatementLine, StatementTransactionKind, TransactionDateBasis, resolve_transaction_date


StatementNormalizationStatus = Literal["ready", "pending"]


@dataclass(frozen=True)
class NormalizedStatementLine:
    statement_id: str
    row_hash: str
    line_index: int
    page_number: int | None
    source_sequence: str | None
    transaction_date: date | None
    source_transaction_date: date | None
    transaction_date_basis: TransactionDateBasis
    posting_date: date | None
    description: str
    transaction_kind: StatementTransactionKind
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class StatementNormalizationResult:
    status: StatementNormalizationStatus
    lines: tuple[NormalizedStatementLine, ...]
    reason_codes: tuple[str, ...]

    @property
    def can_import(self) -> bool:
        return self.status == "ready"


def normalize_statement(
    statement: StatementData,
    *,
    statement_id: str,
) -> StatementNormalizationResult:
    """Create stable rows and return a fail-closed import decision.

    The statement line index, scoped by the persisted statement ID, is the
    idempotency identity. Content is intentionally not part of the hash: two
    identical-looking purchases on different source lines remain distinct, and
    correcting a draft line cannot create a second row identity.
    """

    normalized_statement_id = statement_id.strip()
    if not normalized_statement_id:
        raise ValueError("statement_id must not be empty")

    lines = tuple(
        _normalize_line(normalized_statement_id, line, statement.closing_date)
        for line in statement.lines
    )
    reasons: list[str] = []
    if any(line.transaction_kind == "unknown" for line in statement.lines):
        reasons.append("unknown_line")
    if any(line.transaction_date is None for line in lines):
        reasons.append("missing_transaction_date")
    if statement.reconciliation.status == "not_checked":
        reasons.append("reconciliation_not_checked")
    elif statement.reconciliation.status == "mismatch":
        reasons.append("reconciliation_mismatch")

    return StatementNormalizationResult(
        status="pending" if reasons else "ready",
        lines=lines,
        reason_codes=tuple(reasons),
    )


def _normalize_line(statement_id: str, line: StatementLine, closing_date: date | None) -> NormalizedStatementLine:
    transaction_date, date_basis = resolve_transaction_date(line, closing_date)
    return NormalizedStatementLine(
        statement_id=statement_id,
        row_hash=_line_hash(statement_id, line.line_index),
        line_index=line.line_index,
        page_number=line.page_number,
        source_sequence=line.source_sequence,
        transaction_date=transaction_date,
        source_transaction_date=line.transaction_date,
        transaction_date_basis=date_basis,
        posting_date=line.posting_date,
        description=line.description,
        transaction_kind=line.transaction_kind,
        amount=line.amount,
        currency=line.currency,
    )


def _line_hash(statement_id: str, line_index: int) -> str:
    value = f"family-finance-hub:statement-line:v1:{statement_id}:{line_index}"
    return sha256(value.encode("utf-8")).hexdigest()
