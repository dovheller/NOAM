"""WP3 — שגיאות שעוצרות את כל ההעתקה (בניגוד לדילוג על קובץ בודד)."""
from __future__ import annotations


class CopyError(Exception):
    """בסיס לשגיאות העתקה שעוצרות את הסשן."""


class TargetError(CopyError):
    """היעד נכשל (נותק, לא כתיב, שגיאת דיסק). קוד בלבד, בלי נתיבים."""

    def __init__(self, code: str, errno: int | None = None) -> None:
        super().__init__(f"{code} (errno={errno})")
        self.code = code
        self.errno = errno


class InsufficientSpace(TargetError):
    def __init__(self, needed: int, free: int) -> None:
        super().__init__("ERR_TARGET_SPACE")
        self.needed, self.free = needed, free


class CopyCancelled(CopyError):
    """המפעיל ביטל באמצע. ההעתקה נעצרה בין קבצים או בין חתיכות."""
