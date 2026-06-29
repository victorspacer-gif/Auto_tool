"""Input-oriented infrastructure and services."""

from __future__ import annotations

import logging
import math
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime, HAS_PYNPUT, HAS_WIN32, pynput_kb, pynput_mouse, win32con, win32gui
from ..constants import (
    AFK_EXEC_MAX_WAIT,
    RCCLICK_INTER_CLICK_MIN,
    RCCLICK_INTER_CLICK_JITTER,
    RCCLICK_WAIT_INTERRUPTIBLE,
    RCCLICK_QUEUE_WINDOW_MIN,
    EXEC_WAIT_TIMEOUT_DEFAULT,
    INPUT_MOUSE_DURATION_MIN,
    INPUT_MOUSE_DURATION_MAX,
    INPUT_MOUSE_SPEED_DIVISOR_MIN,
    INPUT_MOUSE_SPEED_DIVISOR_MAX,
    INPUT_CONTROL_SCALE_RANGE,
    INPUT_FAKE_JITTER_RANGE,
    INPUT_PRESS_DELAY_MIN,
    INPUT_PRESS_DELAY_MAX,
    INPUT_HOLD_DELAY_MIN,
    INPUT_HOLD_DELAY_MAX,
    INPUT_SETTLE_DELAY_MIN,
    INPUT_SETTLE_DELAY_MAX,
    INPUT_POST_CLICK_SLEEP,
    INPUT_RCCLICK_PAUSE_1,
    INPUT_RCCLICK_PAUSE_2,
    INPUT_RCCLICK_PAUSE_3,
    INPUT_RCCLICK_MAX_WAIT,
    INPUT_QUEUE_WINDOW,
    RIGHT_CLICK_FOOD_BURST_COOLDOWN,
    RCCLICK_FOOD_COOLDOWN_SECONDS,
    AFK_CTRL_HOLD_MIN,
    AFK_CTRL_HOLD_MAX,
    AFK_DIR_PRESS_MIN,
    AFK_DIR_PRESS_MAX,
    AFK_DIR_RELEASE_MIN,
    AFK_DIR_RELEASE_MAX,
)
from ..theme import GREEN, ORANGE, RED


# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------

def _curve_move(
    mouse,
    start: tuple[int, int],
    end: tuple[int, int],
    duration: float,
    *,
    noise_scale: float = 1.0,
    smooth: bool = False,
    control_scale_override: float | None = None,
    easing_mode: str = "ballistic",
    settle_mode: bool = False,
) -> None:
    """Execute a single Bézier-curve mouse movement from *start* to *end*.

    Reuses the original quadratic-Bézier math with easing and fading jitter.

    Parameters
    ----------
    noise_scale : float
        Scales jitter intensity (1.0 = original, < 1.0 = smoother).
    smooth : bool
        When True, reduces control-point randomness and noise for a cleaner arc.
    control_scale_override : float | None
        If given, overrides the random control-scale selection.
    easing_mode : str
        "ballistic" → original cubic ease-out (t²·(3−2t))
        "correction" → quadratic ease-in (t²) for slower, deliberate motion
    settle_mode : bool
        When True, applies extra jitter suppression throughout the entire move.
        Uses a steeper fade curve so even the first steps are near-silent —
        prevents the "heavy wiggle before clicking" look on final approach.
    """
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    distance = math.hypot(dx, dy)

    # Skip movement if target is within 1px — no-op threshold
    if distance < 1:
        mouse.position = (int(ex), int(ey))
        return

    # Minimum 10 steps for smooth curves; ~1 step per 7px for reasonable pacing
    steps = max(10, int(distance / 7))
    step_duration = duration / steps

    # Control point — perpendicular offset from midpoint
    if settle_mode:
        # Final settling should not arc past the cursor axis or introduce any
        # last-moment wobble before clicking.
        raw_scale = 0.0
    elif smooth:
        # Reduced randomness for smoother curves (scale to 45% of full range)
        raw_scale = random.uniform(*INPUT_CONTROL_SCALE_RANGE) * 0.45
    else:
        raw_scale = (
            control_scale_override
            if control_scale_override is not None
            else random.uniform(*INPUT_CONTROL_SCALE_RANGE)
        )

    cx = (sx + ex) / 2 + (-dy / distance) * raw_scale
    cy = (sy + ey) / 2 + (dx / distance) * raw_scale

    # Easing function selection
    if easing_mode == "correction":
        # Quadratic ease-in: slower start, builds up speed
        def _easing(t):
            return t * t
    else:
        # Original cubic ease-out (t²·(3−2t)) — polynomial coefficients for smooth accel/decel
        def _easing(t):
            return t * t * (3.0 - 2.0 * t)

    for index in range(steps):
        t_value = index / steps
        eased = _easing(t_value)

        x_pos = (1 - eased) ** 2 * sx + 2 * (1 - eased) * eased * cx + eased**2 * ex
        y_pos = (1 - eased) ** 2 * sy + 2 * (1 - eased) * eased * cy + eased**2 * ey

        # Fading jitter — less noise near the end of movement.
        # In settle_mode, use a quadratic fade so even early steps are near-silent;
        # this prevents the "heavy wiggle before clicking" look on final approach.
        if settle_mode:
            fade = 0.0
        else:
            fade = 1.0 - t_value
        x_pos += random.uniform(*INPUT_FAKE_JITTER_RANGE) * fade * noise_scale
        y_pos += random.uniform(*INPUT_FAKE_JITTER_RANGE) * fade * noise_scale

        mouse.position = (int(x_pos), int(y_pos))
        time.sleep(step_duration)

    # Always finish on the exact target pixel. The loop above stops short of
    # t=1.0, which can otherwise leave a visible 1px correction at click time.
    mouse.position = (int(ex), int(ey))


