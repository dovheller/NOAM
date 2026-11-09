"""WP2 — בדיקות שכבת המכשיר."""
from __future__ import annotations

import pytest

from noam.device import MassStorageSource, MTPError, scan
from noam.device import registry
from noam.device import mtp


def test_mass_storage_info(tmp_path):
    root = tmp_path / "SD"
    root.mkdir()
    src = MassStorageSource(root, label="SDXC 64GB")
    info = src.info()
    assert info.interface == "mass_storage"
    assert info.model == "SDXC 64GB"
    assert info.device_id.startswith("mass-")


def test_mass_storage_walk_categories(tmp_path):
    root = tmp_path / "SD"
    (root / "DCIM").mkdir(parents=True)
    (root / "DCIM" / "a.jpg").write_bytes(b"x" * 10)
    (root / "DCIM" / "b.mp4").write_bytes(b"x" * 20)
    (root / "docs").mkdir()
    (root / "docs" / "c.pdf").write_bytes(b"x" * 30)

    src = MassStorageSource(root, label="SD")
    entries = list(src.walk())

    assert {e.category for e in entries} == {"images", "video", "docs"}
    assert {e.rel_path for e in entries} == {"DCIM/a.jpg", "DCIM/b.mp4", "docs/c.pdf"}
    dcim_groups = {e.group for e in entries if e.rel_path.startswith("DCIM/")}
    assert len(dcim_groups) == 1


def test_mass_storage_open(tmp_path):
    root = tmp_path / "SD"
    root.mkdir()
    payload = b"hello noam"
    (root / "a.txt").write_bytes(payload)

    src = MassStorageSource(root, label="SD")
    entry = next(iter(src.walk()))
    with src.open(entry) as fh:
        assert fh.read() == payload


def test_mtp_source_requires_libmtp(monkeypatch):
    monkeypatch.setattr(mtp, "_lib", None)
    monkeypatch.setattr(mtp.ctypes.util, "find_library", lambda _: None)
    with pytest.raises(MTPError):
        mtp._load()


def test_scan_returns_list(monkeypatch):
    monkeypatch.setattr(registry, "_scan_mtp", lambda: [])
    monkeypatch.setattr(registry, "_scan_mass_storage", lambda: [])
    assert scan() == []


@pytest.mark.mtp
def test_mtp_real_device_scan():
    sources = scan()
    mtp_sources = [s for s in sources if s.info().interface == "mtp"]
    if not mtp_sources:
        pytest.skip("no MTP device attached")
    src = mtp_sources[0]
    entries = list(src.walk())
    assert entries
    assert {e.category for e in entries} <= {"images", "video", "docs", "other"}
    with src.open(entries[0]) as fh:
        assert fh.read(1)
