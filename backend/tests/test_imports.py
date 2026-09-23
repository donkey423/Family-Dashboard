from fastapi.testclient import TestClient
from sqlalchemy import select

from family_finance_hub.config import Settings
from family_finance_hub.database import Base, make_engine, make_session_factory
from family_finance_hub.main import create_app
from family_finance_hub.models import Document, FinanceTransaction, ImportJob


def make_client(tmp_path):
    db_file = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{db_file.as_posix()}", storage_root=tmp_path / "documents")
    app = create_app(settings, create_schema=True)
    return TestClient(app), settings


def test_document_upload_deduplicates_by_sha256(tmp_path):
    client, settings = make_client(tmp_path)
    with client:
        first = client.post("/api/documents", files={"file": ("receipt.pdf", b"same-bytes", "application/pdf")})
        second = client.post("/api/documents", files={"file": ("copy.pdf", b"same-bytes", "application/pdf")})
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["duplicate"] is False
        assert second.json()["duplicate"] is True
        content = client.get(f"/api/documents/{first.json()['id']}/content")
        assert content.status_code == 200
        assert content.content == b"same-bytes"

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1
        assert len(session.scalars(select(ImportJob)).all()) == 2
    engine.dispose()


def test_finance_csv_import_is_idempotent_and_linked_to_document(tmp_path):
    client, settings = make_client(tmp_path)
    csv_bytes = b"date,description,amount,currency\n2026-09-01,Groceries,-42.50,TWD\n2026-09-02,Salary,1000,TWD\n2026-09-03,Train,50,USD\n"
    with client:
        first = client.post("/api/finance/import-csv", files={"file": ("ledger.csv", csv_bytes, "text/csv")})
        second = client.post("/api/finance/import-csv", files={"file": ("ledger.csv", csv_bytes, "text/csv")})
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["created_transactions"] == 3
        assert second.json()["created_transactions"] == 0
        assert first.json()["document_id"] == second.json()["document_id"]
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["transaction_count"] == 3
        assert dashboard["currency_totals"] == [
            {"currency": "TWD", "income": "1000.00", "expenses": "42.50", "net": "957.50"},
            {"currency": "USD", "income": "50.00", "expenses": "0.00", "net": "50.00"},
        ]
        assert client.get("/api/search", params={"q": "Groceries"}).json()["transactions"]

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        rows = session.scalars(select(FinanceTransaction)).all()
        assert len(rows) == 3
        assert all(row.source_document_id == first.json()["document_id"] for row in rows)
    engine.dispose()


def test_upload_rejects_unsupported_file(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.post("/api/documents", files={"file": ("notes.txt", b"text", "text/plain")})
    assert response.status_code == 400


def test_failed_csv_import_is_visible_in_job_history(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.post("/api/finance/import-csv", files={"file": ("ledger.csv", b"date,description\\n2026-09-01,Missing amount\\n", "text/csv")})
        assert response.status_code == 400
        jobs = client.get("/api/jobs").json()
        assert any(job["status"] == "failed" and job["target_module"] == "finance" for job in jobs)
