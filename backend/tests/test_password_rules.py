import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from family_finance_hub.database import Base, make_engine, make_session_factory
from family_finance_hub.models import AIProviderProfile, DocumentSecurityProfile, PasswordRuleRecord, SecretProfile
from family_finance_hub.security.password_rules.composer import PasswordComposer
from family_finance_hub.security.password_rules.extractor import PasswordInstructionContext, PasswordInstructionExtractor
from family_finance_hub.security.password_rules.groq_responses import GroqResponsesInterpreter
from family_finance_hub.security.password_rules.openai_responses import OpenAIResponsesInterpreter
from family_finance_hub.security.password_rules.ports import PasswordRuleInterpreterUnavailable
from family_finance_hub.security.password_rules.provider_service import AIProviderService
from family_finance_hub.security.password_rules.schema import PasswordRule
from family_finance_hub.security.password_rules.service import PasswordRuleService


class MemorySecretStore:
    def __init__(self, values):
        self.values = values

    def get(self, reference):
        return self.values.get(reference)

    def set(self, reference, value):
        self.values[reference] = value

    def delete(self, reference):
        self.values.pop(reference, None)


def make_rule(transform="suffix", count=4, date_format="YYYYMMDD", separator=""):
    parts = [{
        "source": "national_id",
        "transform": transform,
        "start": None,
        "length": count,
        "date_format": None,
        "case": "upper",
    }]
    if date_format:
        parts.append({
            "source": "birthday",
            "transform": "date_format",
            "start": None,
            "length": None,
            "date_format": date_format,
            "case": "preserve",
        })
    return PasswordRule.model_validate({
        "version": 1,
        "status": "resolved",
        "candidates": [{"parts": parts, "separator": separator}],
    })


def test_extractor_sends_only_redacted_password_instruction_lines():
    extracted = PasswordInstructionExtractor().extract(
        PasswordInstructionContext(
            subject="信用卡電子帳單密碼說明",
            sender="person@example.test",
            filename="statement-A123456789.pdf",
            body=(
                "您好，附件為本期帳單。\n"
                "密碼規則：身分證字號末四碼 + 出生年月日 YYYYMMDD。\n"
                "身分證字號 A123456789，生日 19840302。\n"
                "消費明細：早餐 120 元。\n"
            ),
        ),
        sensitive_values=("A123456789", "1984-03-02"),
    )

    assert "密碼規則" in extracted
    assert "YYYYMMDD" in extracted
    assert "A123456789" not in extracted
    assert "19840302" not in extracted
    assert "120 元" not in extracted
    assert "person@example.test" not in extracted
    assert "statement-A123456789.pdf" not in extracted


def test_extractor_can_use_password_metadata_without_sending_email_or_account_numbers():
    extracted = PasswordInstructionExtractor().extract(
        PasswordInstructionContext(
            sender="Bank Password Notice <statements@example.test>",
            filename="password-rule-A123456789.pdf",
            body="附件密碼為生日月日與證件末四碼，帳號 987654321。",
        ),
        sensitive_values=("A123456789",),
    )

    assert "Bank Password Notice" in extracted
    assert "password-rule" in extracted
    assert "statements@example.test" not in extracted
    assert "987654321" not in extracted
    assert "A123456789" not in extracted


def test_extractor_masks_compact_dates_inside_chinese_and_assigned_password_literals():
    extracted = PasswordInstructionExtractor().extract(PasswordInstructionContext(
        body="密碼為生日19840302加證號末四碼。Password is validABC9!"
    ))

    assert "19840302" not in extracted
    assert "validABC9!" not in extracted
    assert "證號末四碼" in extracted


def test_extractor_keeps_neighboring_multiline_password_instructions_without_transaction_text():
    extracted = PasswordInstructionExtractor().extract(PasswordInstructionContext(
        body=(
            "<p>附件密碼規則如下：</p>"
            "<p>身分證後四碼</p>"
            "<p>加出生日期 YYYYMMDD</p>"
            "<p>消費明細：早餐 120 元。</p>"
        ),
        subject="本期信用卡帳單",
    ), sensitive_values=("20991231",))

    assert "附件密碼規則如下" in extracted
    assert "身分證後四碼" in extracted
    assert "出生日期 YYYYMMDD" in extracted
    assert "消費明細" not in extracted
    assert "120 元" not in extracted


def test_extractor_preserves_inline_html_text_and_plain_text_line_breaks():
    extractor = PasswordInstructionExtractor()
    html = extractor.extract(PasswordInstructionContext(
        body="<p>密<span>碼</span>規則：</p><p>身分證後四碼</p><p>生日 YYYYMMDD</p>",
    ))
    plain = extractor.extract(PasswordInstructionContext(
        body="附件密碼規則如下：\n身分證後四碼\n加出生日期 YYYYMMDD",
    ))

    assert "密碼規則" in html
    assert "身分證後四碼" in html
    assert "\n身分證後四碼" in html
    assert "附件密碼規則如下：\n身分證後四碼" in plain


