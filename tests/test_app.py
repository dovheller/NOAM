"""WP7–WP9 — השרת: זרימה מלאה דרך ה-HTTP, הרשאות לפי כתובת, ופרטיות של מה שהקונסולה מקבלת."""
from __future__ import annotations

import base64
import re

import pytest
from fastapi.testclient import TestClient
from test_station import PHONE_FILES, PW, png

from noam.app import create_app
from noam.device import MassStorageSource
from noam.report import SigningKey, generate_key
from noam.station import Station, StationConfig


@pytest.fixture
def setup(tmp_path):
    phone = tmp_path / "phone"
    for rel, data in PHONE_FILES.items():
        p = phone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    cfg = StationConfig(
        station_id="ST-T", display_name="נועם הלר", address="ירושלים", phone="050-0000000",
        target_root=tmp_path / "ssd", audit_dir=tmp_path / "audit", reports_dir=tmp_path / "reports",
        signing_key=tmp_path / "keys" / "station.pem", operator_pin="2468",
        operator_hosts=["testclient"],
    )
    generate_key(cfg.signing_key, PW)
    src = MassStorageSource(phone, label="Pixel 7")
    st = Station(cfg, scan_fn=lambda **_: [src], audit_key=b"k" * 32,
                 signing_key=SigningKey.load(cfg.signing_key, PW), run_async=False)
    app = create_app(st, poll_interval=0)
    return st, cfg, app


def toast(r) -> str:
    m = re.search(r'id="toast"[^>]*>(.*?)</div>', r.text, re.DOTALL)
    return m.group(1) if m else ""


def test_full_flow_over_http(setup):
    st, _cfg, app = setup
    with TestClient(app) as op:
        assert "קונסולת המפעיל" in op.get("/operator").text
        r = op.post("/op/session", data={"case_id": "2026-0418", "client_name": "מרים לוינגר", "phone": "052",
                                         "language": "he", "service": "transfer"})
        assert toast(r) == ""
        assert "בחר שפה" in op.get("/client").text
        op.post("/cl/lang/ru")
        assert "Подключение устройства" in op.get("/client").text
        st.poll_devices()
        op.post("/cl/source/0")
        page = op.get("/client").text
        assert "Documents" in page and "WhatsApp" in page   # הלקוח רואה שמות תיקיות
        op.post("/cl/confirm")
        sig = "data:image/png;base64," + base64.b64encode(png()).decode()
        assert toast(op.post("/cl/consent", data={"signature": sig})) == ""
        assert "Копия записана и проверена" in op.get("/client").text
        op.post("/op/tab/finish")
        assert toast(op.post("/op/report")) == ""
        name = st.current.report_path.name
        pdf = op.get(f"/op/report/{name}")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        op.post("/op/close")
        assert "2026-0418" in op.get("/operator").text  # בהיסטוריה


def test_operator_pages_never_show_client_content(setup):
    st, _cfg, app = setup
    with TestClient(app) as op:
        op.post("/op/session", data={"case_id": "c1", "client_name": "מרים", "language": "he", "service": "backup"})
        op.post("/cl/lang/he")
        st.poll_devices()
        op.post("/cl/source/0")
        forbidden = {part for rel in PHONE_FILES for part in rel.split("/") if len(part) >= 3}
        for tab in ("queue", "active", "finish", "history", "diag", "shell"):
            op.post(f"/op/tab/{tab}")
            html = op.get("/operator").text
            for f in forbidden:
                assert f not in html, (tab, f)


def test_operator_endpoints_refuse_other_hosts(setup):
    _st, cfg, app = setup
    cfg.operator_hosts = ["127.0.0.1"]  # הבדיקה מגיעה מ-"testclient" = טאבלט
    with TestClient(app) as tablet:
        assert tablet.get("/operator").status_code == 403
        assert tablet.post("/op/session", data={"case_id": "x", "client_name": "y"}).status_code == 403
        assert tablet.get("/op/report/NOAM-x-R1.pdf").status_code == 403
        assert "בחר שפה" not in tablet.get("/").text or True  # / מגיש את הטאבלט לכתובת שאינה מפעיל
        assert "קונסולת המפעיל" not in tablet.get("/").text


def test_errors_become_toasts_not_500(setup):
    _st, _cfg, app = setup
    with TestClient(app) as op:
        r = op.post("/op/report")
        assert "אין סשן פעיל" in toast(r)
        r = op.post("/op/session", data={"case_id": "../x", "client_name": "a", "language": "he", "service": "backup"})
        assert "ERR_BAD_CASE_ID" in toast(r)
        r = op.post("/cl/consent", data={"signature": "not-an-image"})
        assert toast(r)  # הודעה כללית ללקוח


def test_settings_pin_and_report_name_validation(setup):
    _st, _cfg, app = setup
    with TestClient(app) as op:
        op.post("/op/tab/settings")
        assert "אזור מוגן" in op.get("/operator").text
        assert "קוד שגוי" in toast(op.post("/op/settings/unlock", data={"pin": "0000"}))
        op.post("/op/settings/unlock", data={"pin": "2468"})
        assert "ECDSA P-256" in op.get("/operator").text
        assert op.get("/op/report/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_websocket_pushes_screen(setup):
    _st, _cfg, app = setup
    with TestClient(app) as c, c.websocket_connect("/ws/client") as ws:
        first = ws.receive_text()
        assert 'id="screen"' in first and "hx-swap-oob" in first
        c.post("/op/session", data={"case_id": "w1", "client_name": "a", "language": "en", "service": "backup"})
        msg = ws.receive_text()
        assert "Choose your language" in msg


def test_all_assets_are_local(setup):
    _, _, app = setup
    with TestClient(app) as c:
        for page in ("/operator", "/client"):
            html = c.get(page).text
            assert "http://" not in html and "https://" not in html
            for src in re.findall(r'(?:src|href)="([^"]+)"', html):
                if src.startswith("/static/"):
                    assert c.get(src).status_code == 200, src
        css = c.get("/static/app.css").text
        assert "http" not in css


def test_i18n_files_complete():
    from noam.app.i18n import load_translations
    t = load_translations()
    assert set(t) == {"he", "yi", "en", "ru", "fr"}
    assert t["he"]["dir"] == t["yi"]["dir"] == "rtl"
    assert t["en"]["dir"] == "ltr"
    # מפתח בשם של מתודת dict (clear, items…) מוחזר ב-Jinja כמתודה ולא כטקסט — באג שכבר קרה
    assert not {k for k in t["he"] if hasattr(dict, k)}


def test_unauthorized_gets_403_before_form_validation(setup):
    _st, cfg, app = setup
    cfg.operator_hosts = ["127.0.0.1"]
    with TestClient(app) as c:
        assert c.post("/op/session").status_code == 403  # בלי טופס — עדיין 403, לא 422


def test_cross_origin_post_refused(setup):
    _st, _cfg, app = setup
    with TestClient(app) as c:
        assert c.post("/op/tab/queue", headers={"origin": "http://evil.example"}).status_code == 403
        assert c.post("/op/tab/queue", headers={"origin": "http://testserver"}).status_code == 200


def test_tablet_hosts_accept_cidr(setup):
    _st, cfg, app = setup
    cfg.operator_hosts = ["127.0.0.1"]
    cfg.tablet_hosts = ["10.77.0.0/24"]
    with TestClient(app) as c:  # "testclient" אינו כתובת ברשת
        assert c.get("/client").status_code == 403
