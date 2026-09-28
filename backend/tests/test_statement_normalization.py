from datetime import date
from decimal import Decimal

import pytest

from family_finance_hub.finance.statements.contracts import (
    ReconciliationSummary,
    StatementData,
    StatementLine,
)
from family_finance_hub.finance.statements.normalization import normalize_statement


def _line(index, *, transaction_date=date(2026, 2, 5), kind="purchase", amount="-10.00"):
    return StatementLine(
        line_index=index,
        page_number=1,
        transaction_date=transaction_date,
        description="Synthetic merchant",
        transaction_kind=kind,
        amount=Decimal(amount),
        currency="TWD",
    )


def _statement(lines, *, reconciliation=None):
    return StatementData(
        bank_id="synthetic-bank",
        format_version="synthetic-v1",
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        lines=tuple(lines),
        reconciliation=reconciliation or ReconciliationSummary(
            status="matched", basis="synthetic", difference=Decimal("0")
        ),
    )


def test_normalization_preserves_distinct_duplicate_lines_and_stable_hashes():
    statement = _statement([_line(1), _line(2)])

    first = normalize_statement(statement, statement_id="statement-1")
    second = normalize_statement(statement, statement_id="statement-1")
    other = normalize_statement(statement, statement_id="statement-2")

    assert first.can_import is True
    assert first.reason_codes == ()
    assert [line.line_index for line in first.lines] == [1, 2]
    assert first.lines[0].row_hash != first.lines[1].row_hash
    assert first.lines[0].row_hash == second.lines[0].row_hash
    assert first.lines[0].row_hash != other.lines[0].row_hash
    assert all(len(line.row_hash) == 64 for line in first.lines)


def test_normalization_preserves_statement_amount_sign_and_kind():
    statement = _statement([
        _line(1, kind="refund", amount="20.00"),
        _line(2, kind="payment", amount="100.00"),
        _line(3, kind="fee", amount="-5.00"),
    ])

    result = normalize_statement(statement, statement_id="statement-1")

    assert [(line.transaction_kind, line.amount) for line in result.lines] == [
        ("refund", Decimal("20.00")),
        ("payment", Decimal("100.00")),
        ("fee", Decimal("-5.00")),
    ]


@pytest.mark.parametrize(
    ("lines", "reconciliation", "expected_reasons"),
    [
        ([_line(1, kind="unknown", amount="-1.00")], "matched", ("unknown_line",)),
        ([_line(1, transaction_date=None)], "matched", ("missing_transaction_date",)),
        ([_line(1)], "not_checked", ("reconciliation_not_checked",)),
        (
            [_line(1)],
            "mismatch",
            ("reconciliation_mismatch",),
        ),
    ],
)
def test_normalization_fails_closed_for_review_required_lines(
    lines, reconciliation, expected_reasons
):
    difference = {
        "matched": Decimal("0"),
        "not_checked": None,
        "mismatch": Decimal("1.00"),
    }[reconciliation]
    summary = ReconciliationSummary(
        status=reconciliation,
        basis="synthetic",
        difference=difference,
    )
    result = normalize_statement(
        _statement(lines, reconciliation=summary), statement_id="statement-1"
    )

    assert result.status == "pending"
    assert result.can_import is False
    assert result.reason_codes == expected_reasons


def test_normalization_can_import_a_zero_line_matched_statement():
    result = normalize_statement(_statement([]), statement_id="statement-1")

    assert result.status == "ready"
    assert result.lines == ()
    assert result.reason_codes == ()


def test_normalization_rejects_blank_statement_identity():
    with pytest.raises(ValueError, match="statement_id"):
        normalize_statement(_statement([]), statement_id="  ")
