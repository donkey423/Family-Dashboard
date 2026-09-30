import re
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


StatementTransactionKind = Literal["purchase", "refund", "payment", "fee", "interest", "unknown"]
TransactionDateBasis = Literal["statement", "statement_closing_date", "missing"]


class StatementLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    line_index: int = Field(ge=1)
    page_number: int | None = Field(default=None, ge=1)
    source_sequence: str | None = Field(default=None, max_length=40)
    transaction_date: date | None = None
    posting_date: date | None = None
    description: str = Field(min_length=1, max_length=500)
    transaction_kind: StatementTransactionKind
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("amount")
    @classmethod
    def amount_must_be_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("statement amount must be finite")
        return value

    @model_validator(mode="after")
    def amount_sign_matches_kind(self):
        if self.transaction_kind in {"purchase", "fee", "interest"} and self.amount > 0:
            raise ValueError("purchase, fee, and interest amounts must be normalized as negative")
        if self.transaction_kind in {"refund", "payment"} and self.amount < 0:
            raise ValueError("refund and payment amounts must be normalized as positive")
        return self


class ReconciliationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    status: Literal["not_checked", "matched", "mismatch"] = "not_checked"
    basis: str | None = Field(default=None, max_length=80)
    difference: Decimal | None = None

    @field_validator("difference")
    @classmethod
    def difference_must_be_finite(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("reconciliation difference must be finite")
        return value

    @model_validator(mode="after")
    def difference_matches_status(self):
        if self.status == "not_checked" and self.difference is not None:
            raise ValueError("unchecked reconciliation cannot have a difference")
        if self.status == "matched" and self.difference != 0:
            raise ValueError("matched reconciliation must have zero difference")
        if self.status == "mismatch" and (self.difference is None or self.difference == 0):
            raise ValueError("mismatched reconciliation requires a non-zero difference")
        return self


class StatementData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    bank_id: str = Field(min_length=1, max_length=80)
    format_version: str = Field(min_length=1, max_length=40)
    period_start: date
    period_end: date
    closing_date: date | None = None
    account_hint: str | None = Field(default=None, max_length=80)
    lines: tuple[StatementLine, ...]
    reconciliation: ReconciliationSummary = Field(default_factory=ReconciliationSummary)

    @field_validator("account_hint")
    @classmethod
    def account_hint_must_not_expose_an_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return value
        digit_runs = re.findall(r"\d+", value)
        visible_digits = sum(len(run) for run in digit_runs)
        masked = (
            "*" in value
            or any(marker in value for marker in "•●")
            or re.search(r"[xX]{2,}", value) is not None
        )
        if any(len(run) > 4 for run in digit_runs):
            raise ValueError("account hint must not contain long unmasked digit runs")
        if visible_digits > 4 and (not masked or visible_digits > 8):
            raise ValueError("account hint must contain only a masked identifier")
        return value

    @model_validator(mode="after")
    def validate_period_and_line_indexes(self):
        if self.period_start > self.period_end:
            raise ValueError("statement period start must not be after end")
        if self.closing_date is not None and not self.period_start <= self.closing_date <= self.period_end:
            raise ValueError("statement closing date must be within the period")
        indexes = [line.line_index for line in self.lines]
        if len(indexes) != len(set(indexes)):
            raise ValueError("statement line indexes must be unique")
        return self


class StatementParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    status: Literal["parsed", "unsupported"]
    statement: StatementData | None = None
    reason_code: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == "parsed" and (self.statement is None or self.reason_code is not None):
            raise ValueError("parsed result requires statement data and no reason code")
        if self.status == "unsupported" and (self.statement is not None or not self.reason_code):
            raise ValueError("unsupported result requires a reason code and no statement data")
        return self


class BankStatementParser(Protocol):
    bank_id: str
    format_version: str

    def parse(self, extracted_text: str, *, page_count: int) -> StatementParseResult: ...


class StatementMonthlyTotals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    month: date
    currency: str
    purchases: Decimal = Decimal("0")
    refunds: Decimal = Decimal("0")
    net_spend: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    interest: Decimal = Decimal("0")
    payments: Decimal = Decimal("0")
    unknown_line_count: int = 0


class StatementMonthlyReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    months: tuple[StatementMonthlyTotals, ...]
    undated_line_indexes: tuple[int, ...]


def resolve_transaction_date(line: StatementLine, closing_date: date | None) -> tuple[date | None, TransactionDateBasis]:
    if line.transaction_date is not None:
        return line.transaction_date, "statement"
    # User-approved recognition policy; retain the source line's missing date.
    if line.transaction_kind == "interest" and closing_date is not None:
        return closing_date, "statement_closing_date"
    return None, "missing"


def summarize_statement_months(statement: StatementData) -> StatementMonthlyReport:
    buckets: dict[tuple[date, str], dict[str, Decimal | int]] = {}
    undated: list[int] = []

    for line in statement.lines:
        transaction_date, _basis = resolve_transaction_date(line, statement.closing_date)
        if transaction_date is None:
            undated.append(line.line_index)
            continue
        month = date(transaction_date.year, transaction_date.month, 1)
        values = buckets.setdefault((month, line.currency), {
            "purchases": Decimal("0"),
            "refunds": Decimal("0"),
            "fees": Decimal("0"),
            "interest": Decimal("0"),
            "payments": Decimal("0"),
            "unknown_line_count": 0,
        })
        if line.transaction_kind == "purchase":
            values["purchases"] += -line.amount
        elif line.transaction_kind == "refund":
            values["refunds"] += line.amount
        elif line.transaction_kind == "fee":
            values["fees"] += -line.amount
        elif line.transaction_kind == "interest":
            values["interest"] += -line.amount
        elif line.transaction_kind == "payment":
            values["payments"] += line.amount
        else:
            values["unknown_line_count"] += 1

    months = tuple(
        StatementMonthlyTotals(
            month=month,
            currency=currency,
            purchases=values["purchases"],
            refunds=values["refunds"],
            net_spend=values["purchases"] - values["refunds"],
            fees=values["fees"],
            interest=values["interest"],
            payments=values["payments"],
            unknown_line_count=values["unknown_line_count"],
        )
        for (month, currency), values in sorted(buckets.items())
    )
    return StatementMonthlyReport(months=months, undated_line_indexes=tuple(undated))
