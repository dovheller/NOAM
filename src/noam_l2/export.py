"""WP12 — ארכיון HTML (RTL, אינדקס, חיפוש, מדיה) ו-PDF.
לוגיקת ה-SQL מ-whatsapp-msgstore-viewer (dbs/v1/db.py), בלי ה-UI שלו."""
from __future__ import annotations

from pathlib import Path


def export_html(msgstore: Path, media_dir: Path | None, out_dir: Path) -> Path:
    raise NotImplementedError("WP12")


def export_pdf(msgstore: Path, out_path: Path) -> Path:
    raise NotImplementedError("WP12")
