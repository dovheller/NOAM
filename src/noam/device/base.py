"""WP2 — ממשק אחיד למקור נתונים (טלפון ב-MTP, כרטיס SD, דיסק)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

# write(chunk) — מקבל כל חתיכה של הקובץ כפי שהיא נקראת מהמקור.
Sink = Callable[[bytes], None]


@dataclass(frozen=True)
class DeviceInfo:
    device_id: str
    model: str
    interface: str  # "mtp" | "mass_storage"


@dataclass(frozen=True)
class Entry:
    idx: int        # מספר רץ בתוך הסשן (0, 1, 2…) — מופיע במניפסט ובדוח
    group: str      # מזהה תיקייה אנונימי (g01…) — לצד המפעיל
    rel_path: str   # הנתיב האמיתי — לצד הלקוח בלבד, דרך privacy/
    size: int
    category: str   # images | video | docs | other
    handle: int = field(default=0, compare=False)  # מזהה פנימי במכשיר (MTP item_id); לא מוצג


class Source(ABC):
    """מקור לקריאה בלבד. אין כאן שום פעולת כתיבה או מחיקה — עיקרון 2 ב-CLAUDE.md."""

    @abstractmethod
    def info(self) -> DeviceInfo: ...

    @abstractmethod
    def walk(self) -> Iterator[Entry]: ...

    @abstractmethod
    def stream(self, entry: Entry, write: Sink) -> None:
        """מזרים את תוכן הקובץ ישירות ל-write, בחתיכות.
        לא כותב שום עותק ביניים לדיסק של העמדה (docs/PRIVACY_MODEL.md).
        זורק DeviceDisconnected אם המכשיר נותק, DeviceError על כל כשל אחר."""

    def close(self) -> None:
        """משחרר את המכשיר. בטוח לקרוא יותר מפעם אחת."""
