from hashlib import sha256
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from family_finance_hub.config import Settings
from family_finance_hub.database import Base, make_engine, make_session_factory
from family_finance_hub.documents.processors.csv import CsvDocumentProcessor
from family_finance_hub.documents.processors.ports import ProcessingContext, ProcessingRequest
from family_finance_hub.documents.service import DocumentService
from family_finance_hub.documents.sources import DocumentSourceRegistry, LocalFileDocumentSource
from family_finance_hub.documents.sources.ports import DocumentSourceUnavailable
from family_finance_hub.main import create_app
from family_finance_hub.models import Document, DocumentSourceRecord, FinanceTransaction, ImportJob, SecretProfile
from family_finance_hub.storage.local_filesystem import LocalFilesystemStorage


class MemorySecretStore:
    def __init__(self):
        self.values = {}

    def set(self, reference, value):
        self.values[reference] = value

    def get(self, reference):
        return self.values.get(reference)

    def delete(self, reference):
        self.values.pop(reference, None)


def make_client(tmp_path, secret_store=None):
    db_file = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{db_file.as_posix()}", storage_root=tmp_path / "documents")
    app = create_app(settings, create_schema=True, secret_store=secret_store)
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
        source = session.scalar(select(DocumentSourceRecord))
        assert source.source_type == "local_file"
        assert source.availability_status == "available"
        assert source.last_verified_at is not None
    engine.dispose()


def test_secret_profile_keeps_secret_values_out_of_sqlite_and_api(tmp_path):
    secret_store = MemorySecretStore()
    client, settings = make_client(tmp_path, secret_store)
    national_id = "A123456789"
    birthday = "1984-03-02"

    with client:
        response = client.post("/api/security/profiles", json={
            "display_name": "測試成員",
            "national_id": national_id,
            "birthday": birthday,
        })
        assert response.status_code == 201
        assert national_id not in response.text
        assert birthday not in response.text
        profile_id = response.json()["id"]
        bank_profile = client.post("/api/security/document-profiles", json={
            "display_name": "測試信用卡",
            "institution": "測試銀行",
            "sender_pattern": "statement@example.test",
            "secret_profile_id": profile_id,
        })
        assert bank_profile.status_code == 201
        assert bank_profile.json()["secret_profile_id"] == profile_id
        assert national_id not in bank_profile.text
        assert birthday not in bank_profile.text
        listed = client.get("/api/security/profiles")
        assert listed.status_code == 200
        assert national_id not in listed.text
        assert birthday not in listed.text
        assert listed.json() == [{"id": profile_id, "display_name": "測試成員", "has_credentials": True}]

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        profile = session.get(SecretProfile, profile_id)
        assert profile is not None
        assert national_id not in profile.national_id_credential_ref
        assert birthday not in profile.birthday_credential_ref
        assert profile.national_id_credential_ref in secret_store.values
        assert profile.birthday_credential_ref in secret_store.values
        assert secret_store.get(profile.national_id_credential_ref) == national_id
        assert secret_store.get(profile.birthday_credential_ref) == birthday
    engine.dispose()


def test_secret_profile_cleans_up_partial_vault_write(tmp_path):
    class FailingSecretStore(MemorySecretStore):
        def set(self, reference, value):
            if reference.endswith(":birthday"):
                raise RuntimeError("vault unavailable")
            super().set(reference, value)

    secret_store = FailingSecretStore()
    client, _ = make_client(tmp_path, secret_store)
    with client:
        response = client.post("/api/security/profiles", json={
            "display_name": "測試成員",
            "national_id": "A123456789",
            "birthday": "1984-03-02",
        })
    assert response.status_code == 503
    assert secret_store.values == {}


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
        sources=[DocumentSourceRecord(
            id="source",
            source_type="local_file",
            source_key="aa/source.csv",
            storage_key="aa/source.csv",
            availability_status="available",
        )],
    )

    parsed = CsvDocumentProcessor().process(ProcessingRequest(
        content=source.read(document),
        context=ProcessingContext(filename=document.filename, content_type=document.content_type),
    ))

    assert parsed.headers == ("date", "amount")
    assert parsed.rows == ({"date": "2026-09-23", "amount": "12"},)


