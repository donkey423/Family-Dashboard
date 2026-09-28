from datetime import date

from ..secrets.ports import SecretStore
from .schema import PasswordCandidateRule, PasswordRule


class PasswordComposer:
    def __init__(self, secret_store: SecretStore):
        self.secret_store = secret_store

    def compose(
        self,
        rule: PasswordRule,
        national_id_reference: str,
        birthday_reference: str,
    ) -> tuple[str, ...]:
        candidates, _ = self.compose_with_rule_indexes(
            rule, national_id_reference, birthday_reference
        )
        return candidates

    def compose_with_rule_indexes(
        self,
        rule: PasswordRule,
        national_id_reference: str,
        birthday_reference: str,
    ) -> tuple[tuple[str, ...], tuple[int, ...]]:
        if rule.status == "unsupported":
            return (), ()
        national_id = self.secret_store.get(national_id_reference)
        birthday_text = self.secret_store.get(birthday_reference)
        if not national_id or not birthday_text:
            return (), ()
        try:
            birthday = date.fromisoformat(birthday_text)
        except ValueError:
            return (), ()
        values = {"national_id": national_id, "birthday": birthday}
        candidates: list[str] = []
        rule_indexes: list[int] = []
        for rule_index, candidate in enumerate(rule.candidates[:3]):
            value = self._compose_candidate(candidate, values)
            if value and value not in candidates:
                candidates.append(value)
                rule_indexes.append(rule_index)
        return tuple(candidates[:3]), tuple(rule_indexes[:3])

    @classmethod
    def _compose_candidate(cls, candidate: PasswordCandidateRule, values: dict[str, str | date]) -> str:
        parts: list[str] = []
        for part in candidate.parts:
            value = values[part.source]
            if part.transform == "date_format":
                assert isinstance(value, date) and part.date_format is not None
                segment = cls._format_birthday(value, part.date_format)
            else:
                assert isinstance(value, str)
                if part.transform == "prefix":
                    segment = value[:part.length]
                elif part.transform == "suffix":
                    segment = value[-part.length:]
                elif part.transform == "substring":
                    segment = value[part.start:part.start + part.length]
                else:
                    segment = value
            if part.case == "upper":
                segment = segment.upper()
            elif part.case == "lower":
                segment = segment.lower()
            if not segment:
                return ""
            parts.append(segment)
        return candidate.separator.join(parts)

    @staticmethod
    def _format_birthday(value: date, pattern: str) -> str:
        if pattern == "YYYYMMDD":
            return value.strftime("%Y%m%d")
        if pattern == "YYMMDD":
            return value.strftime("%y%m%d")
        if pattern == "MMDD":
            return value.strftime("%m%d")
        if pattern == "DDMM":
            return value.strftime("%d%m")
        roc_year = value.year - 1911
        if roc_year <= 0:
            raise ValueError("Birthday predates the supported Taiwan calendar")
        year = f"{roc_year:03d}" if pattern == "ROCYYYMMDD" else f"{roc_year % 100:02d}"
        return f"{year}{value:%m%d}"
