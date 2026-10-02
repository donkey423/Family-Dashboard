# Secure Documents Skill

## Purpose

Turn a local or Gmail-delivered PDF into a trustworthy local `DocumentIR`, including password-protected PDFs, without exposing secrets to the agent or cloud services.

This skill is intentionally **document-type agnostic**. Credit-card statements, insurance documents, bank statements, tax documents, receipts, and other PDFs are downstream use cases. The core stops at secure extraction.

## Trigger

Use this skill when the user asks to read, inspect, extract, summarize, organize, or understand a PDF/document, especially when the PDF may be password protected.

## Non-goals for v0.1

- No financial transaction classification.
- No insurance schema.
- No Excel/dashboard output.
- No cloud AI parsing.
- No OCR fallback yet.
- No automatic guessing of unknown passwords.

## Required workflow

1. **Acquire bytes**
   - Prefer direct attachment bytes from the source connector.
   - For Gmail browser fallback, use the browser download only when direct attachment bytes are unavailable.
   - Never depend on a Windows Save As dialog.

2. **Create SourceDocument**
   - Compute SHA-256 from the original bytes.
   - Keep the original encrypted PDF as the replayable source.
   - Never save a decrypted PDF copy.

3. **Unlock locally if needed**
   - Read only the minimum password-hint text needed to understand the password rule.
   - Do not ask the user to paste national ID, birthday, PDF password, or other secret values into chat.
   - Convert an explicit hint into the symbolic PasswordRule DSL.
   - The rule may reference `national_id` and/or `birthday`, but must not contain the actual secret values.
   - Compose at most 3 password candidates locally using Windows Credential Manager.
   - If the hint is ambiguous, return `needs_review`; do not invent permutations or brute force.

4. **Extract**
   - Decrypt only in process memory.
   - Extract native text and position-aware text blocks.
   - Produce versioned `DocumentIR`.
   - Record extraction method and warnings.

5. **Return status**
   - `verified`: PDF opened and native extraction completed.
   - `needs_review`: password rule/candidate unavailable or extraction quality is insufficient.
   - `unsupported`: input is not a supported PDF or is malformed.

6. **Downstream understanding**
   - Domain-specific interpretation happens after `DocumentIR`.
   - Facts derived later should retain evidence pointers back to page/block IDs.

## Security invariants

- Secrets never enter `SKILL.md`, repo files, normal logs, IR JSON, SQLite, or model prompts.
- Real password candidates exist only in local process memory.
- Do not log candidate values or secret values.
- Maximum password candidates: 3.
- No brute force.
- No automatic paid/cloud fallback.
- Do not persist decrypted PDFs.
- A successful decrypt does not mean the extracted content is semantically correct.

## CLI

Inspect a PDF:

```powershell
secure-documents inspect C:\path\document.pdf
```

Extract an unencrypted PDF:

```powershell
secure-documents extract C:\path\document.pdf --ir-out C:\path\document.ir.json
```

For an encrypted PDF, pass a symbolic rule JSON and a local config containing only credential references:

```powershell
secure-documents extract C:\path\document.pdf `
  --rule C:\path\rule.json `
  --config C:\path\secure-documents.toml `
  --ir-out C:\path\document.ir.json
```

Import the **credential references only** from an existing Family Dashboard SQLite DB:

```powershell
secure-documents import-family-hub-refs `
  --db C:\path\family-finance-hub-live.db `
  --config C:\path\secure-documents.toml
```

This command does not read or export the actual national ID/birthday values.

## PasswordRule DSL example

Full national ID:

```json
{
  "status": "resolved",
  "candidates": [
    {
      "segments": [
        {"kind": "secret", "secret": "national_id", "transform": "upper"}
      ]
    }
  ]
}
```

Birthday as YYYYMMDD:

```json
{
  "status": "resolved",
  "candidates": [
    {
      "segments": [
        {"kind": "secret", "secret": "birthday", "date_format": "YYYYMMDD"}
      ]
    }
  ]
}
```

See `references/SECURITY.md`, `references/DOCUMENT_IR.md`, and `references/FAILURE_POLICY.md` before extending the core.
