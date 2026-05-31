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

bridge_dll_candidates = [
    Path("systool") / "pointers" / "studiomem_bridge.dll",
    Path("bridge") / "build" / "Release" / "studiomem_bridge.dll",
]

binaries = [
    (str(path), str(Path("systool") / "pointers"))
    for path in bridge_dll_candidates
    if path.exists()
]

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
    # Pointer modules (consolidated into systool.pointers package)
    "systool.pointers.pointer_reader",
    "systool.pointers.memory_backend",
    "systool.pointers.profiles",
    "systool.pointers.pointer_chain_ranker",
    # Purecase module (dynamically imported at runtime)
    "purecase_module",
    # OCR modules (dynamically imported in systool/runtime.py inside try/except)
    "pytesseract",
    "tesserocr",
    "cysignals",
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