def _apply_target_error(
    sx: float, sy: float, ex: float, ey: float, distance: float
) -> tuple[float, float, str]:
    """Decide whether to introduce overshoot / undershoot on the target.

    Returns (tx, ty, error_type) where *error_type* is one of:
        "none", "overshoot", "undershoot"

    Short distances (< 50 px) are strongly biased toward no error so that
    tiny movements remain clean and direct.
    """
    # Bias toward "none" for short distances (< 50px threshold)
    if distance < 50:
        # none_chance ramps from 0.7 (at 0px) to 0.84 (at 50px), capped at 0.92 max
        none_chance = min(0.92, 0.7 + (distance / 50) * 0.14)
    else:
        # Base no-error probability for distances >= 50px is 60%
        none_chance = 0.6

    roll = random.random()
    if roll < none_chance:
        return (ex, ey, "none")

    # Split the remaining error cases between overshoot and undershoot while
    # preserving the distance-based bias toward "none".
    error_roll = (roll - none_chance) / max(1e-9, 1.0 - none_chance)

    if error_roll < (10.0 / 18.0):
        # Overshoot: ~10% probability (roll threshold) — factor starts at 1.01, scales +0.03 per 500px distance
        factor = 1.01 + (distance / 500) * 0.03  # capped ~1.04 max overshoot
        tx = sx + (ex - sx) * factor
        ty = sy + (ey - sy) * factor
        return (tx, ty, "overshoot")

    if error_roll <= 1.0:
        # Undershoot: ~8% exclusive probability (cumulative threshold at 18%) — factor ~0.96–0.98
        factor = 0.96 + random.random() * 0.02  # base 0.96, random up to +0.02
        tx = sx + (ex - sx) * factor
        ty = sy + (ey - sy) * factor
        return (tx, ty, "undershoot")

    # Safety fallback if floating-point drift nudges us outside the expected range.
    return (ex, ey, "none")


# ---------------------------------------------------------------------------
# Public API — HumanMouse
# ---------------------------------------------------------------------------

