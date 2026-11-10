"""הגדרות העמדה — config.toml (לא בריפו; ראו config.example.toml)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StationConfig:
    station_id: str = "ST-01"
    display_name: str = "נועם הלר"
    address: str = ""
    phone: str = ""
    target_root: Path = Path("/media/noam/NOAM-SSD")
    target_label: str = "NOAM-SSD"
    audit_dir: Path = Path("/var/lib/noam/audit")
    reports_dir: Path = Path("/var/lib/noam/reports")
    signing_key: Path = Path("/var/lib/noam/keys/station.pem")
    languages: list[str] = field(default_factory=lambda: ["he", "yi", "en", "ru", "fr"])
    operator_name: str = "נועם"
    operator_pin: str = ""                       # הגדרות: נעול בקוד; ריק = נעול לגמרי
    operator_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "::1"])
    tablet_hosts: list[str] = field(default_factory=list)  # ריק = כל כתובת ברשת הסגורה


def load_config(path: Path) -> StationConfig:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    st, paths, sig = data.get("station", {}), data.get("paths", {}), data.get("signing", {})
    tg, lang, op, net = data.get("targets", {}), data.get("languages", {}), data.get("operator", {}), data.get("network", {})
    cfg = StationConfig()
    cfg.station_id = st.get("id", cfg.station_id)
    cfg.display_name = st.get("display_name", cfg.display_name)
    cfg.address = st.get("address", cfg.address)
    cfg.phone = st.get("phone", cfg.phone)
    cfg.audit_dir = Path(paths.get("audit_dir", cfg.audit_dir))
    cfg.reports_dir = Path(paths.get("reports_dir", cfg.reports_dir))
    cfg.target_root = Path(tg.get("root", cfg.target_root))
    cfg.target_label = tg.get("default", cfg.target_label)
    cfg.signing_key = Path(sig.get("private_key_path", cfg.signing_key))
    cfg.languages = lang.get("enabled", cfg.languages)
    cfg.operator_name = op.get("name", cfg.operator_name)
    cfg.operator_pin = str(op.get("pin", cfg.operator_pin))
    cfg.operator_hosts = net.get("operator_hosts", cfg.operator_hosts)
    cfg.tablet_hosts = net.get("tablet_hosts", cfg.tablet_hosts)
    return cfg
