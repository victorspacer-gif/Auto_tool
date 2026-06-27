"""ChaseTargetService — continuous monster-targeting scanner.

Runs as a background thread alongside the CaveBot to ensure the character
always has a valid target selected in the battle list. Adapted from the
TibiaAuto12 ShowMap/AutoAttack engine pattern.

Scan cycle:
  1. Check if stop/paused
  2. Press skill key to target nearest monster
  3. Click battle list to ensure selection
  4. Check follow mode (click follow if idle)
  5. Sleep scan_interval_ms
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
    pynput_kb,
    pynput_mouse,
)
from ..constants import EXEC_WAIT_TIMEOUT_DEFAULT, INPUT_POST_CLICK_SLEEP
from ..theme import GREEN, ORANGE, RED
from .input_services import HumanMouse, SafeKeyboardSession


class ChaseTargetService:
    """Background monster targeting scanner.

    Lifecycle:
      - ``start()`` — begins the continuous scan thread
      - ``stop()`` — signals the thread to exit
    """

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
        self.runtime.ui.log(f"▶ Chase target started — {len(state.monster_names)} monster(s)")

        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing — chase target unavailable")
            state.active = False
            self.runtime.ui.module_state_changed("chase_target", False)
            return

        mouse = pynput_mouse.Controller()
        keyboard = pynput_kb.Controller()

        # Circular index over configured monsters
        monster_idx = 0

        try:
            while not self._stop_event.is_set():
                self.runtime.pause.wait()
                if self._stop_event.is_set():
                    break

                # Re-read state for live config changes
                monster_list = state.monster_names
                if not monster_list:
                    self._wait_interruptible(1.0)
                    continue

                monster_idx = (monster_idx + 1) % len(monster_list)
                _monster_name = monster_list[monster_idx]
                battle_x = state.battle_list_x
                attack_key_str = state.attack_key

                # ── Step 1: Press skill key to target ─────────────
                if attack_key_str:
                    skill_key = self._key_str_to_pynput(attack_key_str)
                    if skill_key:
                        if not self.runtime.execution.acquire(
                            self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
                        ):
                            continue
                        try:
                            session = SafeKeyboardSession(keyboard)
                            session.tap(skill_key, hold_seconds=0.04)
                            time.sleep(random.uniform(0.08, 0.15))
                        finally:
                            self.runtime.execution.release()

                # ── Step 2: Click battle list to ensure target ────
                if battle_x > 0:
                    # Click at varying Y positions to cycle through targets
                    click_y = 120 + (monster_idx * 20) + random.randint(-2, 2)
                    if not self.runtime.execution.acquire(
                        self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
                    ):
                        continue
                    try:
                        HumanMouse.move(mouse, (battle_x + random.randint(-3, 3), click_y))
                        time.sleep(random.uniform(0.02, 0.05))
                        mouse.click(pynput_mouse.Button.left)
                        time.sleep(INPUT_POST_CLICK_SLEEP)
                    finally:
                        self.runtime.execution.release()

                # ── Step 3: Follow mode check ─────────────────────
                if state.follow_mode:
                    self._click_follow_if_needed(mouse)

                # ── Wait for next scan cycle ──────────────────────
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

    def _click_follow_if_needed(self, mouse) -> None:
        """Left-click on character position to re-engage follow."""
        char_pos = self.runtime.state.healer.character_pos
        if char_pos and char_pos != (0, 0):
            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
            ):
                return
            try:
                jittered = (
                    char_pos[0] + random.randint(-3, 3),
                    char_pos[1] + random.randint(-3, 3),
                )
                HumanMouse.move(mouse, jittered)
                time.sleep(random.uniform(0.02, 0.04))
                mouse.click(pynput_mouse.Button.left)
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

    @staticmethod
    def _key_str_to_pynput(key_str: str):
        if not HAS_PYNPUT:
            return None
        value = key_str.strip().lower()
        named = {}
        for key_name, attr_name in [
            ("f1", "f1"), ("f2", "f2"), ("f3", "f3"), ("f4", "f4"),
            ("f5", "f5"), ("f6", "f6"), ("f7", "f7"), ("f8", "f8"),
            ("f9", "f9"), ("f10", "f10"), ("f11", "f11"), ("f12", "f12"),
            ("home", "home"), ("end", "end"),
            ("up", "up"), ("down", "down"), ("left", "left"), ("right", "right"),
        ]:
            key_value = getattr(pynput_kb.Key, attr_name, None)
            if key_value is not None:
                named[key_name] = key_value
        if value in named:
            return named[value]
        if len(value) == 1:
            return pynput_kb.KeyCode.from_char(value)
        return None
