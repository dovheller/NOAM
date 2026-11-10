"""WP6 — הבדיקה החשובה במערכת: שום מידע מזהה לא מגיע למפעיל.
כל נקודת יציאה חדשה לצד המפעיל מוסיפה כאן בדיקה (ראו גם test_app.py)."""
from __future__ import annotations

import json

import pytest

from noam.device.base import Entry
from noam.privacy import (
    PrivacyViolation,
    assert_operator_safe,
    client_view,
    group_label,
    is_blocked,
    operator_view,
    secrets_from_entries,
)

# שמות מזהים בכוונה (סינתטיים): שם אדם, כתובת, מסמך רפואי, תיקיית WhatsApp
ENTRIES = [
    Entry(0, "g01", "s10001/DCIM/Camera/IMG_ברית_יוסי_כהן.jpg", 2_000_000, "images"),
    Entry(1, "g01", "s10001/DCIM/Camera/VID_חתונה.mp4", 9_000_000, "video"),
    Entry(2, "g02", "s10001/Documents/בדיקות_דם_מרים.pdf", 120_000, "docs"),
    Entry(3, "g03", "s10001/WhatsApp/Media/WhatsApp Images/IMG-20240412-WA0007.jpg", 300_000, "images"),
    Entry(4, "g04", "s10001/רחוב_הנביאים_12.txt", 900, "other"),
]


def all_strings(obj):
    return json.dumps(obj, ensure_ascii=False)


def test_operator_view_has_no_names_paths_or_folders():
    view = operator_view(ENTRIES)
    text = all_strings(view)
    for e in ENTRIES:
        for part in e.rel_path.split("/"):
            if len(part) >= 3 and not part.startswith("s1000"):
                assert part not in text, part
    assert view["total"] == 5
    assert view["by_category"]["images"] == {"count": 2, "bytes": 2_300_000}
    assert [g["id"] for g in view["groups"]] == ["g01", "g02", "g03", "g04"]


def test_operator_view_passes_runtime_leak_check():
    assert_operator_safe(operator_view(ENTRIES), secrets_from_entries(ENTRIES))


def test_client_view_has_real_labels():
    view = client_view(ENTRIES)
    labels = {g["id"]: g["label"] for g in view["groups"]}
    assert labels["g01"] == "DCIM" and labels["g02"] == "Documents" and labels["g04"] == ""
    assert view["total"] == 5


def test_client_view_would_fail_operator_check():
    with pytest.raises(PrivacyViolation):
        assert_operator_safe(client_view(ENTRIES), secrets_from_entries(ENTRIES))


@pytest.mark.parametrize("leak", [
    {"note": "IMG_ברית_יוסי_כהן.jpg"},
    {"x": ["ok", {"deep": "camera"}]},
    {"error": "failed at /sdcard/DCIM/a"},
    {"Documents": 1},                                   # גם מפתחות נבדקים
    {"msg": "file msgstore.db.crypt15"},
])
def test_runtime_check_catches_leaks(leak):
    with pytest.raises(PrivacyViolation) as ei:
        assert_operator_safe(leak, secrets_from_entries(ENTRIES))
    # ההודעה עצמה לא מדליפה
    assert "יוסי" not in str(ei.value) and "Camera" not in str(ei.value)


def test_runtime_check_allows_codes_and_numbers():
    assert_operator_safe({"state": "copying", "error": "ERR_READ_FAILED", "g": "g02", "n": 5},
                         secrets_from_entries(ENTRIES))


def test_group_label_strips_mtp_storage_prefix():
    assert group_label("s10001/DCIM/Camera/a.jpg") == "DCIM"
    assert group_label("DCIM/a.jpg") == "DCIM"
    assert group_label("loose.txt") == ""


@pytest.mark.parametrize("cmd,blocked", [
    ("ls /sdcard/DCIM/Camera", True), ("cat notes.txt", True), ("/bin/ls", True),
    ("find / -name x", True), ("noam index dev0 --names", True), ("noam index dev0 --counts-only", False),
    ("noam session open", False), ("help", False), ("", False),
])
def test_is_blocked(cmd, blocked):
    assert is_blocked(cmd) is blocked
