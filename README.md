# SystemMonitor

SystemMonitor is a desktop monitoring and input-control utility built with Python and Tkinter.
It provides a GUI for several configurable workflows, including:

- Hotkey-based repeating jobs
- Activity monitor movement
- Right-click monitoring
- Screen change watch
- Fishing session controls
- Rune session controls
- Save/load configuration in JSON or XML

The current codebase has been refactored from a single-file script into a modular package to improve maintainability, readability, and extensibility.

## Project Structure

```text
Systool/
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
    `-- theme.py
```

## File Overview

- `raw.py`
  Entry point for the application. Launches the GUI.

- `systool/app.py`
  Tkinter application layer. Builds the interface, wires UI actions to services, handles widget synchronization, hotkeys, and config UI flows.

- `systool/models.py`
  Domain models and shared state objects such as `AppState` and `HotkeyJob`.

- `systool/runtime.py`
  Runtime support layer for optional dependencies, synchronization primitives, pause control, UI-safe notifications, and mouse locking.

- `systool/services.py`
  Feature services and workflow logic:
  activity monitoring, right-click monitoring, screen watch, fishing sessions, rune sessions, position capture, and hotkey behavior.

- `systool/config.py`
  Configuration serialization/deserialization for JSON and XML.

- `systool/theme.py`
  Shared UI colors and font constants.

- `SystemMonitor.spec`
  PyInstaller build specification for packaging the application into a Windows executable.

- `build_windows.bat`
  Windows batch script that installs dependencies and builds the executable automatically.

## Requirements

Python 3.9+ is recommended.

Main dependencies:

- `pynput`
- `pywin32`
- `pystray`
- `pillow`
- `mss`
- `numpy`
- `pygame`
- `pyautogui`

Notes:

- `pywin32` is Windows-only.
- The application is designed primarily for Windows because several features depend on Win32 APIs.
- You can still inspect or partially run the code on macOS/Linux, but Windows-specific functionality may not work there.

## Run Locally

From the project folder:

```bash
python raw.py
```

or:

```bash
python3 raw.py
```

## Install Dependencies

### Windows

```bash
python -m pip install pynput pywin32 pystray pillow mss numpy pygame pyautogui
```

### macOS/Linux

```bash
python3 -m pip install pynput pystray pillow mss numpy pygame pyautogui
```

`pywin32` is omitted on macOS/Linux because it is not supported there.

## Build a Windows EXE

Build on Windows, using a Windows Python environment.

### Option 1: Automatic build

Run:

```powershell
.\build_windows.bat
```

This script will:

1. Check that Python is installed
2. Install/update packaging dependencies
3. Clean old build artifacts
4. Build the exe with PyInstaller
5. Open the `dist` folder

Expected output:

```text
dist\SystemMonitor.exe
```

### Option 2: Manual build from spec

```powershell
py -m pip install pyinstaller pynput pywin32 pystray pillow mss numpy pygame pyautogui
py -m PyInstaller --noconfirm --clean SystemMonitor.spec
```

## Configuration

The application supports saving and loading configuration files in:

- JSON
- XML

The saved configuration includes:

- Hotkey jobs
- Hotkey bindings
- Session timers
- Recorded positions
- Screen watch settings
- Fishing settings
- Rune session settings

## Architecture Summary

The refactor introduces clear boundaries:

- UI layer: `systool/app.py`
- Domain state: `systool/models.py`
- Runtime/infrastructure: `systool/runtime.py`
- Feature services: `systool/services.py`
- Persistence/config: `systool/config.py`

This makes the project easier to:

- maintain
- test
- extend with new monitoring features
- package and deploy

## Typical Workflow

1. Install dependencies
2. Run `python raw.py`
3. Configure hotkeys and feature settings in the GUI
4. Save configuration if needed
5. Build on Windows with `build_windows.bat` when you want a distributable exe

## Troubleshooting

### The EXE says libraries are missing

Use the included `SystemMonitor.spec` and `build_windows.bat` instead of a plain PyInstaller one-liner. The spec explicitly includes hidden imports and collected package assets.

### Some features do not work on macOS/Linux

That is expected for Win32-specific functionality. Build and use the full application on Windows for best compatibility.

### PyInstaller build succeeds but runtime behavior differs

Test the application first with:

```bash
python raw.py
```

in the same Windows environment before packaging it.

## Entry Point

The application starts from:

```python
from systool.app import run

if __name__ == "__main__":
    run()
```

## Future Improvements

- Add `requirements.txt`
- Add automated tests around config/state behavior
- Add logging abstraction for easier debugging
- Add installer packaging for Windows distribution
