"""Auto-healer automation service."""

from __future__ import annotations

import logging
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime, HAS_PYNPUT, pynput_kb, pynput_mouse
from ..constants import (
    HEALER_WAIT_INTERRUPTIBLE_1,
    HEALER_WAIT_INTERRUPTIBLE_2,
    HEALER_WAIT_INTERRUPTIBLE_3,
    HEALER_EXEC_MAX_WAIT,
    HEALER_COOLDOWN_SHORT,
    HEALER_COOLDOWN_LONG,
    HEALER_COOLDOWN_AFTER_MOUSE,
    HEALER_MOUSE_MAX_WAIT,
    HEALER_MIN_WAIT_TIMEOUT,
    HEALER_CAST_HOLD_SECONDS,
    HEALER_COOLDOWN_AFTER_TAP,
    HEALER_MOVE_BASE_DURATION,
    HEALER_MIN_MOVE_DURATION,
    HEALER_POST_ACTION_SLEEP,
    HEALER_MAX_COOLDOWN_BASE,
)
from ..theme import GREEN, ORANGE, RED
from .hotkeys import HotkeyService

class AutoHealerService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.healer_active:
            return
        if state.healer_mode == "rune" and (
            state.healer_character_pos == (0, 0) or state.healer_rune_pos == (0, 0)
        ):
            self.runtime.ui.log("⚠️  Record character center and healing rune position first")
            self.runtime.ui.set_status("Record healer positions first", ORANGE)
            return
        self.runtime.healer_stop.clear()
        state.healer_active = True
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("healer", True)
        self.runtime.ui.set_status("Auto healer active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.healer_active:
            return
        self.runtime.healer_stop.set()
        state.healer_active = False
        self.runtime.ui.module_state_changed("healer", False)
        self.runtime.ui.set_status("Auto healer stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Auto healer start")
        router = self.runtime.input_router
        cooldown_until = 0.0
        while not self.runtime.healer_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.healer_stop.is_set():
                break
            now = time.monotonic()
            if now < cooldown_until:
                if not self.runtime.pause.wait_interruptible(min(HEALER_MIN_WAIT_TIMEOUT, cooldown_until - now), self.runtime.healer_stop):
                    break
                continue
            with self.runtime.settings_lock:
                hp_peak = state.char_status_hp_peak
                mana_value = None
                if self.runtime.mp_service is not None:
                    try:
                        mana_value = self.runtime.mp_service.get_mp()
                    except Exception:
                        logger.debug("MP read failed in healer loop")
                mode = state.healer_mode
                spell_key_name = state.healer_spell_key
                use_percent = state.healer_use_percent
                hp_percent = state.healer_hp_percent
                hp_fixed = state.healer_hp_value
                min_mana = state.healer_min_mana
                max_mana = state.healer_max_mana
                character_pos = state.healer_character_pos
                rune_pos = state.healer_rune_pos
                mouse_speed = state.healer_mouse_speed
                rune_delay_ms = state.healer_rune_delay_ms
            hp_value = None
            if self.runtime.hp_service is not None:
                try:
                    hp_value = self.runtime.hp_service.get_hp()
                except Exception:
                    logger.debug("HP read failed in healer loop")
            if hp_value is None:
                if not self.runtime.pause.wait_interruptible(HEALER_WAIT_INTERRUPTIBLE_1, self.runtime.healer_stop):
                    break
                continue
            should_heal = False
            if use_percent:
                if hp_peak > 0 and (hp_value / hp_peak) * 100.0 <= hp_percent:
                    should_heal = True
            elif hp_value <= hp_fixed:
                should_heal = True
            if not should_heal:
                if not self.runtime.pause.wait_interruptible(HEALER_WAIT_INTERRUPTIBLE_2, self.runtime.healer_stop):
                    break
                continue
            if min_mana > 0 and mana_value is not None:
                threshold = random.randint(min_mana, max_mana) if max_mana > min_mana else min_mana
                if mana_value < threshold:
                    if not self.runtime.pause.wait_interruptible(HEALER_WAIT_INTERRUPTIBLE_3, self.runtime.healer_stop):
                        break
                    continue
            try:
                if mode == "spell":
                    if not self.runtime.execution.acquire(self.runtime.healer_stop, max_wait=HEALER_EXEC_MAX_WAIT, module_id="healer"):
                        if self.runtime.healer_stop.is_set():
                            break
                        cooldown_until = time.monotonic() + HEALER_COOLDOWN_AFTER_TAP
                        continue
                    try:
                        router.tap_key(spell_key_name.lower(), hold_seconds=HEALER_CAST_HOLD_SECONDS)
                    finally:
                        self.runtime.execution.release()
                    cooldown_until = time.monotonic() + HEALER_COOLDOWN_LONG
                    self.runtime.ui.log(f"❤️ Spell heal ({spell_key_name.upper()}) at HP {hp_value}")
                else:
                    if not self.runtime.mouse.acquire(self.runtime.healer_stop, max_wait=HEALER_MOUSE_MAX_WAIT, module_id="healer"):
                        if self.runtime.healer_stop.is_set():
                            break
                        cooldown_until = time.monotonic() + HEALER_COOLDOWN_AFTER_MOUSE
                        continue
                    try:
                        dur = max(HEALER_MIN_MOVE_DURATION, HEALER_MOVE_BASE_DURATION / max(mouse_speed, 0.2))
                        router.human_move_and_click(rune_pos[0], rune_pos[1], "right", duration=dur)
                        time.sleep(HEALER_POST_ACTION_SLEEP)
                        if not self.runtime.pause.wait_interruptible(rune_delay_ms / 1000.0, self.runtime.healer_stop):
                            break
                        router.human_move_and_click(character_pos[0], character_pos[1], "left", duration=dur)
                        time.sleep(HEALER_POST_ACTION_SLEEP)
                    finally:
                        self.runtime.mouse.release()
                    cooldown_until = time.monotonic() + max(HEALER_MAX_COOLDOWN_BASE, rune_delay_ms / 1000.0 + 0.15)
                    self.runtime.ui.log(f"❤️ Rune heal at HP {hp_value}")
                with self.runtime.record_lock:
                    state.stats["heals"] += 1
                self.runtime.ui.refresh_stats()
            except Exception as exc:
                self.runtime.ui.log(f"❌ Auto healer: {exc}")
                break
        state.healer_active = False
        self.runtime.ui.module_state_changed("healer", False)
        self.runtime.ui.log("⏹ Auto healer end")
