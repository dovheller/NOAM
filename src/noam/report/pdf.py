"""WP5 — הפקת הדוח. מבנה ב-docs/REPORT_FORMAT.md."""
from __future__ import annotations

from pathlib import Path


def build_report(session, manifest, out_dir: Path) -> Path:
    raise NotImplementedError("WP5")


def sign(pdf_path: Path, private_key_path: Path) -> str:
    """חתימת ECDSA P-256. מחזיר את טביעת המפתח."""
    raise NotImplementedError("WP5")
