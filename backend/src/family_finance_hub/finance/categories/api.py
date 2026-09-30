from typing import Literal
from uuid import uuid4
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ...models import FinanceCategory, FinanceCategoryRule, FinanceTransaction, TransactionCategoryOverride, utc_now
from ..queries import active_transaction_filter
from .domain import PROTECTED_CODES, normalize_merchant
from .service import CategorizationService, transaction_payload


class CategoryCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    display_name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=100, ge=0, le=100000)

    @field_validator("display_name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("分類名稱不可空白")
        return value.strip()


class CategoryPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    is_active: bool | None = None

    @field_validator("display_name")
    @classmethod
    def nonblank(cls, value):
        return CategoryCreate.nonblank(value) if value is not None else value


class RuleCreate(BaseModel):
    category_id: str = Field(min_length=1, max_length=36)
    match_type: Literal["normalized_exact", "contains"]
    pattern: str = Field(min_length=1, max_length=500)
    priority: int = Field(default=0, ge=-100000, le=100000)
    enabled: bool = True

    @field_validator("pattern")
    @classmethod
    def normalize(cls, value):
        value = normalize_merchant(value)
        if not value or len(value) > 500:
            raise ValueError("商家文字長度無效")
        return value


class RulePatch(BaseModel):
    category_id: str | None = Field(default=None, min_length=1, max_length=36)
    pattern: str | None = Field(default=None, min_length=1, max_length=500)
    priority: int | None = Field(default=None, ge=-100000, le=100000)
    enabled: bool | None = None

    @field_validator("pattern")
    @classmethod
    def normalize(cls, value):
        return RuleCreate.normalize(value) if value is not None else value


class Assignment(BaseModel):
    category_id: str = Field(min_length=1, max_length=36)
    scope: Literal["transaction", "merchant"] = "transaction"


def category_payload(row):
    return dict(id=row.id, code=row.code, display_name=row.display_name, sort_order=row.sort_order, is_system=row.is_system, is_active=row.is_active)


def rule_payload(row):
    return dict(id=row.id, category_id=row.category_id, match_type=row.match_type, pattern=row.normalized_pattern, priority=row.priority, enabled=row.enabled)


def require_category(session, category_id, *, active=False):
    row = session.get(FinanceCategory, category_id)
    if row is None:
        raise HTTPException(404, "找不到分類")
    if active and not row.is_active:
        raise HTTPException(422, "無法指定停用的分類")
    return row


def require_transaction(session, transaction_id):
    row = session.scalar(select(FinanceTransaction).where(FinanceTransaction.id == transaction_id, active_transaction_filter()))
    if row is None:
        raise HTTPException(404, "找不到有效交易")
    return row


def commit(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "分類代碼或商家規則已存在；請修改既有項目") from None


def category_router(get_session, month_range, currency_code):
    router = APIRouter(prefix="/api/finance")

    def category_session(session: Session = Depends(get_session)):
        try:
            yield session
        except OperationalError as error:
            session.rollback()
            code = getattr(error.orig, "sqlite_errorcode", 0)
            if (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise HTTPException(409, "分類資料正在更新；請稍後重試") from None
            raise

    @router.get("/categories")
    def categories(session: Session = Depends(category_session)):
        return [category_payload(row) for row in session.scalars(select(FinanceCategory).order_by(FinanceCategory.sort_order, FinanceCategory.id))]

    @router.post("/categories", status_code=201)
    def create_category(body: CategoryCreate, session: Session = Depends(category_session)):
        row = FinanceCategory(id=str(uuid4()), **body.model_dump(), is_system=False, is_active=True)
        session.add(row)
        commit(session)
        return category_payload(row)

    @router.patch("/categories/{category_id}")
    def change_category(category_id: str, body: CategoryPatch, session: Session = Depends(category_session)):
        row = require_category(session, category_id)
        if row.code in PROTECTED_CODES and body.is_active is False:
            raise HTTPException(422, "必要系統分類不可停用")
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        commit(session)
        return category_payload(row)

    @router.get("/category-rules")
    def rules(session: Session = Depends(category_session)):
        return [rule_payload(row) for row in session.scalars(select(FinanceCategoryRule).order_by(FinanceCategoryRule.id))]

    @router.post("/category-rules", status_code=201)
    def create_rule(body: RuleCreate, session: Session = Depends(category_session)):
        require_category(session, body.category_id, active=True)
        data = body.model_dump()
        data["normalized_pattern"] = data.pop("pattern")
        row = FinanceCategoryRule(id=str(uuid4()), **data)
        session.add(row)
        commit(session)
        return rule_payload(row)

    @router.patch("/category-rules/{rule_id}")
    def change_rule(rule_id: str, body: RulePatch, session: Session = Depends(category_session)):
        row = session.get(FinanceCategoryRule, rule_id)
        if row is None:
            raise HTTPException(404, "找不到商家規則")
        if body.category_id:
            require_category(session, body.category_id, active=True)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, "normalized_pattern" if key == "pattern" else key, value)
        commit(session)
        return rule_payload(row)

    @router.delete("/category-rules/{rule_id}")
    def delete_rule(rule_id: str, session: Session = Depends(category_session)):
        row = session.get(FinanceCategoryRule, rule_id)
        if row is None:
            raise HTTPException(404, "找不到商家規則")
        session.delete(row)
        commit(session)
        return {"deleted": True}

    @router.patch("/transactions/{transaction_id}/category")
    def assign(transaction_id: str, body: Assignment, session: Session = Depends(category_session)):
        row = require_transaction(session, transaction_id)
        require_category(session, body.category_id, active=True)
        now = utc_now()
        if body.scope == "transaction":
            session.execute(insert(TransactionCategoryOverride).values(transaction_id=row.id, category_id=body.category_id, created_at=now, updated_at=now)
                .on_conflict_do_update(index_elements=["transaction_id"], set_=dict(category_id=body.category_id, updated_at=now)))
        else:
            key = normalize_merchant(row.description)
            if not key:
                raise HTTPException(422, "空白商家不可建立規則")
            session.execute(insert(FinanceCategoryRule).values(id=str(uuid4()), category_id=body.category_id, match_type="normalized_exact", normalized_pattern=key, priority=0, enabled=True, created_at=now, updated_at=now)
                .on_conflict_do_update(index_elements=["match_type", "normalized_pattern"], set_=dict(category_id=body.category_id, enabled=True, updated_at=now)))
        commit(session)
        service = CategorizationService(session)
        return transaction_payload(row, service.resolve([row])[row.id])

    @router.delete("/transactions/{transaction_id}/category")
    def clear_override(transaction_id: str, session: Session = Depends(category_session)):
        row = require_transaction(session, transaction_id)
        session.execute(delete(TransactionCategoryOverride).where(TransactionCategoryOverride.transaction_id == row.id))
        commit(session)
        service = CategorizationService(session)
        return transaction_payload(row, service.resolve([row])[row.id])

    def filtered(session, month, currency):
        code = currency_code(currency)
        service = CategorizationService(session)
        rows = service.rows(month_range=month_range(month), currency=code)
        return code, service, rows, service.resolve(rows)

    @router.get("/spending-by-category")
    def spending(month: str | None = Query(default=None, max_length=7), currency: str = Query(default="TWD", max_length=3, min_length=3), session: Session = Depends(category_session)):
        code, service, rows, resolved = filtered(session, month, currency)
        return dict(month=month, currency=code, **service.spending(rows, resolved))

    @router.get("/category-merchants")
    def merchants(category_id: str, month: str | None = Query(default=None, max_length=7), currency: str = Query(default="TWD", max_length=3, min_length=3), session: Session = Depends(category_session)):
        require_category(session, category_id)
        code, service, rows, resolved = filtered(session, month, currency)
        return dict(month=month, currency=code, items=service.merchants(rows, resolved, category_id))

    @router.get("/uncategorized-merchants")
    def uncategorized(month: str | None = Query(default=None, max_length=7), currency: str = Query(default="TWD", max_length=3, min_length=3), session: Session = Depends(category_session)):
        code, service, rows, resolved = filtered(session, month, currency)
        return dict(month=month, currency=code, items=service.merchants(rows, resolved, service.resolver.codes["uncategorized"].id))

    return router