class HumanMouse:
    @staticmethod
    def jitter(pos: tuple[int, int], amount: int) -> tuple[int, int]:
        return (
            pos[0] + random.randint(-amount, amount),
            pos[1] + random.randint(-amount, amount),
        )

    @staticmethod
    def move(
        mouse,
        target: tuple[int, int],
        duration: float | None = None,
        *,
        target_error_enabled: bool = False,
    ) -> None:
        sx, sy = mouse.position
        ex, ey = target
        dx, dy = ex - sx, ey - sy
        distance = math.hypot(dx, dy)

        if distance < 1:
            mouse.position = (int(ex), int(ey))
            return

        # --- Phase 0: Optional reaction delay (20-120 ms human response time) ---
        time.sleep(random.uniform(0.020, 0.120))  # 20ms min to 120ms max reaction delay

        if duration is None:
            duration = max(
                INPUT_MOUSE_DURATION_MIN,
                min(
                    INPUT_MOUSE_DURATION_MAX,
                    distance / random.uniform(INPUT_MOUSE_SPEED_DIVISOR_MIN, INPUT_MOUSE_SPEED_DIVISOR_MAX),
                ),
            )

        # --- Phase 1: Ballistic movement with optional target error ---
        if target_error_enabled:
            err_ex, err_ey, error_type = _apply_target_error(sx, sy, ex, ey, distance)
        else:
            err_ex, err_ey, error_type = ex, ey, "none"

        ballistic_duration = duration * random.uniform(0.75, 0.90)
        _curve_move(
            mouse,
            start=(sx, sy),
            end=(int(err_ex), int(err_ey)),
            duration=ballistic_duration,
            noise_scale=1.0,
            smooth=False,
            easing_mode="ballistic",
        )

        # --- Phase 2: Correction phase (only if error was introduced) ---
        if error_type != "none":
            correction_budget = duration * random.uniform(0.30, 0.50)
            cur_x, cur_y = mouse.position
            corr_dist = math.hypot(ex - cur_x, ey - cur_y)
            if corr_dist >= 1:
                # Use one deliberate correction so we do not stack multiple
                # random micro-adjustments before the final settle phase.
                corr_dur = max(0.06, correction_budget * random.uniform(0.65, 0.85))
                _curve_move(
                    mouse,
                    start=(cur_x, cur_y),
                    end=(int(ex), int(ey)),
                    duration=corr_dur,
                    noise_scale=random.uniform(0.06, 0.14),
                    smooth=True,
                    easing_mode="correction",
                    settle_mode=True,
                )

        # --- Smooth settle to true target (no hard snap) ---
        cur_x, cur_y = mouse.position
        settle_dist = math.hypot(ex - cur_x, ey - cur_y)
        if settle_dist < 1:
            return

        settle_duration = max(0.04, duration * random.uniform(0.08, 0.15))
        _curve_move(
            mouse,
            start=(cur_x, cur_y),
            end=(int(ex), int(ey)),
            duration=settle_duration,
            noise_scale=random.uniform(0.02, 0.05),
            smooth=True,
            settle_mode=True,
        )

    @staticmethod
    def drag(
        mouse,
        source: tuple[int, int],
        dest: tuple[int, int],
        *,
        move_duration: float | None = None,
        target_error_enabled: bool = False,
        press_delay_range: tuple[float, float] = (INPUT_PRESS_DELAY_MIN, INPUT_PRESS_DELAY_MAX),
        hold_delay_range: tuple[float, float] = (INPUT_HOLD_DELAY_MIN, INPUT_HOLD_DELAY_MAX),
        settle_delay_range: tuple[float, float] = (INPUT_SETTLE_DELAY_MIN, INPUT_SETTLE_DELAY_MAX),
    ) -> None:
        HumanMouse.move(
            mouse,
            source,
            duration=move_duration,
            target_error_enabled=target_error_enabled,
        )
        time.sleep(random.uniform(*press_delay_range))
        mouse.press(pynput_mouse.Button.left)
        time.sleep(random.uniform(*hold_delay_range))
        HumanMouse.move(
            mouse,
            dest,
            duration=move_duration,
            target_error_enabled=target_error_enabled,
        )
        time.sleep(random.uniform(*settle_delay_range))
        mouse.release(pynput_mouse.Button.left)

