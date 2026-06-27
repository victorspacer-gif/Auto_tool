"""ChaseTargetService — continuous monster-targeting scanner.

Runs as a background thread alongside the CaveBot to ensure the character
always has a valid target selected in the battle list.

All input goes through InputRouter (supports hardware + direct modes).
"""

from __future__ import annotations

import logging
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime, HAS_PYNPUT
from ..constants import EXEC_WAIT_TIMEOUT_DEFAULT, INPUT_POST_CLICK_SLEEP
from ..theme import GREEN, ORANGE, RED


class ChaseTargetService:
    """Background monster targeting scanner."""

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._stop_event = threading.Event()

    # ── Public API ────────────────────────────────────────────────────

    def start(self) -> None:
        state = self.runtime.state.chase_target
        if state.active:
            return
        if not state.monster_names:
            self.runtime.ui.log("⚠️  No chase-target monsters configured")
            self.runtime.ui.set_status("Add monsters to chase target", ORANGE)
            return
        if state.battle_list_x <= 0:
            self.runtime.ui.log("⚠️  Battle list X not configured for chase")
            self.runtime.ui.set_status("Set battle list X for chase target", ORANGE)
            return
        state.active = True
        self._stop_event.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("chase_target", True)
        self.runtime.ui.set_status("🎯 Chase target started", GREEN)

    def stop(self) -> None:
        state = self.runtime.state.chase_target
        if not state.active:
            return
        self._stop_event.set()
        state.active = False
        self.runtime.ui.module_state_changed("chase_target", False)
        self.runtime.ui.set_status("🎯 Chase target stopped", RED)

    # ── Internal worker ──────────────────────────────────────────────

    def _worker(self) -> None:
        state = self.runtime.state.chase_target
        router = self.runtime.input_router
        self.runtime.ui.log(f"▶ Chase target — {len(state.monster_names)} monster(s) [input: {self.runtime.state.input_mode}]")

        if not HAS_PYNPUT and self.runtime.state.input_mode == "hardware":
            self.runtime.ui.log("❌ pynput missing — hardware mode unavailable for chase")
            state.active = False
            self.runtime.ui.module_state_changed("chase_target", False)
            return

        monster_idx = 0

        try:
            while not self._stop_event.is_set():
                self.runtime.pause.wait()
                if self._stop_event.is_set():
                    break

                monster_list = state.monster_names
                if not monster_list:
                    self._wait_interruptible(1.0)
                    continue

                monster_idx = (monster_idx + 1) % len(monster_list)
                battle_x = state.battle_list_x
                attack_key_str = state.attack_key

                # ── Step 1: Press attack key ──────────────────
                if attack_key_str:
                    if not self.runtime.execution.acquire(
                        self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
                    ):
                        continue
                    try:
                        router.tap_key(attack_key_str, hold_seconds=0.04)
                        time.sleep(random.uniform(0.08, 0.15))
                    finally:
                        self.runtime.execution.release()

                # ── Step 2: Click battle list ─────────────────
                if battle_x > 0:
                    click_y = 120 + (monster_idx * 20) + random.randint(-2, 2)
                    bx = battle_x + random.randint(-3, 3)

                    if not self.runtime.execution.acquire(
                        self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
                    ):
                        continue
                    try:
                        router.human_move_and_click(bx, click_y, "left")
                        time.sleep(INPUT_POST_CLICK_SLEEP)
                    finally:
                        self.runtime.execution.release()

                # ── Step 3: Follow mode ───────────────────────
                if state.follow_mode:
                    self._click_follow_if_needed(router)

                interval_s = max(0.05, state.scan_interval_ms / 1000.0)
                if not self._wait_interruptible(interval_s):
                    break

        except Exception as exc:
            logger.exception("Chase target worker crashed")
            self.runtime.ui.log(f"❌ Chase target error: {exc}")
        finally:
            state.active = False
            self.runtime.ui.module_state_changed("chase_target", False)
            self.runtime.ui.log("⏹ Chase target ended")

    # ── Follow mode ─────────────────────────────────────────────────

    def _click_follow_if_needed(self, router) -> None:
        char_pos = self.runtime.state.healer.character_pos
        if char_pos and char_pos != (0, 0):
            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
            ):
                return
            try:
                jx = char_pos[0] + random.randint(-3, 3)
                jy = char_pos[1] + random.randint(-3, 3)
                router.left_click(jx, jy)
                time.sleep(INPUT_POST_CLICK_SLEEP)
            finally:
                self.runtime.execution.release()

    # ── Helpers ─────────────────────────────────────────────────────

    def _wait_interruptible(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop_event.is_set():
                return False
            self.runtime.pause.wait()
            time.sleep(0.05)
        return True
