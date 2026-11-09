"""WP1 — מעברים חוקיים / לא חוקיים."""
import pytest
from noam.session.model import Session, State, Service, ALLOWED_TRANSITIONS


def make_session(**kw):
    data = dict(
        case_id="2026-0418",
        client_name="מרים לוינגר",
        phone="052-000-0000",
        language="he",
        service=Service.TRANSFER,
    )
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
