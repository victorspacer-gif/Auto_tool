"""Input-oriented infrastructure and services."""

from __future__ import annotations

import logging
import math
import random
import threading
import time

logger = logging.getLogger(__name__)

from ..runtime import AppRuntime, HAS_PYNPUT, HAS_WIN32, pynput_kb, pynput_mouse, win32con, win32gui
from ..constants import AFK_EXEC_MAX_WAIT, RCCLICK_INTER_CLICK_MIN, RCCLICK_INTER_CLICK_JITTER, EXEC_WAIT_TIMEOUT_DEFAULT
from ..theme import GREEN, ORANGE, RED

class HumanMouse:
    @staticmethod
    def jitter(pos: tuple[int, int], amount: int) -> tuple[int, int]:
        return (
            pos[0] + random.randint(-amount, amount),
            pos[1] + random.randint(-amount, amount),
        )

    @staticmethod
    def move(mouse, target: tuple[int, int], duration: float | None = None) -> None:
        sx, sy = mouse.position
        ex, ey = target
        dx, dy = ex - sx, ey - sy
        distance = math.hypot(dx, dy)
        if distance < 1:
            mouse.position = (int(ex), int(ey))
            return
        if duration is None:
            duration = max(0.12, min(0.55, distance / random.uniform(900, 1500)))
        steps = max(10, int(distance / 7))
        control_scale = random.uniform(-35, 35)
        cx = (sx + ex) / 2 + (-dy / distance) * control_scale
        cy = (sy + ey) / 2 + (dx / distance) * control_scale
        step_duration = duration / steps
        for index in range(steps):
            t_value = index / steps
            eased = t_value * t_value * (3.0 - 2.0 * t_value)
            x_pos = (1 - eased) ** 2 * sx + 2 * (1 - eased) * eased * cx + eased**2 * ex
            y_pos = (1 - eased) ** 2 * sy + 2 * (1 - eased) * eased * cy + eased**2 * ey
            fade = 1.0 - t_value
            x_pos += random.uniform(-0.9, 0.9) * fade
            y_pos += random.uniform(-0.9, 0.9) * fade
            mouse.position = (int(x_pos), int(y_pos))
            time.sleep(step_duration)
        mouse.position = (int(ex), int(ey))

    @staticmethod
    def drag(
        mouse,
        source: tuple[int, int],
        dest: tuple[int, int],
        *,
        move_duration: float | None = None,
        press_delay_range: tuple[float, float] = (0.06, 0.14),
        hold_delay_range: tuple[float, float] = (0.05, 0.10),
        settle_delay_range: tuple[float, float] = (0.04, 0.09),
    ) -> None:
        HumanMouse.move(mouse, source, duration=move_duration)
        time.sleep(random.uniform(*press_delay_range))
        mouse.press(pynput_mouse.Button.left)
        time.sleep(random.uniform(*hold_delay_range))
        HumanMouse.move(mouse, dest, duration=move_duration)
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
                time.sleep(0.08)
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
                time.sleep(random.uniform(0.04, 0.08))
                session.press(direction_key)
                time.sleep(random.uniform(0.03, 0.06))
                session.release(direction_key)
                time.sleep(random.uniform(0.02, 0.04))
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
        return food_seconds is not None and food_seconds >= max(1, threshold_minutes) * 60

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Right-click macro start")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.rclick_active = False
            return
        mouse = pynput_mouse.Controller()
        while not self.runtime.rclick_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.rclick_stop.is_set():
                break
            with self.runtime.settings_lock:
                min_ms = state.rclick_min_ms
                max_ms = state.rclick_max_ms
                target = state.rclick_pos
                mode = state.rclick_mode
                require_food = state.rclick_require_food
                food_seconds = state.char_status_food_seconds
                food_min_minutes = state.rclick_food_min_minutes
                burst_count_min = state.rclick_food_burst_count_min
                burst_count_max = state.rclick_food_burst_count_max
                burst_interval_ms = state.rclick_food_burst_interval_ms
                click_delay_min_ms = state.rclick_click_delay_min_ms
                click_delay_max_ms = state.rclick_click_delay_max_ms
                post_settle_ms = state.rclick_post_click_settle_ms
            food_ok = self.food_timer_meets_threshold(food_seconds, food_min_minutes)
            if mode == "food":
                if food_ok:
                    if not self.runtime.pause.wait_interruptible(1.0, self.runtime.rclick_stop):
                        break
                    continue
                clicks_to_send = random.randint(burst_count_min, burst_count_max)
                queue_window = max(
                    0.35,
                    clicks_to_send * (click_delay_max_ms / 1000.0) + max(0, clicks_to_send - 1) * max(click_delay_min_ms / 1000.0, burst_interval_ms / 1000.0),
                )
            else:
                if not self.runtime.pause.wait_interruptible(random.randint(min_ms, max_ms) / 1000.0, self.runtime.rclick_stop):
                    break
                if require_food and not food_ok:
                    if food_seconds is None:
                        self.runtime.ui.log("🍖 Timer click blocked — food timer unavailable")
                    else:
                        self.runtime.ui.log(
                            f"🍖 Timer click blocked — food {food_seconds // 60}:{food_seconds % 60:02d} below {food_min_minutes}:00"
                        )
                    continue
                clicks_to_send = 1
                queue_window = 0.80
            if not self.runtime.mouse.acquire(self.runtime.rclick_stop, max_wait=queue_window, module_id="right_click"):
                if self.runtime.rclick_stop.is_set():
                    break
                continue
            try:
                HumanMouse.move(mouse, target)
                for click_index in range(clicks_to_send):
                    # Add slight random variation between clicks for natural rhythm
                    inter_click = max(RCCLICK_INTER_CLICK_MIN, burst_interval_ms / 1000.0 + random.uniform(*RCCLICK_INTER_CLICK_JITTER))
                    time.sleep(inter_click)
                    mouse.click(pynput_mouse.Button.right, 1)
                # Settle after all clicks — lets the game register and adds human-like pause
                time.sleep(post_settle_ms / 1000.0)
            except Exception as exc:
                self.runtime.ui.log(f"❌ R-click: {exc}")
            finally:
                self.runtime.mouse.release()
            with self.runtime.record_lock:
                state.stats["right_clicks"] += clicks_to_send
            if mode == "food":
                self.runtime.ui.log(f"🖱️  Food burst at {target} ×{clicks_to_send}")
                if not self.runtime.pause.wait_interruptible(1.5, self.runtime.rclick_stop):
                    break
            else:
                self.runtime.ui.log(f"🖱️  Right-click at {target}")
            self.runtime.ui.refresh_stats()
        state.rclick_active = False
        self.runtime.ui.module_state_changed("rclick", False)
        self.runtime.ui.log("⏹ Right-click end")
