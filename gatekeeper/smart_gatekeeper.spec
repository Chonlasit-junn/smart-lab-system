# smart_gatekeeper.spec
import os
import cv2
from PyInstaller.utils.hooks import collect_data_files, collect_all

block_cipher = None

# Collect customtkinter assets
ctk_datas = collect_data_files("customtkinter")

# Collect torch fully
torch_datas, torch_binaries, torch_hiddenimports = collect_all('torch')

# cv2 haar cascade path
cv2_data = os.path.dirname(cv2.__file__)

a = Analysis(
    ['smart_gatekeeper.py'],
    pathex=['.'],
    binaries=[
        *torch_binaries,
    ],
    datas=[
        *ctk_datas,
        *torch_datas,
        (os.path.join(cv2_data, 'data', 'haarcascade_frontalface_default.xml'), os.path.join('cv2', 'data')),
        ('Silent-Face-Anti-Spoofing', 'Silent-Face-Anti-Spoofing'),
        ('known_faces', 'known_faces'),
        ('embeddings_cache.pkl', '.'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL._tkinter_finder',
        'cv2',
        'torch',
        'torch.nn',
        'torch.nn.functional',
        'torchvision',
        'torchvision.transforms',
        'src.anti_spoof_predict',
        'src.generate_patches',
        *torch_hiddenimports,
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=['hook-torch.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    exclude_binaries=False,
    name='SmartGatekeeper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='NONE',
)
