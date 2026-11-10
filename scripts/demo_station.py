"""הדגמה: מריץ את העמדה עם "טלפון" מדומה (תיקייה), בלי חומרה, בלי מפתח אמיתי.

    python scripts/demo_station.py           # http://127.0.0.1:8000/operator  ·  /client
לא לשימוש בחנות: מפתח החתימה והיומן כאן זמניים.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import uvicorn

from noam.app import create_app
from noam.device import MassStorageSource
from noam.report import SigningKey, generate_key
from noam.station import Station, StationConfig

PW = "demo passphrase only"
FILES = {
    "DCIM/Camera/IMG_20240412_101500.jpg": 2_400_000, "DCIM/Camera/VID_20240412_102010.mp4": 9_000_000,
    "DCIM/Screenshots/Screenshot_20240501.png": 300_000, "Documents/חוזה שכירות.pdf": 180_000,
    "WhatsApp/Media/WhatsApp Images/IMG-20240412-WA0007.jpg": 220_000,
    "WhatsApp/Media/WhatsApp Voice Notes/PTT-20240412-WA0002.opus": 40_000,
    "Music/שירי שבת.mp3": 4_000_000,
}


def main() -> None:
    base = Path(os.environ.get("NOAM_DEMO_DIR") or tempfile.mkdtemp(prefix="noam-demo-"))
    phone = base / "phone"
    for rel, size in FILES.items():
        p = phone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(os.urandom(min(size, 64_000)) * (size // 64_000 or 1))
    cfg = StationConfig(station_id="ST-DEMO", display_name="נועם הלר", address="מרכז אורנים · כנפי נשרים 68, ירושלים",
                        phone="052-898-8890", target_root=base / "ssd", audit_dir=base / "audit",
                        reports_dir=base / "reports", signing_key=base / "keys/station.pem", operator_pin="1234")
    if not cfg.signing_key.exists():
        generate_key(cfg.signing_key, PW, station_name=cfg.display_name)
    os.environ.setdefault("NOAM_DEV", "1")
    src = MassStorageSource(phone, label="Galaxy A54 (הדגמה)")
    st = Station(cfg, scan_fn=lambda **_: [src], signing_key=SigningKey.load(cfg.signing_key, PW))
    print(f"demo dir: {base}", file=sys.stderr)
    uvicorn.run(create_app(st), host="127.0.0.1", port=int(os.environ.get("NOAM_PORT", "8000")))


if __name__ == "__main__":
    main()
