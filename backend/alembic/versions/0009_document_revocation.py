"""Support reversible document import revocation."""

from alembic import op
import sqlalchemy as sa

revision = "0009_document_revocation"
down_revision = "0008_gmail_auto_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("revocation_reason", sa.String(200), nullable=True))
    op.add_column("documents", sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    # Old readers would silently count revoked transactions again.
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM documents WHERE revoked_at IS NOT NULL")):
        raise RuntimeError("Restore revoked documents before downgrading document revocation")
    op.drop_column("documents", "lifecycle_version")
    op.drop_column("documents", "revocation_reason")
    op.drop_column("documents", "revoked_at")
