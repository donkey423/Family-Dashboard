import shutil

from fastapi.testclient import TestClient

from family_finance_hub.config import Settings
from family_finance_hub.main import create_app


def make_settings(root):
    return Settings(
        database_url=f"sqlite:///{(root / 'family.db').as_posix()}",
        storage_root=root / "documents",
    )


def test_database_and_document_storage_restore_together(tmp_path):
    source_root = tmp_path / "source"
    backup_root = tmp_path / "backup"
    restore_root = tmp_path / "restored"
    original_settings = make_settings(source_root)
    original_pdf = b"synthetic backup rehearsal PDF bytes"
    csv_content = b"date,description,amount\n2026-09-01,Backup rehearsal,-5.00\n"

    with TestClient(create_app(original_settings, create_schema=True)) as client:
        uploaded = client.post("/api/documents", files={
            "file": ("rehearsal.pdf", original_pdf, "application/pdf"),
        })
        assert uploaded.status_code == 200
        imported = client.post("/api/finance/import-csv", files={
            "file": ("rehearsal.csv", csv_content, "text/csv"),
        })
        assert imported.status_code == 200

    backup_root.mkdir()
    shutil.copy2(source_root / "family.db", backup_root / "family.db")
    shutil.copytree(original_settings.storage_root, backup_root / "documents")
    restore_root.mkdir()
    shutil.copy2(backup_root / "family.db", restore_root / "family.db")
    shutil.copytree(backup_root / "documents", restore_root / "documents")

    with TestClient(create_app(make_settings(restore_root))) as restored:
        documents = restored.get("/api/documents").json()
        pdf = next(document for document in documents if document["filename"] == "rehearsal.pdf")
        assert restored.get(f"/api/documents/{pdf['id']}/content").content == original_pdf
        assert restored.get("/api/dashboard").json()["transaction_count"] == 1
        assert restored.get("/api/search", params={"q": "Backup rehearsal"}).json()["transactions"]
