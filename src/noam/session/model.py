"""WP1 — מודל הסשן ומכונת המצבים. ראו docs/SPEC_LAYER1.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    ABORTED = "aborted"


# קדימה: שלב אחד בכל פעם. אחורה: שלב אחד, ורק עד "לקוח בחר" (docs/SPEC_LAYER1.md).
# אחרי חתימת ההסכמה אין חזרה; עצירה רק דרך abort(), שמובילה ל-ABORTED.
ALLOWED_TRANSITIONS: dict[State, frozenset[State]] = {
    State.OPEN: frozenset({State.DEVICE_DETECTED}),
    State.DEVICE_DETECTED: frozenset({State.TARGET_CHECKED, State.OPEN}),
    State.TARGET_CHECKED: frozenset({State.INDEXED, State.DEVICE_DETECTED}),
    State.INDEXED: frozenset({State.CLIENT_SELECTED, State.TARGET_CHECKED}),
    State.CLIENT_SELECTED: frozenset({State.CONSENT_SIGNED, State.INDEXED}),
    State.CONSENT_SIGNED: frozenset({State.COPYING}),
    State.COPYING: frozenset({State.VERIFIED}),
    State.VERIFIED: frozenset({State.REPORTED}),
    State.REPORTED: frozenset({State.CLOSED}),
    State.CLOSED: frozenset(),
    # סשן שבוטל עדיין מקבל דוח (חלקי, חתום) לפני סגירה, או נסגר ישר אם לא הועתק כלום.
    State.ABORTED: frozenset({State.REPORTED, State.CLOSED}),
}

TERMINAL_FOR_ABORT = frozenset({State.ABORTED, State.REPORTED, State.CLOSED})

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
    abort_code: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

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
        self.updated_at = datetime.now(UTC)

    def abort(self, error_code: str) -> None:
        """עצירת סשן מכל שלב פעיל (ניתוק, דיסק מלא, הלקוח ביטל).
        error_code הוא קוד טכני בלבד, למשל ERR_DEVICE_DISCONNECTED — לא טקסט חופשי."""
        if not error_code or not error_code.strip():
            raise ValueError("abort requires an error_code")
        if self.state in TERMINAL_FOR_ABORT:
            raise ValueError(f"cannot abort from state: {self.state.value}")
        self.abort_code = error_code
        self.state = State.ABORTED
        self.history.append(State.ABORTED)
        self.updated_at = datetime.now(UTC)

    def to_operator_view(self) -> dict:
        """Non-PII projection for the operator console."""
        return {
            "session_id": self.session_id,
            "case_id": self.case_id,
            "service": self.service.value,
            "language": self.language,
            "operator": self.operator,
            "state": self.state.value,
            "abort_code": self.abort_code,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
        }
