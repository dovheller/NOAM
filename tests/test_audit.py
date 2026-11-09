"""WP1 — היומן מסרב לשדות תוכן."""

import pytest

from noam.session.audit import AuditLog, ContentLeakError


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl", key=b"test-key-0123456789abcdef")


def test_audit_rejects_content_fields(audit):
    with pytest.raises((ContentLeakError, ValueError)):
        audit.record("copy", filename="IMG_1234.jpg")


def test_audit_rejects_path_in_value(audit):
    with pytest.raises((ContentLeakError, ValueError)):
        audit.record("/sdcard/DCIM/photo.jpg")


def test_audit_accepts_metadata(audit):
    audit.record("session_open", session_id="abc", status="ok", count=1)
    assert audit.verify() == 1
    digest = audit.seal()
    assert len(digest) == 64


def test_audit_chain_and_tamper(audit):
    audit.record("a", status="ok")
    audit.record("b", status="ok")
    assert audit.verify() == 2
    lines = audit.path.read_text().splitlines()
    import json
    first = json.loads(lines[0])
    first["event"] = "tampered"
    lines[0] = json.dumps(first, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    audit.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="signature"):
        audit.verify()


def test_missing_key_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.delenv("NOAM_AUDIT_KEY", raising=False)
    monkeypatch.delenv("NOAM_DEV", raising=False)
    with pytest.raises(RuntimeError, match="NOAM_AUDIT_KEY"):
        AuditLog(tmp_path / "a.jsonl")


def test_dev_key_only_with_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("NOAM_AUDIT_KEY", raising=False)
    monkeypatch.setenv("NOAM_DEV", "1")
    AuditLog(tmp_path / "a.jsonl").record("x", status="ok")
