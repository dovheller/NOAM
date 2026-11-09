"""WP2 — MTPSource: libmtp דרך ctypes.

ההצהרות כאן תואמות ל-libmtp.h (libmtp 1.1.x). כל שינוי — לבדוק מול הכותר.
  LIBMTP_Detect_Raw_Devices + LIBMTP_Open_Raw_Device_Uncached   — רשימת מכשירים
  LIBMTP_Get_Storage(dev, sort) -> int, ממלא את dev->storage      — אחסונים
  LIBMTP_Get_Files_And_Folders(dev, storage, parent) -> file_t*  — תיקייה אחת (תיקיות = filetype FOLDER)
  LIBMTP_Get_File_To_Handler(dev, id, put_func, priv, NULL, NULL) — הזרמה, בלי קובץ ביניים
"""
from __future__ import annotations

import ctypes
import ctypes.util
from collections.abc import Iterator

from .base import DeviceInfo, Entry, Sink, Source
from .categories import GroupNamer, category, top_folder
from .errors import DeviceDisconnected, DeviceError, MTPError

FILES_AND_FOLDERS_ROOT = 0xFFFFFFFF
FILETYPE_FOLDER = 0  # הערך הראשון ב-LIBMTP_filetype_t

# LIBMTP_error_number_t
ERROR_NONE = 0
ERROR_GENERAL = 1
ERROR_PTP_LAYER = 2
ERROR_USB_LAYER = 3
ERROR_MEMORY_ALLOCATION = 4
ERROR_NO_DEVICE_ATTACHED = 5
_DISCONNECT_ERRORS = {ERROR_USB_LAYER, ERROR_NO_DEVICE_ATTACHED}

HANDLER_RETURN_OK = 0
HANDLER_RETURN_ERROR = 1


class _File(ctypes.Structure):
    pass


_File._fields_ = [
    ("item_id", ctypes.c_uint32),
    ("parent_id", ctypes.c_uint32),
    ("storage_id", ctypes.c_uint32),
    ("filename", ctypes.c_char_p),
    ("filesize", ctypes.c_uint64),
    ("modificationdate", ctypes.c_long),  # time_t
    ("filetype", ctypes.c_int),
    ("next", ctypes.POINTER(_File)),
]


class _Storage(ctypes.Structure):
    pass


_Storage._fields_ = [
    ("id", ctypes.c_uint32),
    ("StorageType", ctypes.c_uint16),
    ("FilesystemType", ctypes.c_uint16),
    ("AccessCapability", ctypes.c_uint16),
    ("MaxCapacity", ctypes.c_uint64),
    ("FreeSpaceInBytes", ctypes.c_uint64),
    ("FreeSpaceInObjects", ctypes.c_uint64),
    ("StorageDescription", ctypes.c_char_p),
    ("VolumeIdentifier", ctypes.c_char_p),
    ("next", ctypes.POINTER(_Storage)),
    ("prev", ctypes.POINTER(_Storage)),
]


class _Device(ctypes.Structure):
    """רק תחילת LIBMTP_mtpdevice_struct, עד השדה storage. לעולם לא מקצים אותו בעצמנו."""

    _fields_ = [
        ("object_bitsize", ctypes.c_uint8),
        ("params", ctypes.c_void_p),
        ("usbinfo", ctypes.c_void_p),
        ("storage", ctypes.POINTER(_Storage)),
    ]


class _DeviceEntry(ctypes.Structure):
    _fields_ = [
        ("vendor", ctypes.c_char_p),
        ("vendor_id", ctypes.c_uint16),
        ("product", ctypes.c_char_p),
        ("product_id", ctypes.c_uint16),
        ("device_flags", ctypes.c_uint32),
    ]


class _RawDevice(ctypes.Structure):
    _fields_ = [
        ("device_entry", _DeviceEntry),
        ("bus_location", ctypes.c_uint32),
        ("devnum", ctypes.c_uint8),
    ]


class _Error(ctypes.Structure):
    pass


_Error._fields_ = [
    ("errornumber", ctypes.c_int),
    ("error_text", ctypes.c_char_p),
    ("next", ctypes.POINTER(_Error)),
]

