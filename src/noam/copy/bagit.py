"""מניפסט בתקן BagIt (RFC 8493), כך שעורך דין או לקוח יאמתו את ההעתקה בכל כלי BagIt — בלי התוכנה שלנו.

נכתב על מדיית הלקוח בלבד (הוא כולל שמות קבצים). ה-SHA-256 כבר חושב בזמן ההעתקה; לא קוראים שוב.
אימות: `python -m bagit --validate <תיק>` או כל מימוש אחר (Go, Java, Rust).
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from .targets import PAYLOAD_DIR


def _enc(path: str) -> str:
    # RFC 8493 §2.1.3: % ו-CR/LF בנתיב מקודדים
    return path.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_bag(root: Path, files: list[tuple[str, str, int]], *, case_id: str, manifest_sha256: str) -> None:
    """files: (נתיב יחסי תחת data/, sha256, גודל) — רק קבצים שאומתו."""
    root = Path(root)
    (root / PAYLOAD_DIR).mkdir(parents=True, exist_ok=True)
    total = sum(f[2] for f in files)
    (root / "bagit.txt").write_text("BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n", encoding="utf-8")
    info = [
        "Source-Organization: NOAM",
        f"Bagging-Date: {datetime.now(UTC).date().isoformat()}",
        f"External-Identifier: {case_id}",
        f"Payload-Oxum: {total}.{len(files)}",
        f"NOAM-Manifest-SHA256: {manifest_sha256}",
        ("Internal-Sender-Description: Every file was copied to a temporary file, read back from disk and"
         " compared to the source by SHA-256 before being committed."),
    ]
    (root / "bag-info.txt").write_text("\n".join(info) + "\n", encoding="utf-8")
    lines = sorted(f"{sha}  {PAYLOAD_DIR}/{_enc(rel)}" for rel, sha, _ in files)
    (root / "manifest-sha256.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    tags = ["bagit.txt", "bag-info.txt", "manifest-sha256.txt"]
    (root / "tagmanifest-sha256.txt").write_text(
        "".join(f"{_sha256_file(root / t)}  {t}\n" for t in tags), encoding="utf-8"
    )
