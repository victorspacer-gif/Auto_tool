"""AutoLooterService — automatic corpse looting.

Picks up items from defeated creatures by right-clicking SQM positions
around the character. All input goes through InputRouter.

Runs as its own thread. Supports continuous mode and one-shot loot_once().
"""

from __future__ import annotations

import logging
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime, HAS_PYNPUT
from ..constants import EXEC_WAIT_TIMEOUT_DEFAULT
from ..theme import GREEN, ORANGE, RED


class AutoLooterService:
    """Background corpse looter."""

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
        state = self.runtime.state.auto_looter
        if not state.active or not state.sqm_positions:
            return
        threading.Thread(target=self._run_loot_cycle, daemon=True).start()

    # ── Internal worker ──────────────────────────────────────────────

    def _worker(self) -> None:
        state = self.runtime.state.auto_looter
        self.runtime.ui.log(f"▶ Auto-looter started — {len(state.sqm_positions)} SQM(s) [input: {self.runtime.state.input_mode}]")

        if not HAS_PYNPUT and self.runtime.state.input_mode == "hardware":
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

                delay_min = max(0.05, state.loot_delay_min_ms / 1000.0)
                delay_max = max(delay_min, state.loot_delay_max_ms / 1000.0)
                if not self._wait_interruptible(random.uniform(delay_min, delay_max)):
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
        state = self.runtime.state.auto_looter
        router = self.runtime.input_router
        if not state.sqm_positions:
            return

        jitter_range = state.jitter

        for sqm in state.sqm_positions:
            if self._stop_event.is_set():
                return

            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="looter"
            ):
                continue

            try:
                jx = sqm[0] + random.randint(-jitter_range, jitter_range)
                jy = sqm[1] + random.randint(-jitter_range, jitter_range)
                router.right_click(jx, jy)
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
