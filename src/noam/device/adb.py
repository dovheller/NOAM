"""WP2 — ADBSource: קריאה מהטלפון דרך adb, כשהמכשיר כבר מאושר ל-USB debugging מול העמדה.

מתי זה עוזר: טלפון שמסך ה-MTP שלו לא נגיש אבל debugging פעיל ומאושר, או שאפשר ללחוץ "אפשר"
פעם אחת עם עכבר OTG / scrcpy. מכשיר שמחזיר unauthorized → UnavailableSource (registry).

קריאה בלבד: find, stat, cat. שום פקודה שכותבת למכשיר (עיקרון 2).
כל נתיב שעובר ל-shell של המכשיר מצוטט (shlex.quote) — שמות כמו "WhatsApp Images" ו-$ ו-' נפוצים.
"""
from __future__ import annotations

import shlex
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from .base import DeviceInfo, Entry, Sink, Source
from .categories import GroupNamer, category, top_folder
from .errors import REASON_ADB_ERROR, DeviceDisconnected, DeviceError, Unreachable

CHUNK = 64 * 1024
LIST_CMD = "find . -type f -exec stat -c '%s\t%n' {} +"


@dataclass(frozen=True)
class ADBDevice:
    serial: str
    state: str          # device | unauthorized | offline | no permissions …
    model: str = ""


def parse_devices_output(text: str) -> list[ADBDevice]:
    """`adb devices -l`. 'no permissions' הוא שתי מילים — מטופל בנפרד."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("List of devices", "*")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = "no permissions" if parts[1:3] == ["no", "permissions"] else parts[1]
        model = next((p.split(":", 1)[1] for p in parts if p.startswith("model:")), "")
        out.append(ADBDevice(serial, state, model.replace("_", " ")))
    return out


@dataclass
class Listing:
    files: list[tuple[int, str]]
    unparsed: int  # שורות שלא פוענחו (למשל שם קובץ עם ירידת שורה) — מדווח, לא נבלע


def parse_files_output(text: str) -> Listing:
    files, bad = [], 0
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if not line:
            continue
        size_s, sep, rel = line.partition("\t")
        if not sep or not size_s.isdigit():
            bad += 1
            continue
        rel = rel.removeprefix("./")
        files.append((int(size_s), rel))
    return Listing(files, bad)


class ADBBackend(Protocol):
    def list_devices(self) -> list[ADBDevice]: ...
    def list_files(self, serial: str, root: str) -> Listing: ...
    def stream_file(self, serial: str, path: str, write: Sink) -> None: ...
    def get_state(self, serial: str) -> str: ...


class SubprocessADBBackend:
    """adb אמיתי. exec-out (לא shell): בלי pty, בלי המרת \\n ל-\\r\\n, בתים נקיים."""

    def __init__(self, adb_path: str = "adb") -> None:
        self.adb = adb_path

    def _run(self, args: list[str], timeout: float) -> subprocess.CompletedProcess:
        return subprocess.run([self.adb, *args], capture_output=True, check=False, timeout=timeout)

    def list_devices(self) -> list[ADBDevice]:
        try:
            p = self._run(["devices", "-l"], 10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        return parse_devices_output(p.stdout.decode("utf-8", "replace"))

    def get_state(self, serial: str) -> str:
        try:
            p = self._run(["-s", serial, "get-state"], 5)
        except subprocess.TimeoutExpired:
            return "offline"
        return p.stdout.decode().strip() or "offline"

    def list_files(self, serial: str, root: str) -> Listing:
        cmd = f"cd {shlex.quote(root)} && {LIST_CMD}"
        try:
            p = self._run(["-s", serial, "exec-out", cmd], 600)
        except subprocess.TimeoutExpired as e:
            raise DeviceDisconnected(serial) from e
        if p.returncode != 0 and self.get_state(serial) != "device":
            raise DeviceDisconnected(serial)
        # rc≠0 עם מכשיר חי = find נתקל בתיקייה בלי הרשאה; הרשימה החלקית תקפה.
        return parse_files_output(p.stdout.decode("utf-8", "surrogateescape"))

    def stream_file(self, serial: str, path: str, write: Sink) -> None:
        proc = subprocess.Popen(
            [self.adb, "-s", serial, "exec-out", f"cat {shlex.quote(path)}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            assert proc.stdout is not None
            while chunk := proc.stdout.read(CHUNK):
                write(chunk)
            rc = proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()  # כשל ביעד באמצע — לא משאירים adb תלוי
                proc.wait()
        if rc != 0:
            if self.get_state(serial) != "device":
                raise DeviceDisconnected(serial)
            raise DeviceError(REASON_ADB_ERROR)


class ADBSource(Source):
    def __init__(self, backend: ADBBackend, serial: str, *, root: str = "/sdcard", model: str = "") -> None:
        self._be = backend
        self.serial = serial
        self.root = root.rstrip("/") or "/sdcard"
        self.model = model or "Android"
        self.unparsed = 0

    def info(self) -> DeviceInfo:
        return DeviceInfo(device_id=self.serial, model=self.model, interface="adb")

    def walk(self) -> Iterator[Entry]:
        if self._be.get_state(self.serial) != "device":
            raise DeviceDisconnected(self.serial)
        listing = self._be.list_files(self.serial, self.root)
        self.unparsed = listing.unparsed
        groups = GroupNamer()
        for idx, (size, rel) in enumerate(sorted(listing.files, key=lambda f: f[1])):
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            yield Entry(idx=idx, group=groups(top_folder(parent)), rel_path=rel,
                        size=size, category=category(rel))

    def stream(self, entry: Entry, write: Sink) -> None:
        self._be.stream_file(self.serial, f"{self.root}/{entry.rel_path}", write)


def unreachable_reason(state: str) -> str | None:
    from .errors import (
        REASON_ADB_UNAUTHORIZED,
        REASON_DISCONNECTED,
        REASON_NO_PERMISSION,
    )
    return {
        "unauthorized": REASON_ADB_UNAUTHORIZED,
        "offline": REASON_DISCONNECTED,
        "no permissions": REASON_NO_PERMISSION,
    }.get(state, None if state == "device" else REASON_ADB_ERROR)


__all__ = ["ADBBackend", "ADBDevice", "ADBSource", "Listing", "SubprocessADBBackend",
           "Unreachable", "parse_devices_output", "parse_files_output", "unreachable_reason"]
