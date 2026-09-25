"""MSI entry point for the Admin-authenticated Lab registration wizard."""

from __future__ import annotations

from qt_runtime import prepare_qt_dll_search_path

prepare_qt_dll_search_path()

from lab_setup import main


if __name__ == "__main__":
    raise SystemExit(main())
