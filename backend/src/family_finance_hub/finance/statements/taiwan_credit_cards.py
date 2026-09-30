"""Small, fail-closed parsers for the verified Taiwan card statement layouts.

The parser intentionally handles text that pypdf can extract reliably.  It does
not guess rows from OCR or from a statement total alone.  A new bank/layout
must be added with its own sample and reconciliation tests before it can post
transactions.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from .contracts import (
    ReconciliationSummary,
    StatementData,
    StatementLine,
    StatementParseResult,
)


_DATE = r"\d{3,4}/\d{1,2}/\d{1,2}"
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
_CTBC_SUMMARY = re.compile(
    rf"(?P<close>{_DATE})\s+0\s+(?P<current>{_NUMBER})\s+0\s+0\s+0\s+(?P<due>[+-]?{_NUMBER})",
    re.IGNORECASE,
)
_CTBC_ROW = re.compile(
    rf"(?P<transaction_date>{_DATE})\s+(?P<posting_date>{_DATE})\s*"
    rf"(?:\r?\n)+(?P<amount>[+-]?{_NUMBER})\s+"
    rf"(?P<account>\d{{4}})\s+(?P<currency>TW|TWD|NTD|USD|JPY)\s*"
    rf"(?:\r?\n)+(?P<description>[^\r\n]+)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(rf"(?P<value>{_DATE})")
_SHORT_DATE = r"\d{2}/\d{2}"
_DATED_ROW = re.compile(
    rf"(?P<transaction_date>{_SHORT_DATE})\s+(?P<posting_date>{_SHORT_DATE})\s+(?P<tail>.+)"
)
_CATHAY_ROW = re.compile(
    rf"(?P<description>.+?)\s+(?P<amount>[+-]?{_NUMBER})\s+"
    r"(?P<account>\d{4})\s+TW\s+TWD"
)
_SINOPAC_ROW = re.compile(
    rf"(?P<account>\d{{4}})\s+(?P<description>.+?)\s+(?P<amount>[+-]?{_NUMBER})"
)
_SINOPAC_INSTALLMENT = re.compile(
    rf"(?P<account>\d{{4}})\s+(?P<description>\d+-\s*\d+\s*期\s*:\s*.+?)\s+"
    rf"(?P<amount>{_NUMBER})\s+(?P<balance>{_NUMBER})"
)


class TaiwanCreditCardStatementParser:
    """Parse only bank layouts verified against local statement samples."""

    bank_id = "taiwan-credit-card"
    format_version = "taiwan-credit-card-v2"

    def parse(self, extracted_text: str, *, page_count: int) -> StatementParseResult:
        text = _decode_unicode_tokens(extracted_text)
        text = "\n".join(line.strip() for line in text.splitlines())
        if page_count < 1 or not text.strip():
            return self._unsupported("statement_text_unavailable")

        compact = re.sub(r"\D", "", text)
        lowered = text.casefold()
        if "0227458080" in compact and "twqr" in lowered:
            return self._parse_ctbc(text)
        if "0226553355" in compact and "0800023123" in compact:
            return self._parse_taishin(text)
        if "cathaybk.com.tw" in lowered and "新臺幣TWD" in text:
            return self._parse_cathay(text)
        if "永豐銀行" in text and "本期金額合計（含退款/調整）" in text:
            return self._parse_sinopac(text)
        return self._unsupported("unsupported_bank_layout")

    def _parse_cathay(self, text: str) -> StatementParseResult:
        summary = re.search(
            rf"(?m)^新臺幣TWD\s+({_NUMBER})\s+({_NUMBER})\s+([+-]?{_NUMBER})\s+"
            rf"({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+([+-]?{_NUMBER})$", text,
        )
        period = re.search(rf"(?m)^({_DATE})\n({_DATE})\n({_NUMBER})\n({_NUMBER})$", text)
        table = re.search(
            r"新臺幣\n消費日 入帳\n起息日 交易說明 新臺幣金額 卡號\n後四碼\n"
            r"行動卡號\n後四碼\n消費\n國家 幣別 外幣金額 折算日\n"
            rf"(?P<body>.*?)^本期應繳總額\s+(?P<due>[+-]?{_NUMBER})$",
            text, re.MULTILINE | re.DOTALL,
        )
        if not summary or not period or not table:
            return self._unsupported("statement_reconciliation_unavailable")
        try:
            close_date = _parse_date(period[1])
            due_date = _parse_date(period[2])
            previous, paid, current, cash, interest, agency_interest, due = (
                _money(value) for value in summary.groups()
            )
            if not close_date <= due_date or cash != 0 or agency_interest != 0:
                return self._unsupported("unsupported_bank_layout")
            rows: list[StatementLine] = []
            accounts: set[str] = set()
            prior_found = payments_found = interest_found = False
            for line in table["body"].splitlines():
                prior = re.fullmatch(rf"上期帳單總額\s+({_NUMBER})", line)
                payment_total = re.fullmatch(rf"繳款小計\s+([+-]?{_NUMBER})", line)
                interest_row = re.fullmatch(rf"循環利息\s+({_NUMBER})", line)
                subtotal = re.fullmatch(rf"正卡本期消費\s+([+-]?{_NUMBER})", line)
                if prior:
                    if prior_found or _money(prior[1]) != previous:
                        return self._unsupported("statement_reconciliation_mismatch")
                    prior_found = True
                elif payment_total:
                    if payments_found or _money(payment_total[1]) != -paid:
                        return self._unsupported("statement_reconciliation_mismatch")
                    payments_found = True
                elif interest_row:
                    if interest_found or _money(interest_row[1]) != interest:
                        return self._unsupported("statement_reconciliation_mismatch")
                    interest_found = True
                    if interest:
                        # Preserve the source date gap; normalization applies
                        # the approved interest recognition policy separately.
                        rows.append(StatementLine(
                            line_index=len(rows) + 1, posting_date=close_date,
                            description="循環利息", transaction_kind="interest",
                            amount=-interest, currency="TWD",
                        ))
                elif subtotal:
                    if _money(subtotal[1]) != due:
                        return self._unsupported("statement_reconciliation_mismatch")
                elif line:
                    dated = _DATED_ROW.fullmatch(line)
                    if not dated:
                        return self._unsupported("statement_row_value_unreliable")
                    card = _CATHAY_ROW.fullmatch(dated["tail"])
                    payment = _payment_row(dated["tail"], bank_id="cathay")
                    if card:
                        accounts.add(card["account"])
                        rows.append(_card_line(dated, card["description"], _money(card["amount"]), close_date, len(rows) + 1))
                    elif payment:
                        rows.append(_card_line(dated, payment[0], payment[1], close_date, len(rows) + 1, payment=True))
                    else:
                        return self._unsupported("statement_row_value_unreliable")
            if not (prior_found and payments_found and interest_found):
                return self._unsupported("statement_reconciliation_unavailable")
            if (
                _bill_total(rows, exclude={"payment", "interest"}) != current
                or sum(row.amount for row in rows if row.transaction_kind == "payment") != paid
                or previous - paid + current + interest != due
                or _money(table["due"]) != due or _money(period[3]) != due
                or _dated_row_count(text) != sum(row.transaction_date is not None for row in rows)
            ):
                return self._unsupported("statement_reconciliation_mismatch")
            return self._result("cathay", rows, close_date, accounts)
        except (InvalidOperation, ValueError):
            return self._unsupported("statement_row_value_unreliable")

    def _parse_sinopac(self, text: str) -> StatementParseResult:
        period = re.search(rf"(?m)^結帳日\s+({_DATE})$", text)
        table = re.search(
            r"消費日 入帳\n起息日\n卡號\n末四碼 帳單說明 臺幣金額 外幣\n"
            r"折算日\n外幣\n金額\n總費用\n年百分率\n分期未到期\n金額\n"
            rf"(?P<body>.*?)^您的正卡，本期應繳金額合計\s+(?P<due>[+-]?{_NUMBER})$",
            text, re.MULTILINE | re.DOTALL,
        )
        if not period or not table:
            return self._unsupported("statement_reconciliation_unavailable")
        try:
            close_date = _parse_date(period[1])
            values = []
            for label in (
                "上期應繳總金額", "已繳款金額 （註一）", "本期金額合計（含退款/調整）",
                "循環利息", "違約金", "本期應繳總金額",
            ):
                match = re.search(rf"(?m)^{re.escape(label)}\s+([+-]?{_NUMBER})$", text)
                if not match:
                    return self._unsupported("statement_reconciliation_unavailable")
                values.append(_money(match[1]))
            previous, paid, current, interest, penalty, due = values
            if min(previous, paid, interest, penalty) < 0:
                return self._unsupported("statement_row_sign_unreliable")
            rows: list[StatementLine] = []
            accounts: set[str] = set()
            for line in table["body"].splitlines():
                dated = _DATED_ROW.fullmatch(line)
                if not dated:
                    return self._unsupported("statement_row_value_unreliable")
                payment = _payment_row(dated["tail"], bank_id="sinopac")
                card = _SINOPAC_INSTALLMENT.fullmatch(dated["tail"]) or _SINOPAC_ROW.fullmatch(dated["tail"])
                if payment:
                    rows.append(_card_line(dated, payment[0], payment[1], close_date, len(rows) + 1, payment=True))
                elif card:
                    # Multiple trailing amounts only belong to the verified
                    # installment layout; the last is not a current charge.
                    if "balance" not in card.re.groupindex and re.search(rf"\s{_NUMBER}$", card["description"]):
                        return self._unsupported("statement_row_value_unreliable")
                    accounts.add(card["account"])
                    rows.append(_card_line(dated, card["description"], _money(card["amount"]), close_date, len(rows) + 1))
                else:
                    return self._unsupported("statement_row_value_unreliable")
            if (
                _bill_total(rows, exclude={"payment"}) != current
                or sum(row.amount for row in rows if row.transaction_kind == "payment") != paid
                or previous - paid + current + interest + penalty != due
                or _money(table["due"]) != current
                or _dated_row_count(text) != len(rows)
            ):
                return self._unsupported("statement_reconciliation_mismatch")
            for description, kind, amount in (("循環利息", "interest", interest), ("違約金", "fee", penalty)):
                if amount:
                    rows.append(StatementLine(
                        line_index=len(rows) + 1, posting_date=close_date,
                        description=description, transaction_kind=kind, amount=-amount, currency="TWD",
                    ))
            return self._result("sinopac", rows, close_date, accounts)
        except (InvalidOperation, ValueError):
            return self._unsupported("statement_row_value_unreliable")

    def _result(self, bank_id: str, rows: list[StatementLine], close_date: date, accounts: set[str]) -> StatementParseResult:
        return StatementParseResult(status="parsed", statement=StatementData(
            bank_id=bank_id, format_version=self.format_version,
            period_start=min((row.transaction_date for row in rows if row.transaction_date), default=close_date),
            period_end=close_date, closing_date=close_date,
            account_hint=f"****{next(iter(accounts))}" if len(accounts) == 1 else None,
            lines=tuple(rows), reconciliation=ReconciliationSummary(
                status="matched", basis="statement_balance_and_current_charges", difference=Decimal("0"),
            ),
        ))

    def _parse_ctbc(self, text: str) -> StatementParseResult:
        rows: list[StatementLine] = []
        for match in _CTBC_ROW.finditer(text):
            description = _clean_description(match.group("description"))
            if not description:
                return self._unsupported("statement_row_description_unreliable")
            try:
                amount = Decimal(match.group("amount").replace(",", ""))
                transaction_date = _parse_date(match.group("transaction_date"))
                posting_date = _parse_date(match.group("posting_date"))
            except (InvalidOperation, ValueError):
                return self._unsupported("statement_row_value_unreliable")
            if amount <= 0:
                return self._unsupported("statement_row_sign_unreliable")
            kind = "refund" if re.search(r"退貨|退款|回饋|折抵", description) else "purchase"
            normalized_amount = amount if kind == "refund" else -amount
            rows.append(
                StatementLine(
                    line_index=len(rows) + 1,
                    transaction_date=transaction_date,
                    posting_date=posting_date,
                    description=description,
                    transaction_kind=kind,
                    amount=normalized_amount,
                    currency=_currency(match.group("currency")),
                )
            )

        summary = _CTBC_SUMMARY.search(text)
        if summary is None:
            return self._unsupported("statement_reconciliation_unavailable")
        close_date = _parse_date(summary.group("close"))
        expected_due = Decimal(summary.group("due").replace(",", ""))
        if expected_due < 0:
            expected_due = -expected_due
        actual_due = sum(
            (-line.amount if line.transaction_kind in {"purchase", "fee", "interest"} else line.amount)
            for line in rows
        )
        if actual_due != expected_due:
            return self._unsupported("statement_reconciliation_mismatch")
        if not rows and expected_due != 0:
            return self._unsupported("statement_rows_missing")

        first_row = _CTBC_ROW.search(text)
        account_hint = f"****{first_row.group('account')}" if first_row else None
        period_start = min((line.transaction_date for line in rows if line.transaction_date), default=close_date)
        return StatementParseResult(
            status="parsed",
            statement=StatementData(
                bank_id="ctbc",
                format_version=self.format_version,
                period_start=period_start,
                period_end=close_date,
                account_hint=account_hint,
                lines=tuple(rows),
                reconciliation=ReconciliationSummary(
                    status="matched",
                    basis="statement_current_due",
                    difference=Decimal("0"),
                ),
            ),
        )

    def _parse_taishin(self, text: str) -> StatementParseResult:
        dates = [_parse_date(match.group("value")) for match in _DATE_RE.finditer(text)]
        if not dates:
            return self._unsupported("statement_period_unavailable")
        # The verified Taishin sample explicitly states that there are no new
        # transactions.  Do not treat a garbled text layer as a transaction row.
        has_zero_new_transactions = re.search(r"\+[^\r\n]{0,80}\s0\s*$", text, re.MULTILINE) is not None
        if not has_zero_new_transactions:
            return self._unsupported("statement_rows_need_ocr")
        close_date = dates[0]
        period_start = date(close_date.year, close_date.month, 1)
        period_end = date(close_date.year, close_date.month, monthrange(close_date.year, close_date.month)[1])
        return StatementParseResult(
            status="parsed",
            statement=StatementData(
                bank_id="taishin",
                format_version=self.format_version,
                period_start=period_start,
                period_end=period_end,
                lines=(),
                reconciliation=ReconciliationSummary(
                    status="matched",
                    basis="statement_declares_no_new_transactions",
                    difference=Decimal("0"),
                ),
            ),
        )

    @staticmethod
    def _unsupported(reason_code: str) -> StatementParseResult:
        return StatementParseResult(status="unsupported", reason_code=reason_code)


def _parse_date(value: str) -> date:
    year, month, day = (int(part) for part in value.split("/"))
    if year < 1911:
        year += 1911
    return date(year, month, day)


def _decode_unicode_tokens(value: str) -> str:
    """Decode the ASCII /UNIC#### layer emitted by some CTBC PDFs."""

    return re.sub(
        r"/UNIC([0-9A-Fa-f]{4,6})",
        lambda match: chr(int(match.group(1), 16)),
        value,
    )


