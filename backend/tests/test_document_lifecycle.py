from sqlalchemy import event, func, select
import pytest

from family_finance_hub.models import DocumentSourceRecord, FinanceTransaction, ImportJob
from test_imports import make_client
from test_gmail_sync import FakeGmail, MemorySecretStore, make_app


CSV = b"date,description,amount,currency\n2026-09-01,Target purchase,-245,TWD\n2026-09-02,Target refund,20,TWD\n2026-08-01,Target overseas,-12.50,USD\n"


def upload(client, content=CSV, filename="target.csv", finance=True):
    response = client.post("/api/finance/import-csv" if finance else "/api/documents", files={"file": (filename, content)})
    assert response.status_code == 200, response.text
    return response.json()["document_id" if finance else "id"]


def impact(client, document_id):
    response = client.get(f"/api/documents/{document_id}/import-impact")
    assert response.status_code == 200
    return response.json()


def change(client, document_id, action="revoke", token=None, reason="Wrong statement"):
    token = token or impact(client, document_id)["impact_token"]
    return client.post(f"/api/documents/{document_id}/{action}", json={"impact_token": token, "reason": reason})


def test_revoke_restore_scopes_queries_and_preserves_original_records(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        document_id = upload(client)
        # Same filename must not make this unrelated document part of the revocation.
        other_id = upload(client, b"date,description,amount,currency\n2026-09-03,Other purchase,-5,TWD\n")
        before = client.get("/api/finance/transactions").json()
        before_dashboard = client.get("/api/dashboard").json()
        preview = impact(client, document_id)
        assert preview["transaction_count"] == 3
        assert preview["currency_totals"] == [
            {"currency": "TWD", "income": "20.00", "expenses": "245.00", "net": "-225.00"},
            {"currency": "USD", "income": "0.00", "expenses": "12.50", "net": "-12.50"},
        ]
        result = change(client, document_id, token=preview["impact_token"])
        assert result.status_code == 200
        assert result.json()["changed"] is True
        assert result.json()["revoked_at"] is not None
        assert result.json()["revocation_reason"] == "Wrong statement"
        assert [row["id"] for row in client.get("/api/documents").json()] == [other_id]
        assert [row["id"] for row in client.get("/api/documents?state=revoked").json()] == [document_id]
        assert len(client.get("/api/documents?state=all").json()) == 2
        assert client.get("/api/dashboard").json() == {
            "transaction_count": 1,
            "currency_totals": [{"currency": "TWD", "income": "0.00", "expenses": "5.00", "net": "-5.00"}],
        }
        assert client.get("/api/finance/transactions?month=2026-08").json()["total"] == 0
        assert client.get("/api/finance/transactions?month=2026-09").json()["total"] == 1
        assert client.get("/api/search?q=Target%20purchase").json()["transactions"] == []
        assert client.get("/api/search?q=245").json()["transactions"] == []
        assert [row["id"] for row in client.get("/api/search?q=target.csv").json()["documents"]] == [other_id]
        assert client.get(f"/api/documents/{document_id}/content").content == CSV
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count(FinanceTransaction.id))) == 4
            assert session.scalar(select(func.count(DocumentSourceRecord.id))) == 2
        assert change(client, document_id, token=preview["impact_token"]).json()["changed"] is False
        restore_token = impact(client, document_id)["impact_token"]
        assert change(client, document_id, "restore", restore_token).json()["changed"] is True
        assert change(client, document_id, "restore", restore_token).json()["changed"] is False
        assert client.get("/api/finance/transactions").json() == before
        assert client.get("/api/dashboard").json() == before_dashboard
        assert impact(client, document_id)["revocation_reason"] is None
        jobs = [job for job in client.get("/api/jobs").json() if job["source_type"] == "document_lifecycle"]
        assert [job["status"] for job in jobs] == ["restored", "revoked"]
        assert all(job["document_id"] == document_id and "Wrong statement" in job["summary"] for job in jobs)


@pytest.mark.parametrize("filename,content", [("only.pdf", b"synthetic-pdf"), ("invalid.csv", b"description\nmissing amount\n")])
def test_zero_transaction_document_can_be_revoked_and_restored(tmp_path, filename, content):
    client, _ = make_client(tmp_path)
    with client:
        document_id = upload(client, content, filename, finance=False)
        if filename.endswith(".csv"):
            assert client.post("/api/finance/import-csv", files={"file": (filename, content)}).status_code == 400
        assert impact(client, document_id)["transaction_count"] == 0
        assert change(client, document_id).status_code == 200
        assert change(client, document_id, "restore").status_code == 200
        assert client.get("/api/dashboard").json()["transaction_count"] == 0


