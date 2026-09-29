from datetime import date

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
