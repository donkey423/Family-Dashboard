from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from family_finance_hub.finance.statements.contracts import (
    ReconciliationSummary,
    StatementData,
    StatementLine,
    StatementParseResult,
    summarize_statement_months,
)


def _line(
    index,
    transaction_date,
    kind,
    amount,
    *,
    posting_date=None,
    description="Synthetic merchant",
    currency="TWD",
):
    return StatementLine(
        line_index=index,
        page_number=1,
        transaction_date=transaction_date,
        posting_date=posting_date,
        description=description,
        transaction_kind=kind,
        amount=Decimal(amount),
        currency=currency,
    )


def _statement(lines):
    return StatementData(
        bank_id="synthetic-bank",
        format_version="synthetic-v1",
        period_start=date(2025, 12, 1),
        period_end=date(2026, 1, 31),
        lines=tuple(lines),
    )


def test_monthly_summary_uses_transaction_date_and_separates_statement_line_kinds():
    statement = _statement([
        _line(1, date(2025, 12, 31), "purchase", "-100.00", posting_date=date(2026, 1, 2)),
        _line(2, date(2025, 12, 31), "purchase", "-100.00", posting_date=date(2026, 1, 2)),
        _line(3, date(2026, 1, 4), "refund", "20.00", posting_date=date(2026, 1, 6)),
        _line(4, date(2026, 1, 10), "payment", "120.00"),
        _line(5, date(2026, 1, 2), "fee", "-5.00"),
        _line(6, date(2026, 1, 2), "interest", "-1.00"),
        _line(7, date(2026, 1, 2), "unknown", "-7.00"),
        _line(8, None, "purchase", "-12.00"),
    ])

    report = summarize_statement_months(statement)

    assert report.undated_line_indexes == (8,)
    assert len(report.months) == 2
    december, january = report.months
    assert (december.month, december.currency) == (date(2025, 12, 1), "TWD")
    assert december.purchases == Decimal("200.00")
    assert december.refunds == Decimal("0")
    assert december.net_spend == Decimal("200.00")
    assert january.month == date(2026, 1, 1)
    assert january.purchases == Decimal("0")
    assert january.refunds == Decimal("20.00")
    assert january.net_spend == Decimal("-20.00")
    assert january.fees == Decimal("5.00")
    assert january.interest == Decimal("1.00")
    assert january.payments == Decimal("120.00")
    assert january.unknown_line_count == 1


def test_monthly_summary_keeps_currencies_separate_and_allows_zero_consumption():
    statement = _statement([
        _line(1, date(2026, 1, 5), "purchase", "-10.00", currency="TWD"),
        _line(2, date(2026, 1, 5), "purchase", "-2.00", currency="USD"),
    ])

    report = summarize_statement_months(statement)
    assert [(row.month, row.currency) for row in report.months] == [
        (date(2026, 1, 1), "TWD"),
        (date(2026, 1, 1), "USD"),
    ]
    empty = summarize_statement_months(_statement([]))
    assert empty.months == ()
    assert empty.undated_line_indexes == ()


@pytest.mark.parametrize(("kind", "amount"), [
    ("purchase", "1.00"),
    ("fee", "1.00"),
    ("interest", "1.00"),
    ("refund", "-1.00"),
    ("payment", "-1.00"),
])
def test_statement_line_requires_normalized_sign_by_kind(kind, amount):
    with pytest.raises(ValidationError):
        _line(1, date(2026, 1, 5), kind, amount)


def test_parse_result_and_reconciliation_require_explicit_outcomes():
    with pytest.raises(ValidationError):
        StatementParseResult(status="unsupported")
    unsupported = StatementParseResult(status="unsupported", reason_code="unknown_format")
    assert unsupported.statement is None

    with pytest.raises(ValidationError):
        ReconciliationSummary(status="matched", difference=Decimal("1.00"))
    with pytest.raises(ValidationError):
        ReconciliationSummary(status="mismatch", difference=Decimal("0"))


def test_statement_lines_keep_distinct_indexes_even_when_rows_are_identical():
    first = _line(1, date(2026, 1, 5), "purchase", "-10.00")
    second = _line(2, date(2026, 1, 5), "purchase", "-10.00")
    statement = _statement([first, second])
    assert len(statement.lines) == 2
    assert summarize_statement_months(statement).months[0].purchases == Decimal("20.00")

    with pytest.raises(ValidationError):
        _statement([first, first])


@pytest.mark.parametrize("account_hint", [
    "1234567812345678",
    "T124024974",
    "1234 5678 9012 3456",
    "X1234 5678",
    "12345-****-5678",
    "1234-****-56789",
])
def test_statement_rejects_unmasked_or_insufficiently_masked_account_hints(account_hint):
    with pytest.raises(ValidationError):
        StatementData(
            bank_id="synthetic-bank",
            format_version="synthetic-v1",
            period_start=date(2025, 12, 1),
            period_end=date(2026, 1, 31),
            account_hint=account_hint,
            lines=(),
        )


@pytest.mark.parametrize("account_hint", ["1234", "1234-****-5678", "●●●●1234"])
def test_statement_accepts_masked_account_hints(account_hint):
    statement = StatementData(
        bank_id="synthetic-bank",
        format_version="synthetic-v1",
        period_start=date(2025, 12, 1),
        period_end=date(2026, 1, 31),
        account_hint=account_hint,
        lines=(),
    )
    assert statement.account_hint == account_hint
