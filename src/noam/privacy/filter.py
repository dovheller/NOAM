"""WP6 — המסנן היחיד בין הנתונים לבין צד המפעיל. ראו docs/PRIVACY_MODEL.md.

שתי שכבות הגנה:
1. **בנייה מ-allow-list:** תצוגת המפעיל נבנית רק משדות מספריים, מזהי קבוצה (g01…), קודים וסטטוס.
   אין בה rel_path, שם קובץ או שם תיקייה — הם פשוט לא מועתקים.
2. **בדיקת דליפה בזמן ריצה:** כל מטען שיוצא ל-API של המפעיל נסרק (assert_operator_safe) מול
   כל מקטעי הנתיבים של הסשן הנוכחי ומול תבניות תוכן. התאמה → PrivacyViolation, והמטען לא נשלח.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from noam.device.base import Entry

BLOCKED_COMMANDS = (
    "ls", "cat", "find", "tree", "open", "xdg-open", "head", "tail", "less", "more", "cp", "mv",
    "du", "file", "strings", "explorer", "dir", "grep", "vi", "vim", "nano", "python", "sh", "bash",
)
_CONTENT_HINTS = re.compile(r"(dcim|sdcard|/mnt/|/media/|--names|--show|thumb|whatsapp|msgstore)", re.IGNORECASE)

CONTENT_PATTERNS = (
    "/sdcard/", "/storage/emulated/", "DCIM/", "WhatsApp/", ".jpg", ".jpeg", ".png", ".heic",
    ".mp4", ".mov", ".pdf", ".docx", ".crypt", "msgstore",
)
_STORAGE_PREFIX = re.compile(r"^s[0-9a-f]{5,}$")  # MTP: מזהה האחסון שמוסיף device/mtp.py
CATEGORIES = ("images", "video", "docs", "other")


class PrivacyViolation(RuntimeError):
    """מטען לצד המפעיל הכיל תוכן. לא נשלח. ההודעה עצמה לא כוללת את התוכן."""


# ---------------------------------------------------------------------------
# מפעיל

def operator_view(entries: Iterable[Entry]) -> dict:
    """ספירה ונפח: סה"כ, לפי קטגוריה, ולפי קבוצה אנונימית. בלי rel_path, בלי שמות."""
    total = 0
    size = 0
    by_cat: dict[str, dict[str, int]] = {c: {"count": 0, "bytes": 0} for c in CATEGORIES}
    groups: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    for e in entries:
        total += 1
        size += e.size
        cat = e.category if e.category in by_cat else "other"
        by_cat[cat]["count"] += 1
        by_cat[cat]["bytes"] += e.size
        groups[e.group]["count"] += 1
        groups[e.group]["bytes"] += e.size
    return {
        "total": total,
        "bytes": size,
        "by_category": by_cat,
        "groups": [{"id": g, **v} for g, v in sorted(groups.items())],
    }


# ---------------------------------------------------------------------------
# לקוח

def group_label(rel_path: str) -> str:
    """שם התיקייה הראשית — ללקוח בלבד. '' = קבצים בשורש."""
    parts = [p for p in rel_path.split("/") if p]
    if parts and _STORAGE_PREFIX.match(parts[0]):
        parts = parts[1:]
    return parts[0] if len(parts) > 1 else ""


def client_view(entries: Iterable[Entry]) -> dict:
    """הקבוצות עם השמות האמיתיים, לטאבלט של הלקוח בלבד."""
    groups: dict[str, dict[str, Any]] = {}
    for e in entries:
        g = groups.setdefault(e.group, {
            "id": e.group, "label": group_label(e.rel_path), "count": 0, "bytes": 0,
            "categories": {c: 0 for c in CATEGORIES},
        })
        g["count"] += 1
        g["bytes"] += e.size
        g["categories"][e.category if e.category in CATEGORIES else "other"] += 1
    out = []
    for g in groups.values():
        g["main_category"] = max(g["categories"], key=g["categories"].get)
        out.append(g)
    out.sort(key=lambda g: (-g["count"], g["label"]))
    return {"groups": out, "total": sum(g["count"] for g in out), "bytes": sum(g["bytes"] for g in out)}


# ---------------------------------------------------------------------------
# מסך נועם

def is_blocked(command: str) -> bool:
    """פקודת תוכן במסך נועם. נחסמת ונרשמת ביומן."""
    cmd = command.strip()
    if not cmd:
        return False
    first = cmd.split()[0].rsplit("/", 1)[-1]
    return first in BLOCKED_COMMANDS or bool(_CONTENT_HINTS.search(cmd))


# ---------------------------------------------------------------------------
# בדיקת דליפה

def secrets_from_entries(entries: Iterable[Entry], min_len: int = 3) -> set[str]:
    """כל מקטע נתיב (תיקייה או שם קובץ) של הסשן — מה שאסור שיופיע אצל המפעיל."""
    out: set[str] = set()
    for e in entries:
        for part in e.rel_path.split("/"):
            if len(part) >= min_len and not _STORAGE_PREFIX.match(part):
                out.add(part.lower())
    return out


def _walk_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _walk_strings(v)


def assert_operator_safe(payload: Any, secrets: Iterable[str] = ()) -> Any:
    """זורק PrivacyViolation אם מחרוזת כלשהי במטען מכילה מקטע נתיב של הלקוח או תבנית תוכן.
    מחזיר את המטען כמו שהוא אם הוא נקי — לשימוש בשרשור: return assert_operator_safe(build())."""
    secret_list = [s for s in secrets if s]
    for s in _walk_strings(payload):
        low = s.lower()
        for p in CONTENT_PATTERNS:
            if p.lower() in low:
                raise PrivacyViolation("operator payload contains a content pattern")
        for sec in secret_list:
            if sec in low:
                raise PrivacyViolation("operator payload contains a client path segment")
    return payload
