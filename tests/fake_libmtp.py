"""libmtp מדומה לבדיקות: מחקה את ה-API של libmtp ברמת ctypes, כולל ניתוק באמצע."""
from __future__ import annotations

import ctypes
import itertools

from noam.device import mtp as m


class FakeLibMTP:
    """tree: {storage_id: {"files": {name: bytes}, "dirs": {name: subtree}}}"""

    def __init__(self, tree: dict, serial: bytes = b"FAKE123", model: bytes = b"Pixel Test"):
        self._keep: list = []
        self._ids: dict[int, tuple] = {}
        self._next_id = 100
        self.tree = tree
        self.serial, self.model = serial, model
        self.disconnect_after_folders: int | None = None
        self.disconnect_after_bytes: int | None = None
        self.folder_calls = 0
        self.destroyed = 0
        self.released = False
        self._errors: list[int] = []
        self._dev = m._Device()
        self.dev = ctypes.pointer(self._dev)
        self._index(tree)

    def _index(self, tree):
        self._children: dict[tuple[int, int], list[int]] = {}
        for sid, root in tree.items():
            self._add(sid, m.FILES_AND_FOLDERS_ROOT, root)

    def _add(self, sid, parent, node):
        kids = self._children.setdefault((sid, parent), [])
        for name, data in node.get("files", {}).items():
            iid = self._new(("file", name, data))
            kids.append(iid)
        for name, sub in node.get("dirs", {}).items():
            iid = self._new(("dir", name, None))
            kids.append(iid)
            self._add(sid, iid, sub)

    def _new(self, rec):
        iid = self._next_id
        self._next_id += 1
        self._ids[iid] = rec
        return iid

    # ---- API -------------------------------------------------------------------------
    def LIBMTP_Get_Serialnumber(self, dev):
        return self._malloc_str(self.serial)

    def LIBMTP_Get_Modelname(self, dev):
        return self._malloc_str(self.model)

    def _malloc_str(self, b):
        p = ctypes.c_char_p(b)
        addr = ctypes.cast(p, ctypes.c_void_p).value
        buf = m._libc.malloc(len(b) + 1) if hasattr(m._libc, "malloc") else None
        if buf:
            ctypes.memmove(buf, addr, len(b) + 1)
            return buf
        return None

    def LIBMTP_Get_Storage(self, dev, sort):
        prev = None
        head = None
        for sid in self.tree:
            s = m._Storage(id=sid)
            self._keep.append(s)
            if prev is None:
                head = s
            else:
                prev.next = ctypes.pointer(s)
            prev = s
        dev.contents.storage = ctypes.pointer(head) if head else ctypes.POINTER(m._Storage)()
        return 0

    def LIBMTP_Get_Files_And_Folders(self, dev, sid, parent):
        self.folder_calls += 1
        if self.disconnect_after_folders is not None and self.folder_calls > self.disconnect_after_folders:
            self._errors.append(m.ERROR_USB_LAYER)
            return m.FileP()
        nodes = []
        for iid in self._children.get((sid, parent), []):
            kind, name, data = self._ids[iid]
            f = m._File(item_id=iid, parent_id=parent, storage_id=sid, filename=name.encode(),
                        filesize=len(data or b""), filetype=m.FILETYPE_FOLDER if kind == "dir" else 1)
            nodes.append(f)
        self._keep.extend(nodes)
        for a, b in itertools.pairwise(nodes):
            a.next = ctypes.pointer(b)
        return ctypes.pointer(nodes[0]) if nodes else m.FileP()

    def LIBMTP_destroy_file_t(self, f):
        self.destroyed += 1

    def LIBMTP_Get_File_To_Handler(self, dev, iid, cb, priv, prog, data):
        payload = self._ids[iid][2]
        sent = 0
        for i in range(0, len(payload), 4):
            if self.disconnect_after_bytes is not None and sent >= self.disconnect_after_bytes:
                self._errors.append(m.ERROR_NO_DEVICE_ATTACHED)
                return 1
            chunk = payload[i:i + 4]
            buf = (ctypes.c_ubyte * len(chunk)).from_buffer_copy(chunk)
            putlen = ctypes.c_uint32(0)
            rc = cb(None, None, len(chunk), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)), ctypes.pointer(putlen))
            if rc != m.HANDLER_RETURN_OK:
                return 1
            sent += putlen.value
        return 0

    def LIBMTP_Get_Errorstack(self, dev):
        if not self._errors:
            return ctypes.POINTER(m._Error)()
        e = m._Error(errornumber=self._errors[0], error_text=b"/sdcard/DCIM/secret.jpg")
        self._keep.append(e)
        return ctypes.pointer(e)

    def LIBMTP_Clear_Errorstack(self, dev):
        self._errors.clear()

    def LIBMTP_Release_Device(self, dev):
        self.released = True
