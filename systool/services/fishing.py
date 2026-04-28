"""Fishing automation service."""

from __future__ import annotations

import logging
import math
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime, HAS_PYNPUT, pynput_mouse
from ..constants import FISHING_BONUS_MULTIPLIER, FISHING_MIN_BONUS_SECS, FISHING_CHUNK_MIN, FISHING_CYCLE_WINDOW_BASE, FISHING_CYCLE_WINDOW_ADDITION, FISHING_PAUSE_SHORT_MIN, FISHING_PAUSE_SHORT_MAX, FISHING_PAUSE_MEDIUM_MIN, FISHING_PAUSE_MEDIUM_MAX
from ..theme import GREEN, ORANGE, RED
from .input_services import HumanMouse

class FishingService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.fish_active:
            return
        if state.fish_rod_pos == (0, 0):
            self.runtime.ui.log("❌ Record rod position first")
            self.runtime.ui.set_status("Record rod position first", ORANGE)
            return
        if not state.fish_spots:
            self.runtime.ui.log("❌ Record at least one spot")
            self.runtime.ui.set_status("Record at least one fishing spot", ORANGE)
            return
        if state.fish_min_cap > 0:
            # Use pointer-based Cap first, fall back to OCR
            fish_cap = None
            if self.runtime.cap_service is not None:
                try:
                    fish_cap = self.runtime.cap_service.get_cap()
                except Exception:
                    logger.debug("Cap read failed in fishing start")
            if fish_cap is None:
                with self.runtime.settings_lock:
                    fish_cap = state.char_status_cap
            if fish_cap is not None and fish_cap <= state.fish_min_cap:
                self.runtime.ui.log("⚠️  Capacity is already at or below the fishing stop threshold")
                self.runtime.ui.set_status("Capacity too low to start fishing", ORANGE)
                return
        self.runtime.fish_stop.clear()
        
        # Calculate random bonus time scaled by user configuration (up to 15 minutes at 60min mark)
        max_bonus_mins = max(1.0, FISHING_BONUS_MULTIPLIER * (state.fish_session_minutes / 60.0))
        bonus_secs = random.randint(FISHING_MIN_BONUS_SECS, max(60, int(max_bonus_mins * 60)))
        total_seconds = max(1, state.fish_session_minutes * 60) + bonus_secs
        
        state.fish_session_remaining_secs = total_seconds
        state.fish_session_deadline = time.monotonic() + total_seconds
        state.fish_active = True
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("fish", True)
        
        self.runtime.ui.set_status(
            f"Fishing session running ({state.fish_session_minutes} min + {bonus_secs//60} min random bonus)",
            GREEN,
        )
        self.runtime.ui.log(f"🎣 Session setup: {state.fish_session_minutes} min base + {bonus_secs//60}m {bonus_secs%60}s randomized padding")

    def stop(self) -> None:
        state = self.runtime.state
        if not state.fish_active:
            return
        self.runtime.fish_stop.set()
        state.fish_active = False
        state.fish_session_remaining_secs = 0
        state.fish_session_deadline = None
        self.runtime.ui.module_state_changed("fish", False)
        self.runtime.ui.set_status("Fishing session stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(f"▶ Fishing start — rod={state.fish_rod_pos}  spots={len(state.fish_spots)}")
        stopped_by_food = False
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.fish_active = False
            state.fish_session_remaining_secs = 0
            state.fish_session_deadline = None
            self.runtime.ui.module_state_changed("fish", False)
            return
        mouse = pynput_mouse.Controller()
        deck = list(state.fish_spots)
        random.shuffle(deck)
        index = 0
        session_deadline = state.fish_session_deadline or (time.monotonic() + max(1, state.fish_session_remaining_secs))

        def update_remaining() -> bool:
            remaining = max(0, int(math.ceil(session_deadline - time.monotonic())))
            state.fish_session_remaining_secs = remaining
            return remaining > 0

        def wait_with_session_limit(seconds: float) -> bool:
            while seconds > 0:
                if not update_remaining():
                    return False
                chunk = min(seconds, FISHING_CHUNK_MIN, max(0.0, session_deadline - time.monotonic()))
                if chunk <= 0:
                    return False
                if not self.runtime.pause.wait_interruptible(chunk, self.runtime.fish_stop):
                    return False
                seconds -= chunk
            return update_remaining()

        while not self.runtime.fish_stop.is_set():
            if not update_remaining():
                self.runtime.ui.log("⏲️ Fishing session complete")
                self.runtime.ui.set_status("Fishing session finished", ORANGE)
                self.runtime.fish_stop.set()
                break
            self.runtime.pause.wait()
            with self.runtime.settings_lock:
                rod = state.fish_rod_pos
                rod_jitter = state.fish_rod_jitter
                spot_jitter = state.fish_spot_jitter
                cast_min = state.fish_cast_min_ms
                cast_max = state.fish_cast_max_ms
                wait_min = state.fish_wait_min_ms
                wait_max = state.fish_wait_max_ms
                min_cap = state.fish_min_cap
                food_seconds = state.char_status_food_seconds
                auto_restart_enabled = state.fish_auto_restart_enabled
                auto_restart_food_min_secs = state.fish_auto_restart_food_min_secs
                # Use pointer-based Cap first, fall back to OCR
                current_cap = None
                if self.runtime.cap_service is not None:
                    try:
                        current_cap = self.runtime.cap_service.get_cap()
                    except Exception:
                        logger.debug("Cap read failed during fishing loop")
                if current_cap is None:
                    current_cap = state.char_status_cap
            if min_cap > 0 and current_cap is not None and current_cap <= min_cap:
                self.runtime.ui.log(f"📦 Fishing stopped — capacity {current_cap} is at/below limit {min_cap}")
                self.runtime.ui.set_status("Fishing stopped by capacity threshold", ORANGE)
                self.runtime.fish_stop.set()
                break
            # Check food level for auto-restart (only stop if no other session is running)
            if not auto_restart_enabled:
                self.runtime.ui.log("⚠️  Food check skipped — auto-restart disabled")
            elif food_seconds is None:
                self.runtime.ui.log("⚠️  Food check skipped — food value not available (ensure Character Status OCR is running)")
            else:
                self.runtime.ui.log(f"🍖 Food check: {food_seconds}s / threshold {auto_restart_food_min_secs}s")
            if (
                auto_restart_enabled
                and food_seconds is not None
                and food_seconds <= auto_restart_food_min_secs
            ):
                self.runtime.ui.log(f"🍖 Food running low ({food_seconds}s) — stopping session to eat")
                self.runtime.ui.set_status("Food low — stopping fishing to eat", ORANGE)
                self.runtime.fish_stop.set()
                stopped_by_food = True
                break
            cycle_locked = False
            try:
                cycle_window = max(FISHING_CYCLE_WINDOW_BASE, max(cast_max, 0) / 1000.0 + FISHING_CYCLE_WINDOW_ADDITION)
                cycle_locked = self.runtime.mouse.acquire(
                    self.runtime.fish_stop,
                    max_wait=cycle_window,
                    module_id="fishing",
                )
                if not cycle_locked:
                    if self.runtime.fish_stop.is_set():
                        break
                    continue
                rod_target = HumanMouse.jitter(rod, rod_jitter)
                HumanMouse.move(mouse, rod_target)
                time.sleep(random.uniform(FISHING_PAUSE_SHORT_MIN, FISHING_PAUSE_SHORT_MAX))
                mouse.click(pynput_mouse.Button.right, 1)
                self.runtime.ui.log(f"🎣 Rod clicked at {rod_target}")
                if index >= len(deck):
                    deck = list(state.fish_spots)
                    random.shuffle(deck)
                    index = 0
                spot_target = HumanMouse.jitter(deck[index], spot_jitter)
                index += 1
                HumanMouse.move(mouse, spot_target)
                time.sleep(random.uniform(FISHING_PAUSE_MEDIUM_MIN, FISHING_PAUSE_MEDIUM_MAX))
                mouse.click(pynput_mouse.Button.left, 1)
                with self.runtime.record_lock:
                    state.stats["fish_casts"] += 1
                self.runtime.ui.log(f"🪣 Cast → {spot_target}")
                self.runtime.ui.refresh_stats()
            except Exception as exc:
                self.runtime.ui.log(f"❌ Fish cycle: {exc}")
                self.runtime.fish_stop.set()
                break
            finally:
                if cycle_locked:
                    self.runtime.mouse.release()
            if not update_remaining():
                self.runtime.ui.log("⏲️ Fishing session complete")
                self.runtime.ui.set_status("Fishing session finished", ORANGE)
                self.runtime.fish_stop.set()
                break
            if not wait_with_session_limit(random.randint(wait_min, wait_max) / 1000.0):
                break
        state.fish_active = False
        self.runtime.ui.module_state_changed("fish", False)
        if self.runtime.fish_stop.is_set():
            state.fish_session_remaining_secs = 0
            state.fish_session_deadline = None
        # Check if we stopped due to low food and auto-restart is enabled
        with self.runtime.settings_lock:
            food_seconds = state.char_status_food_seconds
            auto_restart_enabled = state.fish_auto_restart_enabled
            auto_restart_food_min_secs = state.fish_auto_restart_food_min_secs
        if (
            stopped_by_food
            and auto_restart_enabled
            and food_seconds is not None
            and food_seconds <= auto_restart_food_min_secs
        ):
            self.runtime.ui.log(
                f"🔄 Auto-restart triggered — waiting 1s for cleanup, then starting fresh session"
            )
            time.sleep(1.0)
            self.start()
        else:
            self.runtime.ui.log(f"⏹ Fishing stopped — {state.stats['fish_casts']} casts")