def test_duplicate_content_adds_a_local_source_to_an_existing_remote_document(tmp_path):
    database_file = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{database_file.as_posix()}", storage_root=tmp_path / "documents")
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    content = b"same statement bytes"
    digest = sha256(content).hexdigest()
    with factory.begin() as session:
        session.add(Document(
            id="remote-document",
            sha256=digest,
            filename="statement.pdf",
            content_type="application/pdf",
            size_bytes=len(content),
            sources=[DocumentSourceRecord(
                id="gmail-source",
                source_type="gmail_attachment",
                source_key="message-1:attachment-1",
                source_reference={"message_id": "message-1", "attachment_id": "attachment-1"},
                availability_status="unknown",
            )],
        ))

    storage = LocalFilesystemStorage(settings.storage_root)
    registry = DocumentSourceRegistry((LocalFileDocumentSource(storage),))
    with factory() as session:
        with session.begin():
            result = DocumentService(storage).import_bytes(session, "saved.pdf", content, "documents")
            assert result.duplicate is True
            assert registry.read(result.document) == content

    with factory() as session:
        sources = session.scalars(
            select(DocumentSourceRecord).where(DocumentSourceRecord.document_id == "remote-document")
        ).all()
        assert {source.source_type for source in sources} == {"gmail_attachment", "local_file"}
        local_source = next(source for source in sources if source.source_type == "local_file")
        assert local_source.availability_status == "available"
        assert local_source.last_verified_at is not None
    engine.dispose()


def test_missing_source_is_marked_unavailable_and_recovers(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "documents")
    source = DocumentSourceRecord(
        id="local-source",
        source_type="local_file",
        source_key="aa/missing.pdf",
        storage_key="aa/missing.pdf",
        availability_status="unknown",
    )
    document = Document(
        id="document",
        sha256="a" * 64,
        filename="missing.pdf",
        content_type="application/pdf",
        size_bytes=4,
        sources=[source],
    )
    registry = DocumentSourceRegistry((LocalFileDocumentSource(storage),))

    try:
        registry.read(document)
    except DocumentSourceUnavailable:
        pass
    else:
        raise AssertionError("expected unavailable source")
    assert source.availability_status == "unavailable"

    storage.put("aa/missing.pdf", b"file")
    assert registry.read(document) == b"file"
    assert source.availability_status == "available"
    assert source.last_verified_at is not None


def test_content_endpoint_persists_source_availability_without_removing_document(tmp_path):
    client, settings = make_client(tmp_path)
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory.begin() as session:
        session.add(Document(
            id="remote-only-document",
            sha256="b" * 64,
            filename="remote.pdf",
            content_type="application/pdf",
            size_bytes=4,
            sources=[DocumentSourceRecord(
                id="local-source",
                source_type="local_file",
                source_key="missing/location.pdf",
                storage_key="missing/location.pdf",
                availability_status="unknown",
            )],
        ))

    with client:
        unavailable = client.get("/api/documents/remote-only-document/content")
        assert unavailable.status_code == 503
        with factory() as session:
            document = session.get(Document, "remote-only-document")
            assert document is not None
            assert document.sources[0].availability_status == "unavailable"

        LocalFilesystemStorage(settings.storage_root).put("missing/location.pdf", b"file")
        available = client.get("/api/documents/remote-only-document/content")
        assert available.status_code == 200
        assert available.content == b"file"

    with factory() as session:
        source = session.get(Document, "remote-only-document").sources[0]
        assert source.availability_status == "available"
        assert source.last_verified_at is not None
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


def test_failed_csv_import_rolls_back_partial_finance_rows(tmp_path):
    client, _ = make_client(tmp_path)
    csv_bytes = b"date,description,amount\n2026-09-01,Valid,10\n2026-09-02,Invalid,nope\n"
    with client:
        response = client.post("/api/finance/import-csv", files={"file": ("ledger.csv", csv_bytes, "text/csv")})
        assert response.status_code == 400
        assert client.get("/api/dashboard").json()["transaction_count"] == 0
        jobs = client.get("/api/jobs").json()
        assert any(job["status"] == "failed" and "金額格式無效" in job["summary"] for job in jobs)
