"""WP3 — העתקה ואימות: כל קובץ מאומת או רשום כדילוג; המשך לא משכפל."""
from __future__ import annotations

import ctypes
import hashlib
import json

import pytest
from fake_libmtp import FakeLibMTP

from noam.copy import InsufficientSpace, LocalTarget, TargetError, copy_and_verify
from noam.copy.targets import PART_SUFFIX, safe_relpath
from noam.device import DeviceDisconnected, DeviceError, MassStorageSource, MTPSource
from noam.device import mtp as m
from noam.device.base import Source

m._libc.malloc.restype = ctypes.c_void_p
m._libc.malloc.argtypes = [ctypes.c_size_t]

FILES = {
    "DCIM/Camera/a.jpg": b"A" * 5000,
    "DCIM/Camera/b.mp4": b"B" * 12000,
    "Documents/c.pdf": b"C" * 700,
    "loose.txt": b"hello",
}


@pytest.fixture
def sd(tmp_path):
    root = tmp_path / "phone"
    for rel, data in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return MassStorageSource(root)


@pytest.fixture
def target(tmp_path):
    return LocalTarget(tmp_path / "NOAM-SSD" / "2026-0418")


def run(src, target, events=None, entries=None):
    events = events if events is not None else []
    return copy_and_verify(src, entries or list(src.walk()), target,
                           lambda p: events.append((p.verified, p.skipped, p.percent)), case_id="2026-0418")


def leftovers(target):
    return [p for p in target.root.rglob("*") if p.name.endswith(PART_SUFFIX)]


class Wrapped(Source):
    """עוטף מקור ומאפשר להזריק תקלות בקובץ מסוים."""

    def __init__(self, inner, fail=None):
        self.inner, self.fail, self.calls = inner, fail or {}, []

    def info(self):
        return self.inner.info()

    def walk(self):
        return self.inner.walk()

    def stream(self, entry, write):
        self.calls.append(entry.idx)
        action = self.fail.get(entry.rel_path)
        if action == "error":
            raise DeviceError("read failed")
        if action == "disconnect":
            write(b"partial")
            raise DeviceDisconnected("dev")
        if action == "short":
            write(b"x")
            return
        self.inner.stream(entry, write)


# ---------------------------------------------------------------------------

def test_every_file_verified(sd, target):
    events = []
    man = run(sd, target, events)
    assert man.verified_count == 4 and man.skipped == []
    for rel, data in FILES.items():
        assert (target.payload / rel).read_bytes() == data
    shas = {f.idx: f.sha256 for f in man.files}
    for e in sd.walk():
        assert shas[e.idx] == hashlib.sha256(FILES[e.rel_path]).hexdigest()
    assert events[-1] == (4, 0, 100)
    assert leftovers(target) == []


def test_read_error_is_skipped_and_copy_continues(sd, target):
    src = Wrapped(sd, {"Documents/c.pdf": "error"})
    man = run(src, target)
    assert man.verified_count == 3
    assert [s.error for s in man.skipped] == ["ERR_READ_FAILED"]
    assert not (target.payload / "Documents/c.pdf").exists()
    assert leftovers(target) == []


def test_short_read_is_size_mismatch(sd, target):
    man = run(Wrapped(sd, {"loose.txt": "short"}), target)
    assert [s.error for s in man.skipped] == ["ERR_SIZE_MISMATCH"]


def test_disconnect_stops_and_leaves_no_partial(sd, target):
    src = Wrapped(sd, {"DCIM/Camera/b.mp4": "disconnect"})
    with pytest.raises(DeviceDisconnected):
        run(src, target)
    assert leftovers(target) == []
    assert not (target.payload / "DCIM/Camera/b.mp4").exists()


def test_resume_does_not_duplicate(sd, target):
    src = Wrapped(sd, {"DCIM/Camera/b.mp4": "disconnect"})
    with pytest.raises(DeviceDisconnected):
        run(src, target)
    first = list(src.calls)
    src.fail.clear()
    src.calls.clear()
    man = run(src, target)
    assert man.verified_count == 4
    already = set(first[:-1])  # מה שאומת לפני הניתוק
    assert already and not (already & set(src.calls))
    journal = target.state_path("progress.jsonl").read_text().splitlines()
    assert len(journal) == 4  # כל קובץ פעם אחת


