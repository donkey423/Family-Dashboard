import base64
from datetime import timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from sqlalchemy import func, select

from family_finance_hub.config import Settings
from family_finance_hub.database import make_engine, make_session_factory
from family_finance_hub.main import create_app
from family_finance_hub.integrations.gmail.client import GmailHistoryExpired
from family_finance_hub.models import Document, DocumentSourceRecord, FinanceTransaction, GmailConnection, GmailSyncState, ImportJob, utc_now
from family_finance_hub.security.password_rules.schema import PasswordRule


class MemorySecretStore:
    def __init__(self):
        self.values = {}

    def set(self, reference, value):
        self.values[reference] = value

    def get(self, reference):
        return self.values.get(reference)

    def delete(self, reference):
        self.values.pop(reference, None)


class FakeGmail:
    def __init__(self):
        self.queries = []
        self.history_calls = []
        self.expire_history = False
        self.csv = b"date,description,amount,currency\n2026-09-01,Test market,-245,TWD\n"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.encrypt("synthetic")
        pdf = BytesIO()
        writer.write(pdf)
        self.attachments = {"att-pdf": pdf.getvalue(), "att-csv": self.csv}

    def list_messages(self, query, page_token=None):
        self.queries.append(query)
        return {"messages": [{"id": "message-1"}]} if page_token is None else {"messages": []}

    def get_message(self, message_id):
        return {
            "id": message_id,
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Synthetic statement"},
                    {"name": "From", "value": "bank@example.test"},
                ],
                "parts": [
                    {"partId": "pdf-0", "filename": "statement.pdf", "mimeType": "application/pdf", "body": {"attachmentId": "att-pdf"}},
                    {"partId": "csv-1", "filename": "activity.csv", "mimeType": "text/csv", "body": {"attachmentId": "att-csv"}},
                ],
            },
        }

    def get_profile(self):
        return {"historyId": "100"}

    def list_history(self, start_history_id, page_token=None):
        self.history_calls.append((start_history_id, page_token))
        if self.expire_history:
            raise GmailHistoryExpired("synthetic expired cursor")
        return {
            "history": [{"messagesAdded": [{"message": {"id": "message-1"}}]}],
            "historyId": "120",
        }

    def get_attachment(self, message_id, attachment_id):
        return self.attachments[attachment_id]


class FakeInterpreter:
    def __init__(self, rule):
        self.rule = rule
        self.calls = []

    def interpret(self, instruction, context):
        self.calls.append((instruction, context))
        return self.rule


def make_app(tmp_path, secret_store, gmail, password_interpreter=None, max_upload_bytes=25 * 1024 * 1024):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'gmail-test.db').as_posix()}",
        storage_root=tmp_path / "documents",
        max_upload_bytes=max_upload_bytes,
    )
    app = create_app(
        settings,
        create_schema=True,
        secret_store=secret_store,
        gmail_client_factory=lambda: gmail,
        password_interpreter=password_interpreter,
    )
    return TestClient(app), settings


