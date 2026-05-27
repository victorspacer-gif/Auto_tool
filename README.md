# SystemMonitor

SystemMonitor is a Windows desktop automation and monitoring utility built with Python and Tkinter.
It combines configurable hotkey automation, screen monitoring, OCR-driven character stat tracking, and game-oriented helper tools in one GUI.

## Current Features

- Activity Control
  Hotkey-based repeating jobs, activity monitor movement, and right-click monitoring.
- Rune Session
  Automated rune-making loop with position recording, mana gating, and timing controls.
- Auto Healer
  Healing by spell hotkey or by rune-on-character flow using watched HP values.
- Screen Watch
  Pixel-change alerts plus low-HP alerts driven by OCR character status.
- Character Status
  OCR watcher for `Level`, `Hit Points`, `Mana`, `Capacity`, and `Food`, with HP/Mana regeneration tracking.
- Fishing Session
  Rod/spot automation with session timing and capacity stop thresholds.
- Hotkeys
  Rebindable global hotkeys for pause, stop, and feature toggles.
- Config
  Save and load complete app state in JSON.

## OCR-Driven Integrations

The Character Status watcher feeds live values into other modules:

- Rune Session can require a minimum mana value before casting.
- Activity Control hotkey jobs can require a minimum mana value before pressing a key.
- Fishing Session can stop automatically when capacity falls below a configured value.
- Screen Watch can trigger alerts when HP falls below a configured percentage.
- Right-Click Monitor can switch to `food` mode and keep food time above a minimum threshold by burst-clicking food.
- Auto Healer uses watched HP values to decide when to heal.

## Auto Healer

The `Auto Healer` tab supports two modes:

- `spell`
  Presses a configured game hotkey such as `F1`, `F2`, and so on.
- `rune`
  Right-clicks a recorded healing rune position, then left-clicks a recorded character-center position.

Healer options include:

- HP percentage threshold or fixed HP threshold
- minimum mana requirement
- rune mouse speed factor
- rune-use delay in milliseconds
- recorded character-center position
- recorded healing-rune position

## Character Status OCR

The Character Status tab supports two OCR styles:

- Full window OCR
  Select the clearer stats/skills window and let the app parse labeled rows like `Hit Points`, `Mana`, `Capacity`, and `Food`.
- Per-field OCR
  Select `HP`, `Mana`, and `Cap` areas individually if you want tighter control.

Tracked values include:

- `Level`
- `Hit Points`
- `Mana`
- `Capacity`
- `Food`
- HP regeneration per minute
- Mana regeneration per minute

These values are stored in runtime state and refreshed while the watcher is active.

## Project Structure

```text
Auto_tool/
|-- raw.py
|-- README.md
|-- SystemMonitor.spec
|-- build_windows.bat
`-- systool/
    |-- __init__.py
    |-- app.py
    |-- config.py
    |-- models.py
    |-- runtime.py
    |-- services.py
    `-- theme.py
```

## File Overview

- `raw.py`
  App entry point.
- `systool/app.py`
  Tkinter UI, tab layout, widget wiring, sync/update logic, position capture flows, and hotkey handling.
- `systool/models.py`
  Shared state and domain models such as `AppState` and `HotkeyJob`.
- `systool/runtime.py`
  Optional dependency loading, pause/mouse synchronization, UI-safe notifications, and Tesseract resolution.
- `systool/services.py`
  Background automation services and feature logic.
- `systool/config.py`
  JSON save and load support for the full app state.
- `systool/theme.py`
  Shared colors and font constants.
- `SystemMonitor.spec`
  PyInstaller spec used for Windows packaging.
- `build_windows.bat`
  Windows build script that installs dependencies, prepares bundled Tesseract, and builds the executable.

## Requirements

Python 3.11+ is recommended on Windows.

Main Python packages:

- `pyinstaller`
- `pynput`
- `pywin32`
- `pystray`
- `pillow`
- `mss`
- `numpy`
- `pygame`
- `pyautogui`
- `opencv-python`
- `pytesseract`

