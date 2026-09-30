"""Audit freshly downloaded card statements in the isolated acceptance API only."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from datetime import date
from decimal import Decimal

import httpx
from pypdf import PdfReader

from family_finance_hub.finance.statements.taiwan_credit_cards import TaiwanCreditCardStatementParser
from family_finance_hub.finance.statements.normalization import normalize_statement
from gmail_attachment_download import ROOT, guarded_run, guarded_output, verified_download


def formal_snapshot():
    database = ROOT / "data" / "family-finance-hub-live.db"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT * FROM finance_transactions ORDER BY id").fetchall()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    return len(rows), revision, sha256(repr(rows).encode("utf-8")).hexdigest()


def isolated_status(client, directory):
    response = client.get("/api/acceptance/status")
    response.raise_for_status()
    status = response.json()
    if (status.get("mode") != "isolated-gmail-acceptance"
        or status.get("run_directory") != directory.name
        or status.get("external_ai_calls") != 0):
        raise ValueError("Refusing to test an unverified or AI-enabled acceptance server")
    return status


def money(s): return Decimal(s.replace(',', ''))
def full_date(s):
    y,m,d=map(int,s.split('/'))
    return date(y+1911 if y<1911 else y,m,d)
def short_date(s,closing):
    m,d=map(int,s.split('/'))
    return date(closing.year-int((m,d)>(closing.month,closing.day)),m,d)
def kind(desc,billed):
    n=unicodedata.normalize('NFKC',desc)
    if n in {'本行自動扣繳','CUBEApp轉帳繳款','永豐自扣已入帳,謝謝!'}: return 'payment'
    if billed<0 or (billed==0 and '回饋入帳戶' in n): return 'refund'
    if '服務費' in n or '手續費' in n: return 'fee'
    if '利息' in n: return 'interest'
    return 'purchase'
def independent(bank,text,data):
    decoded=re.sub(r'/UNIC([0-9a-fA-F]{4,6})',lambda m:chr(int(m[1],16)),text)
    lines=[l.strip() for l in decoded.splitlines()]
    expected=[]
    if bank=='ctbc':
        for i,l in enumerate(lines):
            parts=l.split()
            if len(parts)==2 and all(re.fullmatch(r'\d{3,4}/\d{1,2}/\d{1,2}',p) for p in parts):
                amount,card,currency=lines[i+1].split()
                desc=' '.join(lines[i+2].split());billed=money(amount)
                k='refund' if re.search('退貨|退款|回饋|折抵',desc) else 'purchase'
                expected.append((full_date(parts[0]),full_date(parts[1]),desc,k,billed if k=='refund' else -billed,'TWD' if currency in {'TW','TWD','NTD'} else currency))
        summary=next(l.split() for l in lines if re.fullmatch(r'\d{3,4}/\d{1,2}/\d{1,2}\s+0\s+[\d,]+\s+0\s+0\s+0\s+[+-]?[\d,]+',l))
        assert sum(-r[4] if r[3]!='refund' else r[4] for r in expected)==abs(money(summary[-1])),bank+' independent due'
    else:
        if bank == 'cathay':
            closing_candidates = []
            for index, line in enumerate(lines[:-3]):
                if (re.fullmatch(r'\d{3,4}/\d{1,2}/\d{1,2}', line)
                    and re.fullmatch(r'\d{3,4}/\d{1,2}/\d{1,2}', lines[index+1])
                    and re.fullmatch(r'[\d,]+', lines[index+2])
                    and re.fullmatch(r'[\d,]+', lines[index+3])):
                    closing_candidates.append(full_date(line))
            assert len(closing_candidates) == 1, bank + ' source closing date'
            closing = closing_candidates[0]
        else:
            closing_lines = [line.split()[-1] for line in lines if line.startswith('結帳日 ')]
            assert len(closing_lines) == 1, bank + ' source closing date'
            closing = full_date(closing_lines[0])
        assert data.closing_date == closing, bank + ' closing date mismatch'
        for l in lines:
            if bank=='cathay' and l.startswith('本期應繳總額 '): break
            if bank=='sinopac' and l.startswith('您的正卡，本期應繳金額合計 '): break
            if bank=='cathay' and re.fullmatch(r'循環利息\s+[\d,]+',l):
                billed=money(l.split()[-1])
                if billed: expected.append((None,closing,'循環利息','interest',-billed,'TWD'))
                continue
            p=l.split()
            if len(p)<4 or not all(re.fullmatch(r'\d{2}/\d{2}',s) for s in p[:2]): continue
            tail=p[2:]
            if bank=='cathay' and tail[-2:]==['TW','TWD']:
                billed=money(tail[-4]);desc=' '.join(tail[:-4])
            elif bank=='sinopac' and re.fullmatch(r'\d{4}',tail[0]):
                installment=re.match(r'\d+-\s*\d+\s*期\s*:', ' '.join(tail[1:])) is not None
                amount_index=-2 if installment else -1
                billed=money(tail[amount_index]);desc=' '.join(tail[1:amount_index])
            else:
                billed=money(tail[-1]);desc=' '.join(tail[:-1])
            expected.append((short_date(p[0],closing),short_date(p[1],closing),desc,kind(desc,billed),-billed,'TWD'))
        if bank=='cathay':
            previous,paid,current,cash,interest,agency,due=map(money,next(l.split()[1:] for l in lines if l.startswith('新臺幣TWD ')))
            assert cash==agency==0 and previous-paid+current+interest==due
            assert money(next(l for l in lines if l.startswith('本期應繳總額 ')).split()[-1])==due
        else:
            def value(label):
                i=next(i for i,l in enumerate(lines) if l==label or l.startswith(label+' '))
                remainder=lines[i][len(label):].strip()
                return money(remainder if remainder else lines[i+1])
            previous,paid,current,interest,penalty,due=[value(l) for l in ('上期應繳總金額','已繳款金額 （註一）','本期金額合計（含退款/調整）','循環利息','違約金','本期應繳總金額')]
            assert previous-paid+current+interest+penalty==due
            assert money(next(l for l in lines if l.startswith('您的正卡，本期應繳金額合計 ')).split()[-1])==current
            for desc,k,billed in [('循環利息','interest',interest),('違約金','fee',penalty)]:
                if billed: expected.append((None,closing,desc,k,-billed,'TWD'))
        assert sum(-r[4] for r in expected if r[3] not in {'payment','interest'})==current,bank+' current total'
        assert sum(r[4] for r in expected if r[3]=='payment')==paid,bank+' payment total'
    actual=[(r.transaction_date,r.posting_date,r.description,r.transaction_kind,r.amount,r.currency) for r in data.lines]
    assert len(expected)==len(actual),bank+' independent row count'
    assert expected==actual,bank+' independent source fields'

def run(directory, port=8031):
    directory = guarded_run(directory)
    if not 8031 <= port <= 65535:
        raise ValueError("Use an isolated loopback API port, not the production API")
    cases = json.loads((directory / "cases.json").read_text(encoding="utf-8"))
    if len(cases) != 3 or {case["bank"] for case in cases} != {"ctbc", "cathay", "sinopac"}:
        raise ValueError("This acceptance audit requires three different verified bank layouts")
    before = formal_snapshot()
    results = []
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=90, trust_env=False) as client:
        isolated_status(client, directory)

        def get(path):
            response = client.get(path)
            response.raise_for_status()
            return response.json()

        for case in cases:
            bank = case["bank"]
            output = guarded_output(directory, case["label"])
            receipt, original = verified_download(output)
            assert PdfReader(BytesIO(original), strict=True).is_encrypted, bank + " encrypted source"
            assert case["hint"].strip(), bank + " source mail hint missing"

            def upload():
                response = client.post("/api/integrations/codex-mcp/gmail/import",
                    files={"file": (case["filename"], original, "application/pdf")},
                    data={"message_id": case["message_key"], "attachment_id": case["attachment_key"],
                          "password_instruction": case["hint"]})
                response.raise_for_status()
                return response.json()

            document = upload()
            assert document["instruction_detected"], bank + " mail hint not detected"
            assert document["sha256"] == receipt["sha256"], bank + " stored encrypted bytes"
            document_id = document["document_id"]
            source_count = len(get("/api/documents/" + document_id + "/detail")["sources"])
            # No manual password or hint override: the API must use the stored source hint.
            body = {"allow_ai_analysis": False}
            response = client.post("/api/documents/" + document_id + "/preview", json=body)
            response.raise_for_status()
            pdf = PdfReader(BytesIO(response.content))
            assert not pdf.is_encrypted, bank + " local unlock failed"
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            parsed = TaiwanCreditCardStatementParser().parse(text, page_count=len(pdf.pages))
            assert parsed.status == "parsed" and parsed.statement.bank_id == bank, bank + " wrong bank/layout"
            data = parsed.statement
            assert data.period_end.strftime("%Y-%m") == case["period_month"], bank + " wrong statement period"
            assert data.lines, bank + " credit card transaction details missing"
            independent(bank, text, data)
            normalized = normalize_statement(data, statement_id="acceptance-" + bank)
            assert normalized.status == "ready", bank + " normalization not ready"
            response = client.post("/api/documents/" + document_id + "/statement-analysis", json=body)
            response.raise_for_status()
            statement_id = response.json()["statement_id"]
            statement = get("/api/statements/" + statement_id)
            assert statement["status"] == "ready", bank + " statement not ready"
            assert statement["bank_id"] == bank and statement["transaction_count"] == 0
            expected = [(row.transaction_date.isoformat() if row.transaction_date else None,
                         row.posting_date.isoformat() if row.posting_date else None,
                         row.description, row.transaction_kind, row.amount, row.currency) for row in data.lines]
            actual = [(row["transaction_date"], row["posting_date"], row["description"],
                       row["transaction_kind"], Decimal(str(row["amount"])), row["currency"])
                      for row in statement["lines"]]
            assert expected == actual, bank + " API/source fields mismatch"
            policies = [row for row in statement["lines"]
                        if row["transaction_date_basis"] == "statement_closing_date"]
            for row in policies:
                assert row["transaction_date"] is None and row["transaction_kind"] == "interest"
                assert row["effective_transaction_date"] == data.closing_date.isoformat()
            repeated = upload()
            assert repeated["document_id"] == document_id and repeated["duplicate"] and repeated["duplicate_source"]
            response = client.post("/api/documents/" + document_id + "/statement-analysis", json=body)
            response.raise_for_status()
            assert response.json()["statement_id"] == statement_id, bank + " duplicate statement"
            assert len(get("/api/documents/" + document_id + "/detail")["sources"]) == source_count
            assert len(get("/api/statements/" + statement_id)["lines"]) == len(data.lines)
            results.append({"bank": bank, "period": case["period_month"], "encrypted_source": True,
                "source_hint_detected": True, "pages": len(pdf.pages), "rows": len(data.lines),
                "independent_fields_match": True, "balance_match": True, "api_fields_match": True,
                "interest_date_policy_rows": len(policies), "idempotent": True,
                "sha256": receipt["sha256"], "result": "PASS"})
            print(json.dumps(results[-1]))
        assert get("/api/finance/transactions")["total"] == 0, "Acceptance must not confirm transactions"
        isolated_status(client, directory)
    after = formal_snapshot()
    assert after == before, "Formal Finance rows or schema changed during acceptance"
    report = {"result": "PASS_3BANK", "banks": results, "formal_before": before[0],
              "formal_after": after[0], "formal_revision": after[1], "formal_finance_unchanged": True,
              "external_ai_calls": 0, "confirm_calls": 0, "mode": "gmail-browser-fallback"}
    (directory / "audit-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "banks"}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--port", type=int, default=8031)
    args = parser.parse_args()
    report_path = None
    try:
        report_path = guarded_run(args.run_directory) / "audit-result.json"
        report_path.write_text(json.dumps({"result": "RUNNING"}), encoding="utf-8")
        run(args.run_directory, args.port)
    except Exception as error:
        if report_path is not None:
            report_path.write_text(json.dumps({"result": "FAIL", "error_type": type(error).__name__}), encoding="utf-8")
        # Exception messages from third-party parsers can include source text.
        parser.exit(1, type(error).__name__ + ": acceptance failed; no PASS report was produced\n")