def test_extractor_preserves_inline_spacing_and_table_row_context():
    extracted = PasswordInstructionExtractor().extract(PasswordInstructionContext(
        body=(
            "<table>"
            "<tr><td>Password</td><td>rule: last four digits</td></tr>"
            "<tr><td>消費摘要</td><td>synthetic shop 123 元</td></tr>"
            "</table>"
            "<p>Password <b>rule</b>: use the final four digits</p>"
        ),
    ))

    assert "Password rule: last four digits" in extracted
    assert "Password rule: use the final four digits" in extracted
    assert "synthetic shop" not in extracted


def test_extractor_keeps_repeated_lines_from_overlapping_context_windows():
    extracted = PasswordInstructionExtractor().extract(PasswordInstructionContext(
        body=(
            "密碼規則如下：\n"
            "請使用末四碼\n"
            "共同規則\n"
            "密碼提示：\n"
            "再加出生月日\n"
            "共同規則"
        ),
    ))

    assert extracted.count("共同規則") == 2


def test_extractor_masks_sensitive_values_before_applying_output_limit():
    secret = "SECRETLEAK"
    prefix = "Password instructions: "
    body = prefix + ("x" * (1194 - len(prefix))) + secret
    extracted = PasswordInstructionExtractor().extract(
        PasswordInstructionContext(body=body),
        sensitive_values=(secret,),
    )

    assert len(extracted) <= 1200
    assert "SECRET" not in extracted


def test_password_composer_uses_explicit_roc_date_format_and_never_expands_candidates():
    rule = PasswordRule.model_validate({
        "version": 1,
        "status": "ambiguous",
        "candidates": [
            {"parts": [
                {"source": "national_id", "transform": "suffix", "start": None, "length": 4, "date_format": None, "case": "upper"},
                {"source": "birthday", "transform": "date_format", "start": None, "length": None, "date_format": "ROCYYYMMDD", "case": "preserve"},
            ], "separator": ""},
            {"parts": [
                {"source": "birthday", "transform": "date_format", "start": None, "length": None, "date_format": "YYYYMMDD", "case": "preserve"},
            ], "separator": ""},
        ],
    })
    store = MemorySecretStore({"national": "A123456789", "birthday": "1984-03-02"})

    candidates = PasswordComposer(store).compose(rule, "national", "birthday")

    assert candidates == ("67890730302", "19840302")
    assert len(candidates) <= 3


@pytest.mark.parametrize(
    ("source", "values", "expected"),
    [
        ("national_id", {"national": "A123456789"}, "6789"),
        ("birthday", {"birthday": "1984-03-02"}, "840302"),
    ],
)
def test_password_composer_uses_only_the_secret_named_by_the_rule(source, values, expected):
    part = (
        {"source": "national_id", "transform": "suffix", "start": None, "length": 4, "date_format": None, "case": "upper"}
        if source == "national_id"
        else {"source": "birthday", "transform": "date_format", "start": None, "length": None, "date_format": "YYMMDD", "case": "preserve"}
    )
    rule = PasswordRule.model_validate({
        "version": 1, "status": "resolved", "candidates": [{"parts": [part], "separator": ""}],
    })

    candidates, indexes = PasswordComposer(MemorySecretStore(values)).compose_with_rule_indexes(
        rule, "national", "birthday",
    )

    assert candidates == (expected,)
    assert indexes == (0,)


@pytest.mark.parametrize(
    ("filtered_entries", "expected_candidates", "expected_indexes"),
    [
        ("duplicate", ("A12319840302", "678919840302"), (0, 2)),
        ("empty", ("A12319840302", "678919840302"), (1, 2)),
        ("empty_and_duplicate", ("678919840302",), (1,)),
    ],
)
def test_password_composer_preserves_original_indexes_after_filtering(
    filtered_entries, expected_candidates, expected_indexes,
):
    prefix = make_rule(transform="prefix").model_dump(mode="json")["candidates"][0]
    suffix = make_rule().model_dump(mode="json")["candidates"][0]
    leading = make_rule(transform="prefix").model_dump(mode="json")["candidates"][0]
    if filtered_entries == "duplicate":
        leading["parts"][0]["case"] = "preserve"
        rules = [leading, prefix, suffix]
    else:
        leading["parts"][0].update(transform="substring", start=100)
        rules = [leading, prefix, suffix] if filtered_entries == "empty" else [leading, suffix, suffix]
    rule = PasswordRule.model_validate({"version": 1, "status": "ambiguous", "candidates": rules})
    composer = PasswordComposer(MemorySecretStore({"national": "A123456789", "birthday": "1984-03-02"}))

    candidates, rule_indexes = composer.compose_with_rule_indexes(rule, "national", "birthday")

    assert candidates == expected_candidates
    assert rule_indexes == expected_indexes
    assert composer.compose(rule, "national", "birthday") == candidates
    for password, rule_index in zip(candidates, rule_indexes, strict=True):
        selected_rule = PasswordRule(version=1, status="resolved", candidates=[rule.candidates[rule_index]])
        assert composer.compose(selected_rule, "national", "birthday") == (password,)