class SafeKeyboardSession:
    """Tracks pressed keys and guarantees they are released in reverse order."""

    def __init__(self, keyboard) -> None:
        self.keyboard = keyboard
        self._pressed: list[object] = []

    def tap(self, key, hold_seconds: float = 0.03) -> None:
        self.press(key)
        time.sleep(max(0.0, hold_seconds))
        self.release(key)

    def press(self, key) -> None:
        self.keyboard.press(key)
        self._pressed.append(key)

    def release(self, key) -> None:
        self.keyboard.release(key)
        for index in range(len(self._pressed) - 1, -1, -1):
            if self._pressed[index] == key:
                del self._pressed[index]
                break

    def release_all(self) -> None:
        while self._pressed:
            key = self._pressed.pop()
            try:
                self.keyboard.release(key)
            except Exception:
                logger.debug("Keyboard release failed")

class WindowService:
    @staticmethod
    def get_foreground_hwnd():
        if not HAS_WIN32:
            return None
        try:
            return win32gui.GetForegroundWindow()
        except Exception:
            return None

    @staticmethod
    def focus_window_by_name(name_fragment: str) -> bool:
        if not HAS_WIN32:
            return False
        found = [None]

        def callback(hwnd, _):
            if found[0]:
                return
            try:
                title = win32gui.GetWindowText(hwnd)
                if name_fragment.lower() in title.lower() and win32gui.IsWindowVisible(hwnd):
                    found[0] = hwnd
            except Exception:
                logger.debug("win32gui GetWindowText failed")

        try:
            win32gui.EnumWindows(callback, None)
            if found[0]:
                win32gui.ShowWindow(found[0], win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(found[0])
                time.sleep(INPUT_POST_CLICK_SLEEP)
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def restore(hwnd) -> None:
        if not HAS_WIN32 or not hwnd:
            return
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            logger.debug("win32gui SetForegroundWindow failed")

class AntiAfkService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.afk_active:
            return
        state.afk_active = True
        self.runtime.afk_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("afk", True)
        self.runtime.ui.set_status("Activity monitor active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.afk_active:
            return
        self.runtime.afk_stop.set()
        state.afk_active = False
        self.runtime.ui.module_state_changed("afk", False)
        self.runtime.ui.set_status("Activity monitor stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(f"▶ Activity monitor start — {state.afk_min_ms}–{state.afk_max_ms} ms")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.afk_active = False
            return
        keyboard = pynput_kb.Controller()
        directions = {
            "up": pynput_kb.Key.up,
            "down": pynput_kb.Key.down,
            "left": pynput_kb.Key.left,
            "right": pynput_kb.Key.right,
        }
        while not self.runtime.afk_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.afk_stop.is_set():
                break
            with self.runtime.settings_lock:
                min_ms = state.afk_min_ms
                max_ms = state.afk_max_ms
            if not self.runtime.pause.wait_interruptible(random.randint(min_ms, max_ms) / 1000.0, self.runtime.afk_stop):
                break
            direction_name, direction_key = random.choice(list(directions.items()))
            if not self.runtime.execution.acquire(self.runtime.afk_stop, max_wait=AFK_EXEC_MAX_WAIT, module_id="afk"):
                if self.runtime.afk_stop.is_set():
                    break
                continue
            session = SafeKeyboardSession(keyboard)
            try:
                session.press(pynput_kb.Key.ctrl)
                time.sleep(random.uniform(AFK_CTRL_HOLD_MIN, AFK_CTRL_HOLD_MAX))
                session.press(direction_key)
                time.sleep(random.uniform(AFK_DIR_PRESS_MIN, AFK_DIR_PRESS_MAX))
                session.release(direction_key)
                time.sleep(random.uniform(AFK_DIR_RELEASE_MIN, AFK_DIR_RELEASE_MAX))
            except Exception as exc:
                self.runtime.ui.log(f"❌ AFK: {exc}")
            finally:
                session.release_all()
                self.runtime.execution.release()
            with self.runtime.record_lock:
                state.stats["afk_moves"] += 1
            self.runtime.ui.log(f"🚶 AFK Ctrl+{direction_name}")
            self.runtime.ui.refresh_stats()
        state.afk_active = False
        self.runtime.ui.module_state_changed("afk", False)
        self.runtime.ui.log("⏹ Activity monitor end")

class RightClickService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.last_food_click_ts: float = 0.0  # Anti-spam timestamp for food right-clicks
        self._food_restart_threshold_seconds: int | None = None  # Hysteresis restart threshold (X - random(60–300s))

    def start(self) -> None:
        state = self.runtime.state
        if state.rclick_active:
            return
        if state.rclick_pos == (0, 0):
            self.runtime.ui.log("⚠️  Record a position first")
            self.runtime.ui.set_status("Record position first", ORANGE)
            return
        state.rclick_active = True
        self.runtime.rclick_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("rclick", True)
        self.runtime.ui.set_status("Right-click macro active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.rclick_active:
            return
        self.runtime.rclick_stop.set()
        state.rclick_active = False
        self.runtime.ui.module_state_changed("rclick", False)
        self.runtime.ui.set_status("Right-click macro stopped", RED)

    @staticmethod
    def food_timer_meets_threshold(food_seconds: int | None, threshold_minutes: int) -> bool:
        # Eat when remaining hunger time drops to or below the threshold (e.g., <= 15 min)
        return food_seconds is not None and food_seconds <= max(1, threshold_minutes) * 60

    @staticmethod
    def _format_food_timer_debug(food_seconds: int | None) -> str:
        if food_seconds is None:
            return "unavailable"
        # Time conversion constants: 3600s/hour, 60s/minute
        hours = food_seconds // 3600
        minutes = (food_seconds % 3600) // 60
        return f"{hours}:{minutes:02d}"

    @classmethod
    def _food_mode_decision(
        cls,
        food_text: str,
        food_seconds: int | None,
        threshold_minutes: int,
        restart_threshold_seconds: int | None = None,
    ) -> tuple[bool, str]:
        # Use hysteresis restart threshold when available; fall back to fixed threshold.
        effective_threshold = restart_threshold_seconds if restart_threshold_seconds is not None else max(1, threshold_minutes) * 60
        allowed = food_seconds is not None and food_seconds <= effective_threshold
        raw_value = food_text.strip() or "—"
        parsed_value = cls._format_food_timer_debug(food_seconds)
        threshold_display = f"{max(1, threshold_minutes)}:00"
        decision = "allowed" if allowed else "blocked"
        return allowed, (
            f"🍖 R-click food gate — raw='{raw_value}' parsed={parsed_value} "
            f"threshold={threshold_display}"
            + (f" restart_threshold={effective_threshold}s ({effective_threshold // 60}m)" if restart_threshold_seconds is not None else "")
            + f" decision={decision}"
        )

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Right-click macro start")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.rclick_active = False
            return
        router = self.runtime.input_router
        while not self.runtime.rclick_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.rclick_stop.is_set():
                break
            with self.runtime.settings_lock:
                min_ms = state.rclick_min_ms
                max_ms = state.rclick_max_ms
                target = state.rclick_pos
                mode = state.rclick_mode
                food_text = state.char_status_food_text
                food_seconds = state.char_status_food_seconds
                food_min_minutes = state.rclick_food_min_minutes
                burst_count_min = state.rclick_food_burst_count_min
                burst_count_max = state.rclick_food_burst_count_max
                burst_interval_ms = state.rclick_food_burst_interval_ms
                click_delay_min_ms = state.rclick_click_delay_min_ms
                click_delay_max_ms = state.rclick_click_delay_max_ms
                post_settle_ms = state.rclick_post_click_settle_ms
                rclick_jitter = state.rclick_jitter
            if mode == "food":
                allowed, debug_message = self._food_mode_decision(
                    food_text, food_seconds, food_min_minutes,
                    restart_threshold_seconds=self._food_restart_threshold_seconds,
                )
                self.runtime.ui.log(debug_message)
                if not allowed:
                    # Food timer above threshold — calculate smart sleep until food
                    # reaches the eating threshold + OCR refresh buffer instead of
                    # polling every second.  Hysteresis restart point is still
                    # generated so it's ready when we wake up and re-check.
                    fixed_threshold_seconds = max(1, food_min_minutes) * 60
                    ocr_refresh_delay: float = 20.0  # typical OCR/game update cycle
                    remaining_seconds = max(0, (food_seconds - fixed_threshold_seconds) + ocr_refresh_delay)

                    random_lower_bound = random.randint(60, 300)
                    self._food_restart_threshold_seconds = max(1, food_min_minutes * 60) - random_lower_bound
                    self.runtime.ui.log(
                        f"⏳ Food timer above threshold ({food_seconds}s > {fixed_threshold_seconds}s) "
                        f"— hysteresis restart at {self._food_restart_threshold_seconds}s "
                        f"({self._food_restart_threshold_seconds // 60}m), lower_bound={random_lower_bound}s, "
                        f"sleeping ~{remaining_seconds:.0f}s ({remaining_seconds / 60:.1f}min)"
                    )

                    # Sleep until food should be near threshold instead of polling every second.
                    if not self.runtime.pause.wait_interruptible(remaining_seconds, self.runtime.rclick_stop):
                        break
                    continue
                # Eating resumed — reset hysteresis threshold so next stop generates a new one.
                self._food_restart_threshold_seconds = None
                clicks_to_send = random.randint(burst_count_min, burst_count_max)
                queue_window = max(
                    RCCLICK_QUEUE_WINDOW_MIN,
                    # Convert ms to seconds (/1000); calculate total queue window for food burst
                    clicks_to_send * (click_delay_max_ms / 1000.0) + max(0, clicks_to_send - 1) * max(click_delay_min_ms / 1000.0, burst_interval_ms / 1000.0),
                )
            # Anti-spam / OCR latency buffer: skip if within cooldown of last food click
            if mode == "food" and self.last_food_click_ts > 0:
                current_time = time.time()
                if current_time - self.last_food_click_ts < RCCLICK_FOOD_COOLDOWN_SECONDS:
                    if not self.runtime.pause.wait_interruptible(RCCLICK_WAIT_INTERRUPTIBLE, self.runtime.rclick_stop):
                        break
                    continue
            else:
                # Convert ms to seconds (/1000); wait between non-food right-clicks
                if not self.runtime.pause.wait_interruptible(random.randint(min_ms, max_ms) / 1000.0, self.runtime.rclick_stop):
                    break
                clicks_to_send = 1
                queue_window = INPUT_QUEUE_WINDOW
            if not self.runtime.mouse.acquire(self.runtime.rclick_stop, max_wait=queue_window, module_id="right_click"):
                if self.runtime.rclick_stop.is_set():
                    break
                continue
            try:
                click_target = HumanMouse.jitter(target, rclick_jitter)
                router.human_move_and_click(click_target[0], click_target[1], "right")
                for click_index in range(clicks_to_send):
                    inter_click = max(RCCLICK_INTER_CLICK_MIN, burst_interval_ms / 1000.0 + random.uniform(*RCCLICK_INTER_CLICK_JITTER))
                    time.sleep(inter_click)
                    router.right_click(click_target[0], click_target[1])
                time.sleep(post_settle_ms / 1000.0)
            except Exception as exc:
                self.runtime.ui.log(f"❌ R-click: {exc}")
            finally:
                self.runtime.mouse.release()
            with self.runtime.record_lock:
                state.stats["right_clicks"] += clicks_to_send
            if mode == "food":
                self.runtime.ui.log(f"🖱️  Food burst at {target} ×{clicks_to_send}")
                self.last_food_click_ts = time.time()  # Anti-spam: mark last food click time
                if not self.runtime.pause.wait_interruptible(RIGHT_CLICK_FOOD_BURST_COOLDOWN, self.runtime.rclick_stop):
                    break
            else:
                self.runtime.ui.log(f"🖱️  Right-click at {target}")
            self.runtime.ui.refresh_stats()
        state.rclick_active = False
        self.runtime.ui.module_state_changed("rclick", False)
        self.runtime.ui.log("⏹ Right-click end")