def _currency(value: str) -> str:
    normalized = value.upper()
    return "TWD" if normalized in {"TW", "TWD", "NTD"} else normalized


def _clean_description(value: str) -> str:
    normalized = " ".join(value.split()).strip()
    if not normalized or len(normalized) > 500:
        return ""
    if normalized.startswith(("http://", "https://", "(", "[")):
        return ""
    return normalized


def _money(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _month_day(value: str, close_date: date) -> date:
    month, day = (int(part) for part in value.split("/"))
    year = close_date.year - ((month, day) > (close_date.month, close_date.day))
    return date(year, month, day)


def _payment_row(tail: str, *, bank_id: str) -> tuple[str, Decimal] | None:
    match = re.fullmatch(rf"(.+?)\s+(-{_NUMBER})", tail)
    if not match:
        return None
    description = unicodedata.normalize("NFKC", match[1])
    allowed = {
        "cathay": {"本行自動扣繳", "CUBEApp轉帳繳款"},
        "sinopac": {"永豐自扣已入帳,謝謝!"},
    }
    return (match[1], _money(match[2])) if description in allowed[bank_id] else None


def _card_line(dated: re.Match, description: str, amount: Decimal, close_date: date, index: int, *, payment: bool = False) -> StatementLine:
    description = _clean_description(description)
    if not description:
        raise ValueError("unreliable description")
    normalized = unicodedata.normalize("NFKC", description)
    if payment:
        kind = "payment"
    elif amount < 0 or (amount == 0 and "回饋入帳戶" in normalized):
        kind = "refund"
    elif "服務費" in normalized or "手續費" in normalized:
        kind = "fee"
    elif "利息" in normalized:
        kind = "interest"
    else:
        kind = "purchase"
    transaction_date = _month_day(dated["transaction_date"], close_date)
    posting_date = _month_day(dated["posting_date"], close_date)
    if transaction_date > posting_date:
        raise ValueError("transaction after posting")
    return StatementLine(
        line_index=index, transaction_date=transaction_date, posting_date=posting_date,
        description=description, transaction_kind=kind, amount=-amount, currency="TWD",
    )


def _bill_total(rows: list[StatementLine], *, exclude: set[str]) -> Decimal:
    return sum((-row.amount for row in rows if row.transaction_kind not in exclude), Decimal("0"))


def _dated_row_count(text: str) -> int:
    return len(re.findall(rf"(?m)^{_SHORT_DATE}\s+{_SHORT_DATE}\s", text))
