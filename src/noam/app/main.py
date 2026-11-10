"""WP7–WP8 — שרת FastAPI מקומי: קונסולת המפעיל + טאבלט הלקוח (ADR 0001).

- כל התצוגה נבנית בשרת (Jinja2) ונדחפת לדפדפנים ב-WebSocket כ-HTML (htmx, hx-swap-oob).
  אין לוגיקה בדפדפן מלבד ציור החתימה. אין גישה לחומרה מהדפדפן.
- הקונסולה מקבלת רק Station.operator_snapshot() — שעובר את שכבת הפרטיות (WP6).
  נכשלה בדיקת הפרטיות? מוצג מסך שגיאה, והמטען לא נשלח.
- הקונסולה נגישה רק מכתובות operator_hosts (ברירת מחדל: העמדה עצמה).
- כל הנכסים מקומיים (static/). אין CDN, אין גופן מהרשת (ADR 0003).
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import os
import re
import shutil
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import (
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from noam.privacy import PrivacyViolation
from noam.station import Station, StationError

from .i18n import LANG_NAMES, load_translations

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
REPORT_NAME = re.compile(r"^NOAM-[A-Za-z0-9_\-]+-R\d+\.pdf$")
SETTINGS_TIMEOUT = 10 * 60

SERVICE_HE = {"transfer": "העברה", "backup": "גיבוי", "restore": "שחזור"}
CATEGORY_HE = {"images": "תמונות", "video": "וידאו", "docs": "מסמכים", "other": "אחר"}
ERROR_HE = {
    "ERR_NO_SESSION": "אין סשן פעיל",
    "ERR_WRONG_STATE": "הפעולה לא אפשרית בשלב הזה",
    "ERR_BUSY": "העמדה עסוקה — נסה בעוד רגע",
    "ERR_SESSION_ACTIVE": "יש כבר סשן פעיל",
    "ERR_BAD_CASE_ID": "מספר תיק לא תקין (אותיות לועזיות, ספרות, מקף)",
    "ERR_CASE_EXISTS": "מספר התיק כבר קיים",
    "ERR_BAD_LANGUAGE": "שפה לא זמינה",
    "ERR_BAD_SOURCE": "המקור לא זמין",
    "ERR_NOTHING_SELECTED": "לא נבחר דבר",
    "ERR_SIGNATURE_EMPTY": "חסרה חתימה",
    "ERR_SIGNING_LOCKED": "מפתח החתימה נעול — פתח אותו בהגדרות",
    "ERR_SIGNING_UNLOCK": "הסיסמה שגויה או שקובץ המפתח חסר",
    "ERR_BAD_PIN": "קוד שגוי",
    "ERR_DEVICE_DISCONNECTED": "המכשיר התנתק",
    "ERR_TARGET_SPACE": "אין מספיק מקום ביעד",
    "ERR_TARGET_WRITE": "כתיבה ליעד נכשלה — בדוק את הדיסק",
    "ERR_TARGET_WRITE_TEST": "כתיבת הניסיון ליעד נכשלה — בדוק שהדיסק מחובר",
    "ERR_TARGET_UNAVAILABLE": "היעד לא מחובר",
    "ERR_INDEX_FAILED": "מיפוי המכשיר נכשל",
    "ERR_COPY_FAILED": "ההעתקה נכשלה — ראה יומן",
    "ERR_OPERATOR_CANCELLED": "בוטל על ידי המפעיל",
    "ERR_PRIVACY_BLOCKED": "נחסם: המסך עמד להציג תוכן של לקוח",
}


def _size(n: Any) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def _num(n: Any) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))
    env.filters.update(
        size=_size, num=_num,
        service=lambda v: SERVICE_HE.get(v, v), catname=lambda v: CATEGORY_HE.get(v, v),
        langname=lambda v: LANG_NAMES.get(v, v), errtext=lambda v: ERROR_HE.get(v, ""),
    )
    return env


class Hub:
    """WebSocket: כל שינוי בעמדה → רינדור מחדש ודחיפה לכל דפדפן מחובר (מאוחד, עד ~6 בשנייה)."""

    def __init__(self, app: NoamApp) -> None:
        self.app = app
        self.operator: set[WebSocket] = set()
        self.client: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.event = asyncio.Event()

    def poke(self) -> None:  # נקרא מכל thread
        if self.loop:
            self.loop.call_soon_threadsafe(self.event.set)

    async def run(self) -> None:
        while True:
            await self.event.wait()
            self.event.clear()
            await self.push()
            await asyncio.sleep(0.15)

    async def push(self) -> None:
        if self.operator:
            html = self.app.operator_fragment()
            await self._send(self.operator, html)
        if self.client:
            html = self.app.client_fragment()
            await self._send(self.client, html)

    @staticmethod
    async def _send(sockets: set[WebSocket], html: str) -> None:
        for ws in list(sockets):
            try:
                await ws.send_text(html)
            except Exception:  # noqa: BLE001
                sockets.discard(ws)


class NoamApp:
    def __init__(self, station: Station) -> None:
        self.station = station
        self.env = _env()
        self.t = load_translations()
        self.hub = Hub(self)
        self.settings_until = 0.0
        station.subscribe(self.hub.poke)

    # ---------------------------------------------------------------- render
    def _op_ctx(self) -> dict:
        try:
            snap = self.station.operator_snapshot()
        except PrivacyViolation:
            log.error("operator snapshot blocked by privacy layer")
            snap = {"tab": "active", "session": self._minimal_session(), "history": [], "shell": [], "audit_tail": [],
                    "station": {"name": self.station.cfg.display_name, "id": self.station.cfg.station_id,
                                "operator": "", "target": "", "languages": [], "address": "", "phone": ""},
                    "signing": {"unlocked": False, "fingerprint": None}, "target_free": None}
            return {"s": snap, "blocked": True, "checks": [], "settings_open": False, "next_case": ""}
        return {"s": snap, "blocked": False, "checks": self.diag_checks(snap),
                "settings_open": time.monotonic() < self.settings_until,
                "next_case": self._next_case(snap)}

    def _minimal_session(self) -> dict | None:
        """כשהמטען המלא נחסם: רק מזהה, מצב ושם — כדי שהמפעיל יוכל לבטל, להפיק דוח ולסגור."""
        run = self.station.current
        if run is None:
            return None
        s = run.session
        return {"case_id": s.case_id, "client_name": s.client_name, "state": s.state.value,
                "service": s.service.value, "language": s.language, "abort_code": s.abort_code,
                "error_code": "ERR_PRIVACY_BLOCKED", "busy": run.busy, "progress": None, "devices": [],
                "index": None, "selected": None, "unparsed": 0, "report": None, "manifest_sha256": None,
                "language_chosen": run.language_chosen}

    def operator_page(self) -> str:
        return self.env.get_template("operator.html").render(**self._op_ctx())

    def operator_fragment(self) -> str:
        ctx = self._op_ctx()
        inner = self.env.get_template("operator/screen.html").render(**ctx)
        toast = '<div id="toast" class="toast" role="alert" hx-swap-oob="true">' + \
                (ERROR_HE["ERR_PRIVACY_BLOCKED"] if ctx["blocked"] else "") + "</div>"
        return f'<div id="screen" hx-swap-oob="true">{inner}</div>{toast}'

    def _client_ctx(self) -> dict:
        c = self.station.client_snapshot()
        return {"c": c, "t": self.t.get(c["lang"], self.t["he"])}

    def client_page(self) -> str:
        return self.env.get_template("client.html").render(**self._client_ctx())

    def client_fragment(self) -> str:
        ctx = self._client_ctx()
        inner = self.env.get_template("client/screen.html").render(**ctx)
        return f'<div id="screen" hx-swap-oob="true">{inner}</div>'

    def _next_case(self, snap: dict) -> str:
        today = datetime.now().astimezone().strftime("%Y%m%d")
        used = {h["case_id"] for h in snap.get("history", [])}
        n = 1
        while f"{today}-{n:02d}" in used or (self.station.cfg.audit_dir / f"{today}-{n:02d}.jsonl").exists():
            n += 1
        return f"{today}-{n:02d}"

    def diag_checks(self, snap: dict) -> list[dict]:
        cfg = self.station.cfg
        checks = []
        free = snap.get("target_free")
        marker = (cfg.target_root / ".noam-target").exists()
        if free is None:
            checks.append({"title": "דיסק היעד", "level": "err", "state": "הדיסק לא מחובר או לא נגיש.",
                           "action": "חבר את דיסק היעד. אם הוא מחובר — בדוק שהוא מופיע ב-/media."})
        else:
            lvl = "ok" if free > 50 * 1024**3 else "warn"
            checks.append({"title": "מקום פנוי ביעד", "level": lvl, "state": f"{_size(free)} פנויים.",
                           "action": "אין צורך בפעולה." if lvl == "ok" else "פחות מ-50 GB — החלף דיסק לפני סשן גדול."})
            if not marker:
                checks.append({"title": "סימון דיסק היעד", "level": "warn", "state": "חסר הקובץ .noam-target בשורש היעד.",
                               "action": "בלי הסימון הדיסק עלול להופיע כמקור. הרץ: sudo noam-mark-target <נתיב>"})
        sk = snap["signing"]
        checks.append({"title": "מפתח חתימה", "level": "ok" if sk["unlocked"] else "warn",
                       "state": f"פתוח · {sk['fingerprint']}" if sk["unlocked"] else "נעול.",
                       "action": "אין צורך בפעולה." if sk["unlocked"] else "הגדרות → הזן את סיסמת המנהל. בלי זה הדוח לא ייחתם."})
        try:
            probe = cfg.audit_dir / ".write-probe"
            probe.write_text("x")
            probe.unlink()
            checks.append({"title": "יומן הסשנים", "level": "ok", "state": "נכתב לדיסק העמדה.", "action": "אין צורך בפעולה."})
        except OSError:
            checks.append({"title": "יומן הסשנים", "level": "err", "state": "אי אפשר לכתוב את היומן.",
                           "action": "אל תפתח סשן. פנה לדב."})
        import ctypes.util
        checks.append({"title": "גישה לטלפונים (MTP)", "level": "ok" if ctypes.util.find_library("mtp") else "err",
                       "state": "libmtp מותקן." if ctypes.util.find_library("mtp") else "libmtp לא מותקן.",
                       "action": "אין צורך בפעולה." if ctypes.util.find_library("mtp") else "sudo apt install libmtp9"})
        checks.append({"title": "adb (מסכים שבורים)", "level": "ok" if shutil.which("adb") else "warn",
                       "state": "מותקן." if shutil.which("adb") else "לא מותקן — רק MTP וכרטיסים.",
                       "action": "אין צורך בפעולה." if shutil.which("adb") else "sudo apt install adb"})
        now = datetime.now().astimezone()
        checks.append({"title": "שעון", "level": "ok", "state": now.strftime("%Y-%m-%d %H:%M:%S %z"),
                       "action": "בדוק מול שעון אמין בתחילת היום (SECURITY.md §3)."})
        errs = [e for e in snap.get("audit_tail", []) if e.get("error_code")]
        checks.append({"title": "שגיאות בסשן הנוכחי", "level": "warn" if errs else "ok",
                       "state": f"{len(errs)} שגיאות ביומן." if errs else "אין.",
                       "action": "פרטים בסשן הפעיל." if errs else "אין צורך בפעולה."})
        return checks


def _toast(msg: str) -> HTMLResponse:
    return HTMLResponse(f'<div id="toast" class="toast" role="alert" hx-swap-oob="true">{msg}</div>')


def _clear_toast() -> HTMLResponse:
    return HTMLResponse('<div id="toast" class="toast" role="alert" hx-swap-oob="true"></div>')


def create_app(station: Station, *, poll_interval: float = 2.0) -> FastAPI:
    na = NoamApp(station)
    cfg = station.cfg

    async def poller() -> None:
        while True:
            await asyncio.sleep(poll_interval)
            with suppress(Exception):
                await run_in_threadpool(station.poll_devices)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        na.hub.loop = asyncio.get_running_loop()
        tasks = [asyncio.create_task(na.hub.run())]
        if poll_interval > 0:
            tasks.append(asyncio.create_task(poller()))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.noam = na
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def _in(host: str | None, allowed: list[str]) -> bool:
        if host is None:
            return False
        if host in allowed:
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        for a in allowed:
            try:
                if ip in ipaddress.ip_network(a, strict=False):
                    return True
            except ValueError:
                continue
        return False

    def is_operator(host: str | None) -> bool:
        return _in(host, cfg.operator_hosts)

    def is_tablet(host: str | None) -> bool:
        return not cfg.tablet_hosts or _in(host, cfg.tablet_hosts) or is_operator(host)

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        # CSRF: דף מאתר אחר (אם איכשהו נפתח בדפדפן העמדה) לא יכול לשלוח פעולות
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return Response(status_code=403)
        return await call_next(request)

    def need_op(req: Request) -> None:
        if not is_operator(req.client.host if req.client else None):
            raise HTTPException(403)

    def need_cl(req: Request) -> None:
        if not is_tablet(req.client.host if req.client else None):
            raise HTTPException(403)

    OP = [Depends(need_op)]  # רץ לפני אימות הטופס: 403 ולא 422
    CL = [Depends(need_cl)]

    async def act(fn, *args, client: bool = False, **kw) -> Response:
        try:
            await run_in_threadpool(fn, *args, **kw)
        except StationError as e:
            if client:
                t = na.t.get(station.client_snapshot()["lang"], na.t["he"])
                return _toast(t["err_generic"])
            return _toast(f"{ERROR_HE.get(e.code, e.code)} · <span class='mono'>{e.code}</span>")
        return _clear_toast()

    # ------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    async def root(req: Request):
        host = req.client.host if req.client else None
        return HTMLResponse(na.operator_page() if is_operator(host) else na.client_page())

    @app.get("/operator", response_class=HTMLResponse)
    async def operator_page(req: Request):
        need_op(req)
        return HTMLResponse(na.operator_page())

    @app.get("/client", response_class=HTMLResponse)
    async def client_page(req: Request):
        need_cl(req)
        return HTMLResponse(na.client_page())

    @app.websocket("/ws/operator")
    async def ws_operator(ws: WebSocket):
        if not is_operator(ws.client.host if ws.client else None):
            await ws.close(code=4403)
            return
        await ws.accept()
        na.hub.operator.add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            na.hub.operator.discard(ws)

    @app.websocket("/ws/client")
    async def ws_client(ws: WebSocket):
        if not is_tablet(ws.client.host if ws.client else None):
            await ws.close(code=4403)
            return
        await ws.accept()
        na.hub.client.add(ws)
        try:
            await ws.send_text(na.client_fragment())
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            na.hub.client.discard(ws)

    # ------------------------------------------------------------ operator actions
    @app.post("/op/tab/{tab}", dependencies=OP)
    async def op_tab(tab: str, req: Request):
        need_op(req)
        return await act(station.set_tab, tab)

    @app.post("/op/session", dependencies=OP)
    async def op_session(req: Request, case_id: str = Form(...), client_name: str = Form(...),
                         phone: str = Form(""), language: str = Form("he"), service: str = Form("transfer")):
        need_op(req)
        if service not in SERVICE_HE:
            return _toast("שירות לא מוכר")
        return await act(station.open_session, case_id=case_id, client_name=client_name, phone=phone,
                         language=language, service=service)

    @app.post("/op/abort", dependencies=OP)
    async def op_abort(req: Request):
        need_op(req)
        return await act(station.abort)

    @app.post("/op/scan", dependencies=OP)
    async def op_scan(req: Request):
        need_op(req)
        return await act(station.poll_devices)

    @app.post("/op/report", dependencies=OP)
    async def op_report(req: Request):
        need_op(req)
        return await act(station.make_report)

    @app.post("/op/close", dependencies=OP)
    async def op_close(req: Request):
        need_op(req)
        return await act(station.close)

    @app.post("/op/shell", dependencies=OP)
    async def op_shell(req: Request, cmd: str = Form("")):
        need_op(req)
        return await act(station.shell, cmd)

    @app.post("/op/unlock", dependencies=OP)
    async def op_unlock(req: Request, passphrase: str = Form("")):
        need_op(req)
        return await act(station.unlock_signing, passphrase)

    @app.post("/op/settings/unlock", dependencies=OP)
    async def op_settings_unlock(req: Request, pin: str = Form("")):
        need_op(req)
        if not cfg.operator_pin or pin != cfg.operator_pin:
            return _toast(ERROR_HE["ERR_BAD_PIN"])
        na.settings_until = time.monotonic() + SETTINGS_TIMEOUT
        na.hub.poke()
        return _clear_toast()

    @app.post("/op/settings/lock", dependencies=OP)
    async def op_settings_lock(req: Request):
        need_op(req)
        na.settings_until = 0
        na.hub.poke()
        return _clear_toast()

    @app.get("/op/report/{name}", dependencies=OP)
    async def op_report_file(name: str, req: Request):
        need_op(req)
        if not REPORT_NAME.match(name):
            raise HTTPException(404)
        p = cfg.reports_dir / name
        if not p.exists():
            raise HTTPException(404)
        return FileResponse(p, media_type="application/pdf")

    # ------------------------------------------------------------ client actions
    @app.post("/cl/lang/{code}", dependencies=CL)
    async def cl_lang(code: str, req: Request):
        need_cl(req)
        return await act(station.choose_language, code, client=True)

    @app.post("/cl/source/{idx}", dependencies=CL)
    async def cl_source(idx: int, req: Request):
        need_cl(req)
        return await act(station.choose_source, idx, client=True)

    @app.post("/cl/toggle/{gid}", dependencies=CL)
    async def cl_toggle(gid: str, req: Request):
        need_cl(req)
        cur = set(station.client_snapshot()["selected_groups"])
        cur ^= {gid}
        return await act(station.set_selection, sorted(cur), client=True)

    @app.post("/cl/select", dependencies=CL)
    async def cl_select(req: Request, mode: str = Form("all")):
        need_cl(req)
        snap = station.client_snapshot()
        groups = [g["id"] for g in (snap["browse"] or {}).get("groups", [])] if mode == "all" else []
        return await act(station.set_selection, groups, client=True)

    @app.post("/cl/confirm", dependencies=CL)
    async def cl_confirm(req: Request):
        need_cl(req)
        return await act(station.confirm_selection, client=True)

    @app.post("/cl/back", dependencies=CL)
    async def cl_back(req: Request):
        need_cl(req)
        return await act(station.back_to_selection, client=True)

    @app.post("/cl/consent", dependencies=CL)
    async def cl_consent(req: Request, signature: str = Form("")):
        need_cl(req)
        prefix = "data:image/png;base64,"
        if not signature.startswith(prefix) or len(signature) > 2_000_000:
            return await act(station.sign_consent, b"", client=True)
        try:
            png = base64.b64decode(signature[len(prefix):], validate=True)
        except ValueError:
            png = b""
        return await act(station.sign_consent, png, client=True)

    return app


def main() -> None:  # pragma: no cover — מופעל ע"י systemd
    import uvicorn

    from noam.report import SigningKey
    from noam.station import load_config

    logging.basicConfig(level=logging.INFO)
    cfg = load_config(Path(os.environ.get("NOAM_CONFIG", "/etc/noam/config.toml")))
    key = None
    pw = os.environ.pop("NOAM_SIGNING_PASSPHRASE", None)
    if pw:
        try:
            key = SigningKey.load(cfg.signing_key, pw)
        except Exception:  # noqa: BLE001
            log.warning("signing key not unlocked at start; unlock from the console")
    station = Station(cfg, signing_key=key)
    uvicorn.run(create_app(station), host=os.environ.get("NOAM_HOST", "0.0.0.0"),
                port=int(os.environ.get("NOAM_PORT", "8000")), log_level="info")
