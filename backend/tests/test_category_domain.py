from decimal import Decimal
import random

import pytest

from family_finance_hub.finance.categories.domain import (
    Category, CategoryResolver, DEFAULT_CATEGORIES, Rule, expense_value, normalize_merchant,
)


@pytest.mark.parametrize("value,expected", [
    ("  café\t shop\n", "CAFÉ SHOP"), ("ＡＢＣ　１２３", "ABC 123"),
    ("Store 123", "STORE 123"), ("Store 124", "STORE 124"),
    ("%_\\中文 😀", "%_\\中文 😀"), ("", ""), ("A" * 500, "A" * 500),
])
def test_merchant_normalization(value, expected):
    assert normalize_merchant(value) == expected
    assert normalize_merchant(expected) == expected


def resolver(rules=()):
    return CategoryResolver([Category(code, code, name, index) for index, (code, name) in enumerate(DEFAULT_CATEGORIES)], list(rules))


def test_resolution_precedence_and_stable_ties():
    rules = [Rule("b", "shopping", "contains", "SHOP", 1),
             Rule("a", "food", "contains", "SHOP", 1),
             Rule("c", "travel", "contains", "ABC SHOP", 1),
             Rule("d", "health", "contains", "ABC", 2),
             Rule("e", "transport", "normalized_exact", "ABC SHOP", 0)]
    args = ("abc shop", Decimal("-12"), None, None)
    assert resolver(rules).resolve(*args, "family").source == "override"
    assert resolver(rules).resolve(*args).category.code == "transport"
    assert resolver(rules[:-1]).resolve(*args).category.code == "health"
    assert resolver(rules[:3]).resolve(*args).category.code == "travel"
    assert resolver(rules[:2]).resolve(*args).category.code == "food"
    assert resolver(rules).resolve(*args, "inactive").source == "exact_rule"


@pytest.mark.parametrize("amount,statement,kind,code,expense", [
    ("-50", None, None, "uncategorized", "50"), ("50", None, None, "income", "0"),
    ("0", None, None, "income", "0"), ("-50", "s", "purchase", "uncategorized", "50"),
    ("50", "s", "refund", "uncategorized", "-50"), ("-5", "s", "fee", "finance", "5"),
    ("-8", "s", "interest", "finance", "8"), ("500", "s", "payment", "transfer", "0"),
])
def test_shared_expense_semantics(amount, statement, kind, code, expense):
    amount = Decimal(amount)
    assert resolver().resolve("merchant", amount, statement, kind).category.code == code
    assert expense_value(amount, statement, kind) == Decimal(expense)


def test_generated_rules_are_order_independent_and_never_replace_overrides():
    rng = random.Random(423)
    codes = [code for code, _ in DEFAULT_CATEGORIES]
    for iteration in range(100):
        rules = [Rule(f"{index:03}", rng.choice(codes), rng.choice(("contains", "normalized_exact")),
                      rng.choice(("SHOP", "SHOP 123", "%_\\", "中文", "😀")), rng.randrange(-5, 6))
                 for index in range(rng.randrange(50))]
        description = rng.choice(("Shop 123", "ＳＨＯＰ 123", "%_\\ Shop", "中文 😀", "Store 124"))
        args = (description, Decimal(-iteration), None, None)
        expected = resolver(rules).resolve(*args)
        rng.shuffle(rules)
        assert resolver(rules).resolve(*args) == expected
        override = rng.choice(codes)
        assert resolver(rules).resolve(*args, override).category.code == override
        rules.append(Rule("future", "shopping", "normalized_exact", normalize_merchant(description), 10000))
        assert resolver(rules).resolve(*args, override).source == "override"
        assert resolver(rules).resolve(*args, override).category.code == override


def test_contains_patterns_are_literal_not_sql_wildcards():
    for pattern in ("%", "_", "\\"):
        rule = Rule("literal", "food", "contains", pattern, 0)
        assert resolver([rule]).resolve("Ordinary shop", Decimal("-1"), None, None).category.code == "uncategorized"
        assert resolver([rule]).resolve(f"Shop {pattern}", Decimal("-1"), None, None).category.code == "food"


