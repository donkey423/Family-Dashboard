"""Verify one new browser-downloaded PDF without relying on download events."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import time
from uuid import uuid4

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_ROOT = ROOT / "data" / "gmail-acceptance"
MAX_BYTES = 25 * 1024 * 1024
SUFFIXES = {".pdf", ".tmp", ".crdownload"}


class DownloadNotReady(RuntimeError):
    pass


class AmbiguousDownload(RuntimeError):
    pass


def guarded_run(value):
    directory = Path(value).resolve()
    if not directory.is_relative_to(ACCEPTANCE_ROOT.resolve()) or not directory.name.startswith("retest-"):
        raise ValueError("Use a retest-* directory inside data/gmail-acceptance only")
    return directory


def valid_label(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", value):
        raise ValueError("Use a short lowercase label, not personal information")
    return value


def guarded_output(value, label):
    directory = guarded_run(value)
    output = (directory / valid_label(label)).resolve()
    if not output.is_relative_to(directory):
        raise ValueError("The download label resolves outside the acceptance directory")
    return output


def name_key(path):
    return sha256(path.name.encode("utf-8")).hexdigest()


def snapshot(downloads):
    directory = Path(downloads).resolve(strict=True)
    existing = [name_key(p) for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES]
    return {"downloads": str(directory), "existing": existing,
            "prepared_ns": time.time_ns(), "checkpoint_id": uuid4().hex}


def candidates(baseline):
    result = []
    for path in Path(baseline["downloads"]).iterdir():
        if path.is_symlink() or path.suffix.lower() not in {".pdf", ".tmp"} or name_key(path) in baseline["existing"]:
            continue
        try:
            stat = path.stat()
            if path.is_file() and stat.st_mtime_ns >= baseline["prepared_ns"] and 0 < stat.st_size <= MAX_BYTES:
                result.append(path)
        except OSError:
            continue
    return result


def complete_pdf(content):
    if not content.startswith(b"%PDF-") or not content.rstrip().endswith(b"%%EOF"):
        return None
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if "/Root" not in reader.trailer or "/Size" not in reader.trailer:
            return None
        return {"encrypted": reader.is_encrypted}
    except Exception:
        return None


def read_stable(path, expected):
    try:
        before = path.stat()
        content = path.read_bytes()
        after = path.stat()
    except OSError:
        return None
    identity = (after.st_size, after.st_mtime_ns)
    if identity != expected or (before.st_size, before.st_mtime_ns) != identity or len(content) != after.st_size:
        return None
    info = complete_pdf(content)
    return (content, info) if info is not None else None


def verified_download(output):
    output = Path(output).resolve()
    checkpoint = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
    receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    if (receipt["status"] != "verified_download"
        or not re.fullmatch(r"[0-9a-f]{32}", receipt.get("checkpoint_id", ""))
        or receipt["checkpoint_id"] != checkpoint.get("checkpoint_id")
        or receipt["prepared_ns"] != checkpoint["prepared_ns"]
        or receipt["verified_ns"] < receipt["prepared_ns"]
        or not re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"])):
        raise ValueError("Receipt does not match the current download checkpoint")
    path = Path(receipt["path"]).resolve()
    if path != output / (receipt["sha256"] + ".pdf") or path.is_symlink():
        raise ValueError("Use only the hash-named staged download")
    content = path.read_bytes()
    if (len(content) != receipt["bytes"] or not 0 < len(content) <= MAX_BYTES
        or sha256(content).hexdigest() != receipt["sha256"]
        or complete_pdf(content) != {"encrypted": receipt["encrypted"]}):
        raise ValueError("The verified download changed or is not a complete PDF")
    return receipt, content


def collect(baseline, output, *, timeout=90, stable_seconds=2, interval=0.5):
    if time.time_ns() - baseline["prepared_ns"] > 10 * 60 * 1_000_000_000:
        raise DownloadNotReady("Checkpoint expired; prepare again before clicking download")
    deadline = time.monotonic() + timeout
    observed = {}
    while True:
        now = time.monotonic()
        ready = []
        for path in candidates(baseline):
            try:
                stat = path.stat()
            except OSError:
                continue
            identity = (stat.st_size, stat.st_mtime_ns)
            previous = observed.get(path)
            if previous is None or previous[0] != identity:
                observed[path] = (identity, now)
                continue
            if now - previous[1] < stable_seconds:
                continue
            checked = read_stable(path, identity)
            if checked is not None:
                ready.append((path, *checked))
        if len(ready) > 1:
            raise AmbiguousDownload("Multiple new complete PDFs; do not guess which attachment was downloaded")
        if len(ready) == 1:
            source, content, info = ready[0]
            digest = sha256(content).hexdigest()
            output = Path(output)
            output.mkdir(parents=True, exist_ok=True)
            target = output / (digest + ".pdf")
            if target.exists():
                if sha256(target.read_bytes()).hexdigest() != digest:
                    raise RuntimeError("The staged PDF hash changed")
            else:
                pending = None
                try:
                    with NamedTemporaryFile(mode="wb", dir=output, suffix=".staging", delete=False) as handle:
                        pending = Path(handle.name)
                        handle.write(content)
                    if sha256(pending.read_bytes()).hexdigest() != digest:
                        raise RuntimeError("The staged PDF hash does not match")
                    pending.replace(target)
                finally:
                    if pending is not None:
                        pending.unlink(missing_ok=True)
            receipt = {"status": "verified_download", "path": str(target), "bytes": len(content),
                       "sha256": digest, "encrypted": info["encrypted"], "source_suffix": source.suffix,
                       "prepared_ns": baseline["prepared_ns"], "verified_ns": time.time_ns(),
                       "checkpoint_id": baseline["checkpoint_id"]}
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            return receipt
        if now >= deadline:
            raise DownloadNotReady("No new stable complete PDF; do not use older downloads or import partial bytes")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect"))
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--downloads", default=str(Path.home() / "Downloads"))
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    if not 0 < args.timeout <= 180:
        parser.error("Timeout must be between 0 and 180 seconds")
    try:
        output = guarded_output(args.run_directory, args.label)
        checkpoint = output / "checkpoint.json"
        if args.action == "prepare":
            output.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps(snapshot(args.downloads)), encoding="utf-8")
            result = {"status": "prepared", "checkpoint": str(checkpoint)}
        else:
            result = collect(json.loads(checkpoint.read_text(encoding="utf-8")), output, timeout=args.timeout)
        print(json.dumps(result))
    except (OSError, ValueError, DownloadNotReady, AmbiguousDownload, RuntimeError) as error:
        parser.exit(1, type(error).__name__ + ": " + str(error) + "\n")


if __name__ == "__main__":
    main()
