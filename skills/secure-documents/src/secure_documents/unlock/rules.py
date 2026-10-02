from __future__ import annotations

from datetime import date
from hashlib import sha256

from ..contracts import LiteralSegment, PasswordRule, SecretSegment
from .ports import SecretStore


def rule_fingerprint(rule: PasswordRule) -> str:
    payload = rule.model_dump_json(exclude_none=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def compose_candidates(
    rule: PasswordRule,
    store: SecretStore,
    *,
    national_id_ref: str | None,
    birthday_ref: str | None,
) -> tuple[str, ...]:
    values: dict[str, str | None] = {
        "national_id": store.get(national_id_ref) if national_id_ref else None,
        "birthday": store.get(birthday_ref) if birthday_ref else None,
    }
    output: list[str] = []
    for candidate in rule.candidates:
        parts: list[str] = []
        usable = True
        for segment in candidate.segments:
            if isinstance(segment, LiteralSegment):
                parts.append(segment.value)
                continue
            value = values.get(segment.secret)
            if not value:
                usable = False
                break
            value = _format_secret(value, segment)
            if segment.start is not None or segment.end is not None:
                value = value[segment.start : segment.end]
            if not value:
                usable = False
                break
            parts.append(value)
        if usable:
            password = "".join(parts)
            if password and password not in output:
                output.append(password)
    if len(output) > 3:
        raise ValueError("password candidate limit exceeded")
    return tuple(output)


def _format_secret(value: str, segment: SecretSegment) -> str:
    if segment.secret == "birthday":
        parsed = date.fromisoformat(value)
        formats = {
            None: parsed.isoformat(),
            "ISO": parsed.isoformat(),
            "YYYYMMDD": parsed.strftime("%Y%m%d"),
            "YYMMDD": parsed.strftime("%y%m%d"),
            "MMDD": parsed.strftime("%m%d"),
        }
        value = formats[segment.date_format]
    if segment.transform == "upper":
        value = value.upper()
    elif segment.transform == "lower":
        value = value.lower()
    elif segment.transform == "digits_only":
        value = "".join(character for character in value if character.isdigit())
    return value