@pytest.mark.parametrize("description,code", [
    ("ＵＢＥＲ　ＥＡＴＳ", "food"), ("Uber*Eats Taipei", "food"),
    ("Netflix WWW.NETFLIX.COM", "entertainment"), ("台灣高鐵 - 台北", "transport"),
    ("台北捷運", "transport"), ("停車費 - 車站", "transport"),
    ("電子書 - 平台", "books"), ("課程費 - 程式設計", "education"),
    ("保險費 - 定期保費", "insurance"), ("門診醫療費", "health"), ("航空機票 - 台北", "travel"),
])
def test_explicit_local_purpose_rules(description, code):
    result = resolver().resolve(description, Decimal("-100"), "s", "purchase")
    assert result.category.code == code and result.source == "builtin_rule"
    assert result.rule_id and result.reason


@pytest.mark.parametrize("description,code", [
    ("A- 臺北大眾捷運股份有限公司", "transport"),
    ("OPENAI *CHATGPT SUBSCR OPENAI.COM US", "entertainment"),
    ("A- １０１美食街", "food"), ("A- 三新奧特萊斯 林口Ⅰ館－餐飲", "food"),
    ("小島泰式料理", "food"), ("瑪莎拉印度餐廳－板橋店", "food"),
    ("阿義師的大茶壺茶餐廳", "food"), ("A- 洋城義大利餐酒館內湖店", "food"),
    ("永秦加油站", "transport"), ("高加加油站", "transport"),
    ("A- 車容坊元泰站－自助加油", "transport"), ("中油－基隆路站（Ｄ２１４４）", "transport"),
])
def test_statement_explicit_purposes_handle_bank_prefix_and_fullwidth(description, code):
    result = resolver().resolve(description, Decimal("-100"), "s", "purchase")
    assert (result.category.code, result.source) == (code, "builtin_rule")


def test_subscription_fee_and_refund_keep_their_semantics():
    description = "OPENAI *CHATGPT SUBSCR OPENAI.COM US"
    assert resolver().resolve(description, Decimal("-10"), "s", "fee").category.code == "finance"
    assert resolver().resolve(description, Decimal("100"), "s", "refund").source == "uncategorized"


@pytest.mark.parametrize("description", [
    "7-ELEVEN 001", "全家便利商店", "COSTCO", "蝦皮", "momo", "PChome", "百貨公司",
    "LINE PAY", "街口支付", "APPLE PAY", "APPLE.COM/BILL", "GOOGLE", "UBER", "NETFLIXBOOKSTORE",
    "電子書店旁便利商店", "SHOP NETFLIX", "國泰人壽", "保險費退款", "BOOKS", "",
    "樂購蝦皮-加油站模型", "樂購蝦皮-小島泰式料理食譜", "A- 全家便利商店－新店安和店",
    "悠遊卡自動加值─台北捷", "OPENAI *CHATGPT SUBSCR BOOKSTORE", "A- 臺北大眾捷運股份有限公司商店",
])
def test_ambiguous_merchants_and_false_keyword_matches_stay_unknown(description):
    assert resolver().resolve(description, Decimal("-100"), "s", "purchase").source == "uncategorized"


def test_builtin_precedence_disable_refunds_and_inactive_category():
    args = ("Netflix", Decimal("-100"), "s", "purchase")
    exact = Rule("exact", "travel", "normalized_exact", "NETFLIX", 0)
    contains = Rule("contains", "books", "contains", "NETFLIX", 0)
    assert resolver([exact, contains]).resolve(*args, "family").source == "override"
    assert resolver([exact, contains]).resolve(*args).source == "exact_rule"
    assert resolver([contains]).resolve(*args).source == "contains_rule"
    assert resolver().resolve("Netflix", Decimal("-5"), "s", "fee").category.code == "finance"
    assert resolver().resolve("Netflix", Decimal("100"), "s", "payment").category.code == "transfer"
    assert resolver().resolve("Netflix", Decimal("100"), None, None).category.code == "income"
    assert resolver().resolve("Netflix", Decimal("100"), "s", "refund").source == "uncategorized"
    assert resolver().resolve("Netflix", Decimal("-100"), "s", "unknown").source == "uncategorized"
    categories = list(resolver().categories.values())
    assert CategoryResolver(categories, [], builtin_enabled=False).resolve(*args).source == "uncategorized"
    assert CategoryResolver([item for item in categories if item.code != "entertainment"], []).resolve(*args).source == "uncategorized"
