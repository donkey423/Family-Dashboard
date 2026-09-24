"""Move document sources into one-to-many source records."""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0003_document_source_records"
down_revision = "0002_document_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_key", sa.String(512), nullable=False),
        sa.Column("source_reference", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("availability_status", sa.String(16), server_default="unknown", nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_type", "source_key", name="uq_document_source_identity"),
        sa.CheckConstraint(
            "availability_status IN ('available', 'unavailable', 'unknown')",
            name="ck_document_sources_availability_status",
        ),
    )
    op.create_index("ix_document_sources_document_id", "document_sources", ["document_id"])

    connection = op.get_bind()
    documents = sa.table(
        "documents",
        sa.column("id", sa.String(36)),
        sa.column("source_type", sa.String(32)),
        sa.column("source_reference", sa.JSON(none_as_null=True)),
        sa.column("storage_key", sa.String(512)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    source_records = sa.table(
        "document_sources",
        sa.column("id", sa.String(36)),
        sa.column("document_id", sa.String(36)),
        sa.column("source_type", sa.String(32)),
        sa.column("source_key", sa.String(512)),
        sa.column("source_reference", sa.JSON(none_as_null=True)),
        sa.column("storage_key", sa.String(512)),
        sa.column("availability_status", sa.String(16)),
        sa.column("last_verified_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    rows = connection.execute(sa.select(
        documents.c.id,
        documents.c.source_type,
        documents.c.source_reference,
        documents.c.storage_key,
        documents.c.created_at,
    )).mappings()
    op.bulk_insert(source_records, [
        {
            "id": str(uuid4()),
            "document_id": row["id"],
            "source_type": row["source_type"] or "local_file",
            "source_key": row["storage_key"] or f"legacy:{row['id']}",
            "source_reference": row["source_reference"],
            "storage_key": row["storage_key"],
            "availability_status": "unknown",
            "last_verified_at": None,
            "created_at": row["created_at"],
        }
        for row in rows
    ])

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("storage_key")
        batch_op.drop_column("source_reference")
        batch_op.drop_column("source_type")


def downgrade() -> None:
    connection = op.get_bind()
    invalid_document_count = connection.scalar(sa.text(
        """
        SELECT COUNT(*) FROM (
            SELECT d.id
            FROM documents AS d
            LEFT JOIN document_sources AS s ON s.document_id = d.id
            GROUP BY d.id
            HAVING COUNT(s.id) != 1
        )
        """
    ))
    if invalid_document_count:
        raise RuntimeError("Cannot downgrade while documents have zero or multiple source records")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("storage_key", sa.String(512), nullable=True))
        batch_op.add_column(sa.Column("source_reference", sa.JSON(none_as_null=True), nullable=True))
        batch_op.add_column(sa.Column(
            "source_type", sa.String(32), server_default="local_file", nullable=False
        ))

    documents = sa.table(
        "documents",
        sa.column("id", sa.String(36)),
        sa.column("source_type", sa.String(32)),
        sa.column("source_reference", sa.JSON(none_as_null=True)),
        sa.column("storage_key", sa.String(512)),
    )
    source_records = sa.table(
        "document_sources",
        sa.column("document_id", sa.String(36)),
        sa.column("source_type", sa.String(32)),
        sa.column("source_reference", sa.JSON(none_as_null=True)),
        sa.column("storage_key", sa.String(512)),
    )
    for row in connection.execute(sa.select(source_records)).mappings():
        connection.execute(
            sa.update(documents)
            .where(documents.c.id == row["document_id"])
            .values(
                source_type=row["source_type"],
                source_reference=row["source_reference"],
                storage_key=row["storage_key"],
            )
        )

    op.drop_index("ix_document_sources_document_id", table_name="document_sources")
    op.drop_table("document_sources")
