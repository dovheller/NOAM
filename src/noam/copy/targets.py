"""WP3/WP4 — יעדים. WP3 מממש יעד מקומי (דיסק / SD). ענן — WP4: "הועתק" ≠ "סונכרן"."""
from __future__ import annotations

import os
import re
import shutil
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from .errors import TargetError

PART_SUFFIX = ".noam-part"
STATE_DIR = ".noam"
PAYLOAD_DIR = "data"  # BagIt (RFC 8493): הקבצים עצמם תחת data/
_BAD_CHARS = re.compile(r'[\\:*?"<>|\x00-\x1f]')  # לא חוקיים ב-exFAT/NTFS


def safe_relpath(rel: str) -> PurePosixPath:
    """נתיב שמגיע מהמכשיר לא סומכים עליו: בלי '..', בלי נתיב מוחלט, בלי תווים שהיעד לא מקבל."""
    parts = []
    for p in PurePosixPath(rel).parts:
        if p in ("", "/", ".", ".."):
            continue
        p = _BAD_CHARS.sub("_", p).rstrip(" .") or "_"
        parts.append(p)
    if not parts:
        raise ValueError("empty path")
    return PurePosixPath(*parts)


class Target(ABC):
    @abstractmethod
    def free_bytes(self) -> int: ...

    @abstractmethod
    def write_test(self) -> None:
        """כתיבת-ניסיון לפני התחלה. זורק TargetError אם היעד לא כתיב."""

    @abstractmethod
    def is_synced(self) -> bool:
        """ליעד מקומי: True. לענן: רק אחרי אימות סנכרון."""

    @abstractmethod
    def open_part(self, rel: PurePosixPath) -> BinaryIO:
        """פותח קובץ זמני לכתיבה, ליד היעד הסופי."""

    @abstractmethod
    def read_part(self, rel: PurePosixPath) -> Iterator[bytes]:
        """קורא בחזרה את הקובץ הזמני מהדיסק, לאימות."""

    @abstractmethod
    def commit(self, rel: PurePosixPath) -> None:
        """הקובץ הזמני אומת — מקבל את שמו הסופי (אטומי)."""

    @abstractmethod
    def discard(self, rel: PurePosixPath) -> None:
        """מוחק קובץ זמני. בטוח לקרוא גם אם אינו קיים."""

    @abstractmethod
    def state_path(self, name: str) -> Path:
        """קובץ מצב של העמדה על היעד (יומן התקדמות, מניפסט)."""


class LocalTarget(Target):
    """תיקייה על דיסק מקומי: root/<case>/ הוא תיק BagIt — data/ לקבצים, .noam/ למצב העמדה.
    שורש הדיסק מסומן .noam-target (ראו device/registry)."""

    CHUNK = 1024 * 1024

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.payload = self.root / PAYLOAD_DIR

    def _abs(self, rel: PurePosixPath, part: bool = False) -> Path:
        p = self.payload.joinpath(*rel.parts)
        return p.with_name(p.name + PART_SUFFIX) if part else p

    def free_bytes(self) -> int:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            return shutil.disk_usage(self.root).free
        except OSError as e:
            raise TargetError("ERR_TARGET_UNAVAILABLE", e.errno) from e

    def write_test(self) -> None:
        probe = self.state_path(".write-test")
        try:
            data = os.urandom(4096)
            with probe.open("wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if probe.read_bytes() != data:
                raise TargetError("ERR_TARGET_WRITE_TEST")
        except OSError as e:
            raise TargetError("ERR_TARGET_WRITE_TEST", e.errno) from e
        finally:
            probe.unlink(missing_ok=True)

    def is_synced(self) -> bool:
        return True

    def exists(self, rel: PurePosixPath) -> bool:
        return self._abs(rel).is_file()

    def open_part(self, rel: PurePosixPath) -> BinaryIO:
        p = self._abs(rel, part=True)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return p.open("wb")
        except OSError as e:
            raise TargetError("ERR_TARGET_WRITE", e.errno) from e

    def read_part(self, rel: PurePosixPath) -> Iterator[bytes]:
        try:
            with self._abs(rel, part=True).open("rb") as f:
                while chunk := f.read(self.CHUNK):
                    yield chunk
        except OSError as e:
            raise TargetError("ERR_TARGET_READ", e.errno) from e

    def commit(self, rel: PurePosixPath) -> None:
        try:
            os.replace(self._abs(rel, part=True), self._abs(rel))
            _fsync_dir(self._abs(rel).parent)
        except OSError as e:
            raise TargetError("ERR_TARGET_COMMIT", e.errno) from e

    def discard(self, rel: PurePosixPath) -> None:
        try:
            self._abs(rel, part=True).unlink(missing_ok=True)
        except OSError:
            pass

    def state_path(self, name: str) -> Path:
        d = self.root / STATE_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d / name


def _fsync_dir(d: Path) -> None:
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
