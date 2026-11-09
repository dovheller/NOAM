"""WP2 — בדיקות שכבת המכשיר."""
from __future__ import annotations

import ctypes

import pytest
from fake_libmtp import FakeLibMTP

from noam.device import (
    TARGET_MARKER,
    DeviceDisconnected,
    MassStorageSource,
    MTPError,
    MTPSource,
    registry,
    scan,
)
from noam.device import mtp as m

m._libc.malloc.restype = ctypes.c_void_p
m._libc.malloc.argtypes = [ctypes.c_size_t]

PHONE = {
    0x10001: {
        "files": {"root.txt": b"r"},
        "dirs": {
            "DCIM": {
                "files": {"top.jpg": b"T"},
                "dirs": {
                    "Camera": {"files": {"a.jpg": b"A" * 10, "b.mp4": b"B" * 9}},
                    "Screenshots": {"files": {"s.png": b"S" * 3}},
                },
            },
            "Documents": {"files": {"c.pdf": b"C" * 7}},
        },
    }
}


def collect(src, entry):
    out = bytearray()
    src.stream(entry, out.extend)
    return bytes(out)


# ---------- mass storage ----------

def test_mass_storage_info(tmp_path):
    root = tmp_path / "SD"
    root.mkdir()
    info = MassStorageSource(root, label="SDXC 64GB").info()
    assert info.interface == "mass_storage"
    assert info.model == "SDXC 64GB"


def test_mass_storage_walk_and_groups(tmp_path):
    root = tmp_path / "SD"
    (root / "DCIM").mkdir(parents=True)
    (root / "DCIM" / "a.jpg").write_bytes(b"x" * 10)
    (root / "DCIM" / "b.mp4").write_bytes(b"x" * 20)
    (root / "docs").mkdir()
    (root / "docs" / "c.pdf").write_bytes(b"x" * 30)
    entries = list(MassStorageSource(root).walk())
    assert [e.idx for e in entries] == [0, 1, 2]
    assert {e.category for e in entries} == {"images", "video", "docs"}
    by_dir = {e.rel_path.split("/")[0]: e.group for e in entries}
    assert by_dir["DCIM"] != by_dir["docs"]


def test_mass_storage_groups_by_top_folder(tmp_path):
    root = tmp_path / "SD"
    for d in ("DCIM/Camera", "DCIM/Screenshots", "Music"):
        (root / d).mkdir(parents=True)
    (root / "DCIM/Camera/a.jpg").write_bytes(b"x")
    (root / "DCIM/Screenshots/b.png").write_bytes(b"x")
    (root / "Music/c.mp3").write_bytes(b"x")
    (root / "loose.txt").write_bytes(b"x")
    g = {e.rel_path: e.group for e in MassStorageSource(root).walk()}
    assert g["DCIM/Camera/a.jpg"] == g["DCIM/Screenshots/b.png"]
    assert len({g["DCIM/Camera/a.jpg"], g["Music/c.mp3"], g["loose.txt"]}) == 3


def test_mass_storage_skips_symlinks(tmp_path):
    root = tmp_path / "SD"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    (root / "link.txt").symlink_to(outside)
    assert list(MassStorageSource(root).walk()) == []


def test_mass_storage_stream(tmp_path):
    root = tmp_path / "SD"
    root.mkdir()
    (root / "a.txt").write_bytes(b"hello noam")
    src = MassStorageSource(root)
    assert collect(src, next(src.walk())) == b"hello noam"


def test_mass_storage_disconnect(tmp_path):
    root = tmp_path / "SD"
    root.mkdir()
    (root / "a.txt").write_bytes(b"x")
    src = MassStorageSource(root)
    e = next(src.walk())
    (root / "a.txt").unlink()
    root.rmdir()
    with pytest.raises(DeviceDisconnected):
        collect(src, e)


