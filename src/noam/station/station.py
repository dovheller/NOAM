"""מנהל העמדה (WP7–WP9).

מחבר את כל השכבות לזרימה אחת:
  סשן (WP1) → סריקה (WP2) → בדיקת יעד + מיפוי (WP3) → בחירה + הסכמה (טאבלט) → העתקה ואימות (WP3)
  → דוח חתום (WP5) → סגירה.

כללים:
- כל מה שיוצא למפעיל נבנה ב-operator_snapshot() ועובר privacy.assert_operator_safe. אין דרך אחרת.
- כל מה שיוצא לטאבלט נבנה ב-client_snapshot().
- עבודה ארוכה (מיפוי, העתקה) רצה ב-thread. כל חריגה בו נתפסת, הסשן עובר ל"בוטל" עם קוד,
  והממשק מקבל הודעה — אין כשל שקט (CLAUDE.md).
- thread-safe: כל שינוי מצב תחת self._lock; מאזינים (WebSocket) מקבלים הודעה אחרי כל שינוי.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from noam import privacy
from noam.copy import LocalTarget, Progress, TargetError, copy_and_verify
from noam.copy.manifest import Manifest
from noam.device import DeviceDisconnected, Source, UnavailableSource
from noam.device import scan as device_scan
from noam.device.base import Entry
from noam.report import ReportData, SigningKey, build_report, sign
from noam.session.audit import AuditLog
from noam.session.model import Service, Session, State

from .config import StationConfig

log = logging.getLogger(__name__)

ScanFn = Callable[..., list[Source]]


class StationError(RuntimeError):
    """פעולה לא חוקית במצב הנוכחי. code — קוד קצר לממשק."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class CaseRun:
    session: Session
    audit: AuditLog
    target: LocalTarget
    started_at: datetime
    language_chosen: bool = False
    sources: list[Source] = field(default_factory=list)
    source_idx: int | None = None
    entries: list[Entry] = field(default_factory=list)
    selected_groups: set[str] = field(default_factory=set)
    consent_at: datetime | None = None
    consent_sha256: str | None = None
    progress: Progress | None = None
    manifest: Manifest | None = None
    report_path: Path | None = None
    busy: str | None = None           # "index" | "copy" | None
    error_code: str | None = None
    unparsed: int = 0
    ended_at: datetime | None = None

    @property
    def source(self) -> Source | None:
        if self.source_idx is None or self.source_idx >= len(self.sources):
            return None
        return self.sources[self.source_idx]

    def selected_entries(self) -> list[Entry]:
        return [e for e in self.entries if e.group in self.selected_groups]