def test_gmail_oauth_client_secret_is_saved_to_secret_store_only(tmp_path):
    vault = MemorySecretStore()
    client, settings = make_app(tmp_path, vault, FakeGmail())
    client_config = {
        "installed": {
            "client_id": "synthetic-client-id",
            "client_secret": "synthetic-client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    with client:
        response = client.post("/api/gmail/oauth-client", json={"config": client_config})
        assert response.status_code == 201
        assert "synthetic-client-secret" not in response.text
        status = client.get("/api/gmail/status").json()
        assert status["configured"] is True
        assert status["authorized"] is False

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        connection = session.get(GmailConnection, "gmail")
        assert connection is not None
        assert connection.client_config_credential_ref in vault.values
        assert connection.token_credential_ref not in vault.values
    assert b"synthetic-client-secret" not in (tmp_path / "gmail-test.db").read_bytes()
    engine.dispose()


def test_gmail_sync_imports_csv_once_keeps_pdf_remote_and_can_save_local(tmp_path):
    vault = MemorySecretStore()
    gmail = FakeGmail()
    client, settings = make_app(tmp_path, vault, gmail)

    with client:
        first = client.post("/api/gmail/sync", json={})
        assert first.status_code == 200, first.text
        result = first.json()
        assert {key: result[key] for key in (
            "scanned_messages", "new_attachments", "csv_files", "created_transactions", "duplicates", "failures", "truncated", "sync_mode"
        )} == {
            "scanned_messages": 1,
            "new_attachments": 2,
            "csv_files": 1,
            "created_transactions": 1,
            "duplicates": 0,
            "failures": 0,
            "truncated": 0,
            "sync_mode": "full",
        }
        assert gmail.queries[0] == "in:anywhere has:attachment {filename:pdf filename:csv}"

        documents = client.get("/api/documents").json()
        pdf_document = next(item for item in documents if item["filename"] == "statement.pdf")
        pdf_content = client.get(f"/api/documents/{pdf_document['id']}/content")
        assert pdf_content.status_code == 200
        assert pdf_content.content == gmail.attachments["att-pdf"]

        saved = client.post(f"/api/documents/{pdf_document['id']}/save-local")
        assert saved.status_code == 200
        assert saved.json()["saved_locally"] is True

        second = client.post("/api/gmail/sync", json={})
        assert second.status_code == 200, second.text
        assert second.json()["sync_mode"] == "incremental"
        assert second.json()["new_attachments"] == 0
        assert second.json()["created_transactions"] == 0
        assert second.json()["duplicates"] == 2

        gmail.expire_history = True
        fallback = client.post("/api/gmail/sync", json={})
        assert fallback.status_code == 200, fallback.text
        assert fallback.json()["sync_mode"] == "full-fallback"
        assert fallback.json()["new_attachments"] == 0
        status = client.get("/api/gmail/status").json()
        assert status["last_sync_status"] == "completed"
        assert status["last_successful_sync"] is not None

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 2
        assert session.scalar(select(func.count()).select_from(FinanceTransaction)) == 1
        assert session.scalar(select(func.count()).select_from(ImportJob)) == 3
        sync_state = session.get(GmailSyncState, "gmail")
        assert sync_state is not None
        assert sync_state.history_id == "100"
        assert sync_state.full_sync_in_progress is False
        pdf_sources = session.scalars(select(DocumentSourceRecord).join(Document).where(Document.filename == "statement.pdf")).all()
        assert {source.source_type for source in pdf_sources} == {"gmail_attachment", "local_file"}
        assert all("bank@example.test" not in str(source.source_reference) for source in pdf_sources)
        assert all("Synthetic statement" not in str(source.source_reference) for source in pdf_sources)
    stored_files = list((tmp_path / "documents").rglob("*"))
    assert any(item.is_file() for item in stored_files)
    engine.dispose()


def test_gmail_auto_sync_is_opt_in_and_runs_the_existing_sync_use_case(tmp_path):
    vault = MemorySecretStore()
    gmail = FakeGmail()
    client, _settings = make_app(tmp_path, vault, gmail)

    with client:
        status = client.get("/api/gmail/status").json()
        assert status["auto_sync_enabled"] is False
        assert status["next_sync_at"] is None
        assert status["sync_interval_minutes"] == 30
        assert client.post("/api/gmail/schedule", json={"enabled": True}).status_code == 409

        vault.set("token-ref", "synthetic-token")
        factory = client.app.state.session_factory
        with factory() as session, session.begin():
            session.add(GmailConnection(
                id="gmail",
                client_config_credential_ref="config-ref",
                token_credential_ref="token-ref",
            ))

        enabled = client.post("/api/gmail/schedule", json={"enabled": True})
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["auto_sync_enabled"] is True
        assert enabled.json()["next_sync_at"] is not None

        with factory() as session, session.begin():
            connection = session.get(GmailConnection, "gmail")
            connection.next_scheduled_sync_at = utc_now() - timedelta(seconds=1)
        assert client.app.state.gmail_sync_scheduler.run_due() is True
        assert gmail.queries == ["in:anywhere has:attachment {filename:pdf filename:csv}"]
        assert client.get("/api/gmail/status").json()["last_sync_status"] == "completed"

        disabled = client.post("/api/gmail/schedule", json={"enabled": False})
        assert disabled.status_code == 200
        assert disabled.json()["auto_sync_enabled"] is False
        assert disabled.json()["next_sync_at"] is None


def test_full_gmail_sync_resumes_from_saved_page_token(tmp_path, monkeypatch):
    import family_finance_hub.integrations.gmail.sync as sync_module

    class PagingGmail(FakeGmail):
        def __init__(self):
            super().__init__()
            self.page_tokens = []

        def list_messages(self, query, page_token=None):
            self.page_tokens.append(page_token)
            if page_token is None:
                return {"messages": [{"id": "message-1"}], "nextPageToken": "page-2"}
            return {"messages": [{"id": "message-2"}]}

        def get_message(self, message_id):
            return {"id": message_id, "payload": {"parts": []}}

    monkeypatch.setattr(sync_module, "MAX_MESSAGES_PER_SYNC", 1)
    gmail = PagingGmail()
    client, settings = make_app(tmp_path, MemorySecretStore(), gmail)

    with client:
        first = client.post("/api/gmail/sync", json={})
        assert first.status_code == 200, first.text
        assert first.json()["truncated"] == 1
        assert first.json()["sync_mode"] == "full"
        second = client.post("/api/gmail/sync", json={})
        assert second.status_code == 200, second.text
        assert second.json()["truncated"] == 0
        assert second.json()["sync_mode"] == "full-resume"

    assert gmail.page_tokens == [None, "page-2"]
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        state = session.get(GmailSyncState, "gmail")
        assert state is not None
        assert state.history_id == "100"
        assert state.full_sync_in_progress is False
        assert state.full_sync_page_token is None
    engine.dispose()


def test_gmail_preserves_unparseable_csv_and_records_failed_finance_job(tmp_path):
    gmail = FakeGmail()
    gmail.attachments["att-csv"] = b"not,a,finance,csv\n1,2,3,4\n"
    client, settings = make_app(tmp_path, MemorySecretStore(), gmail)

    with client:
        first = client.post("/api/gmail/sync", json={})
        assert first.status_code == 200, first.text
        assert first.json()["failures"] == 1
        assert first.json()["new_attachments"] == 2
        archived = next(row for row in client.get("/api/documents").json() if row["filename"] == "activity.csv")
        assert client.get(f"/api/documents/{archived['id']}/content").content == gmail.attachments["att-csv"]

        second = client.post("/api/gmail/sync", json={})
        assert second.status_code == 200, second.text
        assert second.json()["failures"] == 0
        assert second.json()["created_transactions"] == 0
        assert second.json()["duplicates"] == 2
        local_retry = client.post("/api/finance/import-csv", files={
            "file": ("activity.csv", FakeGmail().csv, "text/csv"),
        })
        assert local_retry.status_code == 200, local_retry.text
        assert local_retry.json()["created_transactions"] == 1

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        csv_documents = session.scalars(select(Document).where(Document.filename == "activity.csv")).all()
        assert len(csv_documents) == 2
        assert session.scalar(select(func.count()).select_from(FinanceTransaction)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentSourceRecord).where(
            DocumentSourceRecord.source_key == "message-1:csv-1"
        )) == 1
    engine.dispose()


def test_unparseable_csv_does_not_block_later_gmail_pages(tmp_path):
    class MultiPageGmail(FakeGmail):
        def __init__(self):
            super().__init__()
            self.page_tokens = []
            self.attachments = {
                "bad": b"not,a,finance,csv\n1,2,3,4\n",
                "good": FakeGmail().csv,
            }

        def list_messages(self, query, page_token=None):
            self.page_tokens.append(page_token)
            message_id = "bad-message" if page_token is None else "good-message"
            page = {"messages": [{"id": message_id}]}
            if page_token is None:
                page["nextPageToken"] = "page-2"
            return page

        def get_message(self, message_id):
            attachment_id = "bad" if message_id == "bad-message" else "good"
            return {"payload": {"parts": [{
                "partId": "csv-1",
                "filename": f"{message_id}.csv",
                "mimeType": "text/csv",
                "body": {"attachmentId": attachment_id},
            }]}}

    gmail = MultiPageGmail()
    client, settings = make_app(tmp_path, MemorySecretStore(), gmail)
    with client:
        response = client.post("/api/gmail/sync", json={})
        assert response.status_code == 200, response.text
        assert response.json()["scanned_messages"] == 2
        assert response.json()["new_attachments"] == 2
        assert response.json()["created_transactions"] == 1
        assert response.json()["failures"] == 1
        assert response.json()["truncated"] == 0
        assert gmail.page_tokens == [None, "page-2"]

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 2
        assert session.scalar(select(func.count()).select_from(FinanceTransaction)) == 1
        failed_finance_jobs = session.scalars(select(ImportJob).where(
            ImportJob.target_module == "finance", ImportJob.status == "failed"
        )).all()
        assert len(failed_finance_jobs) == 1
        assert failed_finance_jobs[0].document_id is not None
    engine.dispose()


def test_oversized_gmail_attachment_is_recorded_without_blocking_sync(tmp_path):
    class OversizeGmail(FakeGmail):
        def __init__(self):
            super().__init__()
            self.attachments = {"large": b"oversized"}

        def get_message(self, message_id):
            return {"payload": {"parts": [{
                "partId": "pdf-1",
                "filename": "large.pdf",
                "mimeType": "application/pdf",
                "body": {"attachmentId": "large"},
            }]}}

    gmail = OversizeGmail()
    client, settings = make_app(tmp_path, MemorySecretStore(), gmail, max_upload_bytes=4)
    with client:
        response = client.post("/api/gmail/sync", json={})
        assert response.status_code == 200, response.text
        assert response.json()["failures"] == 1
        assert response.json()["truncated"] == 0
        jobs = client.get("/api/jobs").json()
        assert any(job["status"] == "failed" and job["summary"] == "Gmail 附件超過上傳大小限制" for job in jobs)

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        state = session.get(GmailSyncState, "gmail")
        assert state.history_id == "100"
        assert state.full_sync_in_progress is False
    engine.dispose()


def test_gmail_pdf_password_instructions_are_fetched_transiently_and_redacted(tmp_path):
    gmail = FakeGmail()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.encrypt("678919840302")
    encrypted_pdf = BytesIO()
    writer.write(encrypted_pdf)
    gmail.attachments["att-pdf"] = encrypted_pdf.getvalue()
    instruction_body = (
        "密碼規則：身分證末四碼加出生年月日 YYYYMMDD。\n"
        "身分證字號 A123456789，生日 19840302，帳號 987654321。"
    )
    body_data = base64.urlsafe_b64encode(instruction_body.encode()).decode().rstrip("=")

    def message_with_email_context(message_id):
        message = FakeGmail.get_message(gmail, message_id)
        message["payload"]["headers"] = [
            {"name": "Subject", "value": "密碼說明 - 合成帳單"},
            {"name": "From", "value": "Synthetic Bank <statements@example.test>"},
        ]
        message["payload"]["parts"].insert(0, {
            "mimeType": "text/plain",
            "headers": [{"name": "Content-Type", "value": "text/plain; charset=UTF-8"}],
            "body": {"data": body_data},
        })
        return message

    gmail.get_message = message_with_email_context
    rule = PasswordRule.model_validate({
        "version": 1,
        "status": "resolved",
        "candidates": [{"parts": [
            {"source": "national_id", "transform": "suffix", "start": None, "length": 4, "date_format": None, "case": "upper"},
            {"source": "birthday", "transform": "date_format", "start": None, "length": None, "date_format": "YYYYMMDD", "case": "preserve"},
        ], "separator": ""}],
    })
    interpreter = FakeInterpreter(rule)
    vault = MemorySecretStore()
    client, settings = make_app(tmp_path, vault, gmail, interpreter)

    with client:
        member = client.post("/api/security/profiles", json={
            "display_name": "Synthetic Member",
            "national_id": "A123456789",
            "birthday": "1984-03-02",
        }).json()
        profile = client.post("/api/security/document-profiles", json={
            "display_name": "Synthetic Statement",
            "institution": "Synthetic Bank",
            "secret_profile_id": member["id"],
        }).json()
        synced = client.post("/api/gmail/sync", json={})
        assert synced.status_code == 200, synced.text
        document = next(row for row in client.get("/api/documents").json() if row["filename"] == "statement.pdf")

        preview = client.post(f"/api/documents/{document['id']}/preview", json={
            "document_security_profile_id": profile["id"],
            "allow_ai_analysis": True,
        })
        assert preview.status_code == 200, preview.text
        assert not PdfReader(BytesIO(preview.content)).is_encrypted

    assert len(interpreter.calls) == 1
    instruction, context = interpreter.calls[0]
    assert "身分證末四碼" in instruction
    assert "YYYYMMDD" in instruction
    assert all(secret not in instruction for secret in (
        "A123456789", "19840302", "987654321", "statements@example.test"
    ))
    assert context == {"institution": "Synthetic Bank", "document_type": "PDF statement"}
    engine = make_engine(settings.database_url)
    db_bytes = (tmp_path / "gmail-test.db").read_bytes()
    assert "密碼規則".encode("utf-8") not in db_bytes
    assert b"statements@example.test" not in db_bytes
    engine.dispose()
