"""Load the Windows system ICU before importing PyQt6's Qt runtime."""

import ctypes
import os
import sys


_QT_DLL_DIRECTORY_HANDLE = None
_QT_DLL_HANDLES = []


def prepare_qt_dll_search_path() -> None:
    """Prefer this app's Qt DLLs and Windows ICU over unrelated PATH entries."""

    global _QT_DLL_DIRECTORY_HANDLE

    if sys.platform != "win32":
        return

    if getattr(sys, "frozen", False):
        qt_bin = os.path.join(sys._MEIPASS, "PyQt6", "Qt6", "bin")
    else:
        import PyQt6

        qt_bin = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "bin")

    if not os.path.isdir(qt_bin):
        return

    _QT_DLL_DIRECTORY_HANDLE = os.add_dll_directory(qt_bin)
    os.environ["PATH"] = qt_bin + os.pathsep + os.environ.get("PATH", "")

    # Qt6Core imports the unversioned ICU C API from icuuc.dll. Pin the OS
    # copy first so another application's incompatible ICU on PATH cannot win.
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    system_icu = os.path.join(system_root, "System32", "icuuc.dll")
    if os.path.isfile(system_icu):
        _QT_DLL_HANDLES.append(ctypes.WinDLL(system_icu))

    # Explicitly preload this app's Qt stack by absolute path so unrelated Qt
    # DLLs on PATH cannot be selected by the Windows loader.
    for dll_name in (
        "concrt140.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Widgets.dll",
    ):
        dll_path = os.path.join(qt_bin, dll_name)
        if os.path.isfile(dll_path):
            _QT_DLL_HANDLES.append(ctypes.WinDLL(dll_path))
