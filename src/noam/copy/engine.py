"""WP3 — מנוע העתקה ואימות.

לכל קובץ:
  1. הזרמה מהמקור (Source.stream) לקובץ זמני על היעד, עם SHA-256 תוך כדי — קריאה אחת מהטלפון.
  2. fsync, ואז קריאה חוזרת של הקובץ הזמני מהדיסק וחישוב SHA-256 שני.
  3. רק אם שתי הטביעות והגודל זהים — שינוי שם אטומי לשם הסופי, ורישום ביומן ההתקדמות.

קובץ שלא נקרא או לא אומת → דילוג עם קוד, ההעתקה ממשיכה.
ניתוק המכשיר או כשל ביעד → עצירה (החריגה עולה למעלה; הסשן עובר ל-ABORTED).
המשך אחרי עצירה: יומן ההתקדמות על היעד מונע העתקה חוזרת של קובץ שכבר אומת.
"""
from __future__ import annotations

import errno as errno_mod
import hashlib
import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from noam.device.base import Entry, Source
from noam.device.errors import DeviceDisconnected, DeviceError

from .errors import CopyCancelled, InsufficientSpace, TargetError
from .manifest import FileRecord, Manifest, SkipRecord
from .targets import Target, safe_relpath

JOURNAL = "progress.jsonl"
SPACE_MARGIN = 64 * 1024 * 1024  # מרווח ביטחון על היעד


