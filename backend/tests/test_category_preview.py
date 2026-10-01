import importlib.util
import os
import csv
from decimal import Decimal
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from family_finance_hub.models import Document, utc_now


spec = importlib.util.spec_from_file_location(
    "category_preview", Path(__file__).resolve().parents[2] / "scripts" / "category_preview.py"
)
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


def test_preview_directory_rejects_other_data_and_outside_paths(tmp_path):
    root = Path(preview.__file__).resolve().parents[1]
    assert preview.preview_directory().name == "category-preview"
    assert preview.preview_directory(root / "data" / "category-preview-new").name == "category-preview-new"
    for value in (tmp_path, root / "data", root / "data" / "documents", root / "data" / "category-preview" / "child"):
        with pytest.raises(ValueError):
            preview.preview_directory(value)


def test_preview_migration_overrides_ambient_database_and_restores_environment(tmp_path, monkeypatch):
    untouched = tmp_path / "must-not-touch.db"
    ambient = f"sqlite:///{untouched.as_posix()}"
    monkeypatch.setenv("FAMILY_FINANCE_HUB_DATABASE_URL", ambient)
    monkeypatch.setattr(preview, "preview_directory", lambda value: tmp_path / "isolated")
    app = preview.create_preview_app()
    assert os.environ["FAMILY_FINANCE_HUB_DATABASE_URL"] == ambient
    assert not untouched.exists()
    with TestClient(app) as client:
        rows = client.get("/api/finance/transactions").json()
        assert rows["total"] == 18
        by_description = {row["description"]: row for row in rows["items"]}
        assert by_description["電子書"]["category_code"] == "books"
        assert by_description["保險費"]["category_code"] == "insurance"
        assert by_description["7-ELEVEN"]["category_code"] == "uncategorized"
        document_id = rows["items"][0]["source_document_id"]
        content = client.get(f"/api/documents/{document_id}/content").content.decode("utf-8")
        source = list(csv.DictReader(StringIO(content)))
        assert sorted((row["date"], row["description"], Decimal(row["amount"]), row["currency"]) for row in source) == sorted(
            (row["date"], row["description"], Decimal(row["amount"]), row["currency"]) for row in rows["items"])
    # Reopening never restores revoked test documents or duplicates existing rows.
    second = preview.create_preview_app()
    with TestClient(second) as client:
        assert client.get("/api/finance/transactions").json()["total"] == 18
        with second.state.session_factory() as session, session.begin():
            session.get(Document, document_id).revoked_at = utc_now()
    third = preview.create_preview_app()
    with TestClient(third) as client:
        assert client.get("/api/finance/transactions").json()["total"] == 0
