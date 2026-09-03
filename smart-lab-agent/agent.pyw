"""
Force Windows to load the Qt DLLs bundled with this executable.
Must be the very first thing that runs — before any Qt imports.
"""
import sys
import os
import ctypes

# Force Windows to load the Qt DLLs bundled with this executable. This avoids
# importing an incompatible Qt6Widgets.dll from another application on PATH.
_QT_DLL_DIRECTORY_HANDLE = None
_QT_DLL_HANDLES = []


def _prepare_qt_dll_search_path():
    global _QT_DLL_DIRECTORY_HANDLE

    if sys.platform != "win32":
        return

    if getattr(sys, "frozen", False):
        qt_bin = os.path.join(sys._MEIPASS, "PyQt6", "Qt6", "bin")
    else:
        import PyQt6
        qt_bin = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "bin")

    if os.path.isdir(qt_bin):
        _QT_DLL_DIRECTORY_HANDLE = os.add_dll_directory(qt_bin)
        os.environ["PATH"] = qt_bin + os.pathsep + os.environ.get("PATH", "")

        # Explicitly preload the bundled Qt stack by absolute path. A Qt DLL
        # with the same name in the executable directory can otherwise win
        # over the directory added above on some Windows configurations.
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


_prepare_qt_dll_search_path()

# ── Application Entry Point ───────────────────────────────────────────────────
# Qt imports ต้องอยู่หลัง _prepare_qt_dll_search_path() เสมอ
from PyQt6.QtWidgets import QApplication  # noqa: E402
from core.agent_core import SmartLabAgent  # noqa: E402
from core.ui.login_overlay import LoginOverlay  # noqa: E402

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    agent_logic  = SmartLabAgent()
    login_screen = LoginOverlay(agent_logic)
    login_screen.show()
    sys.exit(app.exec())