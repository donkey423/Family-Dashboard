"""Create shared documents, jobs, and finance tables."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"], unique=True)
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("target_module", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "finance_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("row_hash", name="uq_finance_transaction_row_hash"),
    )
    op.create_index("ix_finance_transactions_source_document_id", "finance_transactions", ["source_document_id"])
    op.create_index("ix_finance_transactions_row_hash", "finance_transactions", ["row_hash"])


def downgrade() -> None:
    op.drop_index("ix_finance_transactions_row_hash", table_name="finance_transactions")
    op.drop_index("ix_finance_transactions_source_document_id", table_name="finance_transactions")
    op.drop_table("finance_transactions")
    op.drop_table("import_jobs")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_table("documents")
