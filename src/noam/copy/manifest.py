"""WP3 — מניפסט. ראו docs/REPORT_FORMAT.md."""
from __future__ import annotations


class Manifest:
    def to_json(self) -> str:
        raise NotImplementedError("WP3")

    def sha256(self) -> str:
        raise NotImplementedError("WP3")
