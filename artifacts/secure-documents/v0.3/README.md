# Secure Documents Codex Skill v0.3 — install artifact

This branch carries the verified standalone user-scoped Codex Skill artifact.

## Canonical artifact

The ZIP is stored as six Base64 text parts because the GitHub connector cannot safely round-trip binary ZIP bytes.

Files, in order:

- `secure-documents-codex-skill-v0.3.zip.b64.part00`
- `secure-documents-codex-skill-v0.3.zip.b64.part01`
- `secure-documents-codex-skill-v0.3.zip.b64.part02`
- `secure-documents-codex-skill-v0.3.zip.b64.part03`
- `secure-documents-codex-skill-v0.3.zip.b64.part04`
- `secure-documents-codex-skill-v0.3.zip.b64.part05`

Concatenate the six files exactly in lexical order, Base64-decode once, and write the bytes as:

`secure-documents-codex-skill-v0.3.zip`

Expected decoded ZIP:

- bytes: `21644`
- SHA-256: `2edd94420bd960438e412d858781d0144d8f23dd6e78820e9dacfbc2106bc0f1`

If the decoded ZIP hash differs, stop and do not install.

## Install target

`$HOME\.codex\skills\secure-documents\`

Runtime:

`%LOCALAPPDATA%\secure-documents\venv`

The installer backs up an existing Skill directory before replacement.

## v0.3 scope

- standalone user-scoped Codex Skill
- Windows Credential Manager backend
- service: `personal-secrets`
- refs:
  - `identity:default:national-id`
  - `identity:default:birthday`
- safe `doctor` command
- local hidden-input `setup`
- memory-only PDF decryption
- native PDF extraction to versioned `DocumentIR`
- fail closed on ambiguous password rules
- no project runtime dependency

## Local validation before publishing

- `pytest -q`: **14 passed**
- `python -m compileall -q src`: PASS
- `PYTHONPATH=src python -m secure_documents.cli --help`: PASS
- ZIP structure check: PASS
- synthetic encrypted-PDF tests: PASS
- no real Windows Credential Manager secret was read during packaging
