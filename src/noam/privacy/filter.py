"""WP6 — מה שיוצא למפעיל: ספירות, נפחים, סטטוס, hash. שום דבר אחר."""
from __future__ import annotations

from typing import Iterable

from noam.device.base import Entry

BLOCKED_COMMANDS = ("ls", "cat", "find", "tree", "open", "head", "tail", "less", "cp", "mv", "du", "file", "strings", "explorer", "dir")


def operator_view(entries: Iterable[Entry]) -> dict:
    """ספירה ונפח לפי קטגוריה, ומזהי קבוצות אנונימיים. בלי rel_path."""
    raise NotImplementedError("WP6")


def client_view(entries: Iterable[Entry]) -> dict:
    """העץ המלא, לטאבלט של הלקוח בלבד."""
    raise NotImplementedError("WP6")


def is_blocked(command: str) -> bool:
    """פקודת תוכן במסך נועם. נחסמת ונרשמת ביומן."""
    raise NotImplementedError("WP6")
