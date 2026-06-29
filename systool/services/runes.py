"""Rune-making automation service."""

from __future__ import annotations

import logging
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime
from ..constants import (
    INPUT_HOLD_DELAY_MAX,
    INPUT_MOUSE_DURATION_MAX,
    INPUT_PRESS_DELAY_MAX,
    INPUT_SETTLE_DELAY_MAX,
    RUNE_POST_CAST_SETTLE,
    RUNE_QUEUE_WINDOW_BASE,
    RUNE_QUEUE_WINDOW_BUFFER,
    RUNE_SPELL_HOLD_SECONDS,
    RUNE_WAIT_INTERRUPTIBLE,
)
from ..theme import GREEN, ORANGE, RED
from .input_services import HumanMouse


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
        self.runtime.ui.set_status("Rune session running...", GREEN)

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
        router = self.runtime.input_router

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
                current_mana = None
                if self.runtime.mp_service is not None:
                    try:
                        current_mana = self.runtime.mp_service.get_mp()
                    except Exception:
                        logger.debug("MP read failed in rune loop")
                if current_mana is None:
                    current_mana = state.char_status_mana
                blank_rune_limit = state.rune_available_blank_runes
                post_cast_settle_ms = state.rune_post_cast_settle_ms
            if blank_rune_limit > 0 and cycles_completed >= blank_rune_limit:
                self.runtime.ui.log(f"⏲️ Rune session stopped — avb blank runes limit reached ({blank_rune_limit})")
                self.runtime.ui.set_status("Rune session finished by avb blank runes limit", ORANGE)
                break
            if min_mana > 0 and current_mana is not None:
                threshold = random.randint(min_mana, max_mana) if max_mana > min_mana else min_mana
                if current_mana < threshold:
                    if not self.runtime.pause.wait_interruptible(RUNE_WAIT_INTERRUPTIBLE, self.runtime.rune_stop):
                        break
                    continue
            queue_window = max(
                RUNE_QUEUE_WINDOW_BASE,
                cast_delay_ms / 1000.0
                + (INPUT_MOUSE_DURATION_MAX * 2)
                + (INPUT_PRESS_DELAY_MAX * 2)
                + (INPUT_HOLD_DELAY_MAX * 2)
                + (INPUT_SETTLE_DELAY_MAX * 2)
                + post_cast_settle_ms / 1000.0
                + RUNE_QUEUE_WINDOW_BUFFER,
            )
            if not self.runtime.execution.acquire(self.runtime.rune_stop, max_wait=queue_window, module_id="rune"):
                if self.runtime.rune_stop.is_set():
                    break
                if not self.runtime.pause.wait_interruptible(RUNE_POST_CAST_SETTLE, self.runtime.rune_stop):
                    break
                continue
            try:
                router.tap_key(state.rune_spell_key, hold_seconds=RUNE_SPELL_HOLD_SECONDS)
                self.runtime.ui.log(f"✨ Spell cast ({state.rune_spell_key.upper()})")
                if not self.runtime.pause.wait_interruptible(cast_delay_ms / 1000.0, self.runtime.rune_stop):
                    break

                hand_pos = HumanMouse.jitter(hand, jitter)
                storage_pos = HumanMouse.jitter(storage, jitter)
                router.human_move_and_click(hand_pos[0], hand_pos[1], "left")
                router.human_move_and_click(storage_pos[0], storage_pos[1], "left")
                self.runtime.ui.log("📦 Rune moved → storage")
                blank_pos = HumanMouse.jitter(blank, jitter)
                hand_pos2 = HumanMouse.jitter(hand, jitter)
                router.human_move_and_click(blank_pos[0], blank_pos[1], "left")
                router.human_move_and_click(hand_pos2[0], hand_pos2[1], "left")
                self.runtime.ui.log("📥 Blank rune → hand slot")
                time.sleep(post_cast_settle_ms / 1000.0)
            except Exception as exc:
                self.runtime.ui.log(f"❌ Rune cycle: {exc}")
                break
            finally:
                self.runtime.execution.release()
            with self.runtime.record_lock:
                state.stats["runes_made"] += 1
            cycles_completed += 1
            self.runtime.ui.refresh_stats()
            wait_s = random.randint(
                max(0, cycle_delay_ms - cycle_variation_ms),
                max(0, cycle_delay_ms + cycle_variation_ms),
            ) / 1000.0
            self.runtime.ui.log(f"⏳ Waiting {wait_s:.1f}s before next cast...")
            if not self.runtime.pause.wait_interruptible(wait_s, self.runtime.rune_stop):
                break
        state.rune_active = False
        self.runtime.ui.module_state_changed("rune", False)
        self.runtime.ui.log(f"⏹ Rune session stopped — {state.stats['runes_made']} runes moved")
