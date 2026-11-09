"""מיון קבצים לקטגוריות לפי סיומת. משותף ל-MTP ול-mass storage."""
from __future__ import annotations

from pathlib import PurePosixPath

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".bmp", ".dng"}
_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".3gp", ".webm"}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt"}


def category(name: str) -> str:
    ext = PurePosixPath(name).suffix.lower()
    if ext in _IMAGE_EXT:
        return "images"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _DOC_EXT:
        return "docs"
    return "other"


class GroupNamer:
    """נותן לכל תיקייה מזהה אנונימי יציב (g01, g02…) לפי סדר ההופעה הראשונה של קובץ בה."""

    def __init__(self) -> None:
        self._ids: dict[str, str] = {}

    def __call__(self, folder: str) -> str:
        if folder not in self._ids:
            self._ids[folder] = f"g{len(self._ids) + 1:02d}"
        return self._ids[folder]
