import pytest
from pydantic import ValidationError

from secure_documents.contracts import PasswordRule


def test_resolved_rule_requires_one_candidate():
    with pytest.raises(ValidationError):
        PasswordRule.model_validate({
            "status": "resolved",
            "candidates": [
                {"segments": [{"kind": "literal", "value": "a"}]},
                {"segments": [{"kind": "literal", "value": "b"}]},
            ],
        })


def test_rule_hard_limits_candidates_to_three():
    with pytest.raises(ValidationError):
        PasswordRule.model_validate({
            "status": "ambiguous",
            "candidates": [
                {"segments": [{"kind": "literal", "value": str(i)}]}
                for i in range(4)
            ],
        })
