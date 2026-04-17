# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path


pynput_datas, pynput_binaries, pynput_hiddenimports = collect_all("pynput")
mss_datas, mss_binaries, mss_hiddenimports = collect_all("mss")
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
pygame_datas, pygame_binaries, pygame_hiddenimports = collect_all("pygame")
pystray_datas, pystray_binaries, pystray_hiddenimports = collect_all("pystray")
pil_datas, pil_binaries, pil_hiddenimports = collect_all("PIL")
pyautogui_datas, pyautogui_binaries, pyautogui_hiddenimports = collect_all("pyautogui")
pytesseract_datas, pytesseract_binaries, pytesseract_hiddenimports = collect_all("pytesseract")
psutil_datas, psutil_binaries, psutil_hiddenimports = collect_all("psutil")
pymem_datas, pymem_binaries, pymem_hiddenimports = collect_all("pymem")
win32_hiddenimports = collect_submodules("win32com")
vendor_tesseract_dir = Path("vendor") / "tesseract"
vendor_tesseract_datas = []
if vendor_tesseract_dir.exists():
    for item in vendor_tesseract_dir.rglob("*"):
        if item.is_file():
            vendor_tesseract_datas.append((str(item), str(Path("tesseract") / item.relative_to(vendor_tesseract_dir).parent)))

datas = (
    pynput_datas
    + mss_datas
    + numpy_datas
    + pygame_datas
    + pystray_datas
    + pil_datas
    + pyautogui_datas
    + pytesseract_datas
    + psutil_datas
    + pymem_datas
    + vendor_tesseract_datas
)

binaries = (
    pynput_binaries
    + mss_binaries
    + numpy_binaries
    + pygame_binaries
    + pystray_binaries
    + pil_binaries
    + pyautogui_binaries
    + pytesseract_binaries
    + psutil_binaries
    + pymem_binaries
)

hiddenimports = (
    pynput_hiddenimports
    + mss_hiddenimports
    + numpy_hiddenimports
    + pygame_hiddenimports
    + pystray_hiddenimports
    + pil_hiddenimports
    + pyautogui_hiddenimports
    + pytesseract_hiddenimports
    + psutil_hiddenimports
    + pymem_hiddenimports
    + win32_hiddenimports
    + [
        "pynput.keyboard",
        "pynput.mouse",
        "win32gui",
        "win32con",
        "win32api",
        "win32process",
        "pywintypes",
        "pythoncom",
    ]
)


a = Analysis(
    ["raw.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="SystemMonitor",
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
)
