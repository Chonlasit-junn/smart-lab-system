# smart_gatekeeper.spec
import os
import cv2
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Collect customtkinter assets
ctk_datas = collect_data_files("customtkinter")
ort_notices = collect_data_files("onnxruntime", includes=["LICENSE", "ThirdPartyNotices.txt"])

# cv2 haar cascade path
cv2_data = os.path.dirname(cv2.__file__)
model_root = 'Silent-Face-Anti-Spoofing'
runtime_data = [
    (os.path.join(model_root, 'resources', 'anti_spoof_models', '2.7_80x80_MiniFASNetV2.fp32.onnx'), os.path.join(model_root, 'resources', 'anti_spoof_models')),
    (os.path.join(model_root, 'resources', 'anti_spoof_models', '2.7_80x80_MiniFASNetV2.fp32.json'), os.path.join(model_root, 'resources', 'anti_spoof_models')),
    (os.path.join(model_root, 'LICENSE'), model_root),
]

a = Analysis(
    ['smart_gatekeeper.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        *ctk_datas,
        *ort_notices,
        (os.path.join(cv2_data, 'data', 'haarcascade_frontalface_default.xml'), os.path.join('cv2', 'data')),
        *runtime_data,
    ],
    hiddenimports=[
        'customtkinter',
        'PIL._tkinter_finder',
        'cv2',
        'onnxruntime',
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'onnx',
        'liveness_reference',
        'src',
        'torch._dynamo',
        'torch._export',
        'torch._functorch',
        'torch._inductor',
        'torch.contrib',
        'torch.distributed',
        'torch.testing',
        'torch.utils.benchmark',
        'torch.utils.data.datapipes',
        'torch.utils.tensorboard',
        'tensorboard',
        'tensorflow',
        'keras',
        'scipy',
        'pandas',
        'torchvision',
    ],
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
