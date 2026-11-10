"""WP2 — adb ומכשירים לא נגישים."""
from __future__ import annotations

import pytest

from noam.copy import LocalTarget, copy_and_verify
from noam.device import (
    ADBSource,
    DeviceDisconnected,
    DeviceError,
    UnavailableSource,
    Unreachable,
    registry,
)
from noam.device.adb import (
    ADBDevice,
    Listing,
    SubprocessADBBackend,
    parse_devices_output,
    parse_files_output,
)
from noam.device.errors import (
    REASON_ADB_UNAUTHORIZED,
    REASON_DISCONNECTED,
    REASON_NO_PERMISSION,
)


class FakeADB:
    def __init__(self, devices, files=None):
        self.devices = devices
        self.files = files or {}           # full path -> bytes
        self.state = {d.serial: d.state for d in devices}
        self.disconnect_after = None
        self.fail_paths = set()

    def list_devices(self):
        return self.devices

    def get_state(self, serial):
        return self.state.get(serial, "offline")

    def list_files(self, serial, root):
        return Listing([(len(b), p[len(root) + 1:]) for p, b in self.files.items()], 0)

    def stream_file(self, serial, path, write):
        if path in self.fail_paths:
            raise DeviceError("ERR_ADB")
        data = self.files[path]
        for i in range(0, len(data), 4):
            if self.disconnect_after is not None and i >= self.disconnect_after:
                self.state[serial] = "offline"
                raise DeviceDisconnected(serial)
            write(data[i:i + 4])


PHONE = {
    "/sdcard/DCIM/Camera/a.jpg": b"A" * 40,
    "/sdcard/DCIM/Screenshots/b.png": b"B" * 12,
    "/sdcard/WhatsApp/Media/WhatsApp Images/IMG-20240412-WA0007.jpg": b"W" * 20,
    "/sdcard/notes.txt": b"n",
}


def test_parse_devices():
    text = (
        "List of devices attached\n"
        "R58M123  device usb:1-1 product:a54 model:SM_A546B device:a54x\n"
        "LOCK999  unauthorized usb:1-2\n"
        "OLD777   offline\n"
        "UDEV1    no permissions (user in plugdev group; are your udev rules wrong?)\n"
    )
    d = parse_devices_output(text)
    assert [(x.serial, x.state) for x in d] == [
        ("R58M123", "device"), ("LOCK999", "unauthorized"), ("OLD777", "offline"), ("UDEV1", "no permissions")]
    assert d[0].model == "SM A546B"


def test_parse_files_strips_dot_and_counts_bad_lines():
    out = parse_files_output("40\t./DCIM/a.jpg\r\n12\t./WhatsApp/Media/WhatsApp Images/x y.jpg\ngarbage\n\n")
    assert out.files == [(40, "DCIM/a.jpg"), (12, "WhatsApp/Media/WhatsApp Images/x y.jpg")]
    assert out.unparsed == 1


def test_walk_groups_by_top_folder():
    src = ADBSource(FakeADB([ADBDevice("R1", "device")], PHONE), "R1")
    e = {x.rel_path: x for x in src.walk()}
    assert e["DCIM/Camera/a.jpg"].group == e["DCIM/Screenshots/b.png"].group
    assert len({e["DCIM/Camera/a.jpg"].group, e["notes.txt"].group,
                e["WhatsApp/Media/WhatsApp Images/IMG-20240412-WA0007.jpg"].group}) == 3
    assert [x.idx for x in src.walk()] == [0, 1, 2, 3]


def test_end_to_end_copy(tmp_path):
    src = ADBSource(FakeADB([ADBDevice("R1", "device")], PHONE), "R1")
    man = copy_and_verify(src, list(src.walk()), LocalTarget(tmp_path / "t"), lambda p: None, case_id="c1")
    assert man.verified_count == 4
    assert (tmp_path / "t/WhatsApp/Media/WhatsApp Images/IMG-20240412-WA0007.jpg").read_bytes() == b"W" * 20


