from hashlib import sha256

from fastapi.testclient import TestClient
from sqlalchemy import select

from family_finance_hub.config import Settings
from family_finance_hub.database import Base, make_engine, make_session_factory
from family_finance_hub.documents.processors.csv import CsvDocumentProcessor
from family_finance_hub.documents.service import DocumentService
from family_finance_hub.documents.sources import DocumentSourceRegistry, LocalFileDocumentSource
from family_finance_hub.main import create_app
from family_finance_hub.models import Document, FinanceTransaction, ImportJob
from family_finance_hub.storage.local_filesystem import LocalFilesystemStorage


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


def test_document_service_leaves_transaction_ownership_to_caller(tmp_path):
    database_file = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{database_file.as_posix()}", storage_root=tmp_path / "documents")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    service = DocumentService(LocalFilesystemStorage(settings.storage_root))

    with factory() as session:
        session.begin()
        result = service.import_bytes(session, "receipt.pdf", b"bytes", "documents")
        assert session.in_transaction()
        with factory() as observer:
            assert observer.get(Document, result.document.id) is None
        session.rollback()

    with factory() as session:
        assert session.get(Document, result.document.id) is None
    engine.dispose()


def test_document_service_recovers_sha256_unique_conflict(tmp_path, monkeypatch):
    database_file = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{database_file.as_posix()}", storage_root=tmp_path / "documents")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    content = b"same content"
    digest = sha256(content).hexdigest()
    with factory.begin() as session:
        session.add(Document(
            id="existing-document",
            sha256=digest,
            filename="first.pdf",
            content_type="application/pdf",
            size_bytes=len(content),
            storage_key=f"{digest[:2]}/{digest}.pdf",
            source_type="local_file",
        ))

    with factory() as session:
        actual_scalar = session.scalar
        first_lookup = True

        def simulate_concurrent_insert(statement, *args, **kwargs):
            nonlocal first_lookup
            if first_lookup:
                first_lookup = False
                return None
            return actual_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(session, "scalar", simulate_concurrent_insert)
        with session.begin():
            result = DocumentService(LocalFilesystemStorage(settings.storage_root)).import_bytes(
                session, "second.pdf", content, "documents"
            )

    assert result.duplicate is True
    assert result.document.id == "existing-document"
    engine.dispose()


def test_local_document_source_and_csv_processor_are_adapters(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "documents")
    content = b"\xef\xbb\xbfdate,amount\n2026-09-23,12\n"
    storage.put("aa/source.csv", content)
    source = DocumentSourceRegistry((LocalFileDocumentSource(storage),))
    document = Document(
        id="document",
        sha256="a" * 64,
        filename="source.csv",
        content_type="text/csv",
        size_bytes=len(content),
        storage_key="aa/source.csv",
        source_type="local_file",
    )

    parsed = CsvDocumentProcessor().process(source.read(document))

    assert parsed.headers == ("date", "amount")
    assert parsed.rows == ({"date": "2026-09-23", "amount": "12"},)


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


def test_failed_csv_import_rolls_back_partial_finance_rows(tmp_path):
    client, _ = make_client(tmp_path)
    csv_bytes = b"date,description,amount\n2026-09-01,Valid,10\n2026-09-02,Invalid,nope\n"
    with client:
        response = client.post("/api/finance/import-csv", files={"file": ("ledger.csv", csv_bytes, "text/csv")})
        assert response.status_code == 400
        assert client.get("/api/dashboard").json()["transaction_count"] == 0
        jobs = client.get("/api/jobs").json()
        assert any(job["status"] == "failed" and "金額格式無效" in job["summary"] for job in jobs)
