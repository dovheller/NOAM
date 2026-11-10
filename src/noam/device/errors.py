"""WP2 — שגיאות תחומיות של שכבת המכשיר."""
from __future__ import annotations

# קודי סיבה למכשיר שזוהה אבל לא נקרא. מחרוזות סגורות — לא טקסט חופשי, כדי שלא ידלוף תוכן ליומן.
REASON_ADB_UNAUTHORIZED = "ERR_ADB_UNAUTHORIZED"  # צריך ללחוץ "אפשר" על מסך הטלפון
REASON_NO_PERMISSION = "ERR_USB_PERMISSION"       # הרשאות udev בעמדה
REASON_DISCONNECTED = "ERR_DEVICE_DISCONNECTED"
REASON_NO_STORAGE = "ERR_NO_STORAGE_VISIBLE"      # MTP: נעול או לא נבחר "העברת קבצים"
REASON_ADB_ERROR = "ERR_ADB"


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


class Unreachable(DeviceError):
    """המכשיר זוהה אבל אי אפשר לקרוא ממנו. reason הוא אחד מקבועי REASON_* — נכנס לדוח כ"לא נגיש"."""

    def __init__(self, reason: str, device_id: str = "") -> None:
        super().__init__(f"unreachable ({reason})")
        self.reason = reason
        self.device_id = device_id
