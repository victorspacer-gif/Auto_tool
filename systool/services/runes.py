"""Rune-making automation service."""

from __future__ import annotations

import random
import threading
import time

from ..runtime import AppRuntime, HAS_PYNPUT, pynput_kb, pynput_mouse
from ..theme import GREEN, ORANGE, RED
from .hotkeys import HotkeyService
from .input_services import HumanMouse, SafeKeyboardSession

class RuneMakerService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.rune_active:
            return
        if any(position == (0, 0) for position in [state.rune_hand_pos, state.rune_storage_pos, state.rune_blank_pos]):
            self.runtime.ui.log("⚠️  Record all 3 positions before starting")
            self.runtime.ui.set_status("Record all 3 rune positions first", ORANGE)
            return
        self.runtime.rune_stop.clear()
        state.rune_active = True
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("rune", True)
        self.runtime.ui.set_status("Rune session running…", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.rune_active:
            return
        self.runtime.rune_stop.set()
        state.rune_active = False
        self.runtime.ui.module_state_changed("rune", False)
        self.runtime.ui.set_status("Rune session stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(
            f"▶ Rune session start — spell={state.rune_spell_key.upper()}  "
            f"cycle={state.rune_cycle_delay_ms}ms  post-settle={state.rune_post_cast_settle_ms}ms"
        )
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.rune_active = False
            self.runtime.ui.module_state_changed("rune", False)
            return
        keyboard = pynput_kb.Controller()
        mouse = pynput_mouse.Controller()
        spell = HotkeyService.key_str_to_pynput(state.rune_spell_key)
        if not spell:
            self.runtime.ui.log(f"❌ Unknown spell key: {state.rune_spell_key}")
            state.rune_active = False
            self.runtime.ui.module_state_changed("rune", False)
            return

        cycles_completed = 0
        while not self.runtime.rune_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.rune_stop.is_set():
                break
            with self.runtime.settings_lock:
                hand = state.rune_hand_pos
                storage = state.rune_storage_pos
                blank = state.rune_blank_pos
                jitter = state.rune_jitter
                cast_delay_ms = state.rune_cast_delay_ms
                cycle_delay_ms = state.rune_cycle_delay_ms
                cycle_variation_ms = state.rune_cycle_delay_variation_ms
                min_mana = state.rune_min_mana
                max_mana = state.rune_max_mana
                # Use pointer-based MP first, fall back to OCR
                current_mana = None
                if self.runtime.mp_service is not None:
                    try:
                        current_mana = self.runtime.mp_service.get_mp()
                    except Exception:
                        pass
                if current_mana is None:
                    current_mana = state.char_status_mana
                blank_rune_limit = state.rune_available_blank_runes
                move_min_ms = state.rune_mouse_move_min_ms
                move_max_ms = state.rune_mouse_move_max_ms
                press_min_ms = state.rune_mouse_press_min_ms
                press_max_ms = state.rune_mouse_press_max_ms
                settle_min_ms = state.rune_mouse_settle_min_ms
                settle_max_ms = state.rune_mouse_settle_max_ms
                post_cast_settle_ms = state.rune_post_cast_settle_ms
            if blank_rune_limit > 0 and cycles_completed >= blank_rune_limit:
                self.runtime.ui.log(f"⏲️ Rune session stopped — avb blank runes limit reached ({blank_rune_limit})")
                self.runtime.ui.set_status("Rune session finished by avb blank runes limit", ORANGE)
                break
            if min_mana > 0 and current_mana is not None:
                # Pick a random threshold between min and max (if max set), otherwise use min
                threshold = random.randint(min_mana, max_mana) if max_mana > min_mana else min_mana
                if current_mana < threshold:
                    if not self.runtime.pause.wait_interruptible(1.0, self.runtime.rune_stop):
                        break
                    continue
            queue_window = max(
                0.90,
                cast_delay_ms / 1000.0
                + (move_max_ms * 2 + press_max_ms * 2 + settle_max_ms * 2) / 1000.0
                + post_cast_settle_ms / 1000.0
                + 0.40,
            )
            if not self.runtime.execution.acquire(self.runtime.rune_stop, max_wait=queue_window, module_id="rune"):
                if self.runtime.rune_stop.is_set():
                    break
                if not self.runtime.pause.wait_interruptible(0.15, self.runtime.rune_stop):
                    break
                continue
            session = SafeKeyboardSession(keyboard)
            try:
                session.tap(spell, hold_seconds=0.04)
                self.runtime.ui.log(f"✨ Spell cast ({state.rune_spell_key.upper()})")
                if not self.runtime.pause.wait_interruptible(cast_delay_ms / 1000.0, self.runtime.rune_stop):
                    break

                move_duration = random.uniform(move_min_ms, move_max_ms) / 1000.0
                press_delay_range = (press_min_ms / 1000.0, press_max_ms / 1000.0)
                settle_delay_range = (settle_min_ms / 1000.0, settle_max_ms / 1000.0)

                HumanMouse.drag(
                    mouse,
                    HumanMouse.jitter(hand, jitter),
                    HumanMouse.jitter(storage, jitter),
                    move_duration=move_duration,
                    press_delay_range=press_delay_range,
                    hold_delay_range=press_delay_range,
                    settle_delay_range=settle_delay_range,
                )
                self.runtime.ui.log("📦 Rune moved → storage")
                time.sleep(random.uniform(*settle_delay_range))
                HumanMouse.drag(
                    mouse,
                    HumanMouse.jitter(blank, jitter),
                    HumanMouse.jitter(hand, jitter),
                    move_duration=random.uniform(move_min_ms, move_max_ms) / 1000.0,
                    press_delay_range=press_delay_range,
                    hold_delay_range=press_delay_range,
                    settle_delay_range=settle_delay_range,
                )
                self.runtime.ui.log("📥 Blank rune → hand slot")
                # Settle before next cast — lets mana deplete and OCR catch up
                time.sleep(post_cast_settle_ms / 1000.0)
            except Exception as exc:
                self.runtime.ui.log(f"❌ Rune cycle: {exc}")
                break
            finally:
                session.release_all()
                self.runtime.execution.release()
            with self.runtime.record_lock:
                state.stats["runes_made"] += 1
            cycles_completed += 1
            self.runtime.ui.refresh_stats()
            wait_s = random.randint(
                max(0, cycle_delay_ms - cycle_variation_ms),
                max(0, cycle_delay_ms + cycle_variation_ms),
            ) / 1000.0
            self.runtime.ui.log(f"⏳ Waiting {wait_s:.1f}s before next cast…")
            if not self.runtime.pause.wait_interruptible(wait_s, self.runtime.rune_stop):
                break
        state.rune_active = False
        self.runtime.ui.module_state_changed("rune", False)
        self.runtime.ui.log(f"⏹ Rune session stopped — {state.stats['runes_made']} runes moved")
