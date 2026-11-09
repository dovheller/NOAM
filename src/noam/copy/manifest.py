"""WP3 — מניפסט. ראו docs/REPORT_FORMAT.md.

שני קבצים:
  manifest-<case>.json      — בלי שמות: idx, קבוצה, גודל, טביעה, סטטוס. נכנס לדוח ולעמדה.
  client-files-<case>.json  — idx → נתיב. נשאר רק על מדיית היעד, ללקוח.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class FileRecord:
    idx: int
    group: str
    category: str
    size: int
    sha256: str
    status: str = "verified"


@dataclass(frozen=True)
class SkipRecord:
    idx: int
    group: str
    error: str  # קוד בלבד, למשל ERR_READ_FAILED


@dataclass
class Manifest:
    case: str
    source_device: str
    created: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    files: list[FileRecord] = field(default_factory=list)
    skipped: list[SkipRecord] = field(default_factory=list)

    @property
    def verified_count(self) -> int:
        return len(self.files)

    @property
    def bytes_verified(self) -> int:
        return sum(f.size for f in self.files)

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "source_device": self.source_device,
            "created": self.created,
            "summary": {
                "verified": self.verified_count,
                "skipped": len(self.skipped),
                "bytes": self.bytes_verified,
            },
            "files": [asdict(f) for f in sorted(self.files, key=lambda f: f.idx)],
            "skipped": [asdict(s) for s in sorted(self.skipped, key=lambda s: s.idx)],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)

    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()
