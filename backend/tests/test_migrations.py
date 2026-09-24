from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


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

    command.upgrade(config, "head")

    with engine.connect() as connection:
        document = connection.execute(text(
            "SELECT storage_key, source_type, source_reference FROM documents WHERE id = 'doc-1'"
        )).one()
        transaction_count = connection.scalar(text("SELECT COUNT(*) FROM finance_transactions WHERE source_document_id = 'doc-1'"))
        job_count = connection.scalar(text("SELECT COUNT(*) FROM import_jobs WHERE document_id = 'doc-1'"))
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
        remote_document = connection.execute(text(
            "SELECT storage_key, source_type, source_reference FROM documents WHERE id = 'remote-doc'"
        )).one()
    columns = {column["name"]: column for column in inspect(engine).get_columns("documents")}
    assert document == ("aa/a.pdf", "local_file", None)
    assert transaction_count == 1
    assert job_count == 1
    assert columns["storage_key"]["nullable"] is True
    assert remote_document == (None, "gmail_attachment", '{"message_id":"message-1","attachment_id":"attachment-1"}')
    engine.dispose()
