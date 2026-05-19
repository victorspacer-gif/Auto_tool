"""Runtime services, optional integrations, and synchronization helpers."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

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

MSS_IMPORT_ERROR = ""
NUMPY_IMPORT_ERROR = ""

try:
    import mss

    HAS_MSS = True
except Exception as exc:
    mss = None
    HAS_MSS = False
    MSS_IMPORT_ERROR = str(exc)

try:
    import numpy as np

    HAS_NUMPY = True
except Exception as exc:
    np = None
    HAS_NUMPY = False
    NUMPY_IMPORT_ERROR = str(exc)

CV2_IMPORT_ERROR = ""

try:
    import cv2

    HAS_CV2 = True
except Exception as exc:
    cv2 = None
    HAS_CV2 = False
    CV2_IMPORT_ERROR = str(exc)

TESSERACT_IMPORT_ERROR = ""
TESSEROCR_IMPORT_ERROR = ""

try:
    import pytesseract

    HAS_PYTESSERACT = True
except Exception as exc:
    pytesseract = None
    HAS_PYTESSERACT = False
    TESSERACT_IMPORT_ERROR = str(exc)

try:
    import tesserocr

    HAS_TESSEROCR = True
except Exception as exc:
    tesserocr = None
    HAS_TESSEROCR = False
    TESSEROCR_IMPORT_ERROR = str(exc)

HAS_TESSERACT = HAS_PYTESSERACT or HAS_TESSEROCR

# ── Constants (needed before pygame init) ────────────────────────────
from .constants import (  # noqa: E402
    EXEC_WAIT_TIMEOUT_DEFAULT,
    EXEC_WAIT_TIMEOUT_MAX,
    EXEC_WAIT_TIMEOUT_MIN,
    PAUSE_CONTROLLER_SLEEP_INTERVAL,
    PYGAME_MIXER_BUFFER,
    PYGAME_MIXER_CHANNELS,
    PYGAME_MIXER_FORMAT,
    PYGAME_MIXER_FREQ,
)

try:
    import pygame

    # Eager init at import time (main thread) — matches Pointers-evaluation behavior.
    pygame.mixer.pre_init(PYGAME_MIXER_FREQ, PYGAME_MIXER_FORMAT, PYGAME_MIXER_CHANNELS, PYGAME_MIXER_BUFFER)
    pygame.mixer.init()

    HAS_PYGAME = True
except Exception as exc:
    pygame = None
    HAS_PYGAME = False
    logger.warning("pygame unavailable — audio alerts disabled: %s", exc)


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
        self._module_state_changed: Callable[[str, bool], None] = lambda _module, _running: None

    def configure(
        self,
        dispatch: Callable[[Callable[[], None]], None],
        log: Callable[[str], None],
        set_status: Callable[[str, str], None],
        refresh_stats: Callable[[], None],
        set_pause_label: Callable[[bool], None],
        job_state_changed: Callable[[HotkeyJob], None],
        module_state_changed: Callable[[str, bool], None],
    ) -> None:
        self._dispatch = dispatch
        self._log = log
        self._set_status = set_status
        self._refresh_stats = refresh_stats
        self._set_pause_label = set_pause_label
        self._job_state_changed = job_state_changed
        self._module_state_changed = module_state_changed

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

    def module_state_changed(self, module_id: str, running: bool) -> None:
        self._dispatch(lambda: self._module_state_changed(module_id, running))


class PauseController:
    def __init__(self, ui: UINotifier, *, start_paused: bool = True) -> None:
        self._ui = ui
        self._event = threading.Event()
        self._paused = bool(start_paused)
        if self._paused:
            self._event.clear()
        else:
            self._event.set()

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
            time.sleep(PAUSE_CONTROLLER_SLEEP_INTERVAL)


@dataclass(slots=True)
class CursorRequest:
    token: object = field(default_factory=object)
    expires_at: float | None = None
    module_id: str = "anonymous"


class ExecutionGate:
    def __init__(self, pause: PauseController) -> None:
        self._pause = pause
        self._owner: object | None = None
        self._queue: list[CursorRequest] = []
        self._condition = threading.Condition()

    def acquire(
        self,
        stop_evt: threading.Event,
        max_wait: float | None = None,
        module_id: str = "anonymous",
    ) -> bool:
        request = CursorRequest(module_id=module_id)
        with self._condition:
            self._queue_request_locked(request)
            self._condition.notify_all()
        while True:
            if stop_evt.is_set():
                self._discard_request(request)
                return False
            self._pause.wait()
            with self._condition:
                if not self._is_request_queued_locked(request):
                    return False
                if self._owner is None and self._is_next_request_locked(request):
                    self._owner = request.token
                    self._remove_request_locked(request)
                    return True
                self._condition.wait(timeout=self._wait_timeout_locked(request, max_wait))

    def release(self) -> None:
        with self._condition:
            self._owner = None
            self._condition.notify_all()

    def _queue_request_locked(self, request: CursorRequest) -> None:
        self._queue.append(request)

    def _remove_request_locked(self, request: CursorRequest) -> None:
        self._queue = [queued for queued in self._queue if queued.token is not request.token]

    def _discard_request(self, request: CursorRequest) -> None:
        with self._condition:
            self._remove_request_locked(request)
            self._condition.notify_all()

    def _is_request_queued_locked(self, request: CursorRequest) -> bool:
        return any(queued.token is request.token for queued in self._queue)

    def _is_next_request_locked(self, request: CursorRequest) -> bool:
        return bool(self._queue) and self._queue[0].token is request.token

    @staticmethod
    def _wait_timeout_locked(_request: CursorRequest, max_wait: float | None) -> float:
        if max_wait is None:
            return EXEC_WAIT_TIMEOUT_DEFAULT
        return max(EXEC_WAIT_TIMEOUT_MIN, min(EXEC_WAIT_TIMEOUT_MAX, max_wait))

    # ── Legacy methods (kept for test compatibility) ────────────────
    def _prune_expired_locked(self) -> None:
        """Remove expired requests from the queue. No-op in current impl."""
        self._queue = [r for r in self._queue if r.expires_at is None or r.expires_at > time.monotonic()]

    def _rebalance_queue_for_fairness_locked(self) -> None:
        """Move dominant module to back of queue. No-op when no dominance detected."""
        if (self._last_module_id and
                self._consecutive_grants >= getattr(self, '_max_consecutive_grants', 2)):
            for i in range(len(self._queue)):
                if self._queue[i].module_id == self._last_module_id:
                    self._queue.append(self._queue.pop(i))
                    break


class MouseGate:
    def __init__(self, execution: ExecutionGate) -> None:
        self._execution = execution

    def acquire(
        self,
        stop_evt: threading.Event,
        max_wait: float | None = None,
        module_id: str = "anonymous",
    ) -> bool:
        return self._execution.acquire(stop_evt, max_wait=max_wait, module_id=module_id)

    def release(self) -> None:
        self._execution.release()


class AppRuntime:
    def __init__(self) -> None:
        self.state = AppState()
        self.settings_lock = threading.RLock()
        self.record_lock = threading.RLock()
        self.ui = UINotifier()
        self.pause = PauseController(self.ui, start_paused=True)
        self.execution = ExecutionGate(self.pause)
        self.mouse = MouseGate(self.execution)
        self.afk_stop = threading.Event()
        self.rclick_stop = threading.Event()
        self.alarm_stop = threading.Event()
        self.char_status_stop = threading.Event()
        self.fish_stop = threading.Event()
        self.healer_stop = threading.Event()
        self.rune_stop = threading.Event()
        # Optional service references — set by app.py after creation
        self.hp_service: object | None = None
        self.mp_service: object | None = None
        self.cap_service: object | None = None
        self.food_service: object | None = None
        self.runtime_timer_stop = threading.Event()


@dataclass(slots=True)
class OCRReadResult:
    text: str
    confidence: float = 0.0


class TesseractOCREngine:
    """Thread-local OCR engine that prefers persistent tesserocr instances."""

    _OEM_MAP = {
        "0": 0,
        "1": 1,
        "2": 2,
        "3": 3,
    }
    _PSM_MAP = {
        "3": 3,
        "6": 6,
        "7": 7,
        "8": 8,
        "10": 10,
        "11": 11,
        "13": 13,
    }

    def __init__(self, tesseract_cmd: str) -> None:
        self.tesseract_cmd = tesseract_cmd
        self.backend = "tesserocr" if HAS_TESSEROCR else "pytesseract"
        self._thread_local = threading.local()

    def _get_api(self, *, psm: str, oem: str):
        if not HAS_TESSEROCR or tesserocr is None:
            return None
        cache_key = f"api_{psm}_{oem}"
        api = getattr(self._thread_local, cache_key, None)
        if api is None:
            api = tesserocr.PyTessBaseAPI(
                path=os.environ.get("TESSDATA_PREFIX") or None,
                psm=self._PSM_MAP.get(psm, 6),
                oem=self._OEM_MAP.get(oem, 1),
            )
            setattr(self._thread_local, cache_key, api)
        else:
            api.SetPageSegMode(self._PSM_MAP.get(psm, 6))
        return api

    def recognize(
        self,
        image: Any,
        *,
        psm: str = "6",
        oem: str = "1",
        whitelist: str = "",
    ) -> OCRReadResult:
        if image is None:
            return OCRReadResult(text="", confidence=0.0)
        if HAS_TESSEROCR and tesserocr is not None:
            return self._recognize_tesserocr(image, psm=psm, oem=oem, whitelist=whitelist)
        if HAS_PYTESSERACT and pytesseract is not None:
            return self._recognize_pytesseract(image, psm=psm, oem=oem, whitelist=whitelist)
        raise RuntimeError("No OCR backend is available")

    def _recognize_tesserocr(
        self,
        image: Any,
        *,
        psm: str,
        oem: str,
        whitelist: str,
    ) -> OCRReadResult:
        api = self._get_api(psm=psm, oem=oem)
        if api is None:
            raise RuntimeError("tesserocr backend unavailable")
        api.SetVariable("tessedit_char_whitelist", whitelist or "")
        api.SetVariable("debug_file", os.devnull)
        height, width = image.shape[:2]
        bytes_per_pixel = 1 if len(image.shape) == 2 else image.shape[2]
        bytes_per_line = image.strides[0]
        api.SetImageBytes(image.tobytes(), width, height, bytes_per_pixel, bytes_per_line)
        text = (api.GetUTF8Text() or "").strip()
        confidence = max(0.0, float(api.MeanTextConf() or 0.0)) / 100.0
        return OCRReadResult(text=text, confidence=confidence)

    def _recognize_pytesseract(
        self,
        image: Any,
        *,
        psm: str,
        oem: str,
        whitelist: str,
    ) -> OCRReadResult:
        config_parts = [f"--psm {psm}", f"--oem {oem}"]
        if whitelist:
            config_parts.append(f"-c tessedit_char_whitelist={whitelist}")
        config = " ".join(config_parts)
        data = pytesseract.image_to_data(
            image,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
        text = " ".join(token.strip() for token in data.get("text", []) if token and token.strip()).strip()
        confidences: list[float] = []
        for value in data.get("conf", []):
            try:
                conf = float(value)
            except (TypeError, ValueError):
                continue
            if conf >= 0:
                confidences.append(conf)
        confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        return OCRReadResult(text=text, confidence=confidence)


def resolve_tesseract_cmd(explicit_path: str = "") -> str | None:
    candidates: list[str] = []
    explicit_path = explicit_path.strip()
    if explicit_path:
        candidates.append(explicit_path)
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(os.path.join(meipass, "tesseract", "tesseract.exe"))
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(app_root, "vendor", "tesseract", "tesseract.exe"))
    which_path = shutil.which("tesseract")
    if which_path:
        candidates.append(which_path)
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        root = os.environ.get(env_name)
        if root:
            candidates.append(os.path.join(root, "Tesseract-OCR", "tesseract.exe"))
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def configure_tesseract_runtime(tesseract_cmd: str) -> None:
    tesseract_dir = os.path.dirname(os.path.abspath(tesseract_cmd))
    tessdata_dir = os.path.join(tesseract_dir, "tessdata")
    if os.path.isdir(tessdata_dir):
        os.environ["TESSDATA_PREFIX"] = tessdata_dir
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if tesseract_dir not in path_entries:
        os.environ["PATH"] = tesseract_dir + os.pathsep + os.environ.get("PATH", "")
    if HAS_PYTESSERACT and pytesseract is not None:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def create_ocr_engine(explicit_path: str = "") -> TesseractOCREngine:
    tesseract_cmd = resolve_tesseract_cmd(explicit_path)
    if not tesseract_cmd:
        raise RuntimeError("Tesseract executable not found")
    configure_tesseract_runtime(tesseract_cmd)
    if not HAS_TESSERACT:
        parts = []
        if TESSEROCR_IMPORT_ERROR:
            parts.append(f"tesserocr: {TESSEROCR_IMPORT_ERROR}")
        if TESSERACT_IMPORT_ERROR:
            parts.append(f"pytesseract: {TESSERACT_IMPORT_ERROR}")
        detail = " | ".join(parts) if parts else "no backend imports succeeded"
        raise RuntimeError(f"OCR engine unavailable: {detail}")
    return TesseractOCREngine(tesseract_cmd)


def describe_ocr_environment() -> str:
    parts = [f"Python {sys.version.split()[0]}"]
    if HAS_TESSEROCR:
        parts.append("tesserocr=ready")
    else:
        parts.append(f"tesserocr=missing ({TESSEROCR_IMPORT_ERROR or 'not installed'})")
    if HAS_PYTESSERACT:
        parts.append("pytesseract=ready")
    else:
        parts.append(f"pytesseract=missing ({TESSERACT_IMPORT_ERROR or 'not installed'})")
    return " | ".join(parts)
