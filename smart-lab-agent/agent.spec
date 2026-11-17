# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

logo_icon = str(Path(SPECPATH).resolve().parent / "frontend" / "public" / "smart-lab-logo.ico")

a = Analysis(
    ['agent.pyw'],
    pathex=[],
    binaries=[],
    datas=[(logo_icon, ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=logo_icon,
)
