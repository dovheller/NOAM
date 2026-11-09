"""WP2 — scan(): מזהה את כל המקורות המחוברים כרגע."""
from __future__ import annotations

from pathlib import Path

from .base import Source
from .errors import MTPError
from .mass_storage import MassStorageSource
from .mtp import MTPSource, _load

_MASS_STORAGE_ROOTS = (
    Path("/media"),
    Path("/mnt"),
    Path("/run/media"),
)


def _scan_mtp() -> list[Source]:
    try:
        lib = _load()
    except MTPError:
        return []

    sources: list[Source] = []
    handle = lib.LIBMTP_Get_First_Device()
    while handle:
        try:
            sources.append(MTPSource(handle))
        except Exception:
            lib.LIBMTP_Release_Device(handle)
        handle = lib.LIBMTP_Get_Next_Device()
    return sources


def _scan_mass_storage() -> list[Source]:
    seen: set[Path] = set()
    sources: list[Source] = []
    for root in _MASS_STORAGE_ROOTS:
        if not root.exists():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child in seen:
                continue
            # /run/media/user/LABEL — go one level deeper if needed
            candidates = [child]
            try:
                sub = list(child.iterdir())
                if sub and all(s.is_dir() for s in sub) and not any(
                    (s / "DCIM").exists() or (s / "Android").exists() for s in sub
                ):
                    # likely user folder; scan mounts under it
                    candidates = [s for s in sub if s.is_dir()]
            except OSError:
                pass
            for mount in candidates:
                if mount in seen:
                    continue
                seen.add(mount)
                try:
                    sources.append(MassStorageSource(mount, label=mount.name))
                except OSError:
                    continue
    return sources


def scan() -> list[Source]:
    """מחזיר את כל המקורות המחוברים: MTP + mass storage."""
    return _scan_mtp() + _scan_mass_storage()
