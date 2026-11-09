"""WP2 — ממשק אחיד למקור נתונים (טלפון ב-MTP, כרטיס SD, דיסק)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class DeviceInfo:
    device_id: str
    model: str
    interface: str  # "mtp" | "mass_storage"


@dataclass(frozen=True)
class Entry:
    idx: int
    group: str      # מזהה תיקייה אנונימי (g01…) — לצד המפעיל
    rel_path: str   # הנתיב האמיתי — לצד הלקוח בלבד, דרך privacy/
    size: int
    category: str   # images | video | docs | other


class Source(ABC):
    @abstractmethod
    def info(self) -> DeviceInfo: ...

    @abstractmethod
    def walk(self) -> Iterator[Entry]: ...

    @abstractmethod
    def open(self, entry: Entry) -> BinaryIO: ...


def scan() -> list[Source]:
    """מחזיר את המקורות המחוברים כרגע."""
    raise NotImplementedError("WP2")
