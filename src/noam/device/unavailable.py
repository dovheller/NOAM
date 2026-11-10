"""מכשיר שזוהה ולא ניתן לקריאה. מוצג למפעיל ונרשם בדוח עם הסיבה — לא נעלם בשקט."""
from __future__ import annotations

from collections.abc import Iterator

from .base import DeviceInfo, Entry, Sink, Source
from .errors import Unreachable


class UnavailableSource(Source):
    def __init__(self, info: DeviceInfo, reason: str) -> None:
        self._info = info
        self.reason = reason

    def info(self) -> DeviceInfo:
        return self._info

    def walk(self) -> Iterator[Entry]:
        raise Unreachable(self.reason, self._info.device_id)

    def stream(self, entry: Entry, write: Sink) -> None:
        raise Unreachable(self.reason, self._info.device_id)
