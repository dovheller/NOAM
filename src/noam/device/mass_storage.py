"""WP2 — MassStorageSource: כרטיס SD או דיסק שממופה כתיקייה."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from .base import DeviceInfo, Entry, Source


_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".bmp"}
_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".3gp", ".webm"}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf"}


def _category(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _IMAGE_EXT:
        return "images"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _DOC_EXT:
        return "docs"
    return "other"


class MassStorageSource(Source):
    def __init__(self, root: Path, label: str = "SD") -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.label = label

    def info(self) -> DeviceInfo:
        return DeviceInfo(
            device_id=f"mass-{self.root.name}",
            model=self.label,
            interface="mass_storage",
        )

    def walk(self) -> Iterator[Entry]:
        idx = 0
        group_by_dir: dict[Path, str] = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            parent = path.parent
            if parent not in group_by_dir:
                group_by_dir[parent] = f"g{len(group_by_dir) + 1:02d}"
            yield Entry(
                idx=idx,
                group=group_by_dir[parent],
                rel_path=str(path.relative_to(self.root)),
                size=path.stat().st_size,
                category=_category(path),
            )
            idx += 1

    def open(self, entry: Entry) -> BinaryIO:
        return open(self.root / entry.rel_path, "rb")

    def close(self) -> None:
        pass
