"""WP1 — יומן audit append-only. מטא-דאטה בלבד: אסור שדה תוכן."""
from __future__ import annotations

from pathlib import Path

FORBIDDEN_FIELDS = {"filename", "path", "folder", "thumbnail", "content", "text"}


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, event: str, **meta: object) -> None:
        """רושם אירוע. זורק ValueError אם meta מכיל שדה מ-FORBIDDEN_FIELDS."""
        raise NotImplementedError("WP1")

    def seal(self) -> str:
        """חותם את היומן בסגירת סשן ומחזיר את ה-SHA-256 שלו."""
        raise NotImplementedError("WP1")
