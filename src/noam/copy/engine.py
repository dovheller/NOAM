"""WP3 — מנוע העתקה ואימות."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from noam.copy.manifest import Manifest
from noam.copy.targets import Target
from noam.device.base import Entry, Source


@dataclass
class Progress:
    total: int
    copied: int
    verified: int
    skipped: int


def copy_and_verify(
    source: Source,
    entries: Iterable[Entry],
    target: Target,
    on_progress: Callable[[Progress], None],
) -> Manifest:
    """מעתיק כל קובץ, מחשב SHA-256 על המקור ועל היעד ומשווה.
    קובץ שלא נקרא נרשם כדילוג ולא עוצר את הסשן. שגיאה מגיעה ל-on_progress, לא נבלעת."""
    raise NotImplementedError("WP3")
