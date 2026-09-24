from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import PasswordRuleRecord, utc_now
from .schema import PasswordRule


class PasswordRuleService:
    def fingerprint(self, instruction: str, context: dict[str, str]) -> str:
        material = json.dumps(
            {"instruction": instruction, "context": context},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(material.encode("utf-8")).hexdigest()

    def get_verified(
        self,
        session: Session,
        profile_id: str,
        instruction_fingerprint: str,
    ) -> PasswordRule | None:
        row = session.scalar(
            select(PasswordRuleRecord).where(
                PasswordRuleRecord.document_security_profile_id == profile_id,
                PasswordRuleRecord.rule_version == 1,
                PasswordRuleRecord.instruction_fingerprint == instruction_fingerprint,
            )
        )
        if row is None:
            return None
        try:
            return PasswordRule.model_validate(row.rule_json)
        except ValueError:
            session.delete(row)
            return None

    def save_verified(
        self,
        session: Session,
        profile_id: str,
        instruction_fingerprint: str,
        rule: PasswordRule,
    ) -> None:
        if rule.status != "resolved" or rule.version != 1:
            return
        row = session.scalar(
            select(PasswordRuleRecord).where(
                PasswordRuleRecord.document_security_profile_id == profile_id,
                PasswordRuleRecord.rule_version == rule.version,
                PasswordRuleRecord.instruction_fingerprint == instruction_fingerprint,
            )
        )
        if row is None:
            row = PasswordRuleRecord(
                id=str(uuid4()),
                document_security_profile_id=profile_id,
                rule_version=rule.version,
                instruction_fingerprint=instruction_fingerprint,
                rule_json=rule.model_dump(mode="json"),
                verified_at=utc_now(),
            )
            session.add(row)
        else:
            row.rule_json = rule.model_dump(mode="json")
            row.verified_at = utc_now()