PutFunc = ctypes.CFUNCTYPE(
    ctypes.c_uint16,
    ctypes.c_void_p,                  # params
    ctypes.c_void_p,                  # priv
    ctypes.c_uint32,                  # sendlen
    ctypes.POINTER(ctypes.c_ubyte),   # data
    ctypes.POINTER(ctypes.c_uint32),  # putlen
)

DevP = ctypes.POINTER(_Device)
FileP = ctypes.POINTER(_File)

_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    name = ctypes.util.find_library("mtp")
    if name is None:
        raise MTPError("load: libmtp not found — apt install libmtp9")
    try:
        lib = ctypes.CDLL(name)
        sig = {
            "LIBMTP_Init": (None, []),
            "LIBMTP_Detect_Raw_Devices": (ctypes.c_int, [ctypes.POINTER(ctypes.POINTER(_RawDevice)), ctypes.POINTER(ctypes.c_int)]),
            "LIBMTP_Open_Raw_Device_Uncached": (DevP, [ctypes.POINTER(_RawDevice)]),
            "LIBMTP_Release_Device": (None, [DevP]),
            "LIBMTP_Get_Storage": (ctypes.c_int, [DevP, ctypes.c_int]),
            "LIBMTP_Get_Files_And_Folders": (FileP, [DevP, ctypes.c_uint32, ctypes.c_uint32]),
            "LIBMTP_destroy_file_t": (None, [FileP]),
            "LIBMTP_Get_File_To_Handler": (ctypes.c_int, [DevP, ctypes.c_uint32, PutFunc, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
            "LIBMTP_Get_Errorstack": (ctypes.POINTER(_Error), [DevP]),
            "LIBMTP_Clear_Errorstack": (None, [DevP]),
            "LIBMTP_Get_Modelname": (ctypes.c_void_p, [DevP]),
            "LIBMTP_Get_Serialnumber": (ctypes.c_void_p, [DevP]),
        }
        for fn, (res, args) in sig.items():
            f = getattr(lib, fn)
            f.restype, f.argtypes = res, args
        lib.LIBMTP_Init()
    except (OSError, AttributeError) as e:
        raise MTPError("load") from e
    _lib = lib
    return lib


_libc = ctypes.CDLL(ctypes.util.find_library("c"))
_libc.free.argtypes = [ctypes.c_void_p]
_libc.free.restype = None


def _take_string(ptr: int | None) -> str | None:
    """libmtp מחזירה מחרוזת שהוקצתה ב-malloc; מעתיקים ומשחררים."""
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr).decode("utf-8", "replace")
    finally:
        _libc.free(ptr)


class MTPSource(Source):
    def __init__(self, device: DevP, lib=None) -> None:
        self._lib = lib or _load()
        self._dev = device
        self._closed = False
        serial = _take_string(self._lib.LIBMTP_Get_Serialnumber(device))
        model = _take_string(self._lib.LIBMTP_Get_Modelname(device))
        self._device_id = serial or f"mtp-{ctypes.addressof(device.contents):x}"
        self._model = model or "Android"

    def info(self) -> DeviceInfo:
        return DeviceInfo(device_id=self._device_id, model=self._model, interface="mtp")

    # ---- errors -------------------------------------------------------------------------
    def _raise_from_errorstack(self, op: str) -> None:
        """אם יש שגיאה ב-errorstack — זורק אותה; אחרת חוזר בשקט.
        error_text לא נכנס להודעה: הוא עלול לכלול שמות קבצים."""
        stack = self._lib.LIBMTP_Get_Errorstack(self._dev)
        if not stack:
            return
        codes = []
        node = stack
        while node:
            codes.append(int(node.contents.errornumber))
            node = node.contents.next
        self._lib.LIBMTP_Clear_Errorstack(self._dev)
        if any(c in _DISCONNECT_ERRORS for c in codes):
            raise DeviceDisconnected(self._device_id)
        raise MTPError(op, codes[0])

    def _ensure_alive(self) -> None:
        if self._closed:
            raise DeviceDisconnected(self._device_id)

    # ---- walk ---------------------------------------------------------------------------
    def _list_folder(self, storage_id: int, parent_id: int) -> list[tuple[int, str, int, bool]]:
        """תיקייה אחת: (item_id, name, size, is_folder). משחרר את הרשימה של libmtp."""
        self._ensure_alive()
        head = self._lib.LIBMTP_Get_Files_And_Folders(self._dev, storage_id, parent_id)
        if not head:
            # NULL הוא גם "תיקייה ריקה" וגם "שגיאה" — מבחינים לפי errorstack.
            self._raise_from_errorstack("get_files_and_folders")
            return []
        out = []
        node = head
        while node:
            f = node.contents
            out.append((
                int(f.item_id),
                (f.filename or b"").decode("utf-8", "replace"),
                int(f.filesize),
                f.filetype == FILETYPE_FOLDER,
            ))
            nxt = f.next
            self._lib.LIBMTP_destroy_file_t(node)
            node = nxt
        return out

    def _storage_ids(self) -> list[int]:
        self._ensure_alive()
        rc = self._lib.LIBMTP_Get_Storage(self._dev, 0)
        if rc != 0:
            self._raise_from_errorstack("get_storage")
            raise MTPError("get_storage", rc)
        ids = []
        node = self._dev.contents.storage
        while node:
            ids.append(int(node.contents.id))
            node = node.contents.next
        if not ids:
            # טלפון נעול או שלא אושר "העברת קבצים": אין אחסונים גלויים.
            raise MTPError("no_storage_visible")
        return ids

    def walk(self) -> Iterator[Entry]:
        groups = GroupNamer()
        idx = 0
        for sid in self._storage_ids():
            stack: list[tuple[int, str]] = [(FILES_AND_FOLDERS_ROOT, f"s{sid:x}")]
            while stack:
                parent, prefix = stack.pop()
                items = sorted(self._list_folder(sid, parent), key=lambda t: t[1])
                for item_id, name, size, is_folder in items:
                    if is_folder:
                        continue
                    yield Entry(
                        idx=idx,
                        group=groups(top_folder(prefix, depth=2)),
                        rel_path=f"{prefix}/{name}",
                        size=size,
                        category=category(name),
                        handle=item_id,
                    )
                    idx += 1
                for item_id, name, _size, is_folder in reversed(items):
                    if is_folder:
                        stack.append((item_id, f"{prefix}/{name}"))

    # ---- stream -------------------------------------------------------------------------
    def stream(self, entry: Entry, write: Sink) -> None:
        self._ensure_alive()
        failure: list[BaseException] = []

        def put(_params, _priv, sendlen, data, putlen):
            try:
                write(ctypes.string_at(data, sendlen))
                putlen[0] = sendlen
                return HANDLER_RETURN_OK
            except BaseException as e:  # noqa: BLE001 — חייבים לא לזרוק דרך C
                failure.append(e)
                putlen[0] = 0
                return HANDLER_RETURN_ERROR

        cb = PutFunc(put)  # שומרים הפניה עד סוף הקריאה
        rc = self._lib.LIBMTP_Get_File_To_Handler(self._dev, entry.handle, cb, None, None, None)
        if failure:
            # כשל בצד היעד (למשל דיסק מלא) — לא כשל של הטלפון.
            self._lib.LIBMTP_Clear_Errorstack(self._dev)
            raise failure[0]
        if rc != 0:
            self._raise_from_errorstack("get_file")
            raise MTPError("get_file", rc)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._lib.LIBMTP_Release_Device(self._dev)


def detect(lib=None) -> list[MTPSource]:
    """כל מכשירי ה-MTP המחוברים. מכשיר שלא נפתח (נעול, לא אושר) — מדולג."""
    lib = lib or _load()
    raw = ctypes.POINTER(_RawDevice)()
    n = ctypes.c_int(0)
    err = lib.LIBMTP_Detect_Raw_Devices(ctypes.byref(raw), ctypes.byref(n))
    if err == ERROR_NO_DEVICE_ATTACHED or n.value == 0:
        return []
    if err != ERROR_NONE:
        raise MTPError("detect", err)
    sources: list[MTPSource] = []
    try:
        for i in range(n.value):
            dev = lib.LIBMTP_Open_Raw_Device_Uncached(ctypes.byref(raw[i]))
            if not dev:
                continue
            try:
                sources.append(MTPSource(dev, lib=lib))
            except DeviceError:
                lib.LIBMTP_Release_Device(dev)
    finally:
        if raw and lib is _lib:
            _libc.free(ctypes.cast(raw, ctypes.c_void_p))
    return sources
