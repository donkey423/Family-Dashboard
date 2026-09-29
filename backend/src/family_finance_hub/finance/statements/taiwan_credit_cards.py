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


class TaiwanCreditCardStatementParser:
    """Parse only the CTBC and Taishin layouts verified in local samples."""

    bank_id = "taiwan-credit-card"
    format_version = "taiwan-credit-card-v1"

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
        return self._unsupported("unsupported_bank_layout")

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
