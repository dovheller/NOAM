"""WP2 — scan(): מזהה את כל המקורות המחוברים כרגע."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from . import mtp
from .base import Source
from .errors import DeviceError
from .mass_storage import MassStorageSource

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
            sources.append(MassStorageSource(mount, label=mount.name))
        except OSError:
            continue
    return sources


def scan(exclude: Iterable[Path] = ()) -> list[Source]:
    """כל המקורות המחוברים: MTP ואחסון רגיל. יעדי העמדה (exclude או סמן) לא נכללים."""
    return _scan_mtp() + _scan_mass_storage(exclude=exclude)
