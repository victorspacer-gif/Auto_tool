"""InputRouter — dual-mode mouse/keyboard input abstraction.

Two modes (stored in ``runtime.state.input_mode``):

  * ``"hardware"`` (default) — physical mouse/keyboard events via pynput.
    The cursor moves visibly, and the window must be in the foreground.

  * ``"direct"`` — Win32 SendMessage/PostMessage to the target window HWND.
    The cursor does NOT move; events are injected directly into the window's
    message queue.  This works even when the window is in the background.

Adapted from TibiaAuto12's ``SendToClient`` (mode 0) and ``MoveMouse``
(mode 1) classes.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

from ..runtime import (
    AppRuntime,
    HAS_PYNPUT,
    HAS_WIN32,
    pynput_kb,
    pynput_mouse,
    win32con,
    win32gui,
    win32api,
)
from .input_services import HumanMouse


class InputRouter:
    """Centralised input router that dispatches to hardware or direct mode.

    Usage::

        router = runtime.input_router
        router.left_click(500, 300)
        router.tap_key("f1")
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    # ── Property: current mode ──────────────────────────────────────

    @property
    def mode(self) -> str:
        return self.runtime.state.input_mode

    # ── Public API ──────────────────────────────────────────────────

    def move_mouse(self, x: int, y: int) -> None:
        """Move cursor to screen coordinate (x, y)."""
        if self.mode == "direct":
            # Direct mode: no physical move needed; coordinates are
            # translated at click time via ScreenToClient.
            pass
        else:
            if not HAS_PYNPUT:
                return
            mouse = pynput_mouse.Controller()
            mouse.position = (x, y)

    def left_click(self, x: int, y: int) -> None:
        """Left-click at screen coordinate (x, y)."""
        if self.mode == "direct":
            self._direct_click(x, y, "left")
        else:
            self._hardware_click(x, y, "left")

    def right_click(self, x: int, y: int) -> None:
        """Right-click at screen coordinate (x, y)."""
        if self.mode == "direct":
            self._direct_click(x, y, "right")
        else:
            self._hardware_click(x, y, "right")

    def tap_key(self, key_str: str, hold_seconds: float = 0.04) -> None:
        """Press and release a key identified by name (e.g. 'f1', 'space')."""
        if self.mode == "direct":
            self._direct_key(key_str, hold_seconds)
        else:
            self._hardware_key(key_str, hold_seconds)

    def human_move_and_click(
        self,
        x: int,
        y: int,
        button: str = "left",
        *,
        duration: float | None = None,
    ) -> None:
        """Human-like move then click.

        In hardware mode this uses HumanMouse bezier curves + jitter.
        In direct mode it's a simple direct click (no bezier needed since
        the window receives the coordinate directly).
        """
        if self.mode == "direct":
            self.left_click(x, y) if button == "left" else self.right_click(x, y)
            return

        if not HAS_PYNPUT:
            return
        mouse = pynput_mouse.Controller()
        HumanMouse.move(mouse, (x, y), duration=duration)
        time.sleep(self._jitter_delay())
        if button == "left":
            mouse.click(pynput_mouse.Button.left)
        else:
            mouse.click(pynput_mouse.Button.right)

    # ── Hardware mode (pynput) ──────────────────────────────────────

    @staticmethod
    def _hardware_click(x: int, y: int, button: str) -> None:
        if not HAS_PYNPUT:
            return
        mouse = pynput_mouse.Controller()
        mouse.position = (int(x), int(y))
        time.sleep(0.02)
        if button == "left":
            mouse.click(pynput_mouse.Button.left)
        else:
            mouse.click(pynput_mouse.Button.right)

    @staticmethod
    def _hardware_key(key_str: str, hold_seconds: float) -> None:
        if not HAS_PYNPUT:
            return
        key = _key_str_to_pynput(key_str)
        if key is None:
            return
        kb = pynput_kb.Controller()
        kb.press(key)
        time.sleep(max(0.01, hold_seconds))
        kb.release(key)

    # ── Direct mode (Win32 SendMessage) ─────────────────────────────

    def _get_hwnd(self) -> int | None:
        """Resolve the target window handle."""
        state = self.runtime.state
        # Priority: explicit game_hwnd > attached HWND > window title match
        if state.game_hwnd:
            return state.game_hwnd
        if state.game_window_title:
            try:
                hwnd = win32gui.FindWindow(None, state.game_window_title)
                if hwnd:
                    return hwnd
            except Exception:
                pass
            if HAS_WIN32:
                # Fallback: partial title match
                found = [None]

                def enum_cb(hwnd, _):
                    if found[0]:
                        return
                    try:
                        title = win32gui.GetWindowText(hwnd)
                        if state.game_window_title.lower() in title.lower() and win32gui.IsWindowVisible(hwnd):
                            found[0] = hwnd
                    except Exception:
                        pass

                try:
                    win32gui.EnumWindows(enum_cb, None)
                except Exception:
                    pass
                return found[0]
        return None

    def _direct_click(self, x: int, y: int, button: str) -> None:
        hwnd = self._get_hwnd()
        if not hwnd or not HAS_WIN32:
            logger.warning("direct input: no target HWND available")
            return
        try:
            client_pt = win32gui.ScreenToClient(hwnd, (x, y))
            lparam = win32api.MAKELONG(client_pt[0], client_pt[1])
        except Exception:
            return

        # Post mouse-move so the window knows where the cursor is
        try:
            win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
        except Exception:
            pass

        if button == "left":
            try:
                win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
                win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON, lparam)
            except Exception:
                pass
        else:
            try:
                win32api.SendMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lparam)
                win32api.SendMessage(hwnd, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON, lparam)
            except Exception:
                pass

    def _direct_key(self, key_str: str, hold_seconds: float) -> None:
        hwnd = self._get_hwnd()
        if not hwnd or not HAS_WIN32:
            logger.warning("direct input: no target HWND available")
            return
        vk = _key_str_to_vk(key_str)
        if vk is None:
            return
        try:
            win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
            time.sleep(max(0.01, hold_seconds))
            win32api.SendMessage(hwnd, win32con.WM_KEYUP, vk, 0)
        except Exception:
            pass

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _jitter_delay() -> float:
        import random
        return random.uniform(0.02, 0.06)


