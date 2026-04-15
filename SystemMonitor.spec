# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules


pynput_datas, pynput_binaries, pynput_hiddenimports = collect_all("pynput")
mss_datas, mss_binaries, mss_hiddenimports = collect_all("mss")
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
pygame_datas, pygame_binaries, pygame_hiddenimports = collect_all("pygame")
pystray_datas, pystray_binaries, pystray_hiddenimports = collect_all("pystray")
pil_datas, pil_binaries, pil_hiddenimports = collect_all("PIL")
pyautogui_datas, pyautogui_binaries, pyautogui_hiddenimports = collect_all("pyautogui")
win32_hiddenimports = collect_submodules("win32com")

datas = (
    pynput_datas
    + mss_datas
    + numpy_datas
    + pygame_datas
    + pystray_datas
    + pil_datas
    + pyautogui_datas
)

binaries = (
    pynput_binaries
    + mss_binaries
    + numpy_binaries
    + pygame_binaries
    + pystray_binaries
    + pil_binaries
    + pyautogui_binaries
)

hiddenimports = (
    pynput_hiddenimports
    + mss_hiddenimports
    + numpy_hiddenimports
    + pygame_hiddenimports
    + pystray_hiddenimports
    + pil_hiddenimports
    + pyautogui_hiddenimports
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
