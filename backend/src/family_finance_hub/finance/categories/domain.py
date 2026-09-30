from dataclasses import dataclass
from decimal import Decimal
import unicodedata


DEFAULT_CATEGORIES = (
    ("food", "餐飲"), ("groceries", "日常採買"), ("transport", "交通"),
    ("shopping", "購物"), ("home", "居家／水電通訊"), ("family", "家庭／育兒"),
    ("health", "醫療／健康"), ("entertainment", "娛樂／訂閱"), ("travel", "旅遊"),
    ("education", "教育"), ("finance", "金融／手續費／保險"),
    ("uncategorized", "未分類"), ("income", "收入"), ("transfer", "轉帳／信用卡繳款"),
)
PROTECTED_CODES = frozenset(("uncategorized", "income", "transfer"))
EXPENSE_KINDS = frozenset(("purchase", "fee", "interest", "refund"))


def normalize_merchant(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).upper()


def expense_value(amount: Decimal, statement_id: str | None, kind: str | None) -> Decimal:
    if statement_id is not None:
        return -amount if kind in EXPENSE_KINDS else Decimal("0")
    return -amount if amount < 0 else Decimal("0")


def is_consumption(amount: Decimal, statement_id: str | None, kind: str | None) -> bool:
    return kind in EXPENSE_KINDS if statement_id is not None else amount < 0


@dataclass(frozen=True)
class Category:
    id: str
    code: str
    name: str
    sort_order: int


@dataclass(frozen=True)
class Rule:
    id: str
    category_id: str
    match_type: str
    pattern: str
    priority: int


@dataclass(frozen=True)
class Resolution:
    category: Category
    source: str
    merchant_key: str


class CategoryResolver:
    def __init__(self, categories: list[Category], rules: list[Rule]):
        self.categories = {item.id: item for item in categories}
        self.codes = {item.code: item for item in categories}
        active_rules = [item for item in rules if item.category_id in self.categories]
        self.exact = {item.pattern: item for item in sorted(active_rules, key=lambda item: item.id, reverse=True) if item.match_type == "normalized_exact"}
        self.contains = sorted(
            (item for item in active_rules if item.match_type == "contains"),
            key=lambda item: (-item.priority, -len(item.pattern), item.id),
        )

    def resolve(self, description: str, amount: Decimal, statement_id: str | None, kind: str | None, override: str | None = None) -> Resolution:
        key = normalize_merchant(description)
        if override in self.categories:
            return Resolution(self.categories[override], "override", key)
        exact = self.exact.get(key)
        if exact:
            return Resolution(self.categories[exact.category_id], "exact_rule", key)
        for rule in self.contains:
            if rule.pattern in key:
                return Resolution(self.categories[rule.category_id], "contains_rule", key)
        code = (
            "transfer" if statement_id is not None and kind == "payment" else
            "finance" if statement_id is not None and kind in ("fee", "interest") else
            "income" if statement_id is None and amount >= 0 else "uncategorized"
        )
        category = self.codes.get(code, self.codes["uncategorized"])
        return Resolution(category, "uncategorized" if code == "uncategorized" else "system", key)
