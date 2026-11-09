"""WP1 — מודל הסשן ומכונת המצבים. ראו docs/SPEC_LAYER1.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


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


ALLOWED_TRANSITIONS: dict[State, frozenset[State]] = {
    State.OPEN: frozenset({State.DEVICE_DETECTED}),
    State.DEVICE_DETECTED: frozenset({State.TARGET_CHECKED}),
    State.TARGET_CHECKED: frozenset({State.INDEXED}),
    State.INDEXED: frozenset({State.CLIENT_SELECTED}),
    State.CLIENT_SELECTED: frozenset({State.CONSENT_SIGNED}),
    State.CONSENT_SIGNED: frozenset({State.COPYING}),
    State.COPYING: frozenset({State.VERIFIED}),
    State.VERIFIED: frozenset({State.REPORTED}),
    State.REPORTED: frozenset({State.CLOSED}),
    State.CLOSED: frozenset(),
}

VALID_LANGUAGES = frozenset({"he", "yi", "en", "ru", "fr"})


@dataclass
class Session:
    case_id: str
    client_name: str
    phone: str
    language: str
    service: Service
    operator: str = "operator"
    session_id: str = field(default_factory=lambda: uuid4().hex)
    state: State = State.OPEN
    history: list[State] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if isinstance(self.service, str):
            self.service = Service(self.service)
        if self.language not in VALID_LANGUAGES:
            raise ValueError(f"invalid language: {self.language!r}")
        if not self.history:
            self.history = [self.state]

    def advance(self, to: State) -> None:
        """מעבר מצב. זורק ValueError על מעבר לא חוקי."""
        if to not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"illegal transition: {self.state.value} → {to.value}")
        self.state = to
        self.history.append(to)
        self.updated_at = datetime.now(timezone.utc)

    def to_operator_view(self) -> dict:
        """Non-PII projection for the operator console."""
        return {
            "session_id": self.session_id,
            "case_id": self.case_id,
            "service": self.service.value,
            "language": self.language,
            "operator": self.operator,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
        }
