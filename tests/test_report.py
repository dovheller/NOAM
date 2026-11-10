"""WP5 — דוח חתום."""
from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from noam.copy.manifest import FileRecord, Manifest, SkipRecord
from noam.report import (
    ReportData,
    SigningKey,
    build_report,
    generate_key,
    load_public_key,
    sign,
    verify,
    verify_embedded,
)

PW = "correct horse battery"


@pytest.fixture
def key(tmp_path):
    path = tmp_path / "keys" / "station.pem"
    fp = generate_key(path, PW)
    k = SigningKey.load(path, PW)
    assert k.fingerprint == fp
    return k, path


def make_data(**kw) -> ReportData:
    m = Manifest(case="2026-0418", source_device="9F2C-A81D-4477")
    m.files = [
        FileRecord(0, "g01", "images", 2_400_000, "a" * 64),
        FileRecord(1, "g01", "video", 16_000_000, "b" * 64),
        FileRecord(2, "g02", "docs", 120_000, "c" * 64),
    ]
    m.skipped = [SkipRecord(3, "g02", "ERR_READ_FAILED")]
    t0 = datetime(2026, 9, 28, 9, 41, 22, tzinfo=UTC)
    d = {
        "case_id": "2026-0418", "client_name": "מרים לוינגר", "service": "transfer", "operator": "נועם", "station_id": "ST-02",
        "station_name": "נועם הלר", "station_address": "מרכז אורנים · כנפי נשרים 68, ירושלים",
        "started_at": t0, "ended_at": t0 + timedelta(minutes=11, seconds=48),
        "device_model": "SM-A546B", "device_id": "9F2C-A81D-4477", "device_interface": "mtp",
        "target_desc": "דיסק SSD 1TB · exFAT", "manifest": m, "audit_seal": "d" * 64,
        "consent_at": t0 + timedelta(minutes=2), "consent_sig_sha256": "e" * 64, "total_on_device": 2974,
    }
    d.update(kw)
    return ReportData(**d)


def test_build_sign_verify(tmp_path, key):
    k, path = key
    pdf = build_report(make_data(), tmp_path / "reports", k.fingerprint)
    assert pdf.name == "NOAM-2026-0418-R1.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    sig = sign(pdf, k)
    pub = load_public_key(path.with_suffix(".pub.pem"))
    assert verify(pdf, pub)
    # שינוי של בית אחד שובר את החתימה
    b = bytearray(pdf.read_bytes())
    b[len(b) // 2] ^= 1
    pdf.write_bytes(bytes(b))
    assert not verify(pdf, pub, sig)


def test_openssl_can_verify(tmp_path, key):
    k, path = key
    pdf = build_report(make_data(), tmp_path, k.fingerprint)
    sig = sign(pdf, k)
    r = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify", str(path.with_suffix(".pub.pem")), "-signature", str(sig), str(pdf)],
        capture_output=True, text=True, check=False,
    )
    assert "Verified OK" in r.stdout


def test_report_text_has_hebrew_and_no_filenames(tmp_path, key):
    pypdf = pytest.importorskip("pypdf")
    k, _ = key
    pdf = build_report(make_data(), tmp_path, k.fingerprint)
    text = "".join(p.extract_text() for p in pypdf.PdfReader(str(pdf)).pages)
    assert "2026-0418" in text and "ERR_READ_FAILED" in text
    assert "לוינגר" in text
    assert "dddd dddd" in text and "eeee eeee" in text  # טביעות מלאות
    assert any("֐" <= ch <= "׿" for ch in text)
    assert ".jpg" not in text and "DCIM" not in text


def test_aborted_session_report(tmp_path, key):
    k, _ = key
    pdf = build_report(make_data(aborted_code="ERR_DEVICE_DISCONNECTED", revision=2), tmp_path, k.fingerprint)
    assert pdf.name.endswith("-R2.pdf")


def test_revision_is_never_overwritten(tmp_path, key):
    k, _ = key
    build_report(make_data(), tmp_path, k.fingerprint)
    with pytest.raises(FileExistsError):
        build_report(make_data(), tmp_path, k.fingerprint)


def test_key_requires_passphrase(key, monkeypatch):
    _, path = key
    monkeypatch.delenv("NOAM_SIGNING_PASSPHRASE", raising=False)
    with pytest.raises(RuntimeError, match="locked"):
        SigningKey.load(path)
    with pytest.raises(PermissionError):
        SigningKey.load(path, "wrong passphrase!!")


def test_key_file_is_encrypted_and_private(key):
    _, path = key
    assert b"ENCRYPTED PRIVATE KEY" in path.read_bytes()
    assert (path.stat().st_mode & 0o777) == 0o600


def test_generate_refuses_overwrite_and_short_passphrase(tmp_path, key):
    _, path = key
    with pytest.raises(FileExistsError):
        generate_key(path, PW)
    with pytest.raises(ValueError):
        generate_key(tmp_path / "x.pem", "short")


def test_fonts_bundled():
    fonts = Path(__import__("noam.report.pdf", fromlist=["FONTS"]).FONTS)
    assert (fonts / "DejaVuSans.ttf").exists() and (fonts / "LICENSE").exists()


def test_pades_embedded_signature_valid_and_tamper_evident(tmp_path, key):
    k, path = key
    pdf = build_report(make_data(), tmp_path, k.fingerprint)
    sign(pdf, k)
    crt = path.with_suffix(".crt")
    assert verify_embedded(pdf, crt)
    assert verify(pdf, load_public_key(path.with_suffix(".pub.pem")))  # המנותקת — על הקובץ הסופי
    b = bytearray(pdf.read_bytes())
    b[len(b) // 3] ^= 1  # בית אחד בתוכן החתום
    pdf.write_bytes(bytes(b))
    assert not verify_embedded(pdf, crt)


def test_unavailable_devices_in_report(tmp_path, key):
    pypdf = pytest.importorskip("pypdf")
    k, _ = key
    pdf = build_report(make_data(unavailable=[("Galaxy A12", "ERR_ADB_UNAUTHORIZED")]), tmp_path, k.fingerprint)
    text = "".join(p.extract_text() for p in pypdf.PdfReader(str(pdf)).pages)
    assert "ERR_ADB_UNAUTHORIZED" in text and "Galaxy A12" in text


def test_hebrew_with_inline_latin_extracts_in_order(tmp_path, key):
    """text shaping: קוד לועזי בתוך שורה עברית נשאר שלם (הבאג שהיה עם python-bidi)."""
    import shutil
    if not shutil.which("pdftotext"):
        pytest.skip("poppler-utils not installed")
    k, _ = key
    pdf = build_report(make_data(), tmp_path, k.fingerprint)
    text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    assert "exFAT" in text and "SSD 1TB" in text


def test_pades_rejects_appended_bytes(tmp_path, key):
    k, path = key
    pdf = build_report(make_data(), tmp_path, k.fingerprint)
    sign(pdf, k)
    pdf.write_bytes(pdf.read_bytes() + b"\n%junk appended after signing\n")
    assert not verify_embedded(pdf, path.with_suffix(".crt"))
