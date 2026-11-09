"""WP1 — יומן audit append-only. מטא-דאטה בלבד: אסור שדה תוכן."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORBIDDEN_FIELDS = {
    "filename", "path", "folder", "thumbnail", "content", "text",
    "client_name", "phone", "message", "body",
}

ALLOWED_FIELDS = frozenset({
    "ts", "session_id", "operator", "action", "status", "event",
    "from_state", "to_state", "count", "size_bytes", "hash",
    "client_hash", "error_code", "prev_hash", "sig",
})

CONTENT_PATTERNS = (
    "/sdcard/", "/storage/emulated/", "/DCIM/", "/WhatsApp/",
    "C:\\Users\\", "\\Users\\",
    ".jpg", ".jpeg", ".png", ".heic", ".gif",
    ".mp4", ".mov", ".mkv",
    ".pdf", ".docx", ".xlsx", ".txt",
    ".crypt", "msgstore",
    "@gmail.", "@yahoo.", "@walla.", "@outlook.", "@hotmail.",
    "-----BEGIN",
)

GENESIS_HASH = "0" * 64


class ContentLeakError(ValueError):
    """Raised when an audit entry would leak content."""


class AuditLog:
    def __init__(self, path: Path, key: bytes | None = None) -> None:
        self.path = Path(path)
        env_key = os.environ.get("NOAM_AUDIT_KEY", "")
        self.key = key or (env_key.encode() if env_key else b"dev-only-key-change-me!!")
        if len(self.key) < 16:
            raise ValueError("HMAC key must be at least 16 bytes")
        self._prev_hash = self._tail_hash()

    def record(self, event: str, **meta: object) -> None:
        """רושם אירוע. זורק ValueError אם meta מכיל שדה מ-FORBIDDEN_FIELDS."""
        if not event or not str(event).strip():
            raise ValueError("event must not be empty")
        for k in meta:
            if k in FORBIDDEN_FIELDS or k not in ALLOWED_FIELDS:
                raise ContentLeakError(f"field not allowed: {k}")
        fields: dict[str, Any] = {"event": str(event), **meta}
        self._check_no_content(fields)
        self._append(fields)

    def append(self, **fields: Any) -> dict:
        """Append with explicit fields (whitelist enforced)."""
        for k in fields:
            if k in FORBIDDEN_FIELDS or (k not in ALLOWED_FIELDS and k not in ("event",)):
                raise ContentLeakError(f"field not allowed: {k}")
        self._check_no_content(fields)
        return self._append(dict(fields))

    def seal(self) -> str:
        """חותם את היומן בסגירת סשן ומחזיר את ה-SHA-256 שלו."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return GENESIS_HASH
        h = hashlib.sha256()
        with self.path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def verify(self) -> int:
        """Walk the chain. Returns entry count. Raises on failure."""
        if not self.path.exists():
            return 0
        prev = GENESIS_HASH
        count = 0
        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                entry = json.loads(raw)
                sig = entry.pop("sig", None)
                if entry.get("prev_hash") != prev:
                    raise ValueError(f"line {lineno}: prev_hash mismatch")
                expected = hmac.new(
                    self.key, _canonical(entry), hashlib.sha256
                ).hexdigest()
                if sig is None or not hmac.compare_digest(expected, sig):
                    raise ValueError(f"line {lineno}: bad signature")
                prev = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                count += 1
        return count

    def _append(self, fields: dict[str, Any]) -> dict:
        entry = dict(fields)
        entry.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        entry["prev_hash"] = self._prev_hash
        payload = _canonical(entry)
        entry["sig"] = hmac.new(self.key, payload, hashlib.sha256).hexdigest()
        line = _canonical(entry).decode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._prev_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()
        return entry

    def _check_no_content(self, fields: dict) -> None:
        for key, value in fields.items():
            if not isinstance(value, str):
                continue
            for pattern in CONTENT_PATTERNS:
                if pattern in value:
                    raise ContentLeakError(
                        f"value of {key!r} contains content marker {pattern!r}"
                    )

    def _tail_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return GENESIS_HASH
        with self.path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size == 0:
                return GENESIS_HASH
            pos = max(0, size - 2)
            fh.seek(pos)
            while pos > 0 and fh.read(1) != b"\n":
                pos -= 1
                fh.seek(pos)
            last = fh.readline().decode("utf-8").rstrip("\n")
        return hashlib.sha256(last.encode("utf-8")).hexdigest()


def _canonical(entry: dict) -> bytes:
    return json.dumps(
        entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
