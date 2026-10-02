from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pypdf import PdfReader

from .acquisition.local_file import read_local_pdf
from .config import LocalConfig, load_config, write_config
from .contracts import PasswordRule
from .errors import SecureDocumentError
from .extraction.service import extract_document
from .integration.family_hub import read_family_hub_credential_refs
from .unlock.stores import WindowsCredentialStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="secure-documents")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_cmd = sub.add_parser("inspect", help="Inspect PDF metadata without extracting secrets")
    inspect_cmd.add_argument("pdf", type=Path)

    extract_cmd = sub.add_parser("extract", help="Unlock locally if necessary and create DocumentIR")
    extract_cmd.add_argument("pdf", type=Path)
    extract_cmd.add_argument("--rule", type=Path)
    extract_cmd.add_argument("--config", type=Path)
    extract_cmd.add_argument("--ir-out", type=Path)

    import_cmd = sub.add_parser("import-family-hub-refs", help="Import credential references only")
    import_cmd.add_argument("--db", required=True, type=Path)
    import_cmd.add_argument("--config", required=True, type=Path)
    import_cmd.add_argument("--service-name", default="family-finance-hub")
    return parser


def _inspect(path: Path) -> dict:
    source, content = read_local_pdf(path)
    reader = PdfReader(path, strict=False)
    return {
        "status": "verified",
        "document_id": source.document_id,
        "sha256": source.sha256,
        "filename": source.filename,
        "size_bytes": source.size_bytes,
        "encrypted": bool(reader.is_encrypted),
    }


def _extract(args) -> dict:
    source, content = read_local_pdf(args.pdf)
    rule = None
    config = None
    store = None
    if args.rule:
        rule = PasswordRule.model_validate_json(args.rule.read_text(encoding="utf-8"))
        if not args.config:
            raise ValueError("--config is required when --rule is supplied")
        config = load_config(args.config)
        store = WindowsCredentialStore(config.credential_service)
    ir = extract_document(
        source,
        content,
        rule=rule,
        secret_store=store,
        national_id_ref=config.national_id_ref if config else None,
        birthday_ref=config.birthday_ref if config else None,
    )
    if args.ir_out:
        args.ir_out.parent.mkdir(parents=True, exist_ok=True)
        args.ir_out.write_text(ir.model_dump_json(indent=2), encoding="utf-8")
    return {
        "status": "verified",
        "document_id": ir.document_id,
        "sha256": ir.source_sha256,
        "page_count": ir.page_count,
        "was_encrypted": ir.unlock.was_encrypted,
        "warnings": list(ir.extraction.warnings),
        "ir_out": str(args.ir_out) if args.ir_out else None,
    }


def _import_refs(args) -> dict:
    national_id_ref, birthday_ref = read_family_hub_credential_refs(args.db)
    if not national_id_ref and not birthday_ref:
        return {"status": "needs_review", "reason": "personal_unlock_profile_not_found"}
    config = LocalConfig(
        credential_service=args.service_name,
        national_id_ref=national_id_ref,
        birthday_ref=birthday_ref,
    )
    write_config(args.config, config)
    return {
        "status": "verified",
        "config": str(args.config),
        "national_id_ref_available": bool(national_id_ref),
        "birthday_ref_available": bool(birthday_ref),
        "secret_values_read": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = _inspect(args.pdf)
        elif args.command == "extract":
            result = _extract(args)
        else:
            result = _import_refs(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "verified" else 2
    except SecureDocumentError as error:
        print(json.dumps({"status": "needs_review", "code": error.code, "message": str(error)}, ensure_ascii=False, indent=2))
        return 2
    except Exception as error:
        print(json.dumps({"status": "unsupported", "code": "unexpected_error", "message": str(error)}, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
