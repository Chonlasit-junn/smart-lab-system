"""Read embedded Windows EXE identity without executing the target program."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from functools import lru_cache


@lru_cache(maxsize=1)
def _version_api():
    if os.name != "nt":
        return None
    api = ctypes.WinDLL("version.dll", use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = [
        ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.UINT),
    ]
    api.VerQueryValueW.restype = wintypes.BOOL
    return api


@lru_cache(maxsize=512)
def _read_version_info(path: str, modified_ns: int, size: int) -> dict[str, str]:
    # Modification time/size are cache keys: replaced files must be read again.
    api = _version_api()
    if api is None:
        return {}
    length = api.GetFileVersionInfoSizeW(path, None)
    if not length or length > 4 * 1024 * 1024:
        return {}
    buffer = ctypes.create_string_buffer(length)
    if not api.GetFileVersionInfoW(path, 0, length, buffer):
        return {}

    pointer = ctypes.c_void_p()
    count = wintypes.UINT()
    translations = []
    if api.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(count)):
        words = ctypes.cast(pointer, ctypes.POINTER(wintypes.WORD))
        translations = [(words[index], words[index + 1]) for index in range(0, count.value // 2 - 1, 2)]
    translations.extend([(0x0409, 0x04B0), (0x0409, 0x04E4)])

    identity = {}
    for field, key in (
        ("OriginalFilename", "original_filename"), ("InternalName", "internal_name"),
        ("ProductName", "product_name"), ("CompanyName", "company_name"),
    ):
        for language, codepage in translations:
            subkey = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\{field}"
            if api.VerQueryValueW(buffer, subkey, ctypes.byref(pointer), ctypes.byref(count)):
                if pointer.value and 0 < count.value <= 4096:
                    value = ctypes.wstring_at(pointer.value, count.value).rstrip("\0").strip()
                    if value:
                        identity[key] = value[:256]
                        break
    return identity


def read_executable_identity(path: str) -> dict[str, str]:
    """Return embedded identity, or no evidence if unreadable/absent.

    Version resources survive a simple file rename. They are not a digital
    signature and must not be described as proof against modified binaries.
    """
    if not path:
        return {}
    try:
        stat = os.stat(path)
        return dict(_read_version_info(os.path.abspath(path), stat.st_mtime_ns, stat.st_size))
    except (OSError, ValueError):
        return {}
