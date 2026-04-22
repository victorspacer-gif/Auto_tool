"""Pytest conftest: mock system deps unavailable on this machine."""

import sys
from unittest.mock import MagicMock, PropertyMock

# Mock tkinter before pyautogui tries to import it (Linux requirement)
tk_mock = MagicMock()
tk_mock.TkVersion = 8.6
sys.modules["tkinter"] = tk_mock
sys.modules["_tkinter"] = tk_mock

# Mock pywin32 — Windows-only, not available on Linux
for mod in ["win32con", "win32gui", "pywin32"]:
    sys.modules[mod] = MagicMock()
