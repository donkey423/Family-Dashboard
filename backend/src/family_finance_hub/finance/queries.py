from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import Document, FinanceTransaction
from .categories.domain import EXPENSE_KINDS


def active_transaction_filter():
    return FinanceTransaction.document.has(Document.revoked_at.is_(None))


def expense_expression():
    return case(
        (FinanceTransaction.statement_id.is_(None) & (FinanceTransaction.amount < 0), -FinanceTransaction.amount),
        (FinanceTransaction.statement_id.is_not(None) & FinanceTransaction.transaction_kind.in_(tuple(EXPENSE_KINDS)), -FinanceTransaction.amount),
        else_=0,
    )


def transaction_totals(
    session: Session,
    *,
    document_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    currency: str | None = None,
) -> dict:
    # Impact previews include revoked rows; ordinary summaries include only active documents.
    predicates = [(
        FinanceTransaction.source_document_id == document_id
        if document_id is not None else active_transaction_filter()
    )]
    if start_date is not None:
        predicates.append(FinanceTransaction.transaction_date >= start_date)
    if end_date is not None:
        predicates.append(FinanceTransaction.transaction_date < end_date)
    if currency is not None:
        predicates.append(FinanceTransaction.currency == currency)
    legacy_row = FinanceTransaction.statement_id.is_(None)
    income_amount = case(
        (legacy_row & (FinanceTransaction.amount >= 0), FinanceTransaction.amount),
        else_=0,
    )
    expense_amount = expense_expression()
    totals = session.execute(select(
        FinanceTransaction.currency,
        func.count(FinanceTransaction.id),
        func.coalesce(func.sum(income_amount), 0),
        func.coalesce(func.sum(expense_amount), 0),
    ).where(*predicates).group_by(FinanceTransaction.currency).order_by(FinanceTransaction.currency)).all()
    return {
        "transaction_count": sum(count for _, count, _, _ in totals),
        "currency_totals": [
            {
                "currency": currency,
                "income": str(income.quantize(Decimal("0.01"))),
                "expenses": str(expenses.quantize(Decimal("0.01"))),
                "net": str((income - expenses).quantize(Decimal("0.01"))),
            }
            for currency, _count, income, expenses in totals
        ],
    }
