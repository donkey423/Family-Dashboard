---
name: secure-documents
description: Securely unlock and extract local or Gmail-delivered PDFs into versioned DocumentIR using local secrets; use when reading, inspecting, summarizing, organizing, or understanding PDFs/documents, especially password-protected files.
---

# Codex repository entry point

This is the repo-scoped Codex discovery entry point for the canonical Secure Documents skill.

Before doing any Secure Documents work:

1. Read `../../../skills/secure-documents/SKILL.md` and treat it as authoritative.
2. Read only the supporting references needed for the task from `../../../skills/secure-documents/references/`.
3. Run packaged scripts and Python code from `../../../skills/secure-documents/`; do not duplicate the implementation under `.codex/skills/`.
4. Preserve the canonical security invariants: secrets stay local, decrypted PDFs are not persisted, password candidates are capped at 3, and ambiguous cases fail closed.
5. Do not claim Windows Credential Manager or real encrypted-PDF runtime validation unless it was actually run in the user's Windows logon session.

The canonical package is intentionally kept outside `.codex/skills/` so Codex discovery and the reusable implementation have a single source of truth.
