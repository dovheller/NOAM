"""ממצאי QA (2026-11-10) — כל אחד בדיקה, כדי שלא יחזור."""
from __future__ import annotations

import errno
import io
import threading

import pytest
from test_station import PW, png

from noam.copy import LocalTarget, TargetError, copy_and_verify
from noam.device import DeviceDisconnected, MassStorageSource
from noam.device.base import DeviceInfo, Entry, Source
from noam.report import SigningKey, generate_key
from noam.station import Station, StationConfig, StationError


class MemSource(Source):
    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.calls = 0

    def info(self):
        return DeviceInfo("mem", "Mem", "mass_storage")

    def walk(self):
        for i, (rel, data) in enumerate(self.files.items()):
            yield Entry(i, "g01", rel, len(data), "other")

    def stream(self, entry, write):
        self.calls += 1
        data = self.files[entry.rel_path]
        for i in range(0, len(data), 4):
            write(data[i:i + 4])


def run(src, target, **kw):
    return copy_and_verify(src, list(src.walk()), target, lambda p: None, case_id="c1", **kw)


# 1 — התנגשות שמות
def test_name_collisions_never_overwrite(tmp_path):
    src = MemSource({"D/a:b.jpg": b"first", "D/a_b.jpg": b"second", "x.": b"dot", "x": b"plain",
                     "IMG.jpg": b"upper", "img.JPG": b"lower"})
    t = LocalTarget(tmp_path / "t")
    man = run(src, t)
    assert man.verified_count == 6
    written = sorted(p.read_bytes() for p in t.payload.rglob("*") if p.is_file())
    assert written == sorted(src.files.values())
    bagit = pytest.importorskip("bagit")
    bagit.Bag(str(t.root)).validate()


# 2 — דיסק מלא לא נרשם כ"המכשיר לא החזיר"
def test_target_full_through_mass_storage_is_target_error(tmp_path, monkeypatch):
    phone = tmp_path / "p"
    phone.mkdir()
    (phone / "a.bin").write_bytes(b"x" * 100)
    src = MassStorageSource(phone)
    t = LocalTarget(tmp_path / "t")
    real_open = t.open_part

    class Full(io.BytesIO):
        def write(self, b):
            raise OSError(errno.ENOSPC, "full")

        def fileno(self):
            return 0

    monkeypatch.setattr(t, "open_part", lambda rel: (real_open(rel), Full())[1])
    with pytest.raises(TargetError) as ei:
        run(src, t)
    assert ei.value.code == "ERR_TARGET_SPACE"


# 3 — ביטול באמצע עוצר את ההעתקה ושומר מניפסט חלקי
def test_cancel_stops_copy_and_keeps_partial_manifest(tmp_path):
    src = MemSource({f"f{i}": b"z" * 40 for i in range(6)})
    stop = threading.Event()
    orig = src.stream

    def stream(e, w):
        if e.idx == 2:
            stop.set()
        orig(e, w)

    src.stream = stream
    from noam.copy import CopyCancelled
    with pytest.raises(CopyCancelled) as ei:
        run(src, LocalTarget(tmp_path / "t"), should_stop=stop.is_set)
    assert ei.value.partial_manifest.verified_count == 2
    assert src.calls == 3  # לא המשיך לקרוא אחרי הביטול


# 9 — המשך מאמת את מה שכבר ביעד
def test_resume_rehashes_files_on_target(tmp_path):
    src = MemSource({f"f{i}": bytes([i]) * 50 for i in range(3)})
    t = LocalTarget(tmp_path / "t")
    run(src, t)
    (t.payload / "f0").write_bytes(b"tampered")
    src.calls = 0
    run(src, t)
    assert src.calls == 1
    assert (t.payload / "f0").read_bytes() == bytes([0]) * 50


# 10 — כשל בקריאה חוזרת לא משאיר .noam-part
def test_readback_failure_leaves_no_part(tmp_path, monkeypatch):
    src = MemSource({"a": b"q" * 30})
    t = LocalTarget(tmp_path / "t")

    def broken(rel):
        raise TargetError("ERR_TARGET_READ")
        yield b""

    monkeypatch.setattr(t, "read_part", broken)
    with pytest.raises(TargetError):
        run(src, t)
    assert not [p for p in t.root.rglob("*.noam-part")]


