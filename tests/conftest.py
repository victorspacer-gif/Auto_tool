"""Pytest conftest: mock system deps unavailable on this machine."""

import sys
import ctypes
from unittest.mock import MagicMock, PropertyMock

# Mock tkinter before pyautogui tries to import it (Linux requirement)
tk_mock = MagicMock()
tk_mock.TkVersion = 8.6
sys.modules["tkinter"] = tk_mock
sys.modules["_tkinter"] = tk_mock

# Mock pywin32 — Windows-only, not available on Linux
for mod in ["win32con", "win32gui", "pywin32"]:
    sys.modules[mod] = MagicMock()

# Optional runtime deps that may not be installed in the test environment.
sys.modules.setdefault("psutil", MagicMock())
sys.modules.setdefault("pymem", MagicMock())

if not hasattr(ctypes, "WinDLL"):
    ctypes.WinDLL = lambda *_args, **_kwargs: MagicMock()  # type: ignore[attr-defined]

# Mock pygame — audio backend not available on Linux test machine, but we need
# the module present so systool.runtime can import and define real functions.
sys.modules.setdefault("pygame", MagicMock())