class Station:
    def __init__(self, cfg: StationConfig, *, scan_fn: ScanFn | None = None,
                 audit_key: bytes | None = None, signing_key: SigningKey | None = None,
                 run_async: bool = True) -> None:
        self.cfg = cfg
        self._scan = scan_fn or device_scan
        self._audit_key = audit_key
        self.signing_key = signing_key
        self._run_async = run_async
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []
        self.current: CaseRun | None = None
        self.operator_tab = "queue"
        self.shell_lines: list[tuple[str, str]] = []   # (kind, text) — פקודות ותשובות, בלי תוכן
        cfg.audit_dir.mkdir(parents=True, exist_ok=True)
        cfg.reports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ infra
    def subscribe(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def unsubscribe(self, fn: Callable[[], None]) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                log.exception("listener failed")

    def _spawn(self, name: str, fn: Callable[[], None]) -> None:
        if self._run_async:
            threading.Thread(target=fn, name=f"noam-{name}", daemon=True).start()
        else:
            fn()

    def _require(self, *states: State) -> CaseRun:
        run = self.current
        if run is None:
            raise StationError("ERR_NO_SESSION")
        if states and run.session.state not in states:
            raise StationError("ERR_WRONG_STATE")
        if run.busy:
            raise StationError("ERR_BUSY")
        return run

    def _advance(self, run: CaseRun, to: State) -> None:
        frm = run.session.state
        run.session.advance(to)
        run.audit.record("state", session_id=run.session.session_id, from_state=frm.value, to_state=to.value)

    # ------------------------------------------------------------------ operator actions
    def open_session(self, *, case_id: str, client_name: str, phone: str, language: str, service: str) -> None:
        with self._lock:
            if self.current and self.current.session.state not in (State.CLOSED,):
                raise StationError("ERR_SESSION_ACTIVE")
            case_id = case_id.strip()
            if not case_id or any(c in case_id for c in "/\\. ") or len(case_id) > 40:
                raise StationError("ERR_BAD_CASE_ID")
            if (self.cfg.audit_dir / f"{case_id}.jsonl").exists():
                raise StationError("ERR_CASE_EXISTS")
            if language not in self.cfg.languages:
                raise StationError("ERR_BAD_LANGUAGE")
            session = Session(case_id=case_id, client_name=client_name.strip(), phone=phone.strip(),
                              language=language, service=Service(service), operator=self.cfg.operator_name)
            audit = AuditLog(self.cfg.audit_dir / f"{case_id}.jsonl", key=self._audit_key)
            audit.record("session_open", session_id=session.session_id, operator=self.cfg.operator_name,
                         action=session.service.value)
            self.current = CaseRun(session=session, audit=audit,
                                   target=LocalTarget(self.cfg.target_root / case_id),
                                   started_at=datetime.now(UTC))
            self.operator_tab = "active"
        self._notify()

    def abort(self, code: str = "ERR_OPERATOR_CANCELLED") -> None:
        with self._lock:
            run = self.current
            if run is None:
                raise StationError("ERR_NO_SESSION")
            if run.session.state in (State.ABORTED, State.REPORTED, State.CLOSED):
                raise StationError("ERR_WRONG_STATE")
            self._abort_locked(run, code)
        self._notify()

    def _abort_locked(self, run: CaseRun, code: str) -> None:
        if run.session.state in (State.ABORTED, State.REPORTED, State.CLOSED):
            return
        run.session.abort(code)
        run.error_code = code
        run.ended_at = datetime.now(UTC)
        run.audit.record("abort", session_id=run.session.session_id, error_code=code)

    def make_report(self) -> Path:
        with self._lock:
            run = self._require(State.VERIFIED, State.ABORTED)
            if self.signing_key is None:
                raise StationError("ERR_SIGNING_LOCKED")
            m = run.manifest or Manifest(case=run.session.case_id,
                                         source_device=run.source.info().device_id if run.source else "—")
            src = run.source.info() if run.source else None
            unavailable = [(s.info().model, s.reason) for s in run.sources if isinstance(s, UnavailableSource)]
            seal = run.audit.seal()
            data = ReportData(
                case_id=run.session.case_id, client_name=run.session.client_name,
                service=run.session.service.value, operator=self.cfg.operator_name,
                station_id=self.cfg.station_id, station_name=self.cfg.display_name,
                station_address=self.cfg.address, started_at=run.started_at,
                ended_at=run.ended_at or datetime.now(UTC),
                device_model=src.model if src else "—", device_id=src.device_id if src else "—",
                device_interface=src.interface if src else "—",
                target_desc=f"{self.cfg.target_label}", manifest=m, audit_seal=seal,
                consent_at=run.consent_at, consent_sig_sha256=run.consent_sha256,
                total_on_device=len(run.entries) or None, aborted_code=run.session.abort_code,
                unavailable=unavailable, revision=self._next_revision(run.session.case_id),
            )
            pdf = build_report(data, self.cfg.reports_dir, self.signing_key.fingerprint)
            sign(pdf, self.signing_key)
            run.report_path = pdf
            run.audit.record("report_signed", session_id=run.session.session_id,
                             hash=hashlib.sha256(pdf.read_bytes()).hexdigest())
            # עותק ללקוח, ליד הקבצים שלו
            try:
                for f in (pdf, Path(str(pdf) + ".sig")):
                    shutil.copy2(f, run.target.state_path(f.name))
            except OSError:
                log.warning("could not copy report to target")
            self._advance(run, State.REPORTED)
        self._notify()
        return pdf

    def _next_revision(self, case_id: str) -> int:
        n = 1
        while (self.cfg.reports_dir / f"NOAM-{case_id}-R{n}.pdf").exists():
            n += 1
        return n

    def close(self) -> None:
        with self._lock:
            run = self._require(State.REPORTED, State.ABORTED)
            self._advance(run, State.CLOSED)
            for s in run.sources:
                try:
                    s.close()
                except Exception:
                    log.exception("source close failed")
            m = run.manifest
            entry = {
                "date": datetime.now(UTC).astimezone().strftime("%Y-%m-%d"),
                "case_id": run.session.case_id, "client_name": run.session.client_name,
                "service": run.session.service.value,
                "verified": m.verified_count if m else 0, "skipped": len(m.skipped) if m else 0,
                "status": "aborted" if run.session.abort_code else "ok",
                "abort_code": run.session.abort_code,
                "report": run.report_path.name if run.report_path else None,
            }
            with (self.cfg.reports_dir / "history.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            run.audit.record("session_close", session_id=run.session.session_id, hash=run.audit.seal())
            self.current = None
            self.operator_tab = "queue"
        self._notify()

    def unlock_signing(self, passphrase: str) -> None:
        try:
            key = SigningKey.load(self.cfg.signing_key, passphrase)
        except (PermissionError, FileNotFoundError, RuntimeError) as e:
            raise StationError("ERR_SIGNING_UNLOCK") from e
        with self._lock:
            self.signing_key = key
        self._notify()

    def set_tab(self, tab: str) -> None:
        if tab not in ("queue", "new", "active", "finish", "history", "diag", "settings", "shell"):
            raise StationError("ERR_BAD_TAB")
        with self._lock:
            self.operator_tab = tab
        self._notify()

    # ------------------------------------------------------------------ devices
    def poll_devices(self) -> bool:
        """נקרא מחזורית ע"י השרת. בשלב 'פתוח' — מזהה מכשיר ומעביר ל'מכשיר זוהה'. מחזיר True אם השתנה."""
        with self._lock:
            run = self.current
            if run is None or run.busy or run.session.state is not State.OPEN or not run.language_chosen:
                return False
        found = self._scan(exclude=[self.cfg.target_root])
        with self._lock:
            run = self.current
            if run is None or run.session.state is not State.OPEN:
                return False
            old = [(s.info().device_id, isinstance(s, UnavailableSource)) for s in run.sources]
            new = [(s.info().device_id, isinstance(s, UnavailableSource)) for s in found]
            run.sources = found
            changed = old != new
            if any(not isinstance(s, UnavailableSource) for s in found):
                run.audit.record("device_detected", session_id=run.session.session_id, count=len(found))
                self._advance(run, State.DEVICE_DETECTED)
                changed = True
        if changed:
            self._notify()
        return changed

    def target_free(self) -> int | None:
        try:
            return shutil.disk_usage(self.cfg.target_root).free
        except OSError:
            return None

    # ------------------------------------------------------------------ client actions
    def choose_language(self, lang: str) -> None:
        with self._lock:
            run = self._require(State.OPEN)
            if lang not in self.cfg.languages:
                raise StationError("ERR_BAD_LANGUAGE")
            run.session.language = lang
            run.language_chosen = True
            run.audit.record("language", session_id=run.session.session_id, status=lang)
        self._notify()

    def choose_source(self, idx: int) -> None:
        """הלקוח בחר מקור: בדיקת יעד (מקום + כתיבת-ניסיון) ואז מיפוי ב-thread."""
        with self._lock:
            run = self._require(State.DEVICE_DETECTED)
            if not (0 <= idx < len(run.sources)) or isinstance(run.sources[idx], UnavailableSource):
                raise StationError("ERR_BAD_SOURCE")
            run.source_idx = idx
            try:
                run.target.write_test()
            except TargetError as e:
                run.error_code = e.code
                run.audit.record("target_check", session_id=run.session.session_id, error_code=e.code)
                raise StationError(e.code) from e
            run.audit.record("target_check", session_id=run.session.session_id, status="ok",
                             size_bytes=run.target.free_bytes())
            self._advance(run, State.TARGET_CHECKED)
            run.busy = "index"
        self._notify()
        self._spawn("index", lambda: self._index(run))

    def _index(self, run: CaseRun) -> None:
        try:
            src = run.source
            assert src is not None
            entries = list(src.walk())
            with self._lock:
                run.entries = entries
                run.unparsed = getattr(src, "unparsed", 0)
                run.selected_groups = {e.group for e in entries}  # ברירת מחדל: הכל
                run.audit.record("indexed", session_id=run.session.session_id, count=len(entries),
                                 size_bytes=sum(e.size for e in entries))
                run.busy = None
                self._advance(run, State.INDEXED)
        except DeviceDisconnected:
            with self._lock:
                run.busy = None
                self._abort_locked(run, "ERR_DEVICE_DISCONNECTED")
        except Exception as e:
            log.exception("index failed")
            with self._lock:
                run.busy = None
                self._abort_locked(run, getattr(e, "reason", None) or "ERR_INDEX_FAILED")
        self._notify()

    def set_selection(self, groups: list[str]) -> None:
        with self._lock:
            run = self._require(State.INDEXED, State.CLIENT_SELECTED)
            known = {e.group for e in run.entries}
            run.selected_groups = set(groups) & known
        self._notify()

    def confirm_selection(self) -> None:
        with self._lock:
            run = self._require(State.INDEXED)
            sel = run.selected_entries()
            if not sel:
                raise StationError("ERR_NOTHING_SELECTED")
            run.audit.record("client_selected", session_id=run.session.session_id, count=len(sel),
                             size_bytes=sum(e.size for e in sel))
            self._advance(run, State.CLIENT_SELECTED)
        self._notify()

    def back_to_selection(self) -> None:
        with self._lock:
            run = self._require(State.CLIENT_SELECTED)
            self._advance(run, State.INDEXED)
        self._notify()

    def sign_consent(self, signature_png: bytes) -> None:
        """חתימת הלקוח: התמונה נשמרת על מדיית הלקוח, הטביעה ביומן ובדוח. ההעתקה מתחילה מיד."""
        if not signature_png.startswith(b"\x89PNG") or len(signature_png) < 200:
            raise StationError("ERR_SIGNATURE_EMPTY")
        with self._lock:
            run = self._require(State.CLIENT_SELECTED)
            sha = hashlib.sha256(signature_png).hexdigest()
            try:
                run.target.state_path(f"consent-{run.session.case_id}.png").write_bytes(signature_png)
            except OSError as e:
                raise StationError("ERR_TARGET_WRITE") from e
            run.consent_at = datetime.now(UTC)
            run.consent_sha256 = sha
            run.audit.record("consent_signed", session_id=run.session.session_id, client_hash=sha)
            self._advance(run, State.CONSENT_SIGNED)
            self._advance(run, State.COPYING)
            sel = run.selected_entries()
            run.progress = Progress(total=len(sel), bytes_total=sum(e.size for e in sel))
            run.busy = "copy"
        self._notify()
        self._spawn("copy", lambda: self._copy(run))

    def _copy(self, run: CaseRun) -> None:
        def on_progress(p: Progress) -> None:
            with self._lock:
                run.progress = p
            self._notify()

        try:
            src = run.source
            assert src is not None
            manifest = copy_and_verify(src, run.selected_entries(), run.target, on_progress,
                                       case_id=run.session.case_id)
            with self._lock:
                run.manifest = manifest
                run.busy = None
                run.ended_at = datetime.now(UTC)
                run.audit.record("copy_verified", session_id=run.session.session_id,
                                 count=manifest.verified_count, size_bytes=manifest.bytes_verified,
                                 hash=manifest.sha256())
                if manifest.skipped:
                    run.audit.record("copy_skipped", session_id=run.session.session_id,
                                     count=len(manifest.skipped))
                self._advance(run, State.VERIFIED)
        except DeviceDisconnected:
            with self._lock:
                run.busy = None
                self._abort_locked(run, "ERR_DEVICE_DISCONNECTED")
        except TargetError as e:
            with self._lock:
                run.busy = None
                self._abort_locked(run, e.code)
        except Exception:
            log.exception("copy failed")
            with self._lock:
                run.busy = None
                self._abort_locked(run, "ERR_COPY_FAILED")
        self._notify()

    # ------------------------------------------------------------------ noam shell
    SHELL_HELP: tuple[str, ...] = (
        "status            מצב הסשן",
        "scan              סריקת מכשירים עכשיו",
        "report            הפקת דוח חתום",
        "close             סגירת הסשן",
        "abort             ביטול הסשן",
        "whoami            מי מחובר",
        "clear             ניקוי המסך",
        "פקודות תוכן (ls, cat, open, find…) חסומות ונרשמות ביומן.",
    )

    def shell(self, command: str) -> None:
        cmd = command.strip()[:200]
        out: list[tuple[str, str]] = []
        if privacy.is_blocked(cmd):
            out.append(("err", "✕ נחסם: פקודות תוכן אינן זמינות. הניסיון נרשם ביומן."))
            with self._lock:
                if self.current:
                    self.current.audit.record("blocked_command", session_id=self.current.session.session_id,
                                              status="blocked")
            cmd_shown = cmd.split()[0] if cmd else ""  # לא מציגים את הארגומנטים (עלולים להיות נתיב)
        else:
            cmd_shown = cmd
            try:
                out.extend(self._shell_exec(cmd))
            except StationError as e:
                out.append(("err", e.code))
        with self._lock:
            if cmd == "clear":
                self.shell_lines = []
            else:
                self.shell_lines = (self.shell_lines + [("cmd", cmd_shown)] + out)[-200:]
        self._notify()

    def _shell_exec(self, cmd: str) -> list[tuple[str, str]]:
        if cmd in ("", "clear"):
            return []
        if cmd == "help":
            return [("dim", h) for h in self.SHELL_HELP]
        if cmd == "whoami":
            return [("out", f"{self.cfg.operator_name} · {self.cfg.station_id} · גישה לתוכן: אין")]
        if cmd == "status":
            run = self.current
            if not run:
                return [("out", "אין סשן פעיל")]
            p = run.progress
            return [("out", f"תיק {run.session.case_id} · מצב {run.session.state.value}"
                            + (f" · {p.verified}/{p.total} אומתו" if p else ""))]
        if cmd == "scan":
            changed = self.poll_devices()
            return [("ok" if changed else "dim", "נמצא מכשיר" if changed else "אין שינוי")]
        if cmd == "report":
            pdf = self.make_report()
            return [("ok", f"✓ {pdf.name} נחתם")]
        if cmd == "close":
            self.close()
            return [("ok", "✓ הסשן נסגר")]
        if cmd == "abort":
            self.abort()
            return [("warn", "הסשן בוטל")]
        return [("err", "פקודה לא מוכרת · help")]

    # ------------------------------------------------------------------ views
    def history(self, limit: int = 200) -> list[dict]:
        p = self.cfg.reports_dir / "history.jsonl"
        if not p.exists():
            return []
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        return rows[-limit:][::-1]

    def operator_snapshot(self) -> dict[str, Any]:
        """כל מה שהקונסולה מקבלת. נבנה מ-allow-list ונבדק מול נתיבי הסשן לפני יציאה."""
        with self._lock:
            run = self.current
            snap: dict[str, Any] = {
                "tab": self.operator_tab,
                "station": {"id": self.cfg.station_id, "name": self.cfg.display_name,
                            "address": self.cfg.address, "phone": self.cfg.phone,
                            "operator": self.cfg.operator_name, "target": self.cfg.target_label,
                            "languages": list(self.cfg.languages)},
                "target_free": self.target_free(),
                "signing": {"unlocked": self.signing_key is not None,
                            "fingerprint": self.signing_key.fingerprint if self.signing_key else None},
                "session": None,
                "history": self.history(50),
                "shell": list(self.shell_lines[-80:]),
                "audit_tail": [],
            }
            secrets: set[str] = set()
            # שמות קובצי הדוח של העמדה עצמה (NOAM-<תיק>-R<n>.pdf) — לא תוכן של לקוח
            allowed: set[str] = {h["report"] for h in snap["history"] if h.get("report")}
            allowed |= {h["client_name"] for h in snap["history"] if h.get("client_name")}
            if run:
                s = run.session
                p = run.progress
                snap["session"] = {
                    **s.to_operator_view(),
                    "client_name": s.client_name,
                    "language_chosen": run.language_chosen,
                    "busy": run.busy,
                    "error_code": run.error_code,
                    "devices": [
                        {"model": d.info().model, "interface": d.info().interface,
                         "device_id": d.info().device_id,
                         "unavailable": isinstance(d, UnavailableSource),
                         "reason": getattr(d, "reason", None), "selected": i == run.source_idx}
                        for i, d in enumerate(run.sources)
                    ],
                    "index": privacy.operator_view(run.entries) if run.entries else None,
                    "selected": privacy.operator_view(run.selected_entries()) if run.entries else None,
                    "unparsed": run.unparsed,
                    "progress": None if p is None else {
                        "total": p.total, "copied": p.copied, "verified": p.verified, "skipped": p.skipped,
                        "bytes_total": p.bytes_total, "bytes_done": p.bytes_done, "percent": p.percent,
                        "resumed": p.resumed,
                        "skips": [{"idx": k.idx, "group": k.group, "error": k.error} for k in p.skips[-20:]],
                    },
                    "manifest_sha256": run.manifest.sha256() if run.manifest else None,
                    "report": run.report_path.name if run.report_path else None,
                    "consent": run.consent_at.isoformat(timespec="seconds") if run.consent_at else None,
                }
                snap["audit_tail"] = _audit_tail(run.audit.path)
                secrets = privacy.secrets_from_entries(run.entries)
                allowed |= {s.client_name}
                allowed |= {d.info().model for d in run.sources}
                if run.report_path:
                    allowed.add(run.report_path.name)
        return privacy.assert_operator_safe(snap, secrets, allowed_values=allowed)

    def client_snapshot(self) -> dict[str, Any]:
        with self._lock:
            run = self.current
            base: dict[str, Any] = {"station": {"name": self.cfg.display_name, "address": self.cfg.address,
                                                "phone": self.cfg.phone},
                                    "languages": list(self.cfg.languages)}
            if run is None:
                return {**base, "screen": "idle", "lang": "he"}
            s = run.session
            st = s.state
            if st is State.OPEN:
                screen = "connect" if run.language_chosen else "lang"
            elif st in (State.DEVICE_DETECTED, State.TARGET_CHECKED):
                screen = "src"
            elif st is State.INDEXED:
                screen = "browse"
            elif st is State.CLIENT_SELECTED:
                screen = "consent"
            elif st in (State.CONSENT_SIGNED, State.COPYING):
                screen = "progress"
            elif st in (State.VERIFIED, State.REPORTED):
                screen = "done"
            elif st is State.ABORTED:
                screen = "stopped"
            else:
                screen = "idle"
            p = run.progress
            sel = run.selected_entries()
            return {
                **base, "screen": screen, "lang": s.language, "busy": run.busy,
                "service": s.service.value, "case_id": s.case_id,
                "devices": [{"model": d.info().model, "interface": d.info().interface,
                             "unavailable": isinstance(d, UnavailableSource),
                             "reason": getattr(d, "reason", None)} for d in run.sources],
                "target": {"label": self.cfg.target_label, "free": self.target_free()},
                "browse": privacy.client_view(run.entries) if run.entries else None,
                "selected_groups": sorted(run.selected_groups),
                "selection": {"count": len(sel), "bytes": sum(e.size for e in sel)},
                "progress": None if p is None else {"percent": p.percent, "verified": p.verified,
                                                     "total": p.total, "skipped": p.skipped},
                "result": None if run.manifest is None else {
                    "verified": run.manifest.verified_count, "skipped": len(run.manifest.skipped),
                    "bytes": run.manifest.bytes_verified},
                "report": run.report_path.name if run.report_path else None,
                "abort_code": s.abort_code,
            }


def _audit_tail(path: Path, n: int = 12) -> list[dict]:
    """שורות אחרונות מהיומן — מטא-דאטה בלבד (היומן עצמו מסרב לתוכן)."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        out.append({k: e[k] for k in ("ts", "event", "to_state", "count", "size_bytes", "error_code", "status")
                    if k in e})
    return out
