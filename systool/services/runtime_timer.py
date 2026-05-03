"""Persistent runtime-limit enforcement via win32 messagebox."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    import win32con
    import win32gui

    HAS_WIN32_MSGBOX = True
except ImportError:
    win32con = None  # type: ignore[assignment]
    win32gui = None  # type: ignore[assignment]
    HAS_WIN32_MSGBOX = False


class RuntimeTimerService:
    """Independent timer that counts up to a configured duration and then
    displays a system-level Windows warning messagebox.

    Lifecycle
    ---------
    * ``start()`` — spawns the countdown thread (no-op if already running).
    * ``stop()``  — signals the worker to exit before the popup fires.

    The timer runs independently of all other services and is unaffected by
    start/stop of AFK, fishing, runes, healer, or right-click modules.
    """

    # ── Configuration ────────────────────────────────────────────────

    DURATION_SECONDS: int = 7 * 60 * 60  # 7 hours

    def __init__(self, runtime) -> None:
        self._runtime = runtime
        self._active = False
        self._worker_thread: threading.Thread | None = None

    # ── Public API ───────────────────────────────────────────────────

    def start(self) -> None:
        """Begin the countdown.  No-op if a timer is already active."""
        if self._active:
            logger.debug("RuntimeTimerService.start() called but already active — skipping")
            return

        self._runtime.runtime_timer_stop.clear()
        self._active = True
        self._worker_thread = threading.Thread(
            target=self._countdown,
            name="RuntimeTimerWorker",
            daemon=True,
        )
        self._worker_thread.start()
        logger.info("Runtime timer started — will alert after %d seconds (%.1f hours)",
                     self.DURATION_SECONDS, self.DURATION_SECONDS / 3600)

    def stop(self) -> None:
        """Signal the worker to exit (prevents popup from firing)."""
        if not self._active:
            return
        self._runtime.runtime_timer_stop.set()
        self._active = False
        logger.info("Runtime timer stopped")

    # ── Internal ─────────────────────────────────────────────────────

    def _countdown(self) -> None:
        """Background worker that sleeps in 60-second increments until the
        duration elapses or a stop signal arrives."""
        deadline = time.monotonic() + self.DURATION_SECONDS

        while True:
            # Check for early termination
            if self._runtime.runtime_timer_stop.is_set():
                logger.debug("Runtime timer stopped by external signal")
                return

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            # Sleep until next check (max 60s, but wake early on stop)
            sleep_time = min(remaining, 60.0)
            self._runtime.runtime_timer_stop.wait(timeout=sleep_time)

        # Timer expired — show win32 messagebox
        if not self._runtime.runtime_timer_stop.is_set():
            self._show_warning()

    def _show_warning(self) -> None:
        """Display a system-level Windows warning dialog."""
        if not HAS_WIN32_MSGBOX or win32gui is None or win32con is None:
            logger.error("win32gui unavailable — cannot display runtime warning")
            return

        message = (
            "Auto_tool Runtime Limit Reached\n"
            "\n"
            "You have been running for 7 hours.\n"
            "Please log out of the game to avoid penalties.\n"
            "\n"
            "Click OK to acknowledge."
        )
        title = "⏰ Auto_tool — Runtime Warning"

        # win32gui.MessageBox blocks until dismissed by the user.
        # The dialog appears on the taskbar and can be closed via Alt+F4,
        # the close button, or pressing Enter/OK.
        try:
            logger.info("Showing runtime warning messagebox")
            win32gui.MessageBox(None, message, title,
                                win32con.MB_OK | win32con.MB_ICONWARNING | win32con.MB_TOPMOST)
        except Exception as exc:
            logger.error("Failed to show messagebox: %s", exc)
