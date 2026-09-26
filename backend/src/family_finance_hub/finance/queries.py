from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import Document, FinanceTransaction


def active_transaction_filter():
    return FinanceTransaction.document.has(Document.revoked_at.is_(None))


def transaction_totals(session: Session, *, document_id: str | None = None) -> dict:
    # Impact previews include revoked rows; ordinary summaries include only active documents.
    predicate = (
        FinanceTransaction.source_document_id == document_id
        if document_id is not None else active_transaction_filter()
    )
    totals = session.execute(select(
        FinanceTransaction.currency,
        func.count(FinanceTransaction.id),
        func.coalesce(func.sum(case((FinanceTransaction.amount >= 0, FinanceTransaction.amount), else_=0)), 0),
        func.coalesce(func.sum(case((FinanceTransaction.amount < 0, -FinanceTransaction.amount), else_=0)), 0),
    ).where(predicate).group_by(FinanceTransaction.currency).order_by(FinanceTransaction.currency)).all()
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