@pytest.mark.parametrize("values", [
    {},
    {"national": "A123456789"},
    {"birthday": "1984-03-02"},
    {"national": "A123456789", "birthday": "invalid-date"},
])
def test_password_composer_returns_empty_mapping_when_secrets_are_unavailable(values):
    composer = PasswordComposer(MemorySecretStore(values))
    rule = make_rule()

    assert composer.compose_with_rule_indexes(rule, "national", "birthday") == ((), ())
    assert composer.compose(rule, "national", "birthday") == ()


def test_password_composer_returns_empty_mapping_for_unsupported_rule():
    composer = PasswordComposer(MemorySecretStore({"national": "A123456789", "birthday": "1984-03-02"}))
    rule = PasswordRule(version=1, status="unsupported", candidates=[])

    assert composer.compose_with_rule_indexes(rule, "national", "birthday") == ((), ())
    assert composer.compose(rule, "national", "birthday") == ()


def test_password_rule_schema_rejects_unlisted_operations_and_excess_candidates():
    rule = make_rule()
    payload = rule.model_dump(mode="json")
    payload["candidates"][0]["parts"][0]["transform"] = "python"
    try:
        PasswordRule.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("unlisted operations must be rejected")

    payload = {
        "version": 1,
        "status": "ambiguous",
        "candidates": [{"parts": [{
            "source": "national_id", "transform": "full", "start": None,
            "length": None, "date_format": None, "case": "preserve",
        }], "separator": ""}] * 4,
    }
    try:
        PasswordRule.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("candidate limit must be enforced")


def test_password_rule_is_persisted_only_as_verified_dsl_and_fingerprint(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'rules.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    service = PasswordRuleService()
    context = {"institution": "測試銀行", "document_type": "PDF statement"}
    fingerprint = service.fingerprint("密碼為身分證末四碼", context)
    rule = make_rule(date_format=None)

    with factory.begin() as session:
        session.add(SecretProfile(
            id="secret-profile", display_name="成員",
            national_id_credential_ref="ref-id", birthday_credential_ref="ref-birthday",
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        ))
        session.add(DocumentSecurityProfile(
            id="document-profile", display_name="測試銀行卡片", institution="測試銀行",
            secret_profile_id="secret-profile", created_at=datetime.now(timezone.utc),
        ))
        service.save_verified(session, "document-profile", fingerprint, rule)

    with factory() as session:
        stored = session.scalar(select(PasswordRuleRecord))
        assert stored.rule_json == rule.model_dump(mode="json")
        assert stored.instruction_fingerprint == fingerprint
        assert service.get_verified(session, "document-profile", fingerprint) == rule
        assert service.get_verified(session, "document-profile", "f" * 64) is None
        db_text = json.dumps(stored.rule_json)
        assert "national_id_value" not in db_text
        assert "birthday_value" not in db_text
    engine.dispose()


def test_openai_adapter_sends_only_rule_context_and_disables_response_storage(monkeypatch):
    captured = {}
    rule_json = make_rule().model_dump(mode="json")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"output_text": json.dumps(rule_json)}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("family_finance_hub.security.password_rules.openai_responses.urlopen", fake_urlopen)
    result = OpenAIResponsesInterpreter("sk-test-secret", "configured-model").interpret(
        "身分證末四碼加出生日期 YYYYMMDD",
        {"institution": "測試銀行", "document_type": "PDF statement"},
    )

    assert result == PasswordRule.model_validate(rule_json)
    assert captured["payload"]["store"] is False
    user_text = captured["payload"]["input"][1]["content"][0]["text"]
    assert "身分證末四碼" in user_text
    assert "national_id_value" not in user_text
    assert "birthday_value" not in user_text
    assert "sk-test-secret" not in json.dumps(captured["payload"])