# ── Key mapping helpers ──────────────────────────────────────────────

_FUNCTION_KEYS = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
_NAMED_KEYS_VK = {
    "space": 0x20, "enter": 0x0D, "esc": 0x1B, "tab": 0x09,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59,
    "z": 0x5A,
}


def _key_str_to_vk(key_str: str) -> int | None:
    """Convert a key name to a Windows virtual-key code."""
    val = key_str.strip().lower()
    if val in _FUNCTION_KEYS:
        return _FUNCTION_KEYS[val]
    if val in _NAMED_KEYS_VK:
        return _NAMED_KEYS_VK[val]
    if len(val) == 1:
        c = val[0]
        if "a" <= c <= "z":
            return 0x41 + (ord(c) - ord("a"))
        if "0" <= c <= "9":
            return 0x30 + (ord(c) - ord("0"))
    return None


def _key_str_to_pynput(key_str: str):
    """Convert key name to pynput key object."""
    if not HAS_PYNPUT:
        return None
    value = key_str.strip().lower()
    if value in _FUNCTION_KEYS:
        attr = value
        return getattr(pynput_kb.Key, attr, None)
    named = {
        "home": pynput_kb.Key.home, "end": pynput_kb.Key.end,
        "up": pynput_kb.Key.up, "down": pynput_kb.Key.down,
        "left": pynput_kb.Key.left, "right": pynput_kb.Key.right,
        "space": pynput_kb.Key.space, "enter": pynput_kb.Key.enter,
        "esc": pynput_kb.Key.esc, "tab": pynput_kb.Key.tab,
        "backspace": pynput_kb.Key.backspace, "delete": pynput_kb.Key.delete,
        "insert": pynput_kb.Key.insert,
        "page_up": pynput_kb.Key.page_up, "page_down": pynput_kb.Key.page_down,
    }
    if value in named:
        return named[value]
    if len(value) == 1:
        return pynput_kb.KeyCode.from_char(value)
    return None
