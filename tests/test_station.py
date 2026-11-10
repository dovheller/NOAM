"""WP7–WP9 — מנהל העמדה: זרימה מלאה, ביטולים, ופרטיות של מה שיוצא למפעיל."""
from __future__ import annotations

import io
import json

import pytest

from noam.device import (
    DeviceDisconnected,
    DeviceInfo,
    MassStorageSource,
    UnavailableSource,
)
from noam.device.errors import REASON_ADB_UNAUTHORIZED
from noam.report import SigningKey, generate_key, verify_embedded
from noam.session.audit import AuditLog
from noam.station import Station, StationConfig, StationError

KEY = b"k" * 32
PW = "correct horse battery"
PHONE_FILES = {
    "DCIM/Camera/IMG_ברית_יוסי.jpg": b"A" * 5000,
    "DCIM/Screenshots/s.png": b"S" * 300,
    "Documents/בדיקות_דם_מרים.pdf": b"D" * 700,
    "WhatsApp/Media/WhatsApp Images/IMG-20240412-WA0007.jpg": b"W" * 900,
}


def png() -> bytes:
    from PIL import Image  # pillow מגיע עם pyhanko/fpdf2
    b = io.BytesIO()
    im = Image.new("RGB", (300, 120), "white")
    for x in range(20, 280):
        im.putpixel((x, 60), (0, 0, 0))
    im.save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def env(tmp_path):
    phone = tmp_path / "phone"
    for rel, data in PHONE_FILES.items():
        p = phone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    cfg = StationConfig(
        station_id="ST-T", display_name="נועם הלר", address="ירושלים",
        target_root=tmp_path / "ssd", audit_dir=tmp_path / "audit", reports_dir=tmp_path / "reports",
        signing_key=tmp_path / "keys" / "station.pem",
    )
    generate_key(cfg.signing_key, PW)
    devices = {"list": [MassStorageSource(phone, label="Pixel 7"),
                        UnavailableSource(DeviceInfo("LOCK1", "Galaxy A12", "adb"), REASON_ADB_UNAUTHORIZED)]}
    st = Station(cfg, scan_fn=lambda **_: devices["list"], audit_key=KEY,
                 signing_key=SigningKey.load(cfg.signing_key, PW), run_async=False)
    return st, cfg, devices


def open_(st, case="2026-0418"):
    st.open_session(case_id=case, client_name="מרים לוינגר", phone="052-000-0000", language="he", service="transfer")


def full_flow(st):
    open_(st)
    st.choose_language("he")
    assert st.poll_devices()
    st.choose_source(0)
    st.confirm_selection()
    st.sign_consent(png())


def test_full_session_flow(env):
    st, cfg, _ = env
    full_flow(st)
    assert st.client_snapshot()["screen"] == "done"
    pdf = st.make_report()
    assert verify_embedded(pdf, cfg.signing_key.with_suffix(".crt"))
    st.close()
    assert st.current is None
    h = st.history()[0]
    assert h["verified"] == 4 and h["status"] == "ok" and h["report"] == pdf.name
    # יומן: שרשרת תקינה, בלי תוכן
    audit = AuditLog(cfg.audit_dir / "2026-0418.jsonl", key=KEY)
    assert audit.verify() > 8
    text = (cfg.audit_dir / "2026-0418.jsonl").read_text()
    for rel in PHONE_FILES:
        for part in rel.split("/"):
            assert part not in text
    assert "לוינגר" not in text
    # ללקוח: הקבצים + הדוח על המדיה שלו
    case_dir = cfg.target_root / "2026-0418"
    assert (case_dir / "data/Documents/בדיקות_דם_מרים.pdf").exists()
    assert (case_dir / ".noam" / pdf.name).exists()


def test_client_screens_in_order(env):
    st, _, _ = env
    seen = []
    open_(st)
    seen.append(st.client_snapshot()["screen"])
    st.choose_language("yi")
    seen.append(st.client_snapshot()["screen"])
    st.poll_devices()
    seen.append(st.client_snapshot()["screen"])
    st.choose_source(0)
    seen.append(st.client_snapshot()["screen"])
    st.confirm_selection()
    seen.append(st.client_snapshot()["screen"])
    st.sign_consent(png())
    seen.append(st.client_snapshot()["screen"])
    assert seen == ["lang", "connect", "src", "browse", "consent", "done"]
    assert st.client_snapshot()["lang"] == "yi"


