"""Run category acceptance tests against synthetic data, never the live database."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
import uvicorn

from family_finance_hub.config import Settings
from family_finance_hub.documents.service import DocumentService
from family_finance_hub.main import create_app
from family_finance_hub.models import FinanceCategoryRule, FinanceTransaction, Statement
from family_finance_hub.security.secrets import SecretStoreUnavailable
from family_finance_hub.storage.local_filesystem import LocalFilesystemStorage


class DisabledPreviewSecrets:
    def get(self, reference):
        raise SecretStoreUnavailable("Secrets are disabled in the synthetic category preview")

    def set(self, reference, value):
        raise SecretStoreUnavailable("Secrets are disabled in the synthetic category preview")

    def delete(self, reference):
        raise SecretStoreUnavailable("Secrets are disabled in the synthetic category preview")


def create_preview_app():
    root = Path(__file__).resolve().parents[1]
    data = root / "data" / "category-preview"
    data.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{(data / 'synthetic.db').as_posix()}"
    config = Config(str(root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    settings = Settings(database_url=database_url, storage_root=data / "documents")
    app = create_app(settings, secret_store=DisabledPreviewSecrets())
    examples = [
        ("preview-01", "範例餐飲", "-1800", "food", "purchase", "TWD"),
        ("preview-02", "範例超市", "-1600", "groceries", "purchase", "TWD"),
        ("preview-03", "範例交通", "-1200", "transport", "purchase", "TWD"),
        ("preview-04", "範例商店", "-1000", "shopping", "purchase", "TWD"),
        ("preview-05", "範例水電", "-900", "home", "purchase", "TWD"),
        ("preview-06", "範例育兒", "-800", "family", "purchase", "TWD"),
        ("preview-07", "範例醫療", "-700", "health", "purchase", "TWD"),
        ("preview-08", "範例影音", "-600", "entertainment", "purchase", "TWD"),
        ("preview-09", "範例旅遊退款", "200", "travel", "refund", "TWD"),
        ("preview-10", "未整理商家 001", "-500", None, "purchase", "TWD"),
        ("preview-11", "範例餐飲", "100", "food", "refund", "TWD"),
        ("preview-12", "範例信用卡繳款", "8000", None, "payment", "TWD"),
        ("preview-13", "海外範例", "-25", "shopping", "purchase", "USD"),
    ]
    with app.state.session_factory() as session, session.begin():
        if session.scalar(select(FinanceTransaction.id).limit(1)) is None:
            content = ("date,description,amount,currency\n" + "\n".join(
                f"2026-09-15,{name},{amount},{currency}" for _, name, amount, _, _, currency in examples)).encode("utf-8")
            imported = DocumentService(LocalFilesystemStorage(settings.storage_root)).import_bytes(
                session, "分類驗證_合成資料.csv", content, "finance")
            statement_id = "preview-statement"
            session.add(Statement(id=statement_id, document_id=imported.document.id,
                bank_id="synthetic", format_version="preview", status="imported"))
            session.flush()
            for index, (key, name, amount, category, kind, currency) in enumerate(examples):
                session.add(FinanceTransaction(id=key, source_document_id=imported.document.id,
                    row_hash=key, transaction_date=date(2026, 9, 15), description=name,
                    amount=Decimal(amount), currency=currency, raw_json="{}",
                    statement_id=statement_id, statement_line_index=index, transaction_kind=kind))
                if category and not session.scalar(select(FinanceCategoryRule.id).where(
                        FinanceCategoryRule.normalized_pattern == name.upper())):
                    session.add(FinanceCategoryRule(id=f"preview-rule-{index}", category_id=category,
                        match_type="normalized_exact", normalized_pattern=name.upper(), priority=0, enabled=True))
                    session.flush()
    return app


if __name__ == "__main__":
    uvicorn.run(create_preview_app(), host="127.0.0.1", port=8030, access_log=False)
