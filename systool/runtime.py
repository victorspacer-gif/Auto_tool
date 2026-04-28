"""Runtime services, optional integrations, and synchronization helpers."""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from collections.abc import Callable

from .config import ConfigSerializer
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

try:
    import pytesseract

    HAS_TESSERACT = True
except Exception as exc:
    pytesseract = None
    HAS_TESSERACT = False
    TESSERACT_IMPORT_ERROR = str(exc)

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


@dataclass(slots=True)
class CursorRequest:
    token: object = field(default_factory=object)
    expires_at: float | None = None
    module_id: str = "anonymous"


class ModuleQueue:
    """Manages a FIFO queue of module execution requests.

    Enforces single-thread execution per module — only one module can be scheduled
    and executed at a time. When a module enters the queue, it must complete its
    execution before the next module is allowed to run. If another module requests
    execution while one is running, it is added to the queue and waits its turn.

    After a module finishes, the system checks whether other modules are waiting
    in the queue before allowing that module to re-queue. This prevents any single
    module from monopolizing execution and ensures fair task distribution.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # FIFO queue of module IDs (preserves insertion order, no duplicates)
        self._queue: list[str] = []
        # Module currently executing (None when idle)
        self._current_module: str | None = None
        # Condition variable for signaling queue state changes
        self._condition = threading.Condition(self._lock)

    def enqueue(self, module_id: str) -> bool:
        """Add a module to the execution queue if not already queued or executing.

        Returns True if successfully enqueued, False if module is already in queue
        or currently executing (prevents duplicate entries).
        """
        with self._lock:
            # Reject if module is already queued or currently executing
            if module_id in self._queue or module_id == self._current_module:
                return False
            self._queue.append(module_id)
            self._condition.notify_all()
            return True

    def dequeue(self, stop_evt: threading.Event | None = None) -> str | None:
        """Get the next module from the front of the queue.

        Blocks until a module is available or stop_evt is set.
        Returns the module_id string, or None if stopped/empty.
        """
        with self._condition:
            while not self._queue:
                if stop_evt and stop_evt.is_set():
                    return None
                self._condition.wait(timeout=0.1)
                if stop_evt and stop_evt.is_set():
                    return None

            module_id = self._queue.pop(0)
            self._current_module = module_id
            return module_id

    def complete(self, module_id: str | None = None) -> None:
        """Mark a module as completed and release execution ownership.

        If module_id is provided and matches the current module, clears ownership.
        Otherwise, clears any stale ownership reference.
        """
        with self._lock:
            if module_id is not None and self._current_module == module_id:
                self._current_module = None
            elif module_id is None:
                self._current_module = None

    def is_empty(self) -> bool:
        """Check if the queue has no waiting modules."""
        with self._lock:
            return len(self._queue) == 0

    def peek_next(self) -> str | None:
        """Peek at the next module without removing it from the queue."""
        with self._lock:
            return self._queue[0] if self._queue else None

    def has_module_waiting(self, module_id: str) -> bool:
        """Check if a specific module is waiting in the queue."""
        with self._lock:
            return module_id in self._queue

    def get_queue_length(self) -> int:
        """Get the number of modules waiting in the queue."""
        with self._lock:
            return len(self._queue)

    def clear(self) -> None:
        """Clear all queued modules and release current execution."""
        with self._lock:
            self._queue.clear()
            self._current_module = None


class ExecutionGate:
    """Manages execution and mouse access with single-thread per-module enforcement.

    Uses ModuleQueue to ensure only one module executes at a time. When a module
    enters the queue, it must complete before the next module runs. After completion,
    other queued modules get their turn before the same module can re-queue.
    """

    # High-priority modules that need exclusive mouse/execution access during their session.
    # While a high-priority module holds the gate, lower-priority modules (right-click, healer, afk)
    # must skip their attempts to avoid interrupting critical A->B sequences.
    HIGH_PRIORITY_MODULES = frozenset({"fishing", "rune"})

    def __init__(self, pause: PauseController) -> None:
        self._pause = pause
        self._owner: object | None = None
        self._queue: list[CursorRequest] = []
        self._condition = threading.Condition()
        self._last_module_id: str | None = None
        self._consecutive_grants = 0
        self._max_consecutive_grants = 2
        # Track which high-priority module currently holds exclusive access.
        # When set, only that module (and other high-priority modules) can acquire the gate.
        self._session_owner: str | None = None
        # Module-level queue for single-thread execution enforcement per module
        self._module_queue = ModuleQueue()

    def set_session_active(self, module_id: str) -> None:
        """Mark a high-priority session as active. Blocks lower-priority modules."""
        if module_id in self.HIGH_PRIORITY_MODULES:
            with self._condition:
                self._session_owner = module_id

    def clear_session(self) -> None:
        """Clear the exclusive session lock, allowing all modules to compete again."""
        with self._condition:
            self._session_owner = None
            self._condition.notify_all()

    def acquire(
        self,
        stop_evt: threading.Event,
        max_wait: float | None = None,
        module_id: str = "anonymous",
    ) -> bool:
        # Check ModuleQueue first — if this module is already executing or queued, reject.
        # This enforces single-thread execution per module and prevents re-queueing
        # until the current execution completes and other modules get a chance.
        if self._module_queue.has_module_waiting(module_id):
            return False

        request = CursorRequest(
            expires_at=None if max_wait is None else time.monotonic() + max(0.0, max_wait),
            module_id=module_id,
        )
        with self._condition:
            self._queue_request_locked(request)
            self._condition.notify_all()
        while True:
            if stop_evt.is_set():
                self._discard_request(request)
                return False
            self._pause.wait()
            with self._condition:
                self._prune_expired_locked()
                # Session priority check: block lower-priority modules when a high-priority
                # session (fishing/rune) holds exclusive access. High-priority modules can
                # always acquire; lower-priority modules must wait or skip.
                if (
                    self._session_owner is not None
                    and self._session_owner != request.module_id
                    and request.module_id not in self.HIGH_PRIORITY_MODULES
                ):
                    # Lower-priority module blocked by active high-priority session.
                    # Don't queue it — let the caller's loop handle retry/skip logic.
                    self._remove_request_locked(request)
                    return False
                self._rebalance_queue_for_fairness_locked()
                if not self._is_request_queued_locked(request):
                    return False
                if self._owner is None and self._is_next_request_locked(request):
                    self._owner = request.token
                    # Track session ownership for high-priority modules
                    if request.module_id in self.HIGH_PRIORITY_MODULES:
                        self._session_owner = request.module_id
                    elif self._session_owner == request.module_id:
                        # Same session continuing — keep it active
                        pass
                    else:
                        # Non-high-priority module acquired while session was set;
                        # this shouldn't happen due to check above, but be safe.
                        if self._session_owner is not None:
                            self._session_owner = None
                    if request.module_id == self._last_module_id:
                        self._consecutive_grants += 1
                    else:
                        self._last_module_id = request.module_id
                        self._consecutive_grants = 1
                    self._remove_request_locked(request)
                    return True
                wait_time = self._wait_timeout_locked(request)
                self._condition.wait(timeout=wait_time)

    def release(self, module_id: str | None = None) -> None:
        with self._condition:
            was_session_owner = (self._session_owner is not None and self._owner is not None)
            self._owner = None
            self._prune_expired_locked()
            # Clear session lock only if no high-priority requests are still queued.
            # This allows the next high-priority module to grab the gate immediately
            # without going through the fairness queue.
            has_high_priority_queued = any(
                r.module_id in self.HIGH_PRIORITY_MODULES for r in self._queue
            )
            if was_session_owner and not has_high_priority_queued:
                self._session_owner = None

            # Notify ModuleQueue that this module has completed its execution.
            # This allows other waiting modules to be dequeued.
            if module_id is not None:
                self._module_queue.complete(module_id)
            else:
                self._module_queue.complete()

            self._condition.notify_all()

    def _queue_request_locked(self, request: CursorRequest) -> None:
        self._queue.append(request)

    def _prune_expired_locked(self) -> None:
        now = time.monotonic()
        self._queue = [
            request
            for request in self._queue
            if request.expires_at is None or request.expires_at > now
        ]

    def _rebalance_queue_for_fairness_locked(self) -> None:
        if (
            len(self._queue) < 2
            or self._last_module_id is None
            or self._consecutive_grants < self._max_consecutive_grants
        ):
            return
        if self._queue[0].module_id != self._last_module_id:
            return
        for index, request in enumerate(self._queue[1:], start=1):
            if request.module_id != self._last_module_id:
                self._queue.append(self._queue.pop(0))
                self._condition.notify_all()
                return

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
    def _wait_timeout_locked(request: CursorRequest) -> float:
        if request.expires_at is None:
            return 0.05
        return max(0.01, min(0.05, request.expires_at - time.monotonic()))


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

    def release(self, module_id: str | None = None) -> None:
        self._execution.release(module_id=module_id)

    def set_session_active(self, module_id: str) -> None:
        """Delegate to execution gate — mark a high-priority session as active."""
        self._execution.set_session_active(module_id)

    def clear_session(self) -> None:
        """Delegate to execution gate — clear the exclusive session lock."""
        self._execution.clear_session()

    def enqueue_module(self, module_id: str) -> bool:
        """Add a module to the ModuleQueue for fair scheduling."""
        return self._execution._module_queue.enqueue(module_id)

    def dequeue_next_module(self, stop_evt: threading.Event | None = None) -> str | None:
        """Get the next module from the ModuleQueue."""
        return self._execution._module_queue.dequeue(stop_evt)

    def complete_module(self, module_id: str | None = None) -> None:
        """Mark a module as completed in the ModuleQueue."""
        self._execution._module_queue.complete(module_id)

    def has_queued_modules(self) -> bool:
        """Check if there are modules waiting in the queue."""
        return not self._execution._module_queue.is_empty()

    def peek_next_module(self) -> str | None:
        """Peek at the next module without removing it from the queue."""
        return self._execution._module_queue.peek_next()


class AppRuntime:
    def __init__(self) -> None:
        self.state = AppState()
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        if os.path.exists(config_path):
            try:
                payload = ConfigSerializer.load_file(config_path)
                ConfigSerializer.apply_loaded(self.state, payload)
            except Exception as e:
                print(f"Failed to load config: {e}")
        self.settings_lock = threading.RLock()
        self.record_lock = threading.RLock()
        self.ui = UINotifier()
        self.pause = PauseController(self.ui)
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

    def save_config(self) -> None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        ConfigSerializer.save_json(config_path, self.state)


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
