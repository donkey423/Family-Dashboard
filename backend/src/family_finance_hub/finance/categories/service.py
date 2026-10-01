from datetime import date
from decimal import Decimal
from hashlib import sha256
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import FinanceCategory, FinanceCategoryRule, FinanceTransaction, TransactionCategoryOverride
from ..queries import active_transaction_filter
from .domain import Category, CategoryResolver, DEFAULT_CATEGORIES, Resolution, Rule, expense_value, is_consumption
from .builtin import FINGERPRINT, VERSION


def seed_categories(session: Session) -> None:
    existing = set(session.scalars(select(FinanceCategory.code)))
    for index, (code, name) in enumerate(DEFAULT_CATEGORIES):
        if code not in existing:
            session.add(FinanceCategory(id=code, code=code, display_name=name, sort_order=index, is_system=True, is_active=True))
    session.flush()


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


class CategorizationService:
    def __init__(self, session: Session):
        self.session = session
        categories = session.scalars(select(FinanceCategory).order_by(FinanceCategory.sort_order, FinanceCategory.id)).all()
        rules = session.scalars(select(FinanceCategoryRule).order_by(FinanceCategoryRule.id)).all()
        self.resolver = CategoryResolver(
            [Category(row.id, row.code, row.display_name, row.sort_order) for row in categories if row.is_active],
            [Rule(row.id, row.category_id, row.match_type, row.normalized_pattern, row.priority) for row in rules if row.enabled],
            builtin_enabled=session.info.get("builtin_category_rules_enabled", True),
        )
        self._rule_configuration_hash = sha256(json.dumps({
            "categories": [(row.id, row.code, row.display_name, row.sort_order, row.is_active, row.is_system) for row in categories],
            "rules": [(row.id, row.category_id, row.match_type, row.normalized_pattern, row.priority, row.enabled) for row in rules],
            "builtin": (VERSION, FINGERPRINT, self.resolver.builtin_enabled),
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.configuration_hash = self._rule_configuration_hash

    def resolve(self, rows: list[FinanceTransaction]) -> dict[str, Resolution]:
        # One batch query covers configuration changes even when no active rows exist.
        overrides = dict(self.session.execute(select(TransactionCategoryOverride.transaction_id, TransactionCategoryOverride.category_id)
            .order_by(TransactionCategoryOverride.transaction_id)).all())
        self.override_ids = frozenset(overrides)
        self.configuration_hash = sha256(json.dumps({
            "rules": self._rule_configuration_hash,
            "overrides": sorted(overrides.items()),
        }, sort_keys=True).encode()).hexdigest()
        return {row.id: self.resolver.resolve(row.description, row.amount, row.statement_id, row.transaction_kind, overrides.get(row.id)) for row in rows}

    def rows(self, *, month_range: tuple[date, date] | None = None, currency: str | None = None) -> list[FinanceTransaction]:
        filters = [active_transaction_filter()]
        if month_range:
            filters.extend((FinanceTransaction.transaction_date >= month_range[0], FinanceTransaction.transaction_date < month_range[1]))
        if currency:
            filters.append(FinanceTransaction.currency == currency)
        return self.session.scalars(select(FinanceTransaction).where(*filters).order_by(
            FinanceTransaction.transaction_date.desc().nullslast(), FinanceTransaction.created_at.desc(), FinanceTransaction.id)).all()

    def spending(self, rows: list[FinanceTransaction], resolved: dict[str, Resolution]) -> dict:
        totals: dict[str, tuple[Decimal, int]] = {}
        for row in rows:
            if not is_consumption(row.amount, row.statement_id, row.transaction_kind):
                continue
            category_id = resolved[row.id].category.id
            amount, count = totals.get(category_id, (Decimal("0"), 0))
            totals[category_id] = (amount + expense_value(row.amount, row.statement_id, row.transaction_kind), count + 1)
        categories = [dict(category_id=key, code=self.resolver.categories[key].code,
                           name=self.resolver.categories[key].name, net_amount=money(amount), transaction_count=count)
                      for key, (amount, count) in sorted(totals.items(), key=lambda item: (-item[1][0], self.resolver.categories[item[0]].sort_order, item[0]))]
        return dict(
            dashboard_expense=money(sum((value[0] for value in totals.values()), Decimal("0"))),
            positive_category_total=money(sum((value[0] for value in totals.values() if value[0] > 0), Decimal("0"))),
            refund_credit_total=money(sum((value[0] for value in totals.values() if value[0] < 0), Decimal("0"))),
            categories=categories, negative_categories=[item for item in categories if Decimal(item["net_amount"]) < 0],
        )

    def merchants(self, rows: list[FinanceTransaction], resolved: dict[str, Resolution], category_id: str) -> list[dict]:
        groups: dict[str, dict] = {}
        for row in rows:
            resolution = resolved[row.id]
            if resolution.category.id != category_id or not is_consumption(row.amount, row.statement_id, row.transaction_kind):
                continue
            key = resolution.merchant_key
            group = groups.setdefault(key, dict(merchant_key=key, display_name=row.description, transaction_id=row.id, amount=Decimal("0"), transaction_count=0))
            group["amount"] += expense_value(row.amount, row.statement_id, row.transaction_kind)
            group["transaction_count"] += 1
        return [dict(merchant_key=item["merchant_key"], display_name=item["display_name"], transaction_id=item["transaction_id"], net_amount=money(item["amount"]), transaction_count=item["transaction_count"])
                for item in sorted(groups.values(), key=lambda item: (-item["amount"], item["merchant_key"]))]

    def merchant_impact(self, row: FinanceTransaction, category_id: str) -> dict:
        key = self.resolver.resolve(row.description, row.amount, row.statement_id, row.transaction_kind).merchant_key
        rows = self.rows()
        resolved = self.resolve(rows)
        matches = [item for item in rows if resolved[item.id].merchant_key == key]
        protected = [item for item in matches if item.id in self.override_ids]
        eligible = [item for item in matches if item.id not in self.override_ids]
        changed = [item for item in eligible if resolved[item.id].category.id != category_id]
        fingerprint = dict(configuration=self.configuration_hash, category_id=category_id, merchant_key=key,
            rows=[(item.id, item.description, str(item.transaction_date), str(item.amount), item.currency,
                   item.statement_id, item.transaction_kind) for item in matches])
        token = sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return dict(impact_token=token, merchant_key=key, affected_count=len(eligible), changed_count=len(changed),
                    protected_override_count=len(protected),
                    months=sorted({item.transaction_date.strftime("%Y-%m") if item.transaction_date else "未提供日期" for item in changed}),
                    samples=[transaction_payload(item, resolved[item.id]) for item in changed[:5]])

    def batch_impact(self, rows: list[FinanceTransaction], category_id: str) -> dict:
        rows = sorted(rows, key=lambda item: item.id)
        resolved = self.resolve(rows)
        changed = [item for item in rows if item.id not in self.override_ids and resolved[item.id].category.id != category_id]
        fingerprint = dict(operation="transaction_batch", configuration=self.configuration_hash, category_id=category_id,
            rows=[(item.id, item.description, str(item.transaction_date), str(item.amount), item.currency,
                   item.statement_id, item.transaction_kind) for item in rows])
        token = sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return dict(impact_token=token, affected_count=len(rows) - len(self.override_ids.intersection(item.id for item in rows)),
                    changed_count=len(changed), protected_override_count=sum(item.id in self.override_ids for item in rows),
                    months=sorted({item.transaction_date.strftime("%Y-%m") if item.transaction_date else "未提供日期" for item in changed}),
                    changed_transaction_ids=[item.id for item in changed],
                    items=[dict(**transaction_payload(item, resolved[item.id]), protected_override=item.id in self.override_ids) for item in rows])


def transaction_payload(row: FinanceTransaction, resolution: Resolution) -> dict:
    return dict(id=row.id, source_document_id=row.source_document_id, date=row.transaction_date,
                description=row.description, amount=str(row.amount), currency=row.currency,
                category_id=resolution.category.id, category_code=resolution.category.code,
                category_name=resolution.category.name, category_source=resolution.source,
                category_rule_id=resolution.rule_id, category_reason=resolution.reason,
                merchant_key=resolution.merchant_key, transaction_kind=row.transaction_kind)
