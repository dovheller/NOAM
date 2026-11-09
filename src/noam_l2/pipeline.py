"""WP11 — triage → collect → key → decrypt → export → wipe."""
from __future__ import annotations

from enum import Enum
from pathlib import Path


class Route(str, Enum):
    A_LIVE = "a"        # מכשיר חי, גישה מלאה
    B_DAMAGED = "b"     # מכשיר חי, מסך/מגע פגום
    C_DEAD = "c"        # מכשיר מת
    NO_SERVICE = "x"    # אין מפתח / אין גיבוי — אין חיוב


def triage(device_on: bool, has_e2e_key: bool, has_drive: bool | None, full_history: bool) -> Route:
    raise NotImplementedError("WP11")


def validate_backup_key(key: str) -> bool:
    """64 תווים הקסדצימליים (0–9, a–f). לא נשמר לדיסק."""
    raise NotImplementedError("WP11")


def decrypt(crypt_file: Path, key: str, enc_tmp: Path) -> Path:
    """wa-crypt-tools → msgstore.db בתיקייה מוצפנת. אף אדם לא פותח את הפלט."""
    raise NotImplementedError("WP11")


def wipe(enc_tmp: Path) -> list[dict]:
    """מוחק כל קובץ זמני ומחזיר רשומת מחיקה (מה, מתי)."""
    raise NotImplementedError("WP11")
