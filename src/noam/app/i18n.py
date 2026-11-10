"""תרגומי הטאבלט: JSON משלנו לחמש שפות (אין לוקאל יידיש מוכן). he ו-yi מימין לשמאל."""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

LANG_NAMES = {"he": "עברית", "yi": "ייִדיש", "en": "English", "ru": "Русский", "fr": "Français"}


@cache
def load_translations() -> dict[str, dict[str, str]]:
    out = {}
    for p in sorted((Path(__file__).parent / "i18n").glob("*.json")):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    keys = set(out["he"])
    for code, t in out.items():
        if set(t) != keys:
            raise ValueError(f"i18n/{code}.json keys differ from he.json")
    return out
