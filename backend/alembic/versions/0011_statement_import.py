"""Persist statement drafts and confirmed statement transaction identity."""

from alembic import op
import sqlalchemy as sa


revision = "0011_statement_import"
down_revision = "0010_workbook_export"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "statement_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bank_id", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("account_hint", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_statement_accounts_bank_id", "statement_accounts", ["bank_id"])

    op.create_table(
        "statements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("statement_account_id", sa.String(36), sa.ForeignKey("statement_accounts.id"), nullable=True),
        sa.Column("bank_id", sa.String(80), nullable=False),
        sa.Column("format_version", sa.String(40), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("parser_id", sa.String(80), nullable=True),
        sa.Column("parser_version", sa.String(40), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("reason_code", sa.String(300), nullable=True),
        sa.Column("statement_json", sa.JSON(), nullable=True),
        sa.Column("review_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", name="uq_statement_document_id"),
    )
    op.create_index("ix_statements_document_id", "statements", ["document_id"])
    op.create_index("ix_statements_statement_account_id", "statements", ["statement_account_id"])
    op.create_index("ix_statements_period_start", "statements", ["period_start"])
    op.create_index("ix_statements_status", "statements", ["status"])
    op.create_index(
        "uq_statements_imported_account_period",
        "statements",
        ["statement_account_id", "period_start", "period_end"],
        unique=True,
        sqlite_where=sa.text("status = 'imported'"),
    )

    with op.batch_alter_table("finance_transactions") as batch_op:
        batch_op.add_column(sa.Column("statement_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("posting_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("transaction_kind", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("statement_line_index", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_finance_transactions_statement_id", "statements", ["statement_id"], ["id"]
        )
        batch_op.create_index("ix_finance_transactions_statement_id", ["statement_id"])
        batch_op.create_unique_constraint(
            "uq_finance_transaction_statement_line", ["statement_id", "statement_line_index"]
        )


def downgrade() -> None:
    with op.batch_alter_table("finance_transactions") as batch_op:
        batch_op.drop_constraint("uq_finance_transaction_statement_line", type_="unique")
        batch_op.drop_index("ix_finance_transactions_statement_id")
        batch_op.drop_constraint("fk_finance_transactions_statement_id", type_="foreignkey")
        batch_op.drop_column("statement_line_index")
        batch_op.drop_column("transaction_kind")
        batch_op.drop_column("posting_date")
        batch_op.drop_column("statement_id")
    op.drop_index("uq_statements_imported_account_period", table_name="statements")
    op.drop_index("ix_statements_status", table_name="statements")
    op.drop_index("ix_statements_period_start", table_name="statements")
    op.drop_index("ix_statements_statement_account_id", table_name="statements")
    op.drop_index("ix_statements_document_id", table_name="statements")
    op.drop_table("statements")
    op.drop_index("ix_statement_accounts_bank_id", table_name="statement_accounts")
    op.drop_table("statement_accounts")
