from datetime import date

import pytest

from family_finance_hub.finance.statements.normalization import normalize_statement
from family_finance_hub.finance.statements.taiwan_credit_cards import TaiwanCreditCardStatementParser


def test_ctbc_statement_is_parsed_and_reconciled():
    text = """
    115/09/06 0 37 0 0 0 +37
    115/08/16 115/08/17
    37 8224 TW
    eToro
    TWQR
    (02)2745-8080
    """

    result = TaiwanCreditCardStatementParser().parse(text, page_count=2)

    assert result.status == "parsed"
    assert result.statement is not None
    assert result.statement.bank_id == "ctbc"
    assert result.statement.period_start == date(2026, 8, 16)
    assert result.statement.period_end == date(2026, 9, 6)
    assert result.statement.account_hint == "****8224"
    assert len(result.statement.lines) == 1
    assert result.statement.lines[0].description == "eToro"
    assert result.statement.lines[0].amount == -37
    assert result.statement.reconciliation.status == "matched"


def test_ctbc_unicode_token_text_is_supported():
    text = """
    /UNIC0031/UNIC0031/UNIC0035/UNIC002F/UNIC0030/UNIC0039/UNIC002F/UNIC0030/UNIC0036 /UNIC0030 /UNIC0033/UNIC0037 /UNIC0030 /UNIC0030 /UNIC0030 /UNIC002B/UNIC0033/UNIC0037
    /UNIC0031/UNIC0031/UNIC0035/UNIC002F/UNIC0030/UNIC0038/UNIC002F/UNIC0031/UNIC0036 /UNIC0031/UNIC0031/UNIC0035/UNIC002F/UNIC0030/UNIC0038/UNIC002F/UNIC0031/UNIC0037
    /UNIC0033/UNIC0037 /UNIC0038/UNIC0032/UNIC0032/UNIC0034 /UNIC0054/UNIC0057
    /UNIC0065/UNIC0054/UNIC006F/UNIC0072/UNIC006F
    /UNIC0054/UNIC0057/UNIC0051/UNIC0052
    /UNIC0030/UNIC0032/UNIC002D/UNIC0032/UNIC0037/UNIC0034/UNIC0035/UNIC002D/UNIC0038/UNIC0030/UNIC0038/UNIC0030
    """

    result = TaiwanCreditCardStatementParser().parse(text, page_count=2)

    assert result.status == "parsed"
    assert result.statement is not None
    assert result.statement.lines[0].description == "eToro"


def test_taishin_statement_with_no_new_transactions_is_importable():
    text = """
    115/06/14
    115/06/29
    -149
    +本期新增交易 0
    (02)2655-3355
    0800-023-123
    """

    result = TaiwanCreditCardStatementParser().parse(text, page_count=2)

    assert result.status == "parsed"
    assert result.statement is not None
    assert result.statement.bank_id == "taishin"
    assert result.statement.lines == ()
    assert result.statement.reconciliation.status == "matched"


def test_unknown_or_unreconciled_layout_stays_pending():
    unknown = TaiwanCreditCardStatementParser().parse("115/09/01 100", page_count=2)
    mismatch = TaiwanCreditCardStatementParser().parse(
        "115/09/06 0 100 0 0 0 +100\n115/08/16 115/08/17\n37 8224 TW\neToro\nTWQR\n(02)2745-8080",
        page_count=2,
    )

    assert unknown.status == "unsupported"
    assert unknown.reason_code == "unsupported_bank_layout"
    assert mismatch.status == "unsupported"
    assert mismatch.reason_code == "statement_reconciliation_mismatch"


# Sanitized fixtures reproduce the observed text-layer layouts, not customer data.
CATHAY_TEXT = """115/01/15
115/02/05
95
20
信用卡帳單 115年1月
新臺幣TWD 300 300 90 0 5 0 95
新臺幣
消費日 入帳
起息日 交易說明 新臺幣金額 卡號
後四碼
行動卡號
後四碼
消費
國家 幣別 外幣金額 折算日
上期帳單總額 300
12/30 01/02 ＣＵＢＥＡｐｐ轉帳繳款 -300
繳款小計 -300
循環利息 5
01/02 01/05 測試商店 80 1234 TW TWD
01/03 01/06 點數折抵＿測試商店 -10 1234 TW TWD
10/11 01/08 測試分期 03/06 20 1234 TW TWD
正卡本期消費 95
本期應繳總額 95
-----------------END-----------------
115/10/11 未到期分期餘額 100 60
www.cathaybk.com.tw
"""

SINOPAC_TEXT = """永豐銀行
結帳日 2026/01/14
上期應繳總金額 50
已繳款金額 （註一）
50
本期金額合計（含退款/調整）
113
循環利息
0
違約金
0
本期應繳總金額
113
臺幣
消費日 入帳
起息日
卡號
末四碼 帳單說明 臺幣金額 外幣
折算日
外幣
金額
總費用
年百分率
分期未到期
金額
12/30 12/30 永豐自扣已入帳，謝謝！ -50
11/01 01/04 1234 6- 4 期 : 測試分期 9999999999999 20 60
01/01 01/03 1234 測試商店 100
01/02 01/04 1234 測試退款 -10
01/03 01/05 1234 測試商店 國外交易服務費 3
01/04 01/05 1234 大戶消費回饋入帳戶＿任務 99 元 0
您的正卡，本期應繳金額合計 113
您的 " 分期交易未清償餘額 " 尚餘 60
"""


