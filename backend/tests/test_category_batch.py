from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from family_finance_hub.config import Settings
from family_finance_hub.exports.service import read_snapshot
from family_finance_hub.main import create_app
from family_finance_hub.models import Document, FinanceTransaction, TransactionCategoryOverride


@pytest.fixture
def batch_app(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'batch.db').as_posix()}", storage_root=tmp_path / "documents"), create_schema=True)
    with TestClient(app), app.state.session_factory() as session, session.begin():
        session.add(Document(id="doc", sha256="a" * 64, filename="synthetic.csv", content_type="text/csv", size_bytes=0))
        session.flush()
        for index in range(4):
            session.add(FinanceTransaction(id=f"t{index}", source_document_id="doc", row_hash=f"h{index}", description="Shop", amount=Decimal("-100"), currency="TWD", raw_json="{}", transaction_date=date(2026, 6 + index, 1)))
        session.flush()
        session.add(TransactionCategoryOverride(transaction_id="t1", category_id="family"))
    return app


def preview(client, body):
    result = client.post("/api/finance/transactions/category-batch/preview", json=body)
    assert result.status_code == 200, result.text
    return result.json()


def test_batch_protects_manual_even_inactive_and_preserves_facts(batch_app):
    with TestClient(batch_app) as client:
        with batch_app.state.session_factory() as session:
            before = session.execute(text("SELECT * FROM finance_transactions ORDER BY id")).all()
            fingerprint = read_snapshot(session).category_configuration_hash
        assert client.patch("/api/finance/categories/family", json={"is_active": False}).status_code == 200
        body = dict(transaction_ids=["t0", "t1", "t2"], category_id="books")
        impact = preview(client, body)
        assert impact["changed_count"] == 2 and impact["protected_override_count"] == 1
        assert impact["months"] == ["2026-06", "2026-08"]
        assert next(item for item in impact["items"] if item["id"] == "t1")["protected_override"]
        assert preview(client, dict(body, transaction_ids=["t2", "t0", "t1"]))["impact_token"] == impact["impact_token"]
        body["impact_token"] = impact["impact_token"]
        result = client.patch("/api/finance/transactions/category-batch", json=body)
        assert result.status_code == 200 and result.json() == dict(changed_count=2, protected_override_count=1)
        assert client.get("/api/finance/category-rules").json() == []
        assert client.patch("/api/finance/transactions/category-batch", json=body).status_code == 409
        del body["impact_token"]
        assert preview(client, body)["changed_count"] == 0
        with batch_app.state.session_factory() as session:
            assert session.execute(text("SELECT * FROM finance_transactions ORDER BY id")).all() == before
            assert session.get(TransactionCategoryOverride, "t1").category_id == "family"
            assert session.get(TransactionCategoryOverride, "t3") is None
            assert len(session.scalars(select(TransactionCategoryOverride)).all()) == 3
            snapshot = read_snapshot(session)
            assert snapshot.category_configuration_hash != fingerprint
            assert {row.id: row.category_code for row in snapshot.transactions}["t0"] == "books"


@pytest.mark.parametrize("invalid", [[], ["t0", "t0"], [""], ["x" * 37], [f"id{i}" for i in range(51)]])
def test_batch_rejects_invalid_selection(batch_app, invalid):
    with TestClient(batch_app) as client:
        assert client.post("/api/finance/transactions/category-batch/preview", json=dict(transaction_ids=invalid, category_id="books")).status_code == 422


@pytest.mark.parametrize("mutation", ["amount", "revocation", "category", "manual"])
def test_batch_stale_or_missing_never_partially_writes(batch_app, mutation):
    with TestClient(batch_app) as client:
        body = dict(transaction_ids=["t0", "t2"], category_id="books")
        body["impact_token"] = preview(client, body)["impact_token"]
        with batch_app.state.session_factory() as session, session.begin():
            if mutation == "amount":
                session.get(FinanceTransaction, "t2").amount = Decimal("-101")
            elif mutation == "revocation":
                session.execute(text("UPDATE documents SET revoked_at=CURRENT_TIMESTAMP WHERE id='doc'"))
            elif mutation == "category":
                session.execute(text("UPDATE finance_categories SET display_name='New Books' WHERE id='books'"))
            else:
                session.add(TransactionCategoryOverride(transaction_id="t2", category_id="transport"))
        assert client.patch("/api/finance/transactions/category-batch", json=body).status_code == 409
        with batch_app.state.session_factory() as session:
            assert session.get(TransactionCategoryOverride, "t0") is None
            assert session.get(TransactionCategoryOverride, "t2") is None or mutation == "manual"


def test_batch_insert_failure_rolls_back_whole_selection(batch_app):
    with TestClient(batch_app) as client:
        body = dict(transaction_ids=["t0", "t2"], category_id="books")
        body["impact_token"] = preview(client, body)["impact_token"]
        with batch_app.state.session_factory() as session, session.begin():
            session.execute(text("CREATE TRIGGER synthetic_failure BEFORE INSERT ON transaction_category_overrides WHEN NEW.transaction_id='t2' BEGIN SELECT RAISE(ABORT, 'synthetic'); END"))
        assert client.patch("/api/finance/transactions/category-batch", json=body).status_code == 409
        with batch_app.state.session_factory() as session:
            assert session.get(TransactionCategoryOverride, "t0") is None
            assert session.get(TransactionCategoryOverride, "t2") is None


def test_batch_missing_and_non_consumption_fail_closed(batch_app):
    with TestClient(batch_app) as client:
        assert client.post("/api/finance/transactions/category-batch/preview", json=dict(transaction_ids=["t0", "missing"], category_id="books")).status_code == 409
        assert client.patch("/api/finance/transactions/category-batch", json=dict(transaction_ids=["t0"], category_id="books")).status_code == 422
        with batch_app.state.session_factory() as session, session.begin():
            session.get(FinanceTransaction, "t2").amount = Decimal("100")
        assert client.post("/api/finance/transactions/category-batch/preview", json=dict(transaction_ids=["t0", "t2"], category_id="books")).status_code == 422