Notes:

- `pywin32` is Windows-only.
- OCR features depend on `opencv-python`, `pytesseract`, and a Tesseract OCR executable.
- The application is designed primarily for Windows because several features depend on Win32 APIs and global input hooks.

## Run Locally

From the project folder:

```bash
python raw.py
```

## Install Dependencies

### Windows

```bash
python -m pip install pynput pywin32 pystray pillow mss numpy pygame pyautogui opencv-python pytesseract
```

## Tesseract OCR

For local development, SystemMonitor can use:

- a system Tesseract install on `PATH`
- a manually selected `tesseract.exe` path from the Character Status tab
- a bundled Tesseract copy inside the packaged Windows build

The app will try to resolve Tesseract automatically. If needed, the Character Status tab also exposes a `Tesseract path` field and browse button.

## Build a Windows EXE

Build on Windows using a Windows Python environment.

### Automatic build

Run:

```powershell
.\build_windows.bat
```

This script will:

1. Check that the Windows Python launcher is available.
2. Install or update runtime and build dependencies.
3. Install `cysignals` and a bundled `tesserocr` wheel when present.
4. Clean previous build artifacts.
5. Copy a local Tesseract installation into `vendor\tesseract`.
6. Build the executable with PyInstaller.
7. Open the `dist` folder.

Expected output:

```text
dist\SystemMonitor.exe
```

Important:

- The build machine should have Tesseract installed in a standard Windows location such as `C:\Program Files\Tesseract-OCR`.
- The build bundles that Tesseract copy into the packaged app so end users do not need to install Tesseract manually.
- For persistent OCR acceleration, place a compatible Windows wheel in `vendor\python-wheels`.
  The build script looks for `tesserocr-*-cp312-cp312-win_amd64.whl`.
  If present, it installs that wheel automatically before packaging.

### Manual build from spec

```powershell
py -m pip install pyinstaller pynput pywin32 pystray pillow mss numpy pygame pyautogui opencv-python pytesseract cysignals
py -m pip install --upgrade .\vendor\python-wheels\tesserocr-2.10.0-cp312-cp312-win_amd64.whl
py -m PyInstaller --noconfirm --clean SystemMonitor.spec
```

If you build manually and want bundled OCR support, make sure `vendor\tesseract` exists before running PyInstaller.

## Configuration

The application supports saving and loading JSON configuration.

Saved configuration includes:

- hotkey jobs and hotkey bindings
- activity/right-click settings
- screen watch settings
- character status OCR settings
- fishing settings
- rune session settings
- auto healer settings
- recorded positions

## Typical Workflow

1. Install Python dependencies.
2. Run `python raw.py`.
3. Configure hotkeys and automation settings in the GUI.
4. Select the Character Status window or individual OCR fields.
5. Configure feature thresholds such as mana, capacity, HP alerts, food handling, and auto healer behavior.
6. Save a config if desired.
7. Build with `build_windows.bat` when you want a distributable Windows executable.

## Troubleshooting

### OCR features are not working

Check these first:

- `opencv-python` and `pytesseract` are installed in the same Python environment used to run the app.
- Tesseract is installed locally for development, or bundled for the packaged build.
- The Character Status watcher is pointed at a clear stats window or accurate individual stat regions.

### The EXE says a dependency is missing

Use the included `SystemMonitor.spec` and `build_windows.bat`. The spec collects hidden imports and can bundle a local Tesseract copy.

### Runtime behavior differs between Python and the EXE

Test the app first with:

```bash
python raw.py
```

in the same Windows environment used for packaging.

### Some features do not work on macOS/Linux

That is expected. The full application is intended for Windows.

## Entry Point

The application starts from:

```python
from systool.app import run

if __name__ == "__main__":
    run()
```

## Future Improvements

- Add automated tests around config/state behavior
- Improve OCR model tuning for more UI variants
- Add an installer instead of only a raw executable build
- Add more OCR-backed automation triggers
