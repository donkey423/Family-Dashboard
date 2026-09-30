import importlib.util
from io import BytesIO
import json
from pathlib import Path
import time

from pypdf import PdfWriter
import pytest


spec = importlib.util.spec_from_file_location(
    "gmail_attachment_download", Path(__file__).resolve().parents[2] / "scripts" / "gmail_attachment_download.py"
)
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.encrypt("synthetic-test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def baseline(tmp_path):
    directory = tmp_path / "downloads"
    directory.mkdir()
    return directory, download.snapshot(directory)


def test_collects_new_complete_encrypted_tmp_without_a_download_event(tmp_path):
    directory, checkpoint = baseline(tmp_path)
    source = directory / "browser-guid.tmp"
    source.write_bytes(pdf())
    result = download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0, timeout=1)
    assert result["status"] == "verified_download"
    assert result["encrypted"] is True
    assert result["source_suffix"] == ".tmp"
    assert Path(result["path"]).read_bytes() == source.read_bytes()
    assert source.exists()


def test_ignores_old_pdf_even_when_modified_after_prepare(tmp_path):
    directory = tmp_path / "downloads"
    directory.mkdir()
    old = directory / "old.pdf"
    old.write_bytes(pdf())
    checkpoint = download.snapshot(directory)
    old.write_bytes(pdf())
    with pytest.raises(download.DownloadNotReady):
        download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0.001, timeout=0.01)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("content,suffix", [(b"<html>login</html>", ".pdf"), (pdf()[:-15], ".tmp"), (pdf(), ".crdownload")])
def test_rejects_html_truncated_pdf_and_active_download(tmp_path, content, suffix):
    directory, checkpoint = baseline(tmp_path)
    (directory / ("new" + suffix)).write_bytes(content)
    with pytest.raises(download.DownloadNotReady):
        download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0.001, timeout=0.01)
    assert not (tmp_path / "output").exists()


def test_rejects_ambiguous_downloads(tmp_path):
    directory, checkpoint = baseline(tmp_path)
    for name in ("one.tmp", "two.pdf"):
        (directory / name).write_bytes(pdf())
    with pytest.raises(download.AmbiguousDownload):
        download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0, timeout=1)
    assert not (tmp_path / "output").exists()


def test_checks_size_and_mtime_again_when_reading(tmp_path):
    source = tmp_path / "new.tmp"
    source.write_bytes(pdf())
    info = source.stat()
    source.write_bytes(source.read_bytes() + b"changed")
    assert download.read_stable(source, (info.st_size, info.st_mtime_ns)) is None


def test_partial_pdf_becomes_valid_before_retry(tmp_path, monkeypatch):
    directory, checkpoint = baseline(tmp_path)
    source = directory / "new.tmp"
    content = pdf()
    source.write_bytes(content[:60])
    real_sleep = time.sleep
    sleeps = []

    def finish_download(interval):
        sleeps.append(interval)
        if len(sleeps) == 2:
            source.write_bytes(content)
        real_sleep(interval)

    monkeypatch.setattr(download.time, "sleep", finish_download)
    result = download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0.001, timeout=1)
    assert result["bytes"] == len(content)
    assert len(sleeps) >= 3


def test_recollect_is_idempotent_and_detects_changed_staged_bytes(tmp_path):
    directory, checkpoint = baseline(tmp_path)
    (directory / "new.tmp").write_bytes(pdf())
    first = download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0, timeout=1)
    second = download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0, timeout=1)
    assert first["path"] == second["path"]
    Path(first["path"]).write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="hash changed"):
        download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0, timeout=1)


def test_rejects_expired_checkpoint(tmp_path):
    _, checkpoint = baseline(tmp_path)
    checkpoint["prepared_ns"] -= 601 * 1_000_000_000
    with pytest.raises(download.DownloadNotReady, match="expired"):
        download.collect(checkpoint, tmp_path / "output", timeout=1)


def test_output_guard_rejects_production_and_path_traversal(tmp_path):
    for path in (tmp_path, download.ROOT / "data" / "documents", download.ACCEPTANCE_ROOT / "fresh-old",
                 download.ACCEPTANCE_ROOT / "retest-new" / ".." / ".." / "documents"):
        with pytest.raises(ValueError):
            download.guarded_run(path)
    for label in ("../documents", "person name", "A123456789"):
        with pytest.raises(ValueError):
            download.valid_label(label)


def test_rejects_oversize_download(tmp_path, monkeypatch):
    directory, checkpoint = baseline(tmp_path)
    (directory / "new.pdf").write_bytes(pdf())
    monkeypatch.setattr(download, "MAX_BYTES", 10)
    with pytest.raises(download.DownloadNotReady):
        download.collect(checkpoint, tmp_path / "output", stable_seconds=0, interval=0.001, timeout=0.01)


def test_waits_for_stable_size_and_mtime(tmp_path, monkeypatch):
    directory, checkpoint = baseline(tmp_path)
    (directory / "new.tmp").write_bytes(pdf())
    clock = [0]
    monkeypatch.setattr(download.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(download.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    download.collect(checkpoint, tmp_path / "output", stable_seconds=2, interval=0.5, timeout=3)
    assert clock[0] == 2


def test_rejects_old_receipt_after_a_new_prepare_even_with_identical_timestamps(tmp_path, monkeypatch):
    instant = time.time_ns()
    monkeypatch.setattr(download.time, "time_ns", lambda: instant)
    directory, checkpoint = baseline(tmp_path)
    (directory / "new.tmp").write_bytes(pdf())
    output = tmp_path / "output"
    download.collect(checkpoint, output, stable_seconds=0, interval=0, timeout=1)
    (output / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    receipt, content = download.verified_download(output)
    assert receipt["bytes"] == len(content)
    (output / "checkpoint.json").write_text(json.dumps(download.snapshot(directory)), encoding="utf-8")
    with pytest.raises(ValueError, match="checkpoint"):
        download.verified_download(output)


def test_rejects_a_tampered_receipt_or_staged_pdf(tmp_path):
    directory, checkpoint = baseline(tmp_path)
    (directory / "new.tmp").write_bytes(pdf())
    output = tmp_path / "output"
    result = download.collect(checkpoint, output, stable_seconds=0, interval=0, timeout=1)
    (output / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    result["bytes"] += 1
    (output / "receipt.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        download.verified_download(output)
    result["bytes"] -= 1
    (output / "receipt.json").write_text(json.dumps(result), encoding="utf-8")
    Path(result["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        download.verified_download(output)


def test_output_guard_resolves_symlinks_before_writing(tmp_path, monkeypatch):
    root = tmp_path / "gmail-acceptance"
    directory = root / "retest-new"
    directory.mkdir(parents=True)
    monkeypatch.setattr(download, "ACCEPTANCE_ROOT", root)
    assert download.guarded_output(directory, "ctbc") == directory / "ctbc"
    resolve = download.Path.resolve

    def escaped(path, *args, **kwargs):
        return tmp_path / "outside" if path.name == "escaped" else resolve(path, *args, **kwargs)

    monkeypatch.setattr(download.Path, "resolve", escaped)
    with pytest.raises(ValueError, match="outside"):
        download.guarded_output(directory, "escaped")
