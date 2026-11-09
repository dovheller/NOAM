"""WP4 — יעדים. ענן: "הועתק" ≠ "סונכרן" — שני מצבים נפרדים."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Target(ABC):
    @abstractmethod
    def free_bytes(self) -> int: ...

    @abstractmethod
    def write_test(self) -> None:
        """כתיבת-ניסיון לפני התחלה. זורק אם היעד לא כתיב."""

    @abstractmethod
    def is_synced(self) -> bool:
        """ליעד מקומי: True. לענן: רק אחרי אימות סנכרון."""