def test_cathay_parses_all_rows_reconciles_and_preserves_undated_interest():
    parsed = TaiwanCreditCardStatementParser().parse(CATHAY_TEXT, page_count=3)
    assert parsed.status == "parsed"
    statement = parsed.statement
    assert statement.bank_id == "cathay"
    assert statement.period_start == date(2025, 10, 11)
    assert statement.period_end == date(2026, 1, 15)
    assert statement.account_hint == "****1234"
    assert [(row.transaction_kind, row.amount) for row in statement.lines] == [
        ("payment", 300), ("interest", -5), ("purchase", -80), ("refund", 10), ("purchase", -20),
    ]
    assert statement.lines[0].transaction_date == date(2025, 12, 30)
    assert statement.lines[0].posting_date == date(2026, 1, 2)
    assert statement.lines[1].transaction_date is None
    assert statement.lines[1].posting_date == statement.period_end
    assert statement.reconciliation.status == "matched"
    normalized = normalize_statement(statement, statement_id="synthetic-cathay")
    assert normalized.status == "ready"
    assert normalized.reason_codes == ()
    assert normalized.lines[1].transaction_date == statement.closing_date
    assert normalized.lines[1].source_transaction_date is None
    assert normalized.lines[1].transaction_date_basis == "statement_closing_date"


def test_sinopac_uses_current_installment_amount_and_keeps_zero_reward_rows():
    parsed = TaiwanCreditCardStatementParser().parse(SINOPAC_TEXT, page_count=4)
    assert parsed.status == "parsed"
    statement = parsed.statement
    assert statement.bank_id == "sinopac"
    assert statement.period_start == date(2025, 11, 1)
    assert statement.period_end == date(2026, 1, 14)
    assert [(row.transaction_kind, row.amount) for row in statement.lines] == [
        ("payment", 50), ("purchase", -20), ("purchase", -100), ("refund", 10), ("fee", -3), ("refund", 0),
    ]
    assert statement.lines[0].transaction_date == date(2025, 12, 30)
    assert statement.reconciliation.status == "matched"
    assert normalize_statement(statement, statement_id="synthetic-sinopac").can_import


@pytest.mark.parametrize("text", [
    CATHAY_TEXT.replace("測試商店 80", "測試商店 81"),
    CATHAY_TEXT.replace("TW TWD", "US USD"),
    CATHAY_TEXT.replace("01/02 01/05 測試商店", "02/30 01/05 測試商店"),
    CATHAY_TEXT.replace("循環利息 5", "不明費用 5"),
    CATHAY_TEXT.replace("點數折抵＿測試商店 -10", "點數折抵＿測試商店 無法讀取"),
    CATHAY_TEXT.replace("上期帳單總額 300", "上期帳單總額 301"),
    CATHAY_TEXT.replace("繳款小計 -300", "繳款小計 -299"),
    SINOPAC_TEXT.replace("測試商店 100", "測試商店 101"),
    SINOPAC_TEXT.replace("測試商店 100", "測試商店 100 200"),
    SINOPAC_TEXT.replace("01/02 01/04", "01/05 01/04"),
    SINOPAC_TEXT.replace("測試分期 9999999999999 20 60", "測試分期 9999999999999 無法讀取 60"),
    SINOPAC_TEXT.replace("已繳款金額 （註一）\n50", "已繳款金額 （註一）\n51"),
    SINOPAC_TEXT.replace("您的正卡，本期應繳金額合計 113", "您的正卡，本期應繳金額合計 112"),
    SINOPAC_TEXT + "\n01/06 01/07 遺漏列 100",
])
def test_new_bank_layouts_reject_incomplete_unknown_or_unbalanced_rows(text):
    parsed = TaiwanCreditCardStatementParser().parse(text, page_count=3)
    assert parsed.status == "unsupported"


def test_cathay_with_zero_interest_has_no_invented_interest_row():
    text = CATHAY_TEXT.replace("95", "90").replace("90 0 5 0 90", "90 0 0 0 90").replace("循環利息 5", "循環利息 0")
    parsed = TaiwanCreditCardStatementParser().parse(text, page_count=3)
    assert parsed.status == "parsed"
    assert len(parsed.statement.lines) == 4
    assert normalize_statement(parsed.statement, statement_id="cathay-zero").can_import


def test_sinopac_undated_interest_uses_explicit_closing_date_policy():
    text = SINOPAC_TEXT.replace("循環利息\n0", "循環利息\n5").replace("本期應繳總金額\n113", "本期應繳總金額\n118")
    parsed = TaiwanCreditCardStatementParser().parse(text, page_count=4)
    assert parsed.status == "parsed"
    assert parsed.statement.lines[-1].transaction_kind == "interest"
    assert parsed.statement.lines[-1].transaction_date is None
    normalized = normalize_statement(parsed.statement, statement_id="sinopac-interest")
    assert normalized.can_import
    assert normalized.lines[-1].transaction_date == date(2026, 1, 14)
    assert normalized.lines[-1].source_transaction_date is None
    assert normalized.lines[-1].transaction_date_basis == "statement_closing_date"
