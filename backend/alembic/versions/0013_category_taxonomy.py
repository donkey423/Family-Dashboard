"""Split books and insurance; preserve custom names, references and transaction facts."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0013_category_taxonomy"
down_revision = "0012_transaction_categories"
branch_labels = None
depends_on = None

RENAMES = (
    ("food", "餐飲", "飲食"),
    ("entertainment", "娛樂／訂閱", "娛樂／數位服務"),
    ("education", "教育", "課程／教育"),
    ("finance", "金融／手續費／保險", "金融費用"),
)
OLD_ORDER = ("food", "groceries", "transport", "shopping", "home", "family", "health",
             "entertainment", "travel", "education", "finance", "uncategorized", "income", "transfer")
NEW_ORDER = OLD_ORDER[:9] + ("books", "education", "insurance") + OLD_ORDER[10:]


def change_defaults(connection, forward):
    for code, old, new in RENAMES:
        source, target = (old, new) if forward else (new, old)
        connection.execute(sa.text("UPDATE finance_categories SET display_name=:target WHERE code=:code AND is_system=1 AND display_name=:source"),
                           dict(code=code, source=source, target=target))
    source_order, target_order = (OLD_ORDER, NEW_ORDER) if forward else (NEW_ORDER, OLD_ORDER)
    for code in OLD_ORDER:
        connection.execute(sa.text("UPDATE finance_categories SET sort_order=:target WHERE code=:code AND is_system=1 AND sort_order=:source"),
                           dict(code=code, source=source_order.index(code), target=target_order.index(code)))


def upgrade():
    connection = op.get_bind()
    change_defaults(connection, True)
    for code, name in (("books", "圖書"), ("insurance", "保險")):
        connection.execute(sa.text("""INSERT INTO finance_categories
            (id,code,display_name,sort_order,is_system,is_active,created_at,updated_at)
            SELECT :code,:code,:name,:sort,1,1,:now,:now
            WHERE NOT EXISTS (SELECT 1 FROM finance_categories WHERE code=:code)"""),
            dict(code=code, name=name, sort=NEW_ORDER.index(code), now=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(" ")))


def downgrade():
    connection = op.get_bind()
    # Keep referenced or user-modified categories, even when the revision is rolled back.
    for code, name in (("books", "圖書"), ("insurance", "保險")):
        connection.execute(sa.text("""DELETE FROM finance_categories
            WHERE id=:code AND code=:code AND display_name=:name AND is_system=1 AND is_active=1 AND sort_order=:sort
            AND NOT EXISTS (SELECT 1 FROM finance_category_rules WHERE category_id=:code)
            AND NOT EXISTS (SELECT 1 FROM transaction_category_overrides WHERE category_id=:code)"""),
            dict(code=code, name=name, sort=NEW_ORDER.index(code)))
    change_defaults(connection, False)
