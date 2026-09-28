from io import BytesIO
import json

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select

from family_finance_hub.config import Settings
from family_finance_hub.database import make_engine, make_session_factory
from family_finance_hub.documents.processors.pdf import PdfDocumentProcessor
from family_finance_hub.documents.processors.ports import OcrResult
from family_finance_hub.main import create_app
from family_finance_hub.models import AIProviderProfile, PasswordRuleRecord
from family_finance_hub.security.password_rules.schema import PasswordRule


class MemorySecretStore:
    def __init__(self):
        self.values = {}

    def set(self, reference, value):
        self.values[reference] = value

    def get(self, reference):
        return self.values.get(reference)

    def delete(self, reference):
        self.values.pop(reference, None)


class FakeInterpreter:
    def __init__(self, rule):
        self.rule = rule
        self.calls = []

    def interpret(self, instruction, context):
        self.calls.append((instruction, context))
        return self.rule


class FakeOcrProvider:
    def extract_pdf_text(self, content, *, page_count):
        return OcrResult("", "completed")


def make_encrypted_pdf(password):
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def ambiguous_rule():
    return PasswordRule.model_validate({
        "version": 1,
        "status": "ambiguous",
        "candidates": [
            {"parts": [
                {"source": "national_id", "transform": "prefix", "start": None, "length": 4, "date_format": None, "case": "upper"},
                {"source": "birthday", "transform": "date_format", "start": None, "length": None, "date_format": "YYYYMMDD", "case": "preserve"},
            ], "separator": ""},
            {"parts": [
                {"source": "national_id", "transform": "suffix", "start": None, "length": 4, "date_format": None, "case": "upper"},
                {"source": "birthday", "transform": "date_format", "start": None, "length": None, "date_format": "YYYYMMDD", "case": "preserve"},
            ], "separator": ""},
        ],
    })


def make_client(tmp_path, secret_store, password_interpreter=None):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        storage_root=tmp_path / "documents",
    )
    app = create_app(
        settings,
        create_schema=True,
        secret_store=secret_store,
        password_interpreter=password_interpreter,
        pdf_processor=PdfDocumentProcessor(FakeOcrProvider()),
    )
    return TestClient(app), settings


def make_profiles(client):
    secret = client.post("/api/security/profiles", json={
        "display_name": "合成測試成員",
        "national_id": "A123456789",
        "birthday": "1984-03-02",
    })
    assert secret.status_code == 201
    secure = client.post("/api/security/document-profiles", json={
        "display_name": "合成測試帳單",
        "institution": "測試銀行",
        "sender_pattern": "statements@example.test",
        "secret_profile_id": secret.json()["id"],
    })
    assert secure.status_code == 201
    return secret.json(), secure.json()


def test_ai_provider_key_is_kept_in_secret_store_only(tmp_path):
    secret_store = MemorySecretStore()
    client, settings = make_client(tmp_path, secret_store)
    api_key = "sk-synthetic-only-not-real"

    with client:
        response = client.post("/api/security/ai-provider", json={"api_key": api_key, "model": "synthetic-model"})
        assert response.status_code == 201
        assert api_key not in response.text
        assert client.get("/api/security/ai-provider").json() == {
            "configured": True,
            "provider": "openai",
            "model": "synthetic-model",
        }

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        profile = session.get(AIProviderProfile, "openai")
        assert profile is not None
        assert profile.api_key_credential_ref in secret_store.values
        assert api_key not in profile.api_key_credential_ref
    assert api_key.encode() not in (tmp_path / "test.db").read_bytes()
    engine.dispose()


def test_pdf_preview_uses_ai_rules_locally_and_persists_only_verified_rule(tmp_path):
    secret_store = MemorySecretStore()
    interpreter = FakeInterpreter(ambiguous_rule())
    client, settings = make_client(tmp_path, secret_store, interpreter)
    original_pdf = make_encrypted_pdf("678919840302")
    body = {
        "document_security_profile_id": "",
        "subject": "信用卡帳單密碼規則",
        "body": "密碼規則：身分證末四碼加生日 YYYYMMDD。\n身分證 A123456789，生日 19840302。\n消費摘要：早餐 120 元。",
        "sender": "statements@example.test",
        "filename": "statement-A123456789.pdf",
        "allow_ai_analysis": True,
    }

    with client:
        _, document_profile = make_profiles(client)
        body["document_security_profile_id"] = document_profile["id"]
        uploaded = client.post("/api/documents", files={
            "file": ("statement.pdf", original_pdf, "application/pdf"),
        })
        assert uploaded.status_code == 200

        manual = client.post(
            f"/api/documents/{uploaded.json()['id']}/preview",
            json={**body, "allow_ai_analysis": False},
        )
        assert manual.status_code == 422
        assert manual.headers["x-familyhub-error"] == "pdf_password_required"
        assert interpreter.calls == []

        preview = client.post(f"/api/documents/{uploaded.json()['id']}/preview", json=body)

        assert preview.status_code == 200
        assert preview.headers["cache-control"] == "private, no-store, max-age=0"
        assert preview.headers["x-familyhub-text-extraction"] == "insufficient"
        assert not PdfReader(BytesIO(preview.content)).is_encrypted
        assert client.get(f"/api/documents/{uploaded.json()['id']}/content").content == original_pdf
        assert len(interpreter.calls) == 1
        instruction, context = interpreter.calls[0]
        assert "末四碼" in instruction
        assert "YYYYMMDD" in instruction
        for sensitive in ("A123456789", "19840302", "120 元", "statements@example.test", "statement-A123456789.pdf"):
            assert sensitive not in instruction
        assert context == {"institution": "測試銀行", "document_type": "PDF statement"}

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as session:
        rule_record = session.scalar(select(PasswordRuleRecord))
        assert rule_record is not None
        saved_rule = rule_record.rule_json
        assert saved_rule["status"] == "resolved"
        assert len(saved_rule["candidates"]) == 1
        assert saved_rule["candidates"][0]["parts"][0]["transform"] == "suffix"
        serialized = json.dumps(saved_rule)
        assert "A123456789" not in serialized
        assert "19840302" not in serialized
        assert "678919840302" not in serialized
    engine.dispose()


