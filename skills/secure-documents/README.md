# Secure Documents Skill v0.1

A local-first foundation for safely unlocking and extracting PDFs into a versioned, document-type-neutral intermediate representation (`DocumentIR`).

The package is deliberately small. It does not know what a credit-card statement or insurance policy is. Those belong in downstream domain plugins.

## What v0.1 does

- Reads PDF bytes from a local file.
- Computes SHA-256 and source metadata.
- Detects PDF encryption.
- Supports a symbolic password-rule DSL.
- Reads referenced secret values from Windows Credential Manager via `keyring` when installed.
- Reuses the existing Family Dashboard Credential Manager service name (`family-finance-hub`) by default.
- Tries no more than 3 locally composed password candidates.
- Decrypts in memory only.
- Extracts page text and position-aware text blocks with `pypdf`.
- Produces versioned `DocumentIR` JSON.
- Can import only credential references from the existing Family Dashboard SQLite DB.

## What it intentionally does not do yet

- OCR.
- Table reconstruction.
- Document classification.
- Credit-card or insurance parsing.
- Cloud AI.
- RAG/vector database.
- Dashboard/Excel output.

## Install for development

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[windows,dev]"
pytest -q
```

On non-Windows systems, omit `windows`; unencrypted extraction and tests still work.

## Architecture

```text
SourceDocument
     ↓
PasswordRule + local SecretStore
     ↓
UnlockResult
     ↓
Native PDF Extraction
     ↓
DocumentIR
     ↓
Downstream domain plugins / Q&A
```

The architectural rule is: **prepare for many document types; implement only the current core capability.**
