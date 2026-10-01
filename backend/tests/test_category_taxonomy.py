from datetime import date
from decimal import Decimal

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from family_finance_hub.config import Settings
from family_finance_hub.exports.service import read_snapshot
from family_finance_hub.finance.categories.service import CategorizationService
from family_finance_hub.main import create_app
from family_finance_hub.models import Document, FinanceCategory, FinanceTransaction, TransactionCategoryOverride


def test_taxonomy_upgrade_preserves_custom_names_and_referenced_downgrade(tmp_path):
    path = tmp_path / "taxonomy.db"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0012_transaction_categories")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE finance_categories SET display_name='Custom',sort_order=99 WHERE code='food'"))
        before = connection.execute(text("SELECT * FROM finance_transactions")).all()
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT display_name,sort_order FROM finance_categories WHERE code='food'")).one() == ("Custom", 99)
        assert connection.scalar(text("SELECT display_name FROM finance_categories WHERE code='finance'")) == "金融費用"
        assert connection.scalar(text("SELECT count(*) FROM finance_categories")) == 16
        connection.execute(text("INSERT INTO finance_category_rules VALUES('book-rule','books','contains','EBOOK',0,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    command.downgrade(config, "0012_transaction_categories")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM finance_categories WHERE code='books'")) == 1
        assert connection.scalar(text("SELECT count(*) FROM finance_categories WHERE code='insurance'")) == 0
        assert connection.scalar(text("SELECT display_name FROM finance_categories WHERE code='finance'")) == "金融／手續費／保險"
        assert connection.execute(text("SELECT * FROM finance_transactions")).all() == before
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM finance_categories")) == 16
        assert connection.scalar(text("SELECT category_id FROM finance_category_rules")) == "books"
    engine.dispose()


def test_api_excel_builtin_parity_and_disable_changes_empty_fingerprint(tmp_path):
    path = tmp_path / "rules.db"
    settings = Settings(database_url=f"sqlite:///{path.as_posix()}", storage_root=tmp_path / "documents")
    app = create_app(settings, create_schema=True)
    with TestClient(app) as client:
        with app.state.session_factory() as session, session.begin():
            empty_enabled = read_snapshot(session).category_configuration_hash
            session.info["builtin_category_rules_enabled"] = False
            assert read_snapshot(session).category_configuration_hash != empty_enabled
            session.add(Document(id="doc", sha256="b" * 64, filename="synthetic.csv", content_type="text/csv", size_bytes=0))
            session.flush()
            session.add(FinanceTransaction(id="t", source_document_id="doc", row_hash="hash", description="電子書", amount=Decimal("-100"), currency="TWD", raw_json="{}", transaction_date=date(2026, 9, 1)))
        row = client.get("/api/finance/transactions").json()["items"][0]
        assert (row["category_code"], row["category_source"], row["category_rule_id"]) == ("books", "builtin_rule", "ebook")
        with app.state.session_factory() as session:
            enabled = read_snapshot(session)
            assert enabled.transactions[0].category_code == "books"
            session.info["builtin_category_rules_enabled"] = False
            disabled = read_snapshot(session)
            assert disabled.transactions[0].category_code == "uncategorized"
            assert enabled.category_configuration_hash != disabled.category_configuration_hash
        assert client.patch("/api/finance/categories/books", json={"is_active": False}).status_code == 200
        assert client.get("/api/finance/transactions").json()["items"][0]["category_code"] == "uncategorized"
    disabled_app = create_app(Settings(database_url=settings.database_url, storage_root=settings.storage_root, builtin_category_rules_enabled=False))
    with TestClient(disabled_app) as client:
        with disabled_app.state.session_factory() as session:
            assert CategorizationService(session).resolver.builtin_enabled is False


def test_merchant_preview_guards_staleness_cross_months_and_overrides(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'impact.db').as_posix()}", storage_root=tmp_path / "documents"), create_schema=True)
    with TestClient(app) as client:
        with app.state.session_factory() as session, session.begin():
            session.add(Document(id="doc", sha256="a" * 64, filename="synthetic.csv", content_type="text/csv", size_bytes=0))
            session.flush()
            for index, description in enumerate(("Shop", "ＳＨＯＰ", "Shop")):
                session.add(FinanceTransaction(id=f"t{index}", source_document_id="doc", row_hash=f"h{index}", description=description, amount=Decimal("-100"), currency="TWD", raw_json="{}", transaction_date=date(2026, 7 + index, 1)))
            session.flush()
            session.add(TransactionCategoryOverride(transaction_id="t1", category_id="family"))
        url = "/api/finance/transactions/t0/category"
        assert client.patch(url, json={"category_id": "books", "scope": "merchant"}).status_code == 422
        preview = client.get(url + "-impact", params={"category_id": "books"}).json()
        assert preview["changed_count"] == 2 and preview["protected_override_count"] == 1
        assert preview["months"] == ["2026-07", "2026-09"]
        with app.state.session_factory() as session, session.begin():
            session.get(FinanceTransaction, "t2").amount = Decimal("-101")
        body = {"category_id": "books", "scope": "merchant", "impact_token": preview["impact_token"]}
        assert client.patch(url, json=body).status_code == 409
        assert client.get("/api/finance/category-rules").json() == []
        body["impact_token"] = client.get(url + "-impact", params={"category_id": "books"}).json()["impact_token"]
        assert client.patch(url, json=body).status_code == 200
        rows = {row["id"]: row for row in client.get("/api/finance/transactions").json()["items"]}
        assert [rows[f"t{i}"]["category_code"] for i in range(3)] == ["books", "family", "books"]
        assert client.patch(url, json=body).status_code == 409
        with app.state.session_factory() as session:
            assert len(session.scalars(select(FinanceCategory)).all()) == 16


def test_builtin_configuration_environment(monkeypatch):
    monkeypatch.setenv("FAMILY_FINANCE_HUB_BUILTIN_CATEGORY_RULES", "false")
    assert Settings.from_environment().builtin_category_rules_enabled is False
    monkeypatch.setenv("FAMILY_FINANCE_HUB_BUILTIN_CATEGORY_RULES", "true")
    assert Settings.from_environment().builtin_category_rules_enabled is True
