import json

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
import pytest


def test_document_source_migration_preserves_existing_local_documents(tmp_path):
    database_file = tmp_path / "migration.db"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_file.as_posix()}")

    command.upgrade(config, "0001_initial")
    engine = create_engine(f"sqlite:///{database_file.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO documents (
                id, sha256, filename, content_type, size_bytes, storage_key, created_at
            ) VALUES (
                'doc-1', 'a', 'receipt.pdf', 'application/pdf', 12, 'aa/a.pdf', '2026-09-23 00:00:00'
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO finance_transactions (
                id, source_document_id, row_hash, transaction_date, description,
                amount, currency, raw_json, created_at
            ) VALUES (
                'transaction-1', 'doc-1', 'b', '2026-09-23', 'Groceries',
                -12.50, 'TWD', '{}', '2026-09-23 00:00:00'
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO import_jobs (
                id, document_id, source_type, target_module, status, summary, created_at
            ) VALUES (
                'job-1', 'doc-1', 'csv', 'finance', 'completed', '新增 1 筆交易', '2026-09-23 00:00:00'
            )
            """
        ))

    command.upgrade(config, "0002_document_sources")

    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO documents (
                id, sha256, filename, content_type, size_bytes, storage_key,
                source_type, source_reference, created_at
            ) VALUES (
                'remote-doc', 'c', 'statement.pdf', 'application/pdf', 12, NULL,
                'gmail_attachment', '{"message_id":"message-1","attachment_id":"attachment-1"}',
                '2026-09-23 00:00:00'
            )
            """
        ))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        document_source = connection.execute(text(
            """
            SELECT source_key, storage_key, source_type, source_reference,
                   availability_status, last_verified_at
            FROM document_sources WHERE document_id = 'doc-1'
            """
        )).one()
        remote_source = connection.execute(text(
            """
            SELECT source_key, storage_key, source_type, source_reference,
                   availability_status, last_verified_at
            FROM document_sources WHERE document_id = 'remote-doc'
            """
        )).one()
        transaction_count = connection.scalar(text("SELECT COUNT(*) FROM finance_transactions WHERE source_document_id = 'doc-1'"))
        job_count = connection.scalar(text("SELECT COUNT(*) FROM import_jobs WHERE document_id = 'doc-1'"))
    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO document_sources (
                id, document_id, source_type, source_key, source_reference,
                storage_key, availability_status, last_verified_at, created_at
            ) VALUES (
                'local-copy', 'remote-doc', 'local_file', 'aa/statement.pdf', NULL,
                'aa/statement.pdf', 'available', '2026-09-24 00:00:00', '2026-09-24 00:00:00'
            )
            """
        ))
        remote_source_count = connection.scalar(text(
            "SELECT COUNT(*) FROM document_sources WHERE document_id = 'remote-doc'"
        ))
    columns = {column["name"]: column for column in inspect(engine).get_columns("documents")}
    assert document_source == ("aa/a.pdf", "aa/a.pdf", "local_file", None, "unknown", None)
    assert remote_source[:3] == ("legacy:remote-doc", None, "gmail_attachment")
    assert json.loads(remote_source[3]) == {"message_id": "message-1", "attachment_id": "attachment-1"}
    assert remote_source[4:] == ("unknown", None)
    assert transaction_count == 1
    assert job_count == 1
    assert "storage_key" not in columns
    assert "source_type" not in columns
    assert "source_reference" not in columns
    assert remote_source_count == 2
    engine.dispose()


def test_source_migration_refuses_downgrade_when_a_document_has_multiple_sources(tmp_path):
    database_file = tmp_path / "migration.db"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_file.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_file.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO documents (id, sha256, filename, content_type, size_bytes, created_at)
            VALUES ('doc-1', 'a', 'receipt.pdf', 'application/pdf', 12, '2026-09-23 00:00:00')
            """
        ))
        connection.execute(text(
            """
            INSERT INTO document_sources (
                id, document_id, source_type, source_key, availability_status, created_at
            ) VALUES
                ('source-1', 'doc-1', 'local_file', 'local-1', 'available', '2026-09-23 00:00:00'),
                ('source-2', 'doc-1', 'gmail_attachment', 'gmail-1', 'available', '2026-09-23 00:00:00')
            """
        ))

    with pytest.raises(RuntimeError, match="zero or multiple source records"):
        command.downgrade(config, "0002_document_sources")

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM document_sources")) == 2
    engine.dispose()


def test_source_migration_downgrade_restores_a_single_legacy_source(tmp_path):
    database_file = tmp_path / "migration.db"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_file.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_file.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO documents (id, sha256, filename, content_type, size_bytes, created_at)
            VALUES ('doc-1', 'a', 'receipt.pdf', 'application/pdf', 12, '2026-09-23 00:00:00')
            """
        ))
        connection.execute(text(
            """
            INSERT INTO document_sources (
                id, document_id, source_type, source_key, source_reference,
                storage_key, availability_status, created_at
            ) VALUES (
                'source-1', 'doc-1', 'local_file', 'aa/a.pdf', NULL,
                'aa/a.pdf', 'available', '2026-09-23 00:00:00'
            )
            """
        ))

    command.downgrade(config, "0002_document_sources")

    with engine.connect() as connection:
        restored = connection.execute(text(
            "SELECT source_type, source_reference, storage_key FROM documents WHERE id = 'doc-1'"
        )).one()
    assert restored == ("local_file", None, "aa/a.pdf")
    assert "document_sources" not in inspect(engine).get_table_names()
    engine.dispose()


def test_secret_profiles_migration_stores_credential_references_only(tmp_path):
    database_file = tmp_path / "secret-profiles.db"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_file.as_posix()}")
    command.upgrade(config, "0003_document_source_records")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_file.as_posix()}")
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("secret_profiles")}
    assert columns == {
        "id",
        "display_name",
        "national_id_credential_ref",
        "birthday_credential_ref",
        "created_at",
        "updated_at",
    }
    assert {column["name"] for column in inspector.get_columns("document_security_profiles")} == {
        "id",
        "display_name",
        "institution",
        "sender_pattern",
        "secret_profile_id",
        "created_at",
    }
    assert {column["name"] for column in inspector.get_columns("password_rules")} == {
        "id",
        "document_security_profile_id",
        "rule_version",
        "instruction_fingerprint",
        "rule_json",
        "verified_at",
        "created_at",
    }
    assert {column["name"] for column in inspector.get_columns("ai_provider_profiles")} == {
        "id",
        "provider",
        "model",
        "api_key_credential_ref",
        "created_at",
        "updated_at",
    }
    assert "api_key" not in {column["name"] for column in inspector.get_columns("ai_provider_profiles")}
    assert {column["name"] for column in inspector.get_columns("gmail_connections")} == {
        "id",
        "client_config_credential_ref",
        "token_credential_ref",
        "auto_sync_enabled",
        "next_scheduled_sync_at",
        "created_at",
        "updated_at",
    }
    assert "client_secret" not in {column["name"] for column in inspector.get_columns("gmail_connections")}
    assert "refresh_token" not in {column["name"] for column in inspector.get_columns("gmail_connections")}
    assert {column["name"] for column in inspector.get_columns("gmail_sync_state")} == {
        "id",
        "history_id",
        "full_sync_in_progress",
        "full_sync_query",
        "full_sync_page_token",
        "full_sync_baseline_history_id",
        "status",
        "last_attempt_at",
        "last_successful_at",
        "last_error_summary",
        "updated_at",
    }
    engine.dispose()
