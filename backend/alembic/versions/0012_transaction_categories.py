"""Add independent consumption categories without changing transaction identity."""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0012_transaction_categories"
down_revision = "0011_statement_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    categories = op.create_table(
        "finance_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "finance_category_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("finance_categories.id"), nullable=False),
        sa.Column("match_type", sa.String(24), nullable=False),
        sa.Column("normalized_pattern", sa.String(500), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("match_type", "normalized_pattern", name="uq_category_rule_pattern"),
        sa.CheckConstraint("match_type IN ('normalized_exact', 'contains')", name="ck_category_rule_type"),
    )
    op.create_index("ix_finance_category_rules_category_id", "finance_category_rules", ["category_id"])
    op.create_table(
        "transaction_category_overrides",
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("finance_transactions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("finance_categories.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transaction_category_overrides_category_id", "transaction_category_overrides", ["category_id"])
    seeds = (
        ("food", "餐飲"), ("groceries", "日常採買"), ("transport", "交通"),
        ("shopping", "購物"), ("home", "居家／水電通訊"), ("family", "家庭／育兒"),
        ("health", "醫療／健康"), ("entertainment", "娛樂／訂閱"), ("travel", "旅遊"),
        ("education", "教育"), ("finance", "金融／手續費／保險"),
        ("uncategorized", "未分類"), ("income", "收入"), ("transfer", "轉帳／信用卡繳款"),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(categories, [dict(id=code, code=code, display_name=name, sort_order=index, is_system=True, is_active=True, created_at=now, updated_at=now) for index, (code, name) in enumerate(seeds)])


def downgrade() -> None:
    op.drop_table("transaction_category_overrides")
    op.drop_table("finance_category_rules")
    op.drop_table("finance_categories")
