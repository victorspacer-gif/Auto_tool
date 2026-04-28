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
    HEALER_MOUSE_MAX_WAIT,
)
from ..theme import GREEN, ORANGE, RED
from .hotkeys import HotkeyService
from .input_services import HumanMouse, SafeKeyboardSession

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
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.healer_active = False
            self.runtime.ui.module_state_changed("healer", False)
            return
        keyboard = pynput_kb.Controller()
        mouse = pynput_mouse.Controller()
        cooldown_until = 0.0
        while not self.runtime.healer_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.healer_stop.is_set():
                break
            now = time.monotonic()
            if now < cooldown_until:
                if not self.runtime.pause.wait_interruptible(min(0.1, cooldown_until - now), self.runtime.healer_stop):
                    break
                continue
            with self.runtime.settings_lock:
                hp_peak = state.char_status_hp_peak
                # Use pointer-based MP first, fall back to OCR
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
            # Try pointer-based HP first, fall back to OCR
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
                # Pick a random threshold between min and max (if max set), otherwise use min
                threshold = random.randint(min_mana, max_mana) if max_mana > min_mana else min_mana
                if mana_value < threshold:
                    if not self.runtime.pause.wait_interruptible(HEALER_WAIT_INTERRUPTIBLE_3, self.runtime.healer_stop):
                        break
                    continue
            try:
                if mode == "spell":
                    spell_key = HotkeyService.key_str_to_pynput(spell_key_name)
                    if not spell_key:
                        self.runtime.ui.log(f"❌ Unknown healer spell key: {spell_key_name}")
                        break
                    if not self.runtime.execution.acquire(self.runtime.healer_stop, max_wait=HEALER_EXEC_MAX_WAIT, module_id="healer"):
                        if self.runtime.healer_stop.is_set():
                            break
                        cooldown_until = time.monotonic() + 0.05
                        continue
                    session = SafeKeyboardSession(keyboard)
                    try:
                        session.tap(spell_key, hold_seconds=0.03)
                    finally:
                        session.release_all()
                        self.runtime.execution.release()
                    cooldown_until = time.monotonic() + 0.35
                    self.runtime.ui.log(f"❤️ Spell heal ({spell_key_name.upper()}) at HP {hp_value}")
                else:
                    if not self.runtime.mouse.acquire(self.runtime.healer_stop, max_wait=HEALER_MOUSE_MAX_WAIT, module_id="healer"):
                        if self.runtime.healer_stop.is_set():
                            break
                        cooldown_until = time.monotonic() + 0.08
                        continue
                    try:
                        HumanMouse.move(mouse, rune_pos, duration=max(0.05, 0.20 / max(mouse_speed, 0.2)))
                        time.sleep(0.04)
                        mouse.click(pynput_mouse.Button.right, 1)
                        if not self.runtime.pause.wait_interruptible(rune_delay_ms / 1000.0, self.runtime.healer_stop):
                            break
                        HumanMouse.move(mouse, character_pos, duration=max(0.05, 0.20 / max(mouse_speed, 0.2)))
                        time.sleep(0.04)
                        mouse.click(pynput_mouse.Button.left, 1)
                    finally:
                        self.runtime.mouse.release()
                    cooldown_until = time.monotonic() + max(0.45, rune_delay_ms / 1000.0 + 0.15)
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
