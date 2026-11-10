"""WP10 — קבצי ההתקנה עקביים עם הקוד."""
from pathlib import Path

from noam.station import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_example_config_loads():
    cfg = load_config(ROOT / "config.example.toml")
    assert cfg.station_id and cfg.languages == ["he", "yi", "en", "ru", "fr"]
    assert "127.0.0.1" in cfg.operator_hosts


def test_firewall_defaults_to_drop_both_ways():
    text = (ROOT / "deploy/nftables.conf").read_text()
    assert text.count("policy drop") == 3
    assert "tcp dport 8000" in text


def test_service_is_sandboxed_and_networked_only_locally():
    unit = (ROOT / "deploy/systemd/noam-station.service").read_text()
    for d in ("ProtectSystem=strict", "NoNewPrivileges=true", "IPAddressDeny=any", "User=noam-svc"):
        assert d in unit


def test_client_storage_mounts_read_only():
    unit = (ROOT / "deploy/systemd/noam-automount@.service").read_text()
    assert "-o ro," in unit and "noexec" in unit
    rules = (ROOT / "deploy/udev/99-noam-storage.rules").read_text()
    assert 'ID_FS_LABEL}!="NOAM-SSD"' in rules
