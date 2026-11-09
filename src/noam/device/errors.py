"""WP2 — שגיאות תחומיות של שכבת המכשיר."""
from __future__ import annotations


class DeviceError(Exception):
    """שגיאת בסיס לשכבת המכשיר."""


class DeviceDisconnected(DeviceError):
    """המכשיר נותק באמצע העבודה."""


class MTPError(DeviceError):
    """כשל בתקשורת MTP (libmtp החזיר שגיאה)."""

    def __init__(self, operation: str, code: int | None = None) -> None:
        super().__init__(f"MTP {operation} failed (code={code})")
        self.operation = operation
        self.code = code
