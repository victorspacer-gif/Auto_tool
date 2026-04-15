"""Runtime services, optional integrations, and synchronization helpers."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .models import AppState, HotkeyJob

try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    HAS_PYAUTOGUI = True
except ImportError:
    pyautogui = None
    HAS_PYAUTOGUI = False

try:
    from PIL import Image, ImageDraw
    import pystray

    HAS_TRAY = True
except ImportError:
    Image = None
    ImageDraw = None
    pystray = None
    HAS_TRAY = False

try:
    import mss
    import numpy as np

    HAS_MSS = True
except ImportError:
    mss = None
    np = None
    HAS_MSS = False

try:
    import pygame

    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    pygame = None
    HAS_PYGAME = False

try:
    from pynput import keyboard as pynput_kb
    from pynput import mouse as pynput_mouse

    HAS_PYNPUT = True
except ImportError:
    pynput_kb = None
    pynput_mouse = None
    HAS_PYNPUT = False

try:
    import win32con
    import win32gui

    HAS_WIN32 = True
except ImportError:
    win32con = None
    win32gui = None
    HAS_WIN32 = False


class UINotifier:
    """UI-safe communication channel for background workers."""

    def __init__(self) -> None:
        self._dispatch: Callable[[Callable[[], None]], None] = lambda fn: fn()
        self._log: Callable[[str], None] = lambda _msg: None
        self._set_status: Callable[[str, str], None] = lambda _text, _color: None
        self._refresh_stats: Callable[[], None] = lambda: None
        self._set_pause_label: Callable[[bool], None] = lambda _paused: None
        self._job_state_changed: Callable[[HotkeyJob], None] = lambda _job: None

    def configure(
        self,
        dispatch: Callable[[Callable[[], None]], None],
        log: Callable[[str], None],
        set_status: Callable[[str, str], None],
        refresh_stats: Callable[[], None],
        set_pause_label: Callable[[bool], None],
        job_state_changed: Callable[[HotkeyJob], None],
    ) -> None:
        self._dispatch = dispatch
        self._log = log
        self._set_status = set_status
        self._refresh_stats = refresh_stats
        self._set_pause_label = set_pause_label
        self._job_state_changed = job_state_changed

    def dispatch(self, callback: Callable[[], None]) -> None:
        self._dispatch(callback)

    def log(self, message: str) -> None:
        self._dispatch(lambda: self._log(message))

    def set_status(self, text: str, color: str) -> None:
        self._dispatch(lambda: self._set_status(text, color))

    def refresh_stats(self) -> None:
        self._dispatch(self._refresh_stats)

    def set_pause_label(self, paused: bool) -> None:
        self._dispatch(lambda: self._set_pause_label(paused))

    def job_state_changed(self, job: HotkeyJob) -> None:
        self._dispatch(lambda: self._job_state_changed(job))


class PauseController:
    def __init__(self, ui: UINotifier) -> None:
        self._ui = ui
        self._event = threading.Event()
        self._event.set()
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def toggle(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._event.clear()
            self._ui.log("⏸  PAUSED")
        else:
            self._event.set()
            self._ui.log("▶  Resumed")
        self._ui.set_pause_label(self._paused)

    def wait(self) -> None:
        self._event.wait()

    def wait_interruptible(self, seconds: float, stop_evt: threading.Event) -> bool:
        deadline = time.monotonic() + seconds
        while True:
            if stop_evt.is_set():
                return False
            if not self._event.is_set():
                pause_started = time.monotonic()
                self._event.wait()
                deadline += time.monotonic() - pause_started
            if time.monotonic() >= deadline:
                return True
            time.sleep(0.01)


class MouseGate:
    def __init__(self, pause: PauseController) -> None:
        self._pause = pause
        self._lock = threading.Lock()

    def acquire(self, stop_evt: threading.Event) -> bool:
        while True:
            if stop_evt.is_set():
                return False
            self._pause.wait()
            if stop_evt.is_set():
                return False
            if self._lock.acquire(blocking=True, timeout=0.05):
                return True

    def release(self) -> None:
        try:
            self._lock.release()
        except RuntimeError:
            pass


class AppRuntime:
    def __init__(self) -> None:
        self.state = AppState()
        self.settings_lock = threading.Lock()
        self.record_lock = threading.Lock()
        self.ui = UINotifier()
        self.pause = PauseController(self.ui)
        self.mouse = MouseGate(self.pause)
        self.afk_stop = threading.Event()
        self.rclick_stop = threading.Event()
        self.alarm_stop = threading.Event()
        self.fish_stop = threading.Event()
        self.rune_stop = threading.Event()