def test_scan_excludes_target(tmp_path, monkeypatch):
    media = tmp_path / "media"
    (media / "PHONE_SD").mkdir(parents=True)
    (media / "NOAM-SSD").mkdir()
    (media / "NOAM-SSD" / TARGET_MARKER).write_text("")
    monkeypatch.setattr(registry, "_mounts", lambda roots: [media / "PHONE_SD", media / "NOAM-SSD"])
    labels = [s.info().model for s in registry._scan_mass_storage(roots=[media])]
    assert labels == ["PHONE_SD"]


# ---------- MTP (fake libmtp) ----------

def make_src(fake=None):
    fake = fake or FakeLibMTP(PHONE)
    return fake, MTPSource(fake.dev, lib=fake)


def test_mtp_info():
    _, src = make_src()
    assert src.info().device_id == "FAKE123"
    assert src.info().model == "Pixel Test"


def test_mtp_walk():
    fake, src = make_src()
    entries = list(src.walk())
    names = {e.rel_path.rsplit("/", 1)[1] for e in entries}
    assert names == {"root.txt", "top.jpg", "a.jpg", "b.mp4", "s.png", "c.pdf"}
    assert [e.idx for e in entries] == list(range(6))
    groups = {e.rel_path.rsplit("/", 1)[1]: e.group for e in entries}
    # כל DCIM — כולל Camera ו-Screenshots — היא קבוצה אחת
    assert groups["a.jpg"] == groups["b.mp4"] == groups["s.png"] == groups["top.jpg"]
    assert len({groups["root.txt"], groups["a.jpg"], groups["c.pdf"]}) == 3
    assert fake.destroyed > 0  # הרשימות של libmtp משוחררות


def test_mtp_stream_no_temp_files(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    _, src = make_src()
    e = next(e for e in src.walk() if e.rel_path.endswith("a.jpg"))
    assert collect(src, e) == b"A" * 10
    assert list(tmp_path.iterdir()) == []


def test_mtp_disconnect_during_walk():
    fake = FakeLibMTP(PHONE)
    fake.disconnect_after_folders = 1
    _, src = make_src(fake)
    with pytest.raises(DeviceDisconnected) as ei:
        list(src.walk())
    assert "secret" not in str(ei.value)  # error_text של libmtp לא דולף


def test_mtp_disconnect_during_stream():
    fake = FakeLibMTP(PHONE)
    _, src = make_src(fake)
    e = next(e for e in src.walk() if e.rel_path.endswith("a.jpg"))
    fake.disconnect_after_bytes = 4
    with pytest.raises(DeviceDisconnected):
        collect(src, e)


def test_mtp_sink_failure_is_not_device_failure():
    _, src = make_src()
    e = next(src.walk())

    def full_disk(_chunk):
        raise OSError(28, "No space left")

    with pytest.raises(OSError):
        src.stream(e, full_disk)


def test_mtp_close_releases_and_blocks():
    fake, src = make_src()
    src.close()
    src.close()
    assert fake.released
    with pytest.raises(DeviceDisconnected):
        list(src.walk())


def test_load_without_libmtp(monkeypatch):
    monkeypatch.setattr(m, "_lib", None)
    monkeypatch.setattr(m.ctypes.util, "find_library", lambda _: None)
    with pytest.raises(MTPError):
        m._load()


def test_scan_survives_missing_libmtp(monkeypatch):
    monkeypatch.setattr(m, "_lib", None)
    monkeypatch.setattr(m.ctypes.util, "find_library", lambda _: None)
    monkeypatch.setattr(registry, "_scan_mass_storage", lambda **_: [])
    assert scan() == []


# ---------- real device (manual, on the station) ----------

@pytest.mark.mtp
def test_mtp_real_device():
    sources = [s for s in scan() if s.info().interface == "mtp"]
    if not sources:
        pytest.skip("no MTP device attached")
    src = sources[0]
    entries = list(src.walk())
    assert entries
    first = next(e for e in entries if e.size > 0)
    assert len(collect(src, first)) == first.size
    src.close()
