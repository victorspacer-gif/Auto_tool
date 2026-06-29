"""ChaseTargetService — continuous monster-targeting scanner.

Supports two targeting strategies:
  1. **Key-press mode** (default) — press F1 to target nearest monster,
     then click on the battle list at a calculated Y position.
  2. **Image-based mode** (when `image_targeting_enabled` is True) —
     uses OpenCV template matching to locate monster names on the battle
     list (NumberOfTargets / ScanTarget) and detect active combat state
     (IsAttacking), all from TibiaAuto12's Scanners.py.

All input goes through InputRouter (hardware + direct modes).
"""

from __future__ import annotations

import logging
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime, HAS_CV2, HAS_MSS, HAS_NUMPY, HAS_PYNPUT
from ..constants import EXEC_WAIT_TIMEOUT_DEFAULT, INPUT_POST_CLICK_SLEEP
from ..theme import GREEN, ORANGE, RED
from .image_finder import (
    count_monsters_in_battle,
    is_attacking,
    locate_all_images,
    scan_monster_in_battle,
)


class ChaseTargetService:
    """Background monster targeting scanner.

    Supports key-press targeting (press attack key, click battle list)
    and image-based targeting (scan monster name images on battle list,
    detect attack state via border analysis).
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

        # For image-based mode, also require battle_region
        if state.image_targeting_enabled:
            if state.battle_region is None:
                self.runtime.ui.log("⚠️  Battle region not configured — image targeting disabled, falling back to key-press")
                state.image_targeting_enabled = False
            elif not HAS_CV2 or not HAS_MSS or not HAS_NUMPY:
                self.runtime.ui.log("⚠️  OpenCV/mss not available — image targeting disabled, falling back to key-press")
                state.image_targeting_enabled = False

        state.active = True
        self._stop_event.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("chase_target", True)
        self.runtime.ui.set_status("🎯 Chase target started", GREEN)

        if state.image_targeting_enabled:
            self.runtime.ui.log("🔍 Chase target using image-based targeting")
        else:
            self.runtime.ui.log("🔑 Chase target using key-press targeting")

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
        self.runtime.ui.log(
            f"▶ Chase target — {len(state.monster_names)} monster(s) "
            f"[mode: {'image' if state.image_targeting_enabled else 'key-press'}]"
        )

        if not HAS_PYNPUT and self.runtime.state.input_mode == "hardware":
            self.runtime.ui.log("❌ pynput missing — hardware mode unavailable for chase")
            state.active = False
            self.runtime.ui.module_state_changed("chase_target", False)
            return

        monster_idx = 0
        # For image mode: track which monster name we're currently scanning
        img_monster_idx = 0

        try:
            while not self._stop_event.is_set():
                self.runtime.pause.wait()
                if self._stop_event.is_set():
                    break

                monster_list = state.monster_names
                if not monster_list:
                    self._wait_interruptible(1.0)
                    continue

                if state.image_targeting_enabled:
                    self._image_targeting_cycle(state, router, monster_list, img_monster_idx)
                    img_monster_idx = (img_monster_idx + 1) % len(monster_list)
                else:
                    self._keypress_targeting_cycle(state, router, monster_list, monster_idx)
                    monster_idx = (monster_idx + 1) % len(monster_list)

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

    # ── Key-press targeting (original method) ────────────────────────

    def _keypress_targeting_cycle(
        self, state, router, monster_list: list[str], monster_idx: int
    ) -> None:
        """Target using attack key + battle list click (original approach)."""
        battle_x = state.battle_list_x
        attack_key_str = state.attack_key

        # Step 1: Press attack key
        if attack_key_str:
            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
            ):
                return
            try:
                router.tap_key(attack_key_str, hold_seconds=0.04)
                time.sleep(random.uniform(0.08, 0.15))
            finally:
                self.runtime.execution.release()

        # Step 2: Click battle list
        if battle_x > 0:
            click_y = 120 + (monster_idx * 20) + random.randint(-2, 2)
            bx = battle_x + random.randint(-3, 3)

            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
            ):
                return
            try:
                router.human_move_and_click(bx, click_y, "left")
                time.sleep(INPUT_POST_CLICK_SLEEP)
            finally:
                self.runtime.execution.release()

        # Step 3: Follow mode
        if state.follow_mode:
            self._click_follow_if_needed(router)

    # ── Image-based targeting (TibiaAuto12 Scanners) ─────────────────

    def _image_targeting_cycle(
        self, state, router, monster_list: list[str], monster_idx: int
    ) -> None:
        """Target using image detection — mirrors TibiaAuto12's Scanners.py.

        Cycle:
          1. Check IsAttacking — skip if already fighting
          2. NumberOfTargets — count monsters of current name on battle list
          3. ScanTarget — find the monster name and click its health bar
          4. Follow mode check (image-based)
        """
        battle_region = state.battle_region
        if battle_region is None:
            return

        battle_x = state.battle_list_x
        monster_name = monster_list[monster_idx]
        precision = state.image_targeting_precision

        # ── Step 1: IsAttacking (skip if already fighting) ──────────
        if is_attacking(battle_region, precision=0.8):
            return  # Already attacking this target, don't re-target

        # ── Step 2: NumberOfTargets (count monsters on battle list) ─
        count = count_monsters_in_battle(monster_name, battle_region, precision=precision)
        if count <= 0:
            # Try key-press fallback: nearest monster may not be this type
            if battle_x > 0:
                self._fallback_keypress_target(state, router, monster_name, battle_x)
            return

        # ── Step 3: ScanTarget (find and click monster) ─────────────
        target_pos = scan_monster_in_battle(monster_name, battle_region, precision=precision + 0.06)
        if target_pos is None:
            # Monster name found via count but not center-locatable → fallback click
            if battle_x > 0:
                self._fallback_keypress_target(state, router, monster_name, battle_x)
            return

        click_x, click_y = target_pos

        if not self.runtime.execution.acquire(
            self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
        ):
            return
        try:
            router.human_move_and_click(click_x, click_y, "left")
            time.sleep(INPUT_POST_CLICK_SLEEP)
        finally:
            self.runtime.execution.release()

    def _fallback_keypress_target(
        self, state, router, monster_name: str, battle_x: int
    ) -> None:
        """Fallback: press attack key + click battle list when image targeting finds nothing."""
        attack_key_str = state.attack_key

        if attack_key_str:
            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
            ):
                return
            try:
                router.tap_key(attack_key_str, hold_seconds=0.04)
                time.sleep(random.uniform(0.08, 0.15))
            finally:
                self.runtime.execution.release()

        if battle_x > 0:
            click_y = 120 + random.randint(-2, 2)
            bx = battle_x + random.randint(-3, 3)

            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="chase"
            ):
                return
            try:
                router.human_move_and_click(bx, click_y, "left")
                time.sleep(INPUT_POST_CLICK_SLEEP)
            finally:
                self.runtime.execution.release()

        if state.follow_mode:
            self._click_follow_if_needed(router)

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
