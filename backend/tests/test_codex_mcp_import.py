from json import dumps

from fastapi.testclient import TestClient
from sqlalchemy import select

from family_finance_hub.config import Settings
from family_finance_hub.database import make_engine, make_session_factory
from family_finance_hub.main import create_app
from family_finance_hub.models import Document, DocumentSourceRecord, ImportJob


def make_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        storage_root=tmp_path / "documents",
    )
    return TestClient(create_app(settings, create_schema=True)), settings


def attachment_form(content=b"synthetic-pdf"):
    return {
        "files": {"file": ("statement.pdf", content, "application/pdf")},
        "data": {
            "message_id": "message-123",
            "attachment_id": "attachment-456",
            "subject": "信用卡電子帳單",
            "sender": "billing@bank.example",
            "password_instruction": "PDF 密碼為 A123456789，英文字母請用大寫。",
        },
    }


def test_codex_mcp_import_is_local_idempotent_and_masks_password_context(tmp_path):
    client, settings = make_client(tmp_path)
    with client:
        first = client.post("/api/integrations/codex-mcp/gmail/import", **attachment_form())
        second = client.post("/api/integrations/codex-mcp/gmail/import", **attachment_form())
        status = client.get("/api/integrations/codex-mcp/status")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["document_id"] == second.json()["document_id"]
    assert first.json()["duplicate"] is False
    assert first.json()["instruction_detected"] is True
    assert second.json()["duplicate"] is True
    assert second.json()["duplicate_source"] is True
    assert status.json()["mode"] == "codex_mcp"
    assert status.json()["legacy_gmail_oauth_enabled"] is False
    assert status.json()["last_import_at"] is not None

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        documents = session.scalars(select(Document)).all()
        sources = session.scalars(select(DocumentSourceRecord)).all()
        jobs = session.scalars(select(ImportJob).order_by(ImportJob.created_at)).all()
        assert len(documents) == 1
        assert {source.source_type for source in sources} == {"local_file", "codex_mcp_gmail"}
        mcp_source = next(source for source in sources if source.source_type == "codex_mcp_gmail")
        serialized_reference = dumps(mcp_source.source_reference, ensure_ascii=False)
        assert "A123456789" not in serialized_reference
        assert "message-123" not in mcp_source.source_key
        assert "attachment-456" not in mcp_source.source_key
        assert [job.source_type for job in jobs] == ["codex_mcp", "codex_mcp"]
    engine.dispose()
    assert b"A123456789" not in (tmp_path / "test.db").read_bytes()


def test_codex_mcp_rejects_reused_source_identity_with_different_bytes(tmp_path):
    client, settings = make_client(tmp_path)
    with client:
        assert client.post("/api/integrations/codex-mcp/gmail/import", **attachment_form()).status_code == 201
        collision = client.post(
            "/api/integrations/codex-mcp/gmail/import",
            **attachment_form(b"different-pdf"),
        )

    assert collision.status_code == 409
    assert collision.json()["detail"] == "來源識別碼已對應不同內容"
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1
        assert len(session.scalars(select(ImportJob)).all()) == 1
    engine.dispose()


def test_legacy_gmail_oauth_endpoints_are_disabled_by_default(tmp_path):
    client, _settings = make_client(tmp_path)
    with client:
        status = client.get("/api/gmail/status")
        authorize = client.post("/api/gmail/authorize")

    assert status.status_code == 410
    assert authorize.status_code == 410
    assert "Codex MCP" in status.json()["detail"]
