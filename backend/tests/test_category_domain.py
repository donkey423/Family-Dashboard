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
