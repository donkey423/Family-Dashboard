from datetime import date
from decimal import Decimal

import pytest

from family_finance_hub.finance.statements.contracts import (
    ReconciliationSummary,
    StatementData,
    StatementLine,
    summarize_statement_months,
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


def test_undated_interest_recognition_preserves_source_and_monthly_semantics():
    statement = _statement([_line(1, transaction_date=None, kind="interest")]).model_copy(
        update={"closing_date": date(2026, 2, 20)}
    )
    result = normalize_statement(statement, statement_id="interest-policy")
    assert result.can_import
    assert result.lines[0].transaction_date == date(2026, 2, 20)
    assert result.lines[0].source_transaction_date is None
    assert result.lines[0].transaction_date_basis == "statement_closing_date"
    assert statement.lines[0].transaction_date is None
    report = summarize_statement_months(statement)
    assert report.undated_line_indexes == ()
    assert report.months[0].interest == Decimal("10")
    assert report.months[0].purchases == 0


@pytest.mark.parametrize("kind", ["purchase", "fee", "unknown"])
def test_closing_date_policy_does_not_fill_other_missing_dates(kind):
    statement = _statement([_line(1, transaction_date=None, kind=kind)]).model_copy(
        update={"closing_date": date(2026, 2, 20)}
    )
    result = normalize_statement(statement, statement_id="missing-other-date")
    assert not result.can_import
    assert "missing_transaction_date" in result.reason_codes
    assert result.lines[0].transaction_date is None
    assert result.lines[0].transaction_date_basis == "missing"


def test_interest_policy_requires_explicit_closing_date_and_keeps_source_dates():
    undated = _statement([_line(1, transaction_date=None, kind="interest")])
    assert not normalize_statement(undated, statement_id="no-closing-date").can_import
    dated = _statement([_line(1, kind="interest")]).model_copy(update={"closing_date": date(2026, 2, 20)})
    normalized = normalize_statement(dated, statement_id="already-dated").lines[0]
    assert normalized.transaction_date == date(2026, 2, 5)
    assert normalized.transaction_date_basis == "statement"


def test_interest_policy_cannot_override_reconciliation_failure():
    statement = _statement([_line(1, transaction_date=None, kind="interest")], reconciliation=
        ReconciliationSummary(status="mismatch", difference=1)
    ).model_copy(update={"closing_date": date(2026, 2, 20)})
    result = normalize_statement(statement, statement_id="unbalanced-interest")
    assert not result.can_import
    assert result.reason_codes == ("reconciliation_mismatch",)


def test_closing_date_outside_statement_period_is_rejected():
    data = _statement([]).model_dump()
    data["closing_date"] = date(2026, 3, 1)
    with pytest.raises(ValueError, match="closing date"):
        StatementData.model_validate(data)