def test_disconnect_mid_copy_stops(tmp_path):
    be = FakeADB([ADBDevice("R1", "device")], PHONE)
    src = ADBSource(be, "R1")
    be.disconnect_after = 8
    with pytest.raises(DeviceDisconnected):
        copy_and_verify(src, list(src.walk()), LocalTarget(tmp_path / "t"), lambda p: None, case_id="c1")


def test_single_file_error_is_skipped(tmp_path):
    be = FakeADB([ADBDevice("R1", "device")], PHONE)
    be.fail_paths.add("/sdcard/notes.txt")
    src = ADBSource(be, "R1")
    man = copy_and_verify(src, list(src.walk()), LocalTarget(tmp_path / "t"), lambda p: None, case_id="c1")
    assert man.verified_count == 3 and [s.error for s in man.skipped] == ["ERR_READ_FAILED"]


def test_walk_on_offline_device_raises():
    be = FakeADB([ADBDevice("R1", "device")], PHONE)
    src = ADBSource(be, "R1")
    be.state["R1"] = "offline"
    with pytest.raises(DeviceDisconnected):
        list(src.walk())


def test_scan_classifies_states(monkeypatch):
    monkeypatch.setattr(registry, "_scan_mtp", list)
    monkeypatch.setattr(registry, "_scan_mass_storage", lambda **_: [])
    be = FakeADB([ADBDevice("OK1", "device", "Pixel 7"), ADBDevice("LOCK", "unauthorized"),
                  ADBDevice("OLD", "offline"), ADBDevice("UDEV", "no permissions")])
    srcs = registry.scan(adb_backend=be)
    assert isinstance(srcs[0], ADBSource) and srcs[0].info().model == "Pixel 7"
    reasons = [s.reason for s in srcs[1:]]
    assert reasons == [REASON_ADB_UNAUTHORIZED, REASON_DISCONNECTED, REASON_NO_PERMISSION]
    with pytest.raises(Unreachable) as ei:
        list(srcs[1].walk())
    assert ei.value.reason == REASON_ADB_UNAUTHORIZED


def test_scan_skips_adb_twin_of_mtp_device(monkeypatch):
    class M:
        def info(self):
            from noam.device import DeviceInfo
            return DeviceInfo("SAME", "x", "mtp")
    monkeypatch.setattr(registry, "_scan_mtp", lambda: [M()])
    monkeypatch.setattr(registry, "_scan_mass_storage", lambda **_: [])
    srcs = registry.scan(adb_backend=FakeADB([ADBDevice("SAME", "device")]))
    assert len(srcs) == 1 and srcs[0].info().interface == "mtp"


def test_unavailable_stream_raises():
    from noam.device import DeviceInfo
    u = UnavailableSource(DeviceInfo("X", "Galaxy", "adb"), REASON_ADB_UNAUTHORIZED)
    with pytest.raises(Unreachable):
        u.stream(None, lambda b: None)  # type: ignore[arg-type]


def test_shell_quoting_of_hostile_names(monkeypatch):
    """שם עם רווח, גרש ו-$ חייב להגיע ל-cat כמחרוזת אחת, בלי הרחבה בשל ה-shell של המכשיר."""
    seen = {}

    class P:
        stdout = None

        def __init__(self, args, **kw):
            seen["args"] = args
            import io
            self.stdout = io.BytesIO(b"ok")

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr("noam.device.adb.subprocess.Popen", P)
    SubprocessADBBackend().stream_file("S", "/sdcard/WhatsApp Images/it's $HOME.jpg", lambda b: None)
    import shlex
    assert shlex.split(seen["args"][-1]) == ["cat", "/sdcard/WhatsApp Images/it's $HOME.jpg"]


def test_no_adb_binary_means_no_devices():
    assert SubprocessADBBackend(adb_path="/nonexistent/adb").list_devices() == []
