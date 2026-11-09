"""WP1 — מעברים חוקיים / לא חוקיים."""
import pytest

from noam.session.model import Service, Session, State


def make_session(**kw):
    data = {
        "case_id": "2026-0418",
        "client_name": "מרים לוינגר",
        "phone": "052-000-0000",
        "language": "he",
        "service": Service.TRANSFER,
    }
    data.update(kw)
    return Session(**data)


def test_happy_path():
    s = make_session()
    path = [
        State.DEVICE_DETECTED,
        State.TARGET_CHECKED,
        State.INDEXED,
        State.CLIENT_SELECTED,
        State.CONSENT_SIGNED,
        State.COPYING,
        State.VERIFIED,
        State.REPORTED,
        State.CLOSED,
    ]
    for st in path:
        s.advance(st)
    assert s.state is State.CLOSED
    assert s.history[0] is State.OPEN


def test_illegal_transition():
    s = make_session()
    with pytest.raises(ValueError, match="illegal"):
        s.advance(State.COPYING)


def test_closed_is_terminal():
    s = make_session()
    for st in [
        State.DEVICE_DETECTED, State.TARGET_CHECKED, State.INDEXED,
        State.CLIENT_SELECTED, State.CONSENT_SIGNED, State.COPYING,
        State.VERIFIED, State.REPORTED, State.CLOSED,
    ]:
        s.advance(st)
    with pytest.raises(ValueError):
        s.advance(State.OPEN)


def test_operator_view_hides_pii():
    s = make_session()
    view = s.to_operator_view()
    assert "client_name" not in view
    assert "phone" not in view
    assert "מרים" not in str(view)


def test_invalid_language():
    with pytest.raises(ValueError):
        make_session(language="xx")


FORWARD_TO_COPYING = [
    State.DEVICE_DETECTED, State.TARGET_CHECKED, State.INDEXED,
    State.CLIENT_SELECTED, State.CONSENT_SIGNED, State.COPYING,
]


def test_back_allowed_until_client_selected():
    s = make_session()
    for st in FORWARD_TO_COPYING[:4]:
        s.advance(st)
    s.advance(State.INDEXED)          # הלקוח חוזר לבחירה
    s.advance(State.CLIENT_SELECTED)
    s.advance(State.CONSENT_SIGNED)
    with pytest.raises(ValueError, match="illegal"):
        s.advance(State.CLIENT_SELECTED)   # אחרי חתימה אין חזרה


def test_no_back_from_open():
    s = make_session()
    s.advance(State.DEVICE_DETECTED)
    s.advance(State.OPEN)
    assert s.state is State.OPEN


def test_abort_during_copy_then_report_and_close():
    s = make_session()
    for st in FORWARD_TO_COPYING:
        s.advance(st)
    s.abort("ERR_DEVICE_DISCONNECTED")
    assert s.state is State.ABORTED
    assert s.abort_code == "ERR_DEVICE_DISCONNECTED"
    s.advance(State.REPORTED)
    s.advance(State.CLOSED)


def test_abort_requires_code():
    s = make_session()
    with pytest.raises(ValueError):
        s.abort("")


def test_cannot_abort_closed():
    s = make_session()
    s.abort("ERR_CLIENT_CANCELLED")
    s.advance(State.CLOSED)
    with pytest.raises(ValueError):
        s.abort("ERR_X")
