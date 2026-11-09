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

from .errors import InsufficientSpace, TargetError
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
    def __init__(self, fh, on_bytes: Callable[[int], None]) -> None:
        self.fh, self.h, self.n, self.on_bytes = fh, hashlib.sha256(), 0, on_bytes

    def __call__(self, chunk: bytes) -> None:
        self.fh.write(chunk)
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
) -> Manifest:
    """מעתיק ומאמת כל קובץ. מחזיר מניפסט וכותב אותו (ואת רשימת השמות ללקוח) ליעד.
    זורק DeviceDisconnected / TargetError — הסשן נעצר; קריאה חוזרת ממשיכה מאותה נקודה."""
    entries = list(entries)
    journal = _load_journal(target)
    manifest = Manifest(case=case_id, source_device=source.info().device_id)
    names: dict[int, str] = {}

    pending = []
    for e in entries:
        rel = safe_relpath(e.rel_path)
        names[e.idx] = rel.as_posix()
        rec = journal.get(e.idx)
        if rec and rec.get("size") == e.size and rec.get("path") == rel.as_posix() and target.exists(rel):
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

    for e, rel in pending:
        sha = _copy_one(source, target, e, rel, prog, on_progress)
        if sha is None:
            continue
        _append_journal(target, {"idx": e.idx, "path": rel.as_posix(), "size": e.size, "sha256": sha})
        manifest.files.append(FileRecord(e.idx, e.group, e.category, e.size, sha, "verified"))
        prog.verified += 1
        on_progress(prog)

    # סקיפים מהריצה הזו בלבד; קבצים שדולגו בריצה קודמת נוסו שוב.
    manifest.skipped = list(prog.skips)
    _write_outputs(target, manifest, names)
    return manifest


def _skip(prog: Progress, e: Entry, code: str, on_progress) -> None:
    prog.skips.append(SkipRecord(e.idx, e.group, code))
    prog.skipped += 1
    prog.bytes_done += e.size  # כדי שהאחוז יגיע ל-100
    on_progress(prog)


def _copy_one(source, target, e: Entry, rel: PurePosixPath, prog: Progress, on_progress) -> str | None:
    """מחזיר SHA-256 אם הקובץ הועתק ואומת; None אם דולג. זורק על ניתוק / כשל יעד."""
    done_before = prog.bytes_done

    def bump(n: int) -> None:
        prog.bytes_done += n

    for attempt in (1, 2):
        prog.bytes_done = done_before
        try:
            fh = target.open_part(rel)
            try:
                w = _HashingWriter(fh, bump)
                source.stream(e, w)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fh.close()
        except DeviceDisconnected:
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

        check = hashlib.sha256()
        for chunk in target.read_part(rel):
            check.update(chunk)
        if check.hexdigest() == src_sha:
            target.commit(rel)
            return src_sha
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
