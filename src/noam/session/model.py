"""WP1 — מודל הסשן ומכונת המצבים. ראו docs/SPEC_LAYER1.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Service(str, Enum):
    BACKUP = "backup"
    TRANSFER = "transfer"
    RESTORE = "restore"


class State(str, Enum):
    OPEN = "open"
    DEVICE_DETECTED = "device_detected"
    TARGET_CHECKED = "target_checked"
    INDEXED = "indexed"
    CLIENT_SELECTED = "client_selected"
    CONSENT_SIGNED = "consent_signed"
    COPYING = "copying"
    VERIFIED = "verified"
    REPORTED = "reported"
    CLOSED = "closed"


@dataclass
class Session:
    case_id: str
    client_name: str
    phone: str
    language: str
    service: Service
    state: State = State.OPEN
    history: list[State] = field(default_factory=list)

    def advance(self, to: State) -> None:
        """מעבר מצב. זורק ValueError על מעבר לא חוקי."""
        raise NotImplementedError("WP1")