def test_same_bytes_manual_upload_does_not_restore_or_reparse(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        document_id = upload(client)
        assert change(client, document_id).status_code == 200
        for route in ("/api/documents", "/api/finance/import-csv"):
            response = client.post(route, files={"file": ("renamed.csv", CSV)})
            assert response.status_code == 200
            assert response.json()["skipped_revoked"] is True
        assert client.get("/api/dashboard").json()["transaction_count"] == 0
        assert change(client, document_id, "restore").status_code == 200
        assert upload(client) == document_id
        assert client.get("/api/dashboard").json()["transaction_count"] == 3


def test_revoked_invalid_csv_is_not_reparsed(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        content = b"not a valid csv"
        document_id = upload(client, content, finance=False)
        assert change(client, document_id).status_code == 200
        response = client.post("/api/finance/import-csv", files={"file": ("target.csv", content)})
        assert response.status_code == 200
        assert response.json()["skipped_revoked"] is True


def test_stale_preview_and_other_document_token_are_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        document_id = upload(client, finance=False)
        token = impact(client, document_id)["impact_token"]
        upload(client)
        assert change(client, document_id, token=token).status_code == 409
        assert impact(client, document_id)["revoked_at"] is None
        token = impact(client, document_id)["impact_token"]
        other_id = upload(client, b"other", "other.pdf", finance=False)
        assert change(client, other_id, token=token).status_code == 409
        assert change(client, document_id, token=token).status_code == 200
        assert change(client, document_id, "restore").status_code == 200
        assert change(client, document_id, token=token).status_code == 409


@pytest.mark.parametrize("action", ["revoke", "restore"])
def test_audit_failure_rolls_back_state_and_totals(tmp_path, action):
    client, _ = make_client(tmp_path)
    with client:
        document_id = upload(client)
        if action == "restore":
            assert change(client, document_id).status_code == 200
        before = impact(client, document_id)
        totals = client.get("/api/dashboard").json()

        def fail_audit(_mapper, _connection, job):
            if job.source_type == "document_lifecycle":
                raise RuntimeError("synthetic audit failure")

        event.listen(ImportJob, "before_insert", fail_audit)
        try:
            with pytest.raises(RuntimeError, match="synthetic audit failure"):
                change(client, document_id, action)
        finally:
            event.remove(ImportJob, "before_insert", fail_audit)
        assert impact(client, document_id) == before
        assert client.get("/api/dashboard").json() == totals


def test_lifecycle_input_validation(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        assert client.get("/api/documents/missing/import-impact").status_code == 404
        assert change(client, "missing", token="a" * 64).status_code == 404
        document_id = upload(client)
        assert client.post(f"/api/documents/{document_id}/revoke", json={}).status_code == 422
        assert change(client, document_id, reason="a" * 201).status_code == 422
        assert client.get("/api/documents?state=unknown").status_code == 422


def test_gmail_existing_and_new_sources_of_revoked_content_stay_suppressed(tmp_path):
    class RepeatedGmail(FakeGmail):
        new_message = False

        def list_history(self, start_history_id, page_token=None):
            return {"history": [{"messagesAdded": [{"message": {"id": "message-2" if self.new_message else "message-1"}}]}], "historyId": "130"}

    gmail = RepeatedGmail()
    client, _ = make_app(tmp_path, MemorySecretStore(), gmail)
    with client:
        assert client.post("/api/gmail/sync", json={}).json()["created_transactions"] == 1
        docs = client.get("/api/documents").json()
        for doc in docs:
            assert change(client, doc["id"]).status_code == 200
        for new_message in (False, True):
            gmail.new_message = new_message
            result = client.post("/api/gmail/sync", json={})
            assert result.status_code == 200
            assert result.json()["skipped_revoked"] == 2
            assert result.json()["created_transactions"] == result.json()["new_attachments"] == result.json()["failures"] == 0
        assert client.get("/api/dashboard").json()["transaction_count"] == 0
        assert client.get("/api/documents").json() == []
        assert len(client.get("/api/documents?state=revoked").json()) == 2
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count(DocumentSourceRecord.id))) == 4
        pdf_id = next(doc["id"] for doc in docs if doc["filename"].endswith(".pdf"))
        assert client.post(f"/api/documents/{pdf_id}/save-local").status_code == 200
        assert impact(client, pdf_id)["revoked_at"] is not None
        for doc in docs:
            assert change(client, doc["id"], "restore").status_code == 200
        assert client.post("/api/gmail/sync", json={}).json()["created_transactions"] == 0
        assert client.get("/api/dashboard").json()["transaction_count"] == 1


def test_gmail_never_creates_transactions_for_a_document_revoked_before_parsing(tmp_path):
    gmail = FakeGmail()
    client, _ = make_app(tmp_path, MemorySecretStore(), gmail)
    with client:
        document_id = upload(client, gmail.csv, "unparsed.csv", finance=False)
        assert change(client, document_id).status_code == 200
        result = client.post("/api/gmail/sync", json={}).json()
        assert result["skipped_revoked"] == 1
        assert result["created_transactions"] == 0
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count(FinanceTransaction.id))) == 0
        assert change(client, document_id, "restore").status_code == 200
        assert client.get("/api/dashboard").json()["transaction_count"] == 0
        assert upload(client, gmail.csv) == document_id
        assert client.get("/api/dashboard").json()["transaction_count"] == 1
