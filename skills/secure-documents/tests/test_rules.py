from secure_documents.contracts import PasswordRule
from secure_documents.unlock.rules import compose_candidates
from secure_documents.unlock.stores import MemorySecretStore


def test_compose_full_national_id_and_birthday():
    store = MemorySecretStore({"id-ref": "a123456789", "dob-ref": "1991-07-11"})
    rule = PasswordRule.model_validate({
        "status": "ambiguous",
        "candidates": [
            {"segments": [{"kind": "secret", "secret": "national_id", "transform": "upper"}]},
            {"segments": [{"kind": "secret", "secret": "birthday", "date_format": "YYYYMMDD"}]},
        ],
    })
    assert compose_candidates(rule, store, national_id_ref="id-ref", birthday_ref="dob-ref") == (
        "A123456789",
        "19910711",
    )
