"""WP5 — הפקת הדוח החתום. מבנה ב-docs/REPORT_FORMAT.md.

החתימה מנותקת (detached): <report>.pdf.sig (DER) לצד הקובץ. כל שינוי בבית אחד של ה-PDF שובר אותה.
טביעת המפתח הציבורי מודפסת בדוח, וכל אחד יכול לאמת עם המפתח הציבורי של העמדה:
  openssl dgst -sha256 -verify station.pub.pem -signature report.pdf.sig report.pdf
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from bidi import get_display
from cryptography.hazmat.primitives.asymmetric import ec
from fpdf import FPDF

from noam.copy.manifest import Manifest

from .keys import SigningKey, verify_bytes

FONTS = Path(__file__).parent / "fonts"

SERVICE_HE = {"backup": "גיבוי", "transfer": "העברה", "restore": "שחזור"}
CATEGORY_HE = {"images": "תמונות", "video": "וידאו", "docs": "מסמכים", "other": "אחר"}
ERROR_HE = {
    "ERR_READ_FAILED": "המכשיר לא החזיר את הקובץ",
    "ERR_SIZE_MISMATCH": "גודל שונה מהמדווח",
    "ERR_VERIFY_MISMATCH": "הטביעה ביעד לא תאמה",
}


@dataclass
class ReportData:
    case_id: str
    client_name: str             # מודפס בדוח (החלטה: כן). לא נכנס ליומן ה-audit.
    service: str                 # backup | transfer | restore
    operator: str
    station_id: str
    station_name: str
    station_address: str
    started_at: datetime
    ended_at: datetime
    device_model: str
    device_id: str
    device_interface: str        # mtp | mass_storage
    target_desc: str             # "דיסק SSD 1TB · exFAT"
    manifest: Manifest
    audit_seal: str              # AuditLog.seal() — מאפשר לגלות קיצוץ של היומן
    consent_at: datetime | None
    consent_sig_sha256: str | None
    total_on_device: int | None = None
    revision: int = 1
    aborted_code: str | None = None
    extra_notes: list[str] = field(default_factory=list)

    @property
    def report_id(self) -> str:
        return f"NOAM-{self.case_id}-R{self.revision}"


def _he(s: str) -> str:
    return get_display(s)


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def _fmt_dt(d: datetime | None) -> str:
    return d.astimezone().strftime("%Y-%m-%d %H:%M:%S %z") if d else "—"


def _grouped(h: str) -> str:
    return " ".join(h[i:i + 4] for i in range(0, len(h), 4))


class _Doc(FPDF):
    def __init__(self, report_id: str, fp: str) -> None:
        super().__init__(format="A4")
        self.report_id, self.fp = report_id, fp
        self.add_font("he", "", str(FONTS / "DejaVuSans.ttf"))
        self.add_font("he", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
        self.add_font("mono", "", str(FONTS / "DejaVuSansMono.ttf"))
        self.set_auto_page_break(True, margin=18)
        self.set_margins(16, 16, 16)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("mono", "", 7)
        self.set_text_color(110, 120, 130)
        self.cell(0, 5, f"{self.report_id} · key {self.fp} · page {self.page_no()}/{{nb}}", align="C")

    # שורת תווית/ערך מימין לשמאל: התווית בצד ימין, הערך משמאלה.
    def row(self, label: str, value: str, mono: bool = False) -> None:
        w = self.epw
        if self.get_y() + 6.5 > self.page_break_trigger:
            self.add_page()  # לפני שמציירים — אחרת התווית והערך נופלים בשני עמודים
        self.set_font("he", "B", 9.5)
        self.set_text_color(86, 97, 110)
        y = self.get_y()
        self.set_xy(self.l_margin + w * 0.62, y)
        self.cell(w * 0.38, 6.5, _he(label), align="R")
        self.set_xy(self.l_margin, y)
        self.set_text_color(24, 33, 44)
        if mono:
            self.set_font("mono", "", 8.5)
            self.cell(w * 0.6, 6.5, value, align="R")
        else:
            self.set_font("he", "", 9.5)
            self.cell(w * 0.6, 6.5, _he(value), align="R")
        self.ln(6.5)

    def hash_row(self, label: str, digest: str) -> None:
        """טביעה מלאה (64 תווים) בשתי שורות — לא מקצרים, כדי שאפשר יהיה להשוות."""
        self.row(label, _grouped(digest[:32]), mono=True)
        self.row("", _grouped(digest[32:]), mono=True)

    def heading(self, text: str) -> None:
        if self.get_y() + 24 > self.page_break_trigger:
            self.add_page()  # כותרת לא נשארת לבד בתחתית עמוד
        self.ln(3)
        self.set_font("he", "B", 12)
        self.set_text_color(31, 58, 95)
        self.cell(0, 8, _he(text), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(31, 58, 95)
        self.line(self.l_margin, self.get_y(), self.l_margin + self.epw, self.get_y())
        self.ln(2)

    def para(self, text: str, size: float = 9) -> None:
        self.set_font("he", "", size)
        self.set_text_color(86, 97, 110)
        self.multi_cell(0, 5, _he(text), align="R", new_x="LMARGIN", new_y="NEXT")


def build_report(data: ReportData, out_dir: Path, signing_fp: str) -> Path:
    """מפיק את ה-PDF. לא חותם — sign() אחר כך, על הבתים הסופיים."""
    m = data.manifest
    doc = _Doc(data.report_id, signing_fp)
    doc.alias_nb_pages()
    doc.add_page()

    # כותרת
    doc.set_font("he", "B", 18)
    doc.set_text_color(31, 58, 95)
    doc.cell(0, 10, _he(data.station_name), align="R", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("he", "", 9)
    doc.set_text_color(86, 97, 110)
    doc.cell(0, 5, _he(data.station_address), align="R", new_x="LMARGIN", new_y="NEXT")
    doc.ln(2)
    doc.set_font("he", "B", 14)
    doc.set_text_color(24, 33, 44)
    title = "דוח סשן חתום" + (" — סשן שבוטל" if data.aborted_code else "")
    doc.cell(0, 9, _he(title), align="R", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("mono", "", 9)
    doc.cell(0, 5, data.report_id, align="R", new_x="LMARGIN", new_y="NEXT")

    doc.heading("פרטי סשן")
    doc.row("מספר תיק", data.case_id, mono=True)
    doc.row("לקוח", data.client_name)
    doc.row("שירות", SERVICE_HE.get(data.service, data.service))
    doc.row("התחלה", _fmt_dt(data.started_at), mono=True)
    doc.row("סיום", _fmt_dt(data.ended_at), mono=True)
    doc.row("מפעיל", data.operator)
    doc.row("עמדה", data.station_id, mono=True)
    if data.aborted_code:
        doc.row("סיבת ביטול", data.aborted_code, mono=True)

    doc.heading("מכשיר מקור")
    doc.row("דגם", data.device_model)
    doc.row("מזהה", data.device_id, mono=True)
    doc.row("ממשק", data.device_interface.upper(), mono=True)
    doc.para("המכשיר נקרא בלבד. שום קובץ לא נכתב, שונה או נמחק במכשיר.")

    doc.heading("יעד")
    doc.row("מדיה", data.target_desc)

    doc.heading("סיכום")
    if data.total_on_device is not None:
        doc.row("קבצים במקור", f"{data.total_on_device:,}", mono=True)
    selected = m.verified_count + len(m.skipped)
    doc.row("נבחרו להעתקה", f"{selected:,}", mono=True)
    doc.row("הועתקו ואומתו", f"{m.verified_count:,}", mono=True)
    doc.row("דולגו", f"{len(m.skipped):,}", mono=True)
    doc.row("נפח שנכתב ואומת", _fmt_bytes(m.bytes_verified), mono=True)
    doc.row("משך", str(data.ended_at - data.started_at).split(".")[0], mono=True)

    doc.heading("לפי קטגוריה")
    counts = Counter(f.category for f in m.files)
    sizes = Counter()
    for f in m.files:
        sizes[f.category] += f.size
    for cat in ("images", "video", "docs", "other"):
        if counts[cat]:
            doc.row(CATEGORY_HE[cat], f"{counts[cat]:,} · {_fmt_bytes(sizes[cat])}", mono=True)

    if m.skipped:
        doc.heading("דילוגים")
        doc.para("לכל קובץ שדולג מופיע מספר סידורי וסיבה. שמות הקבצים מופיעים רק ברשימה שעל מדיית הלקוח.")
        for code in sorted({s.error for s in m.skipped}):
            doc.para(f"{code}: {ERROR_HE.get(code, '')}")
        for s in m.skipped[:200]:
            doc.row(f"קובץ {s.idx} · קבוצה {s.group}", s.error, mono=True)
        if len(m.skipped) > 200:
            doc.para(f"ועוד {len(m.skipped) - 200} דילוגים — הרשימה המלאה במניפסט.")

    doc.heading("הסכמה")
    doc.row("נחתמה", _fmt_dt(data.consent_at), mono=True)
    if data.consent_sig_sha256:
        doc.hash_row("טביעת החתימה", data.consent_sig_sha256)
    else:
        doc.row("טביעת החתימה", "—", mono=True)

    doc.heading("אימות")
    doc.para("כל קובץ הועתק לקובץ זמני, נקרא בחזרה מהדיסק והושווה למקור בטביעת SHA-256. רק קובץ שתאם קיבל את שמו הסופי.")
    doc.hash_row("טביעת המניפסט", m.sha256())
    doc.hash_row("טביעת יומן הסשן", data.audit_seal)
    doc.row("מפתח החתימה", f"ECDSA P-256 · {signing_fp}", mono=True)
    doc.para("הדוח חתום דיגיטלית. החתימה נמצאת בקובץ sig הצמוד. כל שינוי בדוח מבטל אותה.")

    for note in data.extra_notes:
        doc.para(note)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{data.report_id}.pdf"
    if path.exists():
        raise FileExistsError("report revision already exists — increase revision")
    doc.output(str(path))
    return path


def sign(pdf_path: Path, key: SigningKey) -> Path:
    data = Path(pdf_path).read_bytes()
    sig_path = Path(str(pdf_path) + ".sig")
    sig_path.write_bytes(key.sign(data))
    return sig_path


def verify(pdf_path: Path, public_key: ec.EllipticCurvePublicKey, sig_path: Path | None = None) -> bool:
    sig_path = Path(sig_path or str(pdf_path) + ".sig")
    return verify_bytes(public_key, Path(pdf_path).read_bytes(), sig_path.read_bytes())


def now() -> datetime:
    return datetime.now(UTC)
