"""WP2 — scan(): מזהה את כל המקורות המחוברים כרגע."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from . import mtp
from .adb import ADBBackend, ADBSource, SubprocessADBBackend, unreachable_reason
from .base import DeviceInfo, Source
from .errors import DeviceError
from .mass_storage import MassStorageSource
from .unavailable import UnavailableSource

log = logging.getLogger(__name__)

# דיסק יעד של העמדה מסומן בקובץ הזה בשורש שלו, ולעולם לא מוצג כמקור.
TARGET_MARKER = ".noam-target"

_MASS_STORAGE_ROOTS = (Path("/media"), Path("/mnt"), Path("/run/media"))


def _scan_mtp() -> list[Source]:
    try:
        return list(mtp.detect())
    except DeviceError as e:
        # libmtp חסרה או נכשלה — ממשיכים בלי MTP, ומדווחים (לא בשקט).
        log.warning("MTP scan unavailable: %s", e)
        return []


def _mounts(roots: Iterable[Path]) -> Iterable[Path]:
    """/media/X, /mnt/X, וגם /media/<user>/X ו-/run/media/<user>/X."""
    for root in roots:
        try:
            children = [c for c in root.iterdir() if c.is_dir()]
        except OSError:
            continue
        for child in children:
            if child.is_mount():
                yield child
                continue
            try:
                yield from (g for g in child.iterdir() if g.is_dir() and g.is_mount())
            except OSError:
                continue


def _scan_mass_storage(roots: Iterable[Path] = _MASS_STORAGE_ROOTS, exclude: Iterable[Path] = ()) -> list[Source]:
    excluded = {Path(p).resolve() for p in exclude}
    sources: list[Source] = []
    seen: set[Path] = set()
    for mount in _mounts(roots):
        real = mount.resolve()
        if real in seen or real in excluded or (mount / TARGET_MARKER).exists():
            continue
        seen.add(real)
        try:
            sources.append(MassStorageSource(mount, label="כרטיס / דיסק נשלף"))
        except OSError:
            continue
    return sources


def _scan_adb(backend: ADBBackend | None = None, skip_serials: set[str] = frozenset()) -> list[Source]:
    """מכשירים ב-adb. מכשיר שכבר נקרא ב-MTP לא נכלל שוב. מכשיר לא מאושר → UnavailableSource."""
    be = backend or SubprocessADBBackend()
    out: list[Source] = []
    for d in be.list_devices():
        if d.serial in skip_serials:
            continue
        reason = unreachable_reason(d.state)
        if reason is None:
            out.append(ADBSource(be, d.serial, model=d.model))
        else:
            out.append(UnavailableSource(DeviceInfo(d.serial, d.model or "Android", "adb"), reason))
    return out


def scan(exclude: Iterable[Path] = (), *, adb_backend: ADBBackend | None = None) -> list[Source]:
    """כל המקורות: MTP, adb (אם מאושר), אחסון רגיל. יעדי העמדה לא נכללים.
    מכשיר שזוהה ולא נקרא מוחזר כ-UnavailableSource — כדי שיופיע בדוח, לא ייעלם."""
    mtp_sources = _scan_mtp()
    seen = {s.info().device_id for s in mtp_sources}
    return mtp_sources + _scan_adb(adb_backend, seen) + _scan_mass_storage(exclude=exclude)