@pytest.mark.parametrize("filtered_entry", ["duplicate", "empty"])
def test_pdf_preview_persists_and_reuses_successful_rule_after_candidate_filtering(tmp_path, filtered_entry):
    payload = ambiguous_rule().model_dump(mode="json")
    leading = ambiguous_rule().model_dump(mode="json")["candidates"][0]
    if filtered_entry == "duplicate":
        leading["parts"][0]["case"] = "preserve"
    else:
        leading["parts"][0].update(transform="substring", start=100)
    payload["candidates"].insert(0, leading)
    rule = PasswordRule.model_validate(payload)
    interpreter = FakeInterpreter(rule)
    client, settings = make_client(tmp_path, MemorySecretStore(), interpreter)
    original_pdf = make_encrypted_pdf("678919840302")
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    try:
        with client:
            _, document_profile = make_profiles(client)
            uploaded = client.post("/api/documents", files={
                "file": ("synthetic-statement.pdf", original_pdf, "application/pdf"),
            })
            assert uploaded.status_code == 200
            preview_url = f"/api/documents/{uploaded.json()['id']}/preview"
            body = {
                "document_security_profile_id": document_profile["id"],
                "body": "Password rule: national ID suffix plus birthday YYYYMMDD.",
                "allow_ai_analysis": True,
            }

            preview = client.post(preview_url, json=body)

            assert preview.status_code == 200
            assert not PdfReader(BytesIO(preview.content)).is_encrypted
            assert len(interpreter.calls) == 1
            with factory() as session:
                record = session.scalar(select(PasswordRuleRecord))
                assert record is not None
                assert record.rule_json == PasswordRule(
                    version=1, status="resolved", candidates=[rule.candidates[2]],
                ).model_dump(mode="json")
                serialized = json.dumps(record.rule_json)
                for sensitive in ("A123456789", "19840302", "678919840302"):
                    assert sensitive not in serialized

            reused = client.post(preview_url, json={**body, "allow_ai_analysis": False})

            assert reused.status_code == 200
            assert not PdfReader(BytesIO(reused.content)).is_encrypted
            assert len(interpreter.calls) == 1
            assert client.get(f"/api/documents/{uploaded.json()['id']}/content").content == original_pdf
    finally:
        engine.dispose()


def test_password_rule_analysis_never_returns_secret_material(tmp_path):
    secret_store = MemorySecretStore()
    interpreter = FakeInterpreter(ambiguous_rule())
    client, _ = make_client(tmp_path, secret_store, interpreter)
    with client:
        _, document_profile = make_profiles(client)
        response = client.post("/api/security/password-rules/analyze", json={
            "document_security_profile_id": document_profile["id"],
            "subject": "信用卡帳單密碼規則",
            "body": "密碼規則：身分證末四碼加生日 YYYYMMDD。\n身分證 A123456789，生日 19840302。",
            "sender": "statements@example.test",
            "filename": "statement-A123456789.pdf",
        })

    assert response.status_code == 200
    assert response.json()["status"] == "ambiguous"
    assert "A123456789" not in response.text
    assert "19840302" not in response.text
    assert "678919840302" not in response.text
    instruction, context = interpreter.calls[0]
    assert "A123456789" not in instruction
    assert "19840302" not in instruction
    assert "statements@example.test" not in json.dumps(context)


def test_pdf_extraction_status_header_is_exposed_to_browser(tmp_path):
    secret_store = MemorySecretStore()
    client, _ = make_client(tmp_path, secret_store)
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    output = BytesIO()
    writer.write(output)

    with client:
        uploaded = client.post("/api/documents", files={
            "file": ("scanned.pdf", output.getvalue(), "application/pdf"),
        })
        response = client.post(
            f"/api/documents/{uploaded.json()['id']}/preview",
            json={"allow_ai_analysis": False},
            headers={"Origin": "http://127.0.0.1:5173"},
        )

    assert response.status_code == 200
    assert response.headers["x-familyhub-text-extraction"] == "insufficient"
    assert "x-familyhub-text-extraction" in response.headers["access-control-expose-headers"].lower()
    assert "x-familyhub-error" in response.headers["access-control-expose-headers"].lower()
