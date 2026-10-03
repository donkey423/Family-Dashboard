# Secure Documents Codex Skill v0.3 — verified install artifact

This branch carries the verified standalone user-scoped Codex Skill artifact.

## Canonical artifact

The ZIP is stored as Base64 text parts because the GitHub connector cannot safely round-trip binary ZIP bytes.

Use these files in this exact order:

1. `secure-documents-codex-skill-v0.3.zip.b64.part00`
2. `secure-documents-codex-skill-v0.3.zip.b64.part01`
3. `secure-documents-codex-skill-v0.3.zip.b64.part02`
4. `secure-documents-codex-skill-v0.3.zip.b64.part03a`
5. `secure-documents-codex-skill-v0.3.zip.b64.part03b`
6. `secure-documents-codex-skill-v0.3.zip.b64.part04`
7. `secure-documents-codex-skill-v0.3.zip.b64.part05`

Do not use any other part names.

Concatenate the seven files exactly in that order, Base64-decode once, and write:

`secure-documents-codex-skill-v0.3.zip`

Expected decoded ZIP:

- bytes: `21644`
- SHA-256: `2edd94420bd960438e412d858781d0144d8f23dd6e78820e9dacfbc2106bc0f1`

A helper is included:

`reconstruct.ps1`

Run it from this artifact directory. It refuses to continue if the reconstructed ZIP size or SHA-256 differs.

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

## Validation

Local package validation before publishing:

- `pytest -q`: **14 passed**
- `python -m compileall -q src`: PASS
- `PYTHONPATH=src python -m secure_documents.cli --help`: PASS
- ZIP structure: PASS
- synthetic encrypted-PDF E2E: PASS

Remote artifact verification after upload:

- Base64 parts total length: `28860`
- decoded ZIP bytes: `21644`
- reconstructed remote SHA-256: `2edd94420bd960438e412d858781d0144d8f23dd6e78820e9dacfbc2106bc0f1`
- remote checksum match: **PASS**

No real Windows Credential Manager secret was read during packaging or remote verification.
