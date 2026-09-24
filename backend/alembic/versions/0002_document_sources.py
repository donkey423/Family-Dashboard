"""Allow documents to reference local or remote content sources."""
from alembic import op
import sqlalchemy as sa

revision = "0002_document_sources"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("source_type", sa.String(32), server_default="local_file", nullable=False),
    )
    op.add_column("documents", sa.Column("source_reference", sa.JSON(), nullable=True))
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column("storage_key", existing_type=sa.String(512), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    remote_documents = connection.execute(sa.text(
        "SELECT COUNT(*) FROM documents WHERE source_type != 'local_file' OR storage_key IS NULL"
    )).scalar_one()
    if remote_documents:
        raise RuntimeError("Cannot remove remote document sources while such documents exist")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column("storage_key", existing_type=sa.String(512), nullable=False)
        batch_op.drop_column("source_reference")
        batch_op.drop_column("source_type")