# ---------------------------------------------------------------- station
@pytest.fixture
def st(tmp_path):
    phone = tmp_path / "phone"
    for i in range(4):
        (phone / f"g{i}").mkdir(parents=True, exist_ok=True)
        (phone / f"g{i}" / f"f{i}.bin").write_bytes(bytes([i]) * 2000)
    cfg = StationConfig(target_root=tmp_path / "ssd", audit_dir=tmp_path / "audit",
                        reports_dir=tmp_path / "reports", signing_key=tmp_path / "k/station.pem")
    generate_key(cfg.signing_key, PW)
    src = MassStorageSource(phone, label="X")
    s = Station(cfg, scan_fn=lambda **_: [src], audit_key=b"k" * 32,
                signing_key=SigningKey.load(cfg.signing_key, PW), run_async=False)
    s.open_session(case_id="c1", client_name="a", phone="", language="he", service="backup")
    s.choose_language("he")
    s.poll_devices()
    s.choose_source(0)
    return s, src


# 3 — ביטול מ-Station באמצע העתקה
def test_station_abort_mid_copy(st):
    s, src = st
    s.confirm_selection()
    orig = src.stream
    n = {"k": 0}

    def stream(e, w):
        n["k"] += 1
        if n["k"] == 2:
            s.abort()
        orig(e, w)

    src.stream = stream
    s.sign_consent(png())
    run_ = s.current
    assert run_.session.state.value == "aborted"
    assert n["k"] == 2 and run_.manifest is not None and run_.manifest.verified_count == 1
    s.make_report()
    s.close()
    assert s.history()[0]["status"] == "aborted"


# 7 — חתימה ריקה / מזויפת
@pytest.mark.parametrize("data", [b"\x89PNG" + b"\x00" * 300, b"not png"])
def test_fake_signature_rejected(st, data):
    s, _ = st
    s.confirm_selection()
    with pytest.raises(StationError):
        s.sign_consent(data)


def test_blank_png_rejected(st):
    from PIL import Image
    s, _ = st
    s.confirm_selection()
    b = io.BytesIO()
    Image.new("RGBA", (600, 240), (0, 0, 0, 0)).save(b, "PNG")
    with pytest.raises(StationError):
        s.sign_consent(b.getvalue())


# 8 — הבחירה קפואה אחרי האישור
def test_selection_frozen_after_confirm(st):
    s, _ = st
    s.confirm_selection()
    with pytest.raises(StationError):
        s.set_selection(["g01"])


# 11 — מספר תיק
@pytest.mark.parametrize("case", ["שלום", "-x", "a" + chr(0x202E) + "b", "a$b'\"", "C\x00", "a b", "../x", "x" * 41])
def test_bad_case_ids(tmp_path, case):
    cfg = StationConfig(target_root=tmp_path / "s", audit_dir=tmp_path / "a", reports_dir=tmp_path / "r")
    s = Station(cfg, scan_fn=lambda **_: [], audit_key=b"k" * 32, run_async=False)
    with pytest.raises(StationError) as ei:
        s.open_session(case_id=case, client_name="a", phone="", language="he", service="backup")
    assert ei.value.code == "ERR_BAD_CASE_ID"


# 6 — מסך נועם לא מציג פקודה לא מוכרת ומתאפס בין סשנים
def test_shell_hides_unknown_commands_and_resets(st):
    s, _ = st
    s.shell("stat Wedding2024")
    assert all("Wedding2024" not in t for _, t in s.shell_lines)
    s.operator_snapshot()  # לא נחסם
    s.abort()
    s.close()
    assert s.shell_lines == []


# 19 — סשן בלי קבצים מאומתים אינו "ok"
def test_history_partial_when_skips(st):
    s, src = st
    s.confirm_selection()
    orig = src.stream

    def stream(e, w):
        if e.idx == 0:
            from noam.device import DeviceError
            raise DeviceError("x")
        orig(e, w)

    src.stream = stream
    s.sign_consent(png())
    s.make_report()
    s.close()
    assert s.history()[0]["status"] == "partial"


def test_disconnect_keeps_partial_manifest(st):
    s, src = st
    s.confirm_selection()
    orig = src.stream

    def stream(e, w):
        if e.idx == 2:
            raise DeviceDisconnected("x")
        orig(e, w)

    src.stream = stream
    s.sign_consent(png())
    assert s.current.manifest.verified_count == 2