def test_client_sees_folder_names_operator_does_not(env):
    st, _, _ = env
    open_(st)
    st.choose_language("he")
    st.poll_devices()
    st.choose_source(0)
    labels = {g["label"] for g in st.client_snapshot()["browse"]["groups"]}
    assert {"DCIM", "Documents", "WhatsApp"} <= labels
    op = json.dumps(st.operator_snapshot(), ensure_ascii=False)
    for word in ("DCIM", "Documents", "WhatsApp", "Camera", "יוסי", "בדיקות"):
        assert word not in op
    assert "מרים לוינגר" in op  # השם שהמפעיל הקליד — מותר


def test_selection_subset(env):
    st, _, _ = env
    open_(st)
    st.choose_language("he")
    st.poll_devices()
    st.choose_source(0)
    groups = st.client_snapshot()["browse"]["groups"]
    docs = next(g["id"] for g in groups if g["label"] == "Documents")
    st.set_selection([docs, "g99"])  # g99 לא קיים — מתעלמים
    st.confirm_selection()
    st.sign_consent(png())
    assert st.current.manifest.verified_count == 1


def test_unavailable_device_listed_and_in_report(env):
    st, _, _ = env
    full_flow(st)
    devs = st.operator_snapshot()["session"]["devices"]
    assert any(d["unavailable"] and d["reason"] == REASON_ADB_UNAUTHORIZED for d in devs)
    with pytest.raises(StationError):
        st.choose_source(1)


def test_cannot_choose_unavailable_source(env):
    st, _, _ = env
    open_(st)
    st.choose_language("he")
    st.poll_devices()
    with pytest.raises(StationError) as ei:
        st.choose_source(1)
    assert ei.value.code == "ERR_BAD_SOURCE"


def test_disconnect_during_copy_aborts_with_code(env):
    st, _cfg, devices = env
    src = devices["list"][0]
    orig = src.stream

    def broken(entry, write):
        if "Documents" in entry.rel_path:
            raise DeviceDisconnected("x")
        orig(entry, write)

    src.stream = broken
    full_flow(st)
    assert st.current.session.abort_code == "ERR_DEVICE_DISCONNECTED"
    assert st.client_snapshot()["screen"] == "stopped"
    pdf = st.make_report()  # דוח חלקי לסשן שבוטל
    assert pdf.exists()
    st.close()
    assert st.history()[0]["status"] == "aborted"


def test_report_requires_unlocked_key(env):
    st, _, _ = env
    st.signing_key = None
    full_flow(st)
    with pytest.raises(StationError) as ei:
        st.make_report()
    assert ei.value.code == "ERR_SIGNING_LOCKED"
    with pytest.raises(StationError):
        st.unlock_signing("wrong passphrase!!")
    st.unlock_signing(PW)
    st.make_report()


def test_consent_requires_real_signature(env):
    st, _, _ = env
    open_(st)
    st.choose_language("he")
    st.poll_devices()
    st.choose_source(0)
    st.confirm_selection()
    with pytest.raises(StationError):
        st.sign_consent(b"not a png")


def test_one_session_at_a_time_and_case_ids(env):
    st, _, _ = env
    open_(st)
    with pytest.raises(StationError) as ei:
        open_(st, "2026-0419")
    assert ei.value.code == "ERR_SESSION_ACTIVE"
    st.abort()
    st.close()
    with pytest.raises(StationError) as ei:
        open_(st)  # אותו מספר תיק — יש לו כבר יומן
    assert ei.value.code == "ERR_CASE_EXISTS"
    with pytest.raises(StationError):
        open_(st, "../etc")


def test_shell_blocks_content_commands_and_logs(env):
    st, cfg, _ = env
    open_(st)
    st.shell("ls /sdcard/DCIM/Camera")
    lines = st.operator_snapshot()["shell"]
    assert lines[-2] == ["cmd", "ls"] or lines[-2] == ("cmd", "ls")  # הארגומנט (נתיב) לא מוצג
    assert "blocked_command" in (cfg.audit_dir / "2026-0418.jsonl").read_text()
    st.shell("status")
    assert "2026-0418" in st.operator_snapshot()["shell"][-1][1]


def test_operator_snapshot_leak_is_blocked_not_sent(env):
    """אם באג יכניס שם קובץ למטען המפעיל — המטען לא יוצא."""
    from noam.privacy import PrivacyViolation
    st, _, _ = env
    open_(st)
    st.choose_language("he")
    st.poll_devices()
    st.choose_source(0)
    st.current.error_code = "failed on IMG_ברית_יוסי.jpg"  # מדמה באג
    with pytest.raises(PrivacyViolation):
        st.operator_snapshot()
