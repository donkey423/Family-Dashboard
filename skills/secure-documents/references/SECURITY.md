# Security Contract

## Secrets

Secret values include national ID, birthday, PDF passwords, API keys, OAuth tokens, and similar credentials.

They must not be stored in:

- source control
- `SKILL.md`
- IR JSON
- ordinary SQLite tables
- logs
- command-line arguments containing the actual value
- model prompts

The v0.1 config stores only credential references. The default Windows Credential Manager service is `family-finance-hub` so the skill can reuse existing local secrets without copying their values.

## Password rules

Password rules are symbolic. Example: `national_id[0:1].upper + national_id[1:]` is allowed; the resulting password is not.

Rules may generate no more than 3 candidates. Ambiguity beyond that is a review condition, not permission to guess.

## Decryption

- Keep original encrypted bytes.
- Decrypt in memory.
- Do not write a decrypted PDF to disk.
- Do not include successful password/candidate in result objects.

## Agent boundary

The agent may see a minimal password hint from the source message and may produce a symbolic rule. It must not receive the referenced secret values.

## Logging

Safe fields include document ID, SHA-256, page count, status, rule fingerprint, extractor version, and warning codes. Never log secret values, raw candidates, or full private document text by default.
