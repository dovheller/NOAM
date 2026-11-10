"""WP2 — MassStorageSource: כרטיס SD או דיסק שממופה כתיקייה. מומלץ למפות read-only."""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

from .base import DeviceInfo, Entry, Sink, Source
from .categories import GroupNamer, category, top_folder
from .errors import DeviceDisconnected, DeviceError

CHUNK = 1024 * 1024


class MassStorageSource(Source):
    def __init__(self, root: Path, label: str = "SD") -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.label = label

    def info(self) -> DeviceInfo:
        # תווית הכרך היא טקסט שהלקוח בחר — לא מציגים אותה; מזהה = טביעה קצרה
        did = "mass-" + hashlib.sha256(str(self.root).encode()).hexdigest()[:8]
        return DeviceInfo(device_id=did, model=self.label, interface="mass_storage")

    def walk(self) -> Iterator[Entry]:
        if not self.root.is_dir():
            raise DeviceDisconnected(self.info().device_id)
        groups = GroupNamer()
        idx = 0
        for path in sorted(self.root.rglob("*")):
            # קישור סימבולי יכול להוביל אל מחוץ למקור — מדלגים.
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(self.root)
            yield Entry(
                idx=idx,
                group=groups(top_folder(rel.parent.as_posix())),
                rel_path=rel.as_posix(),
                size=path.stat().st_size,
                category=category(path.name),
            )
            idx += 1

    def stream(self, entry: Entry, write: Sink) -> None:
        path = self.root / entry.rel_path
        try:
            with path.open("rb") as fh:
                while chunk := fh.read(CHUNK):
                    write(chunk)
        except FileNotFoundError as e:
            if not self.root.is_dir():
                raise DeviceDisconnected(self.info().device_id) from e
            raise DeviceError("file vanished") from e
        except OSError as e:
            if not self.root.is_dir():
                raise DeviceDisconnected(self.info().device_id) from e
            raise DeviceError(f"read failed (errno={e.errno})") from e
