from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class LocalConfig:
    credential_service: str = "family-finance-hub"
    national_id_ref: str | None = None
    birthday_ref: str | None = None


def load_config(path: Path) -> LocalConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    secrets = data.get("secrets", {})
    return LocalConfig(
        credential_service=str(secrets.get("service_name") or "family-finance-hub"),
        national_id_ref=secrets.get("national_id_ref") or None,
        birthday_ref=secrets.get("birthday_ref") or None,
    )


def write_config(path: Path, config: LocalConfig) -> None:
    def q(value: str) -> str:
        return '"' + value.replace('\', '\\').replace('"', '\"') + '"'

    lines = ["[secrets]", f"service_name = {q(config.credential_service)}"]
    if config.national_id_ref:
        lines.append(f"national_id_ref = {q(config.national_id_ref)}")
    if config.birthday_ref:
        lines.append(f"birthday_ref = {q(config.birthday_ref)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