def test_groq_adapter_uses_responses_schema_without_unsupported_storage(monkeypatch):
    captured = {}
    rule_json = make_rule().model_dump(mode="json")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"output_text": json.dumps(rule_json)}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("family_finance_hub.security.password_rules.openai_responses.urlopen", fake_urlopen)
    result = GroqResponsesInterpreter("gsk-test-secret", "openai/gpt-oss-20b").interpret(
        "身分證末四碼加出生日期 YYYYMMDD",
        {"document_type": "PDF statement"},
    )

    assert result == PasswordRule.model_validate(rule_json)
    assert captured["request"].full_url == "https://api.groq.com/openai/v1/responses"
    assert captured["payload"]["model"] == "openai/gpt-oss-20b"
    assert "store" not in captured["payload"]
    assert captured["payload"]["text"]["format"]["strict"] is True
    assert "gsk-test-secret" not in json.dumps(captured["payload"])


@pytest.mark.parametrize(
    ("provider", "interpreter_type"),
    [("groq", GroqResponsesInterpreter), ("openai", OpenAIResponsesInterpreter)],
)
def test_ai_provider_service_dispatches_configured_provider(tmp_path, provider, interpreter_type):
    engine = make_engine(f"sqlite:///{(tmp_path / f'{provider}.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    store = MemorySecretStore({"secret-ref": "test-api-key"})

    with factory.begin() as session:
        session.add(AIProviderProfile(
            id="openai",
            provider=provider,
            model="openai/gpt-oss-20b" if provider == "groq" else "gpt-4.1-mini",
            api_key_credential_ref="secret-ref",
        ))

    with factory() as session:
        interpreter = AIProviderService(store).interpreter(session)
        assert isinstance(interpreter, interpreter_type)
    engine.dispose()


def test_ai_provider_service_keeps_legacy_profile_id_when_switching_to_groq(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'configure.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    store = MemorySecretStore({"old-ref": "old-key"})

    with factory() as session:
        profile = AIProviderService(store).configure(
            session,
            "gsk-test-key",
            "openai/gpt-oss-20b",
            provider="groq",
        )
        assert profile.id == "openai"
        assert profile.provider == "groq"
        assert profile.model == "openai/gpt-oss-20b"

    with factory() as session:
        stored = session.get(AIProviderProfile, "openai")
        assert stored.provider == "groq"
        assert store.get(stored.api_key_credential_ref) == "gsk-test-key"
    engine.dispose()


def test_ai_provider_service_rejects_unknown_provider(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'invalid-provider.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)

    with factory() as session:
        with pytest.raises(ValueError, match="只支援 Groq 或 OpenAI"):
            AIProviderService(MemorySecretStore({})).configure(
                session,
                "test-key",
                "test-model",
                provider="unknown",
            )
    engine.dispose()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, "AI 請求格式不被目前模型接受"),
        (401, "AI API key 無效"),
        (403, "AI API key 沒有使用此模型的權限"),
        (429, "AI API 回應 429"),
        (500, "AI 密碼規則服務目前無法使用"),
    ],
)
def test_openai_adapter_reports_safe_http_failure(monkeypatch, status, expected):
    from io import BytesIO
    from urllib.error import HTTPError

    from family_finance_hub.security.password_rules.ports import PasswordRuleInterpreterUnavailable

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, status, "private upstream details", {}, BytesIO(b"private response"))

    monkeypatch.setattr("family_finance_hub.security.password_rules.openai_responses.urlopen", fake_urlopen)
    with pytest.raises(PasswordRuleInterpreterUnavailable) as exc:
        OpenAIResponsesInterpreter("sk-test-secret", "configured-model").interpret(
            "身分證末四碼", {"document_type": "PDF"}
        )
    assert expected in str(exc.value)
    assert "private" not in str(exc.value)
    assert "sk-test-secret" not in str(exc.value)


@pytest.mark.parametrize("error_code", ["insufficient_quota", "credit_balance_exhausted", "project_spend_limit_exceeded"])
def test_openai_adapter_identifies_quota_without_exposing_upstream_body(monkeypatch, error_code):
    from io import BytesIO
    from urllib.error import HTTPError

    from family_finance_hub.security.password_rules.ports import PasswordRuleInterpreterUnavailable

    def fake_urlopen(request, timeout):
        body = json.dumps({"error": {"code": error_code, "message": "private upstream details"}}).encode()
        raise HTTPError(request.full_url, 429, "private upstream details", {}, BytesIO(body))

    monkeypatch.setattr("family_finance_hub.security.password_rules.openai_responses.urlopen", fake_urlopen)
    with pytest.raises(PasswordRuleInterpreterUnavailable) as exc:
        OpenAIResponsesInterpreter("sk-test-secret", "configured-model").interpret(
            "身分證末四碼", {"document_type": "PDF"}
        )
    assert "OpenAI API 額度不足" in str(exc.value)
    assert "private" not in str(exc.value)
