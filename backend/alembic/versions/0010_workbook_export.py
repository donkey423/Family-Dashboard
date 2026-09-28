"""Persist opt-in workbook projection and retry status."""

from alembic import op
import sqlalchemy as sa

revision = "0010_workbook_export"
down_revision = "0009_document_revocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbook_export_state",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("snapshot_hash", sa.String(64), nullable=True),
        sa.Column("output_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="never"),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(48), nullable=True),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("workbook_export_state")
