"""AutoLooterService — automatic corpse looting background service.

Adapted from the TibiaAuto12 looting pattern. Picks up items from defeated
creatures by right-clicking SQM positions around the character.

Runs as its own thread and can be toggled independently of the cavebot.
When auto_loot_on_kill is enabled, it triggers after the chase target
detects a monster count decrease (kill detected).
"""

from __future__ import annotations

import logging
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import (
    AppRuntime,
    HAS_PYNPUT,
    pynput_mouse,
)
from ..constants import EXEC_WAIT_TIMEOUT_DEFAULT, INPUT_POST_CLICK_SLEEP
from ..theme import GREEN, ORANGE, RED
from .input_services import HumanMouse


class AutoLooterService:
    """Background corpse looter.

    Lifecycle:
      - ``start()`` — begins the loot scan thread
      - ``stop()`` — signals the thread to exit
      - ``loot_once()`` — trigger a single loot cycle (for on-kill looting)
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._stop_event = threading.Event()

    # ── Public API ────────────────────────────────────────────────────

    def start(self) -> None:
        state = self.runtime.state.auto_looter
        if state.active:
            return
        if not state.sqm_positions:
            self.runtime.ui.log("⚠️  No SQM positions configured for auto-looter")
            self.runtime.ui.set_status("Add SQM positions for looter", ORANGE)
            return
        state.active = True
        self._stop_event.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("auto_looter", True)
        self.runtime.ui.set_status("💰 Auto-looter started", GREEN)

    def stop(self) -> None:
        state = self.runtime.state.auto_looter
        if not state.active:
            return
        self._stop_event.set()
        state.active = False
        self.runtime.ui.module_state_changed("auto_looter", False)
        self.runtime.ui.set_status("💰 Auto-looter stopped", RED)

    def loot_once(self) -> None:
        """Trigger a single loot cycle (fire-and-forget in a daemon thread)."""
        state = self.runtime.state.auto_looter
        if not state.active or not state.sqm_positions:
            return
        threading.Thread(target=self._run_loot_cycle, daemon=True).start()

    # ── Internal worker (continuous mode) ────────────────────────────

    def _worker(self) -> None:
        state = self.runtime.state.auto_looter
        self.runtime.ui.log(f"▶ Auto-looter started — {len(state.sqm_positions)} SQM(s)")

        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing — auto-looter unavailable")
            state.active = False
            self.runtime.ui.module_state_changed("auto_looter", False)
            return

        try:
            while not self._stop_event.is_set():
                self.runtime.pause.wait()
                if self._stop_event.is_set():
                    break

                self._run_loot_cycle()

                # Wait between cycles
                delay_min = max(0.05, state.loot_delay_min_ms / 1000.0)
                delay_max = max(delay_min, state.loot_delay_max_ms / 1000.0)
                delay = random.uniform(delay_min, delay_max)
                if not self._wait_interruptible(delay):
                    break

        except Exception as exc:
            logger.exception("Auto-looter worker crashed")
            self.runtime.ui.log(f"❌ Auto-looter error: {exc}")
        finally:
            state.active = False
            self.runtime.ui.module_state_changed("auto_looter", False)
            self.runtime.ui.log("⏹ Auto-looter ended")

    # ── Loot cycle ───────────────────────────────────────────────────

    def _run_loot_cycle(self) -> None:
        """Execute one full loot pass over all SQM positions."""
        state = self.runtime.state.auto_looter
        if not state.sqm_positions:
            return

        mouse = pynput_mouse.Controller()
        jitter_range = state.jitter

        for sqm in state.sqm_positions:
            if self._stop_event.is_set():
                return

            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="looter"
            ):
                continue

            try:
                jittered = (
                    sqm[0] + random.randint(-jitter_range, jitter_range),
                    sqm[1] + random.randint(-jitter_range, jitter_range),
                )
                HumanMouse.move(mouse, jittered)
                time.sleep(random.uniform(0.02, 0.05))
                mouse.click(pynput_mouse.Button.right)
                time.sleep(random.uniform(0.08, 0.15))
            finally:
                self.runtime.execution.release()

            if not self._wait_interruptible(random.uniform(0.1, 0.2)):
                return

    # ── Helpers ─────────────────────────────────────────────────────

    def _wait_interruptible(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop_event.is_set():
                return False
            self.runtime.pause.wait()
            time.sleep(0.05)
        return True
