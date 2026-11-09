"""WP2 — MTPSource: עטיפת libmtp דרך ctypes."""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from .base import DeviceInfo, Entry, Source
from .errors import DeviceDisconnected, MTPError


class _File(ctypes.Structure):
    pass


_File._fields_ = [
    ("item_id", ctypes.c_uint32),
    ("parent_id", ctypes.c_uint32),
    ("storage_id", ctypes.c_uint32),
    ("filename", ctypes.c_char_p),
    ("filesize", ctypes.c_uint64),
    ("modificationdate", ctypes.c_long),
    ("filetype", ctypes.c_int),
    ("next", ctypes.POINTER(_File)),
]


class _Folder(ctypes.Structure):
    pass


_Folder._fields_ = [
    ("folder_id", ctypes.c_uint32),
    ("parent_id", ctypes.c_uint32),
    ("storage_id", ctypes.c_uint32),
    ("name", ctypes.c_char_p),
    ("sibling", ctypes.POINTER(_Folder)),
    ("child", ctypes.POINTER(_Folder)),
]


class _Storage(ctypes.Structure):
    pass


_Storage._fields_ = [
    ("id", ctypes.c_uint32),
    ("StorageType", ctypes.c_int),
    ("FilesystemType", ctypes.c_int),
    ("AccessCapability", ctypes.c_int),
    ("MaxCapacity", ctypes.c_uint64),
    ("FreeSpaceInBytes", ctypes.c_uint64),
    ("FreeSpaceInObjects", ctypes.c_uint64),
    ("StorageDescription", ctypes.c_char_p),
    ("VolumeIdentifier", ctypes.c_char_p),
    ("next", ctypes.POINTER(_Storage)),
    ("prev", ctypes.POINTER(_Storage)),
]


_lib: ctypes.CDLL | None = None


def _load() -> ctypes.CDLL:
    global _lib
    if _lib is not None:
        return _lib
    name = ctypes.util.find_library("mtp")
    if name is None:
        raise MTPError("libmtp not found — install libmtp9 / libmtp-dev")
    lib = ctypes.CDLL(name)
    lib.LIBMTP_Init()

    lib.LIBMTP_Get_First_Device.restype = ctypes.c_void_p
    lib.LIBMTP_Get_First_Device.argtypes = []

    lib.LIBMTP_Get_Next_Device.restype = ctypes.c_void_p
    lib.LIBMTP_Get_Next_Device.argtypes = []

    lib.LIBMTP_Release_Device.restype = None
    lib.LIBMTP_Release_Device.argtypes = [ctypes.c_void_p]

    lib.LIBMTP_Get_Storage.restype = ctypes.POINTER(_Storage)
    lib.LIBMTP_Get_Storage.argtypes = [ctypes.c_void_p, ctypes.c_int]

    lib.LIBMTP_Get_Files_And_Folders.restype = ctypes.c_int
    lib.LIBMTP_Get_Files_And_Folders.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.POINTER(_File)),
        ctypes.POINTER(ctypes.POINTER(_Folder)),
    ]

    lib.LIBMTP_Get_File_To_File.restype = ctypes.c_int
    lib.LIBMTP_Get_File_To_File.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]

    lib.LIBMTP_Get_Modelname.restype = ctypes.c_char_p
    lib.LIBMTP_Get_Modelname.argtypes = [ctypes.c_void_p]

    lib.LIBMTP_Get_Serialnumber.restype = ctypes.c_char_p
    lib.LIBMTP_Get_Serialnumber.argtypes = [ctypes.c_void_p]

    _lib = lib
    return lib


_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".bmp"}
_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".3gp", ".webm"}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf"}


def _category(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _IMAGE_EXT:
        return "images"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _DOC_EXT:
        return "docs"
    return "other"


class MTPSource(Source):
    def __init__(self, handle: int) -> None:
        self._lib = _load()
        self._handle = handle
        self._device_id = self._read_serial() or f"mtp-{handle:x}"
        raw_model = self._lib.LIBMTP_Get_Modelname(handle)
        self._model = (raw_model or b"Android").decode("utf-8", "replace")
        self._closed = False

    def info(self) -> DeviceInfo:
        return DeviceInfo(
            device_id=self._device_id,
            model=self._model,
            interface="mtp",
        )

    def walk(self) -> Iterator[Entry]:
        self._ensure_alive()
        storages = self._lib.LIBMTP_Get_Storage(self._handle, -1)
        if not storages:
            raise MTPError("get_storage")

        node = storages
        group_counter = [0]
        while node:
            yield from self._walk_dir(node.contents.id, 0, "", group_counter)
            node = node.contents.next

    def open(self, entry: Entry) -> BinaryIO:
        self._ensure_alive()
        tmp = tempfile.NamedTemporaryFile(
            prefix="noam-mtp-", suffix=Path(entry.rel_path).suffix, delete=False
        )
        tmp.close()
        try:
            rc = self._lib.LIBMTP_Get_File_To_File(
                self._handle, entry.idx, os.fsencode(tmp.name), None, None
            )
            if rc != 0:
                if self._is_disconnected():
                    raise DeviceDisconnected(self._device_id)
                raise MTPError("get_file", rc)
            return open(tmp.name, "rb")
        except Exception:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            raise

    def _walk_dir(
        self,
        storage_id: int,
        parent_id: int,
        prefix: str,
        group_counter: list[int],
    ) -> Iterator[Entry]:
        self._ensure_alive()
        files = ctypes.POINTER(_File)()
        folders = ctypes.POINTER(_Folder)()
        rc = self._lib.LIBMTP_Get_Files_And_Folders(
            self._handle,
            storage_id,
            parent_id,
            ctypes.byref(files),
            ctypes.byref(folders),
        )
        if rc != 0:
            if self._is_disconnected():
                raise DeviceDisconnected(self._device_id)
            raise MTPError("get_files_and_folders", rc)

        fnode = folders
        while fnode:
            name = (fnode.contents.name or b"").decode("utf-8", "replace")
            group_counter[0] += 1
            sub_prefix = f"{prefix}{name}/"
            yield from self._walk_dir(
                storage_id, fnode.contents.folder_id, sub_prefix, group_counter
            )
            fnode = fnode.contents.sibling

        node = files
        while node:
            name = (node.contents.filename or b"").decode("utf-8", "replace")
            yield Entry(
                idx=int(node.contents.item_id),
                group=f"g{max(1, group_counter[0]):02d}" if group_counter[0] else "g01",
                rel_path=f"{prefix}{name}",
                size=int(node.contents.filesize),
                category=_category(name),
            )
            node = node.contents.next

    def _read_serial(self) -> str | None:
        raw = self._lib.LIBMTP_Get_Serialnumber(self._handle)
        return raw.decode("utf-8", "replace") if raw else None

    def _is_disconnected(self) -> bool:
        storages = self._lib.LIBMTP_Get_Storage(self._handle, -1)
        return not storages

    def _ensure_alive(self) -> None:
        if self._closed:
            raise DeviceDisconnected(self._device_id)

    def close(self) -> None:
        if not self._closed:
            self._lib.LIBMTP_Release_Device(self._handle)
            self._closed = True