@dataclass
class Progress:
    total: int
    copied: int = 0
    verified: int = 0
    skipped: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    resumed: int = 0
    skips: list[SkipRecord] = field(default_factory=list, repr=False)

    @property
    def percent(self) -> int:
        return 100 if not self.bytes_total else min(100, self.bytes_done * 100 // self.bytes_total)


class _HashingWriter:
    def __init__(self, fh, on_bytes: Callable[[int], None], should_stop: Callable[[], bool]) -> None:
        self.fh, self.h, self.n, self.on_bytes = fh, hashlib.sha256(), 0, on_bytes
        self.should_stop = should_stop

    def __call__(self, chunk: bytes) -> None:
        if self.should_stop():
            raise CopyCancelled()
        try:
            self.fh.write(chunk)
        except OSError as err:
            # כשל ביעד חייב להגיע כ-TargetError: שכבת המכשיר תופסת OSError ועלולה לרשום "המכשיר לא החזיר"
            code = "ERR_TARGET_SPACE" if err.errno == errno_mod.ENOSPC else "ERR_TARGET_WRITE"
            raise TargetError(code, err.errno) from err
        self.h.update(chunk)
        self.n += len(chunk)
        self.on_bytes(len(chunk))


def _load_journal(target: Target) -> dict[int, dict]:
    path = target.state_path(JOURNAL)
    done: dict[int, dict] = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            done[int(rec["idx"])] = rec
        except (ValueError, KeyError):
            continue  # שורה אחרונה חלקית אחרי הפסקת חשמל
    return done


def _append_journal(target: Target, rec: dict) -> None:
    path = target.state_path(JOURNAL)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def copy_and_verify(
    source: Source,
    entries: Iterable[Entry],
    target: Target,
    on_progress: Callable[[Progress], None],
    *,
    case_id: str,
    should_stop: Callable[[], bool] = lambda: False,
) -> Manifest:
    """מעתיק ומאמת כל קובץ. מחזיר מניפסט וכותב אותו (ואת רשימת השמות ללקוח) ליעד.
    זורק DeviceDisconnected / TargetError / CopyCancelled — הסשן נעצר. לכל חריגה מוצמד
    `partial_manifest` עם מה שכבר אומת, ומניפסט חלקי נכתב ליעד. קריאה חוזרת ממשיכה מאותה נקודה."""
    entries = list(entries)
    journal = _load_journal(target)
    manifest = Manifest(case=case_id, source_device=source.info().device_id)
    names = _unique_names(entries)

    pending = []
    for e in entries:
        rel = PurePosixPath(names[e.idx])
        rec = journal.get(e.idx)
        if (rec and rec.get("size") == e.size and rec.get("path") == rel.as_posix() and target.exists(rel)
                and _rehash(target, rel) == rec.get("sha256")):
            # המשך: לא סומכים על היומן לבד — הקובץ ביעד נקרא שוב ומושווה
            manifest.files.append(FileRecord(e.idx, e.group, e.category, e.size, rec["sha256"], "verified"))
        else:
            pending.append((e, rel))

    prog = Progress(
        total=len(entries),
        verified=len(manifest.files),
        resumed=len(manifest.files),
        bytes_total=sum(e.size for e in entries),
        bytes_done=manifest.bytes_verified,
    )

    needed = sum(e.size for e, _ in pending) + SPACE_MARGIN
    free = target.free_bytes()
    if pending and free < needed:
        raise InsufficientSpace(needed, free)
    target.write_test()
    on_progress(prog)

    try:
        for e, rel in pending:
            if should_stop():
                raise CopyCancelled()
            sha = _copy_one(source, target, e, rel, prog, on_progress, should_stop)
            if sha is None:
                continue
            _append_journal(target, {"idx": e.idx, "path": rel.as_posix(), "size": e.size, "sha256": sha})
            manifest.files.append(FileRecord(e.idx, e.group, e.category, e.size, sha, "verified"))
            prog.verified += 1
            on_progress(prog)
    except (DeviceDisconnected, TargetError, CopyCancelled) as stop:
        manifest.skipped = list(prog.skips)
        stop.partial_manifest = manifest  # type: ignore[attr-defined]
        if not isinstance(stop, TargetError):  # יעד שבור — לא מנסים לכתוב אליו עוד
            try:
                _write_outputs(target, manifest, names)
                _write_bag(target, manifest, names)
            except TargetError:
                pass
        raise

    # סקיפים מהריצה הזו בלבד; קבצים שדולגו בריצה קודמת נוסו שוב.
    manifest.skipped = list(prog.skips)
    _write_outputs(target, manifest, names)
    _write_bag(target, manifest, names)
    return manifest


def _unique_names(entries: list[Entry]) -> dict[int, str]:
    """נתיב יעד לכל קובץ, בלי התנגשויות. safe_relpath יכול למפות שני שמות לאותו נתיב
    (a:b ו-a_b, 'x.' ו-'x'), ו-exFAT לא מבחין באותיות גדולות/קטנות. התנגשות → סיומת ~idx.
    דטרמיניסטי (לפי idx), כך שהמשך אחרי עצירה מקבל את אותם שמות."""
    names: dict[int, str] = {}
    taken: set[str] = set()
    for e in sorted(entries, key=lambda x: x.idx):
        rel = safe_relpath(e.rel_path)
        cand = rel
        if cand.as_posix().casefold() in taken:
            cand = rel.with_name(f"{rel.stem}~{e.idx}{rel.suffix}")
        taken.add(cand.as_posix().casefold())
        names[e.idx] = cand.as_posix()
    return names


def _rehash(target: Target, rel: PurePosixPath) -> str | None:
    read = getattr(target, "read_final", None)
    if read is None:
        return None
    h = hashlib.sha256()
    try:
        for chunk in read(rel):
            h.update(chunk)
    except TargetError:
        return None
    return h.hexdigest()


def _skip(prog: Progress, e: Entry, code: str, on_progress) -> None:
    prog.skips.append(SkipRecord(e.idx, e.group, code))
    prog.skipped += 1
    prog.bytes_done += e.size  # כדי שהאחוז יגיע ל-100
    on_progress(prog)


def _copy_one(source, target, e: Entry, rel: PurePosixPath, prog: Progress, on_progress,
              should_stop: Callable[[], bool]) -> str | None:
    """מחזיר SHA-256 אם הקובץ הועתק ואומת; None אם דולג. זורק על ניתוק / כשל יעד."""
    done_before = prog.bytes_done

    def bump(n: int) -> None:
        prog.bytes_done += n

    for attempt in (1, 2):
        prog.bytes_done = done_before
        try:
            fh = target.open_part(rel)
            try:
                w = _HashingWriter(fh, bump, should_stop)
                source.stream(e, w)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fh.close()
        except (DeviceDisconnected, TargetError, CopyCancelled):
            target.discard(rel)
            prog.bytes_done = done_before
            raise
        except DeviceError:
            target.discard(rel)
            prog.bytes_done = done_before
            _skip(prog, e, "ERR_READ_FAILED", on_progress)
            return None
        except OSError as err:
            target.discard(rel)
            prog.bytes_done = done_before
            code = "ERR_TARGET_SPACE" if err.errno == errno_mod.ENOSPC else "ERR_TARGET_WRITE"
            raise TargetError(code, err.errno) from err

        src_sha = w.h.hexdigest()
        prog.copied += 1
        if w.n != e.size:
            target.discard(rel)
            prog.bytes_done = done_before
            _skip(prog, e, "ERR_SIZE_MISMATCH", on_progress)
            return None

        try:
            check = hashlib.sha256()
            for chunk in target.read_part(rel):
                check.update(chunk)
            if check.hexdigest() == src_sha:
                target.commit(rel)
                return src_sha
        except TargetError:
            target.discard(rel)  # לא משאירים .noam-part
            prog.bytes_done = done_before
            raise
        target.discard(rel)  # הדיסק החזיר משהו אחר ממה שנכתב — ניסיון אחד נוסף

    prog.bytes_done = done_before
    _skip(prog, e, "ERR_VERIFY_MISMATCH", on_progress)
    return None


def _write_outputs(target: Target, manifest: Manifest, names: dict[int, str]) -> None:
    case = manifest.case
    try:
        target.state_path(f"manifest-{case}.json").write_text(manifest.to_json(), encoding="utf-8")
        client = {"case": case, "manifest_sha256": manifest.sha256(), "files": {str(k): v for k, v in sorted(names.items())}}
        target.state_path(f"client-files-{case}.json").write_text(
            json.dumps(client, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        raise TargetError("ERR_TARGET_WRITE", e.errno) from e


def _write_bag(target: Target, manifest: Manifest, names: dict[int, str]) -> None:
    """BagIt על היעד, אם היעד הוא תיקייה מקומית (ענן — WP4)."""
    root = getattr(target, "root", None)
    if root is None:
        return
    from .bagit import write_bag
    try:
        write_bag(root, [(names[f.idx], f.sha256, f.size) for f in manifest.files],
                  case_id=manifest.case, manifest_sha256=manifest.sha256())
    except OSError as e:
        raise TargetError("ERR_TARGET_WRITE", e.errno) from e
