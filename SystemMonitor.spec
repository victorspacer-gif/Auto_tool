# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

# Vendor tesseract (copied into vendor/tesseract by your build script)
vendor_tesseract_dir = Path("vendor") / "tesseract"
vendor_tesseract_datas = []
if vendor_tesseract_dir.exists():
    for item in vendor_tesseract_dir.rglob("*"):
        if item.is_file():
            vendor_tesseract_datas.append(
                (str(item), str(Path("tesseract") / item.relative_to(vendor_tesseract_dir).parent))
            )

datas = vendor_tesseract_datas

binaries = []

hiddenimports = [
    # Core dependencies
    "mss.windows",
    "pynput.keyboard",
    "pynput.mouse",
    "win32gui",
    "win32con",
    "win32api",
    "win32process",
    "pywintypes",
    "pythoncom",
    # Dynamically loaded memory modules (imported inside methods, not at module level)
    "studiomemuer_hp_module",
    "studiomemuer_mp_module",
    "studiomemuer_cap_module",
    "studiomemuer_light_module",
    "studiomemuer_light_module.light_profile",
    "studiomemuer_light_module.memory_backend",
    # Submodules needed for dynamic __import__ resolution
    "studiomemuer_mp_module.mp_profile",
    "studiomemuer_cap_module.cap_profile",
    # Purecase module (dynamically imported at runtime)
    "purecase_module",
]

# Hook and runtime hook paths (ensure these directories exist and are committed)
hookspath = ["hooks"]
runtime_hooks = []

a = Analysis(
    ["raw.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=hookspath,
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="SystemMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SystemMonitor",
)