def test_resume_recopies_if_target_file_missing(sd, target):
    run(sd, target)
    (target.payload / "loose.txt").unlink()
    src = Wrapped(sd)
    man = run(src, target)
    assert man.verified_count == 4 and len(src.calls) == 1


def test_verify_mismatch_retries_then_skips(sd, target, monkeypatch):
    orig = LocalTarget.read_part

    def corrupt(self, rel):
        for chunk in orig(self, rel):
            yield (b"Z" + chunk[1:]) if rel.name == "c.pdf" else chunk

    monkeypatch.setattr(LocalTarget, "read_part", corrupt)
    src = Wrapped(sd)
    man = run(src, target)
    assert [s.error for s in man.skipped] == ["ERR_VERIFY_MISMATCH"]
    c_idx = next(e.idx for e in sd.walk() if e.rel_path == "Documents/c.pdf")
    assert src.calls.count(c_idx) == 2  # ניסיון אחד נוסף
    assert leftovers(target) == []


def test_insufficient_space_before_any_copy(sd, target, monkeypatch):
    monkeypatch.setattr(LocalTarget, "free_bytes", lambda self: 1000)
    src = Wrapped(sd)
    with pytest.raises(InsufficientSpace):
        run(src, target)
    assert src.calls == []


def test_target_full_mid_copy_stops(sd, target, monkeypatch):
    import errno

    class Full:
        def __call__(self, chunk):
            raise OSError(errno.ENOSPC, "full")

    def stream(self, entry, write):
        Full()(b"x")

    src = Wrapped(sd)
    monkeypatch.setattr(Wrapped, "stream", stream)
    with pytest.raises(TargetError) as ei:
        run(src, target)
    assert ei.value.code == "ERR_TARGET_SPACE"
    assert leftovers(target) == []


def test_manifest_has_no_names_client_list_does(sd, target):
    man = run(sd, target)
    text = target.state_path("manifest-2026-0418.json").read_text()
    for rel in FILES:
        for part in rel.split("/"):
            assert part not in text
    data = json.loads(text)
    assert data["summary"]["verified"] == 4
    client = json.loads(target.state_path("client-files-2026-0418.json").read_text())
    assert set(client["files"].values()) == set(FILES)
    assert client["manifest_sha256"] == man.sha256()


def test_manifest_sha_is_deterministic(sd, target):
    man = run(sd, target)
    assert man.sha256() == man.sha256()
    assert len(man.sha256()) == 64


def test_safe_relpath():
    assert safe_relpath("../../etc/passwd").as_posix() == "etc/passwd"
    assert safe_relpath("/abs/x.jpg").as_posix() == "abs/x.jpg"
    assert safe_relpath('DCIM/a:b?.jpg').as_posix() == "DCIM/a_b_.jpg"
    with pytest.raises(ValueError):
        safe_relpath("../..")


def test_path_traversal_stays_inside_target(tmp_path, target):
    class Evil(Wrapped):
        def info(self):
            from noam.device.base import DeviceInfo
            return DeviceInfo("evil", "x", "mass_storage")

        def walk(self):
            from noam.device.base import Entry
            yield Entry(0, "g01", "../../escape.txt", 3, "docs")

        def stream(self, entry, write):
            write(b"bad")

    run(Evil(None), target)
    assert not (tmp_path / "escape.txt").exists()
    assert (target.payload / "escape.txt").read_bytes() == b"bad"


def test_end_to_end_with_fake_mtp(target):
    phone = {0x10001: {"dirs": {"DCIM": {"dirs": {"Camera": {"files": {"p.jpg": b"P" * 9001}}}}}}}
    fake = FakeLibMTP(phone)
    src = MTPSource(fake.dev, lib=fake)
    man = run(src, target)
    assert man.verified_count == 1
    assert man.files[0].sha256 == hashlib.sha256(b"P" * 9001).hexdigest()


def test_bagit_validates_with_reference_implementation(sd, target):
    bagit = pytest.importorskip("bagit")
    run(sd, target)
    bag = bagit.Bag(str(target.root))
    bag.validate()  # זורק אם משהו לא תואם
    assert bag.info["Payload-Oxum"] == f"{sum(len(b) for b in FILES.values())}.{len(FILES)}"
    # שינוי של בית אחד בקובץ — האימות נכשל
    p = target.payload / "loose.txt"
    p.write_bytes(b"HELLO")
    with pytest.raises(bagit.BagValidationError):
        bagit.Bag(str(target.root)).validate()
