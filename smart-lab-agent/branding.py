"""Locate the Smart Lab icon in source runs and PyInstaller builds."""

import sys
from pathlib import Path


def logo_icon_path() -> str:
    bundle_dir = getattr(sys, "_MEIPASS", None)
    asset_dir = (
        Path(bundle_dir)
        if bundle_dir
        else Path(__file__).resolve().parent.parent / "frontend" / "public"
    )
    return str(asset_dir / "smart-lab-logo.ico")
