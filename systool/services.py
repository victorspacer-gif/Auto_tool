"""Automation features and infrastructure services."""

from __future__ import annotations

import math
import os
import random
import re
import threading
import time
from collections.abc import Callable

try:
    from studiomemuer_light_module.light_profile import DEFAULT_PROFILE as DEFAULT_LIGHT_PROFILE
    from studiomemuer_light_module.memory_backend import (
        LightMemoryController,
        MemoryWriteError,
        ProcessNotFoundError,
    )

    HAS_LIGHT_MODULE = True
except ImportError:
    DEFAULT_LIGHT_PROFILE = None
    LightMemoryController = None
    MemoryWriteError = RuntimeError
    ProcessNotFoundError = RuntimeError
    HAS_LIGHT_MODULE = False

from .models import HotkeyJob
from .runtime import (
    AppRuntime,
    HAS_CV2,
    HAS_MSS,
    HAS_PYGAME,
    HAS_PYNPUT,
    HAS_TESSERACT,
    HAS_WIN32,
    cv2,
    mss,
    np,
    pygame,
    pynput_kb,
    pynput_mouse,
    pytesseract,
    resolve_tesseract_cmd,
    win32con,
    win32gui,
)
from .theme import GREEN, ORANGE, RED, TEAL


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
                pass


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
                pass

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
            pass


class LightControlService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller = None

    def is_available(self) -> bool:
        return HAS_LIGHT_MODULE

    def attach(self) -> tuple[bool, str]:
        if not HAS_LIGHT_MODULE:
            return False, "Install psutil and pymem to use light control"
        process_name = self.runtime.state.light_process_name.strip()
        try:
            self.controller = LightMemoryController(process_name)
            self.controller.attach()
            return True, f"Attached to {process_name}"
        except ProcessNotFoundError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"Attach failed: {exc}"

    def detach(self) -> tuple[bool, str]:
        if self.controller is not None:
            try:
                self.controller.detach()
            except Exception:
                pass
            self.controller = None
        return True, "Detached"

    def read_current(self) -> tuple[bool, str]:
        try:
            ctrl = self._require_controller()
            address = int(self.runtime.state.light_address_hex.strip(), 16)
            value = ctrl.read_byte(address)
            return True, f"Current light byte: 0x{value:02X}"
        except Exception as exc:
            return False, str(exc)

    def apply_default(self) -> tuple[bool, str]:
        return self._apply(self.runtime.state.light_default_value_hex.strip())

    def apply_boosted(self) -> tuple[bool, str]:
        return self._apply(self.runtime.state.light_boosted_value_hex.strip())

    def _apply(self, value_hex: str) -> tuple[bool, str]:
        try:
            ctrl = self._require_controller()
            result = ctrl.apply_light_value(self.runtime.state.light_address_hex.strip(), value_hex)
            return True, f"Patched 0x{result.address:X}: 0x{result.old_value:02X} -> 0x{result.new_value:02X}"
        except Exception as exc:
            return False, str(exc)

    def _require_controller(self):
        if self.controller is None:
            raise ProcessNotFoundError("Attach to the game process first.")
        return self.controller


class PositionCaptureService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def capture(self, on_done: Callable[[tuple[int, int]], None], label: str) -> None:
        threading.Thread(target=self._worker, args=(on_done, label), daemon=True).start()

    def _worker(self, on_done: Callable[[tuple[int, int]], None], label: str) -> None:
        state = self.runtime.state
        self.runtime.ui.log(f"🎯 Move mouse to {label} → press record_pos hotkey (30 s)…")
        self.runtime.ui.set_status(
            f"Move to {label} → press {state.hotkey_bindings.get('record_pos', 'f12').upper()}",
            ORANGE,
        )
        captured = threading.Event()
        holder = [None]
        record_key = HotkeyService.key_str_to_pynput(state.hotkey_bindings.get("record_pos", "f12"))

        def on_press(key):
            if key == record_key:
                holder[0] = pynput_mouse.Controller().position
                captured.set()
                return False
            return None

        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            return

        listener = pynput_kb.Listener(on_press=on_press)
        listener.start()
        captured.wait(timeout=30)
        listener.stop()
        if holder[0]:
            on_done(holder[0])
        else:
            self.runtime.ui.log("⚠️  Capture timed out")
            self.runtime.ui.set_status("Capture timed out", ORANGE)


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
        self.runtime.ui.set_status("Activity monitor active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.afk_active:
            return
        self.runtime.afk_stop.set()
        state.afk_active = False
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
            if not self.runtime.execution.acquire(self.runtime.afk_stop, max_wait=0.50, module_id="afk"):
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
        self.runtime.ui.set_status("Right-click macro active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.rclick_active:
            return
        self.runtime.rclick_stop.set()
        state.rclick_active = False
        self.runtime.ui.set_status("Right-click macro stopped", RED)

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
                food_seconds = state.char_status_food_seconds
                food_min_secs = state.rclick_food_min_secs
                burst_count = state.rclick_food_burst_count
                burst_interval_ms = state.rclick_food_burst_interval_ms
            if mode == "food":
                if food_seconds is not None and food_seconds >= food_min_secs:
                    if not self.runtime.pause.wait_interruptible(1.0, self.runtime.rclick_stop):
                        break
                    continue
                clicks_to_send = max(1, burst_count)
                queue_window = max(
                    0.35,
                    clicks_to_send * 0.14 + max(0, clicks_to_send - 1) * max(0.05, burst_interval_ms / 1000.0),
                )
            else:
                if not self.runtime.pause.wait_interruptible(random.randint(min_ms, max_ms) / 1000.0, self.runtime.rclick_stop):
                    break
                clicks_to_send = 1
                queue_window = 0.80
            if not self.runtime.mouse.acquire(self.runtime.rclick_stop, max_wait=queue_window, module_id="right_click"):
                if self.runtime.rclick_stop.is_set():
                    break
                continue
            try:
                HumanMouse.move(mouse, target)
                for click_index in range(clicks_to_send):
                    time.sleep(random.uniform(0.06, 0.14))
                    mouse.click(pynput_mouse.Button.right, 1)
                    if click_index + 1 < clicks_to_send:
                        time.sleep(max(0.05, burst_interval_ms / 1000.0))
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
        self.runtime.ui.log("⏹ Right-click end")


class AlarmService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.alarm_active:
            return
        if not HAS_MSS:
            self.runtime.ui.log("❌ Install mss and numpy")
            return
        state.alarm_active = True
        self.runtime.alarm_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Screen watch active…", TEAL)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.alarm_active:
            return
        self.runtime.alarm_stop.set()
        state.alarm_active = False
        self.runtime.ui.set_status("Screen watch stopped", RED)

    def play_alarm(self) -> None:
        path = self.runtime.state.alarm_mp3
        if not path or not os.path.exists(path):
            self.runtime.ui.log("⚠️  Alert sound file not found")
            return

        def play() -> None:
            try:
                if HAS_PYGAME:
                    pygame.mixer.music.load(path)
                    pygame.mixer.music.play()
                else:
                    os.startfile(path)
            except Exception as exc:
                self.runtime.ui.log(f"❌ Audio: {exc}")

        threading.Thread(target=play, daemon=True).start()

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Screen watch start")
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screen_w = monitor["width"]
            screen_h = monitor["height"]

            def get_region() -> dict:
                with self.runtime.settings_lock:
                    region = state.alarm_region
                if region:
                    return {"top": region[1], "left": region[0], "width": region[2], "height": region[3], "mon": 1}
                size = 200
                return {"top": screen_h // 2 - size // 2, "left": screen_w // 2 - size // 2, "width": size, "height": size, "mon": 1}

            last_frame = None
            cooldown_until = 0.0
            while not self.runtime.alarm_stop.is_set():
                time.sleep(0.1)
                now = time.monotonic()
                with self.runtime.settings_lock:
                    hp_percent = state.alarm_hp_percent
                    hp_value = state.char_status_hp
                    hp_peak = state.char_status_hp_peak
                    auto_pause = state.alarm_auto_pause
                    threshold = state.alarm_threshold
                if hp_percent > 0 and hp_value is not None and hp_peak > 0 and now >= cooldown_until:
                    hp_ratio = (hp_value / hp_peak) * 100.0
                    if hp_ratio <= hp_percent:
                        cooldown_until = now + state.alarm_cooldown
                        with self.runtime.record_lock:
                            state.stats["alarms"] += 1
                        self.runtime.ui.log(f"🚨 LOW HP — {hp_value}/{hp_peak} ({hp_ratio:.1f}%)")
                        self.runtime.ui.set_status(f"⚠️  LOW HP — {hp_ratio:.1f}% remaining", RED)
                        self.play_alarm()
                        self.runtime.ui.refresh_stats()
                        if auto_pause and not self.runtime.pause.paused:
                            self.runtime.ui.log("⏸  Auto-pausing all activities due to low HP")
                            self.runtime.ui.dispatch(self.runtime.pause.toggle)
                        continue
                try:
                    frame = np.array(sct.grab(get_region()))[:, :, :3]
                except Exception as exc:
                    self.runtime.ui.log(f"❌ Capture: {exc}")
                    continue
                if last_frame is not None and last_frame.shape == frame.shape:
                    if now >= cooldown_until:
                        diff = np.abs(frame.astype(np.int16) - last_frame.astype(np.int16))
                        changed = float(np.mean(diff.sum(axis=2) > 30))
                        if changed >= threshold:
                            cooldown_until = now + state.alarm_cooldown
                            with self.runtime.record_lock:
                                state.stats["alarms"] += 1
                            self.runtime.ui.log(f"🚨 ALARM — {changed * 100:.1f}% pixels changed!")
                            self.runtime.ui.set_status(f"⚠️  PIXEL ALARM — {changed * 100:.1f}% changed!", RED)
                            self.play_alarm()
                            self.runtime.ui.refresh_stats()
                            if auto_pause and not self.runtime.pause.paused:
                                self.runtime.ui.log("⏸  Auto-pausing all activities due to screen watch event")
                                self.runtime.ui.dispatch(self.runtime.pause.toggle)
                last_frame = frame
        self.runtime.ui.log("⏹ Screen watch end")


class CharacterStatusService:
    BASE_SIZE = (170, 203)
    ROI_MAP = {
        "hp": [(132, 1, 169, 19), (124, 0, 169, 21)],
        "mana": [(136, 21, 169, 39), (128, 20, 169, 41)],
        "cap": [(0, 180, 42, 203), (0, 164, 44, 203)],
    }

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._regen_history: dict[str, list[tuple[float, int]]] = {"hp": [], "mana": []}

    def get_dependency_error(self) -> str | None:
        state = self.runtime.state
        if not HAS_MSS:
            return "mss is not installed"
        if not HAS_CV2:
            return "opencv-python is not installed"
        if not HAS_TESSERACT:
            return "pytesseract is not installed"
        tesseract_cmd = resolve_tesseract_cmd(state.char_status_tesseract_path)
        if not tesseract_cmd:
            return "Tesseract executable not found"
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        return None

    def start(self) -> None:
        state = self.runtime.state
        if state.char_status_active:
            return
        dependency_error = self.get_dependency_error()
        if dependency_error:
            state.char_status_last_error = dependency_error
            self.runtime.ui.log(f"❌ Character status OCR unavailable: {dependency_error}")
            self.runtime.ui.set_status(f"Character status OCR unavailable: {dependency_error}", RED)
            return
        has_window = bool(state.char_status_region)
        has_field_regions = all([state.char_status_hp_region, state.char_status_mana_region, state.char_status_cap_region])
        if not has_window and not has_field_regions:
            self.runtime.ui.log("⚠️  Select HP, Mana, and Cap areas or select the full character status window first")
            self.runtime.ui.set_status("Select stat areas or a full status window first", ORANGE)
            return
        state.char_status_active = True
        state.char_status_last_error = ""
        self.runtime.char_status_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Character status watcher active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.char_status_active:
            return
        self.runtime.char_status_stop.set()
        state.char_status_active = False
        self.runtime.ui.set_status("Character status watcher stopped", RED)

    def restart_if_needed(self) -> None:
        self.stop()
        if self.runtime.state.char_status_region:
            self.start()

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Character status watcher start")
        try:
            with mss.mss() as sct:
                while not self.runtime.char_status_stop.is_set():
                    with self.runtime.settings_lock:
                        region = state.char_status_region
                        hp_region = state.char_status_hp_region
                        mana_region = state.char_status_mana_region
                        cap_region = state.char_status_cap_region
                        poll_ms = max(250, state.char_status_poll_ms)
                    if not region and not all([hp_region, mana_region, cap_region]):
                        break
                    try:
                        parsed: dict[str, int | None] = {}
                        if region:
                            monitor = {
                                "left": region[0],
                                "top": region[1],
                                "width": region[2],
                                "height": region[3],
                                "mon": 1,
                            }
                            frame = np.array(sct.grab(monitor))[:, :, :3]
                            parsed = self._extract_values(frame)
                        if all([hp_region, mana_region, cap_region]):
                            parsed.update(
                                self._extract_values_from_regions(
                                    sct,
                                    {
                                        "hp": hp_region,
                                        "mana": mana_region,
                                        "cap": cap_region,
                                    },
                                )
                            )
                    except pytesseract.TesseractNotFoundError:
                        with self.runtime.settings_lock:
                            state.char_status_last_error = "Tesseract executable not found"
                        self.runtime.ui.log("❌ Tesseract executable not found for character status OCR")
                        self.runtime.ui.set_status("Configure a Tesseract path in Character Status", RED)
                        self.runtime.char_status_stop.set()
                        break
                    except Exception as exc:
                        with self.runtime.settings_lock:
                            state.char_status_failures += 1
                            state.char_status_last_error = str(exc)
                        time.sleep(0.5)
                        continue

                    if parsed:
                        with self.runtime.settings_lock:
                            for key, value in parsed.items():
                                if value is not None or key == "food_text":
                                    setattr(state, f"char_status_{key}", value)
                            if state.char_status_hp is not None:
                                state.char_status_hp_peak = max(state.char_status_hp_peak, state.char_status_hp)
                            self._update_regen(state)
                            state.char_status_reads += 1
                            state.char_status_last_seen = time.time()
                            state.char_status_last_error = ""
                    else:
                        with self.runtime.settings_lock:
                            state.char_status_failures += 1
                            state.char_status_last_error = "No digits recognized"
                    if self.runtime.char_status_stop.wait(poll_ms / 1000.0):
                        break
        finally:
            state.char_status_active = False
            self.runtime.ui.log("⏹ Character status watcher end")

    def _extract_values(self, frame) -> dict[str, int | None]:
        values: dict[str, int | None] = self._extract_values_from_text(frame)
        for key, boxes in self.ROI_MAP.items():
            if values.get(key) is not None:
                continue
            for box in boxes:
                crop = self._crop(frame, box)
                value = self._ocr_digits(crop, key)
                if value is not None:
                    values[key] = value
                    break
        return values if any(value is not None for value in values.values()) else {}

    def _extract_values_from_regions(self, sct, regions: dict[str, tuple[int, int, int, int]]) -> dict[str, int | None]:
        values: dict[str, int | None] = {}
        for key, region in regions.items():
            monitor = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3],
                "mon": 1,
            }
            frame = np.array(sct.grab(monitor))[:, :, :3]
            values[key] = self._ocr_digits(frame, key)
        return values if any(value is not None for value in values.values()) else {}

    def _update_regen(self, state) -> None:
        now = time.monotonic()
        self._push_regen_sample("hp", now, state.char_status_hp)
        self._push_regen_sample("mana", now, state.char_status_mana)
        state.char_status_hp_regen_per_min = self._compute_regen_rate("hp")
        state.char_status_mana_regen_per_min = self._compute_regen_rate("mana")

    def _push_regen_sample(self, key: str, now: float, value: int | None) -> None:
        if value is None:
            return
        history = self._regen_history[key]
        if not history or history[-1][1] != value:
            history.append((now, value))
        cutoff = now - 180.0
        while len(history) > 1 and history[0][0] < cutoff:
            history.pop(0)

    def _compute_regen_rate(self, key: str) -> float:
        history = self._regen_history[key]
        if len(history) < 2:
            return 0.0
        gained = 0
        for index in range(1, len(history)):
            delta = history[index][1] - history[index - 1][1]
            if delta > 0:
                gained += delta
        elapsed_minutes = max((history[-1][0] - history[0][0]) / 60.0, 1e-6)
        return gained / elapsed_minutes

    @staticmethod
    def _extract_values_from_text(frame) -> dict[str, int | None]:
        values: dict[str, int | None] = {
            "level": None,
            "hp": None,
            "mana": None,
            "cap": None,
            "food_seconds": None,
            "food_text": "",
        }
        enlarged = cv2.resize(frame, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        variants = []
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(binary)
        variants.append(cv2.bitwise_not(binary))
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7)
        variants.append(adaptive)
        variants.append(cv2.bitwise_not(adaptive))
        field_patterns = {
            "level": [r"level\s+(\d+)", r"leve[li]\s+(\d+)"],
            "hp": [r"hit\s*points\s+(\d+)", r"hit\s*point[s]?\s+(\d+)"],
            "mana": [r"mana\s+(\d+)"],
            "cap": [r"capacity\s+(\d+)", r"capacit[yv]\s+(\d+)"],
            "food": [r"food\s+(\d{1,2}:\d{2})"],
        }
        for image_variant in variants:
            text = pytesseract.image_to_string(image_variant, config="--psm 6")
            normalized = re.sub(r"[^a-z0-9:\n ]+", " ", text.lower())
            for key, patterns in field_patterns.items():
                if key == "food" and values["food_seconds"] is not None:
                    continue
                if key != "food" and values[key] is not None:
                    continue
                for pattern in patterns:
                    match = re.search(pattern, normalized)
                    if not match:
                        continue
                    if key == "food":
                        food_text = match.group(1)
                        values["food_text"] = food_text
                        values["food_seconds"] = CharacterStatusService._parse_food_seconds(food_text)
                    else:
                        values[key] = int(match.group(1))
                    break
        return values

    @staticmethod
    def _parse_food_seconds(text: str) -> int | None:
        match = re.match(r"(\d{1,2}):(\d{2})", text.strip())
        if not match:
            return None
        return int(match.group(1)) * 60 + int(match.group(2))

    def _crop(self, frame, box: tuple[int, int, int, int]):
        base_w, base_h = self.BASE_SIZE
        frame_h, frame_w = frame.shape[:2]
        x1 = max(0, int(round(box[0] / base_w * frame_w)))
        y1 = max(0, int(round(box[1] / base_h * frame_h)))
        x2 = min(frame_w, int(round(box[2] / base_w * frame_w)))
        y2 = min(frame_h, int(round(box[3] / base_h * frame_h)))
        return frame[y1:y2, x1:x2]

    @staticmethod
    def _ocr_digits(crop, key: str) -> int | None:
        if crop is None or crop.size == 0:
            return None
        scale = 7 if key == "cap" else 6
        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        variants = []
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(binary)
        variants.append(cv2.bitwise_not(binary))
        adaptive = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            7,
        )
        variants.append(adaptive)
        variants.append(cv2.bitwise_not(adaptive))
        kernel = np.ones((2, 2), np.uint8)
        variants.append(cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel))
        psm_modes = ["7", "8"] if key in {"hp", "mana"} else ["7", "6", "8"]
        best_digits = ""
        for image_variant in variants:
            for psm in psm_modes:
                config = f"--psm {psm} -c tessedit_char_whitelist=0123456789"
                text = pytesseract.image_to_string(image_variant, config=config)
                groups = [group for group in re.findall(r"\d+", text) if group]
                if groups:
                    candidate = max(groups, key=len) if key in {"hp", "mana"} else groups[-1]
                    if len(candidate) > len(best_digits):
                        best_digits = candidate
                    if key in {"hp", "mana"} and len(candidate) >= 2:
                        return int(candidate)
                    if key == "cap" and len(candidate) >= 1:
                        return int(candidate)
        if best_digits:
            return int(best_digits)
        return None


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
        if state.fish_min_cap > 0 and state.char_status_cap is not None and state.char_status_cap <= state.fish_min_cap:
            self.runtime.ui.log("⚠️  Capacity is already at or below the fishing stop threshold")
            self.runtime.ui.set_status("Capacity too low to start fishing", ORANGE)
            return
        self.runtime.fish_stop.clear()
        state.fish_session_remaining_secs = max(1, state.fish_session_minutes * 60)
        state.fish_session_deadline = time.monotonic() + state.fish_session_remaining_secs
        state.fish_active = True
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status(
            f"Fishing session running for {state.fish_session_minutes} min…",
            GREEN,
        )

    def stop(self) -> None:
        state = self.runtime.state
        if not state.fish_active:
            return
        self.runtime.fish_stop.set()
        state.fish_active = False
        state.fish_session_remaining_secs = 0
        state.fish_session_deadline = None
        self.runtime.ui.set_status("Fishing session stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(f"▶ Fishing start — rod={state.fish_rod_pos}  spots={len(state.fish_spots)}")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.fish_active = False
            state.fish_session_remaining_secs = 0
            state.fish_session_deadline = None
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
                chunk = min(seconds, 0.25, max(0.0, session_deadline - time.monotonic()))
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
                current_cap = state.char_status_cap
            if min_cap > 0 and current_cap is not None and current_cap <= min_cap:
                self.runtime.ui.log(f"📦 Fishing stopped — capacity {current_cap} is at/below limit {min_cap}")
                self.runtime.ui.set_status("Fishing stopped by capacity threshold", ORANGE)
                self.runtime.fish_stop.set()
                break
            cycle_locked = False
            try:
                cycle_window = max(0.90, max(cast_max, 0) / 1000.0 + 1.20)
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
                time.sleep(random.uniform(0.07, 0.17))
                mouse.click(pynput_mouse.Button.right, 1)
                self.runtime.ui.log(f"🎣 Rod clicked at {rod_target}")
                if not wait_with_session_limit(random.randint(cast_min, cast_max) / 1000.0):
                    break
                if index >= len(deck):
                    deck = list(state.fish_spots)
                    random.shuffle(deck)
                    index = 0
                spot_target = HumanMouse.jitter(deck[index], spot_jitter)
                index += 1
                HumanMouse.move(mouse, spot_target)
                time.sleep(random.uniform(0.10, 0.26))
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
        if self.runtime.fish_stop.is_set():
            state.fish_session_remaining_secs = 0
            state.fish_session_deadline = None
        self.runtime.ui.log(f"⏹ Fishing stopped — {state.stats['fish_casts']} casts")


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
        self.runtime.ui.set_status("Auto healer active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.healer_active:
            return
        self.runtime.healer_stop.set()
        state.healer_active = False
        self.runtime.ui.set_status("Auto healer stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Auto healer start")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.healer_active = False
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
                hp_value = state.char_status_hp
                hp_peak = state.char_status_hp_peak
                mana_value = state.char_status_mana
                mode = state.healer_mode
                spell_key_name = state.healer_spell_key
                use_percent = state.healer_use_percent
                hp_percent = state.healer_hp_percent
                hp_fixed = state.healer_hp_value
                min_mana = state.healer_min_mana
                character_pos = state.healer_character_pos
                rune_pos = state.healer_rune_pos
                mouse_speed = state.healer_mouse_speed
                rune_delay_ms = state.healer_rune_delay_ms
            if hp_value is None:
                if not self.runtime.pause.wait_interruptible(0.15, self.runtime.healer_stop):
                    break
                continue
            should_heal = False
            if use_percent:
                if hp_peak > 0 and (hp_value / hp_peak) * 100.0 <= hp_percent:
                    should_heal = True
            elif hp_value <= hp_fixed:
                should_heal = True
            if not should_heal:
                if not self.runtime.pause.wait_interruptible(0.12, self.runtime.healer_stop):
                    break
                continue
            if min_mana > 0 and mana_value is not None and mana_value < min_mana:
                if not self.runtime.pause.wait_interruptible(0.2, self.runtime.healer_stop):
                    break
                continue
            try:
                if mode == "spell":
                    spell_key = HotkeyService.key_str_to_pynput(spell_key_name)
                    if not spell_key:
                        self.runtime.ui.log(f"❌ Unknown healer spell key: {spell_key_name}")
                        break
                    if not self.runtime.execution.acquire(self.runtime.healer_stop, max_wait=0.25, module_id="healer"):
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
                    if not self.runtime.mouse.acquire(self.runtime.healer_stop, max_wait=0.35, module_id="healer"):
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
        self.runtime.ui.log("⏹ Auto healer end")


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
        self.runtime.ui.set_status("Rune session running…", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.rune_active:
            return
        self.runtime.rune_stop.set()
        state.rune_active = False
        self.runtime.ui.set_status("Rune session stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(
            f"▶ Rune session start — spell={state.rune_spell_key.upper()}  cycle={state.rune_cycle_delay_ms}ms"
        )
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.rune_active = False
            return
        keyboard = pynput_kb.Controller()
        mouse = pynput_mouse.Controller()
        spell = HotkeyService.key_str_to_pynput(state.rune_spell_key)
        if not spell:
            self.runtime.ui.log(f"❌ Unknown spell key: {state.rune_spell_key}")
            state.rune_active = False
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
                current_mana = state.char_status_mana
                blank_rune_limit = state.rune_available_blank_runes
                move_min_ms = state.rune_mouse_move_min_ms
                move_max_ms = state.rune_mouse_move_max_ms
                press_min_ms = state.rune_mouse_press_min_ms
                press_max_ms = state.rune_mouse_press_max_ms
                settle_min_ms = state.rune_mouse_settle_min_ms
                settle_max_ms = state.rune_mouse_settle_max_ms
            if blank_rune_limit > 0 and cycles_completed >= blank_rune_limit:
                self.runtime.ui.log(f"⏲️ Rune session stopped — avb blank runes limit reached ({blank_rune_limit})")
                self.runtime.ui.set_status("Rune session finished by avb blank runes limit", ORANGE)
                break
            if min_mana > 0 and current_mana is not None and current_mana < min_mana:
                if not self.runtime.pause.wait_interruptible(1.0, self.runtime.rune_stop):
                    break
                continue
            queue_window = max(
                0.90,
                cast_delay_ms / 1000.0
                + (move_max_ms * 2 + press_max_ms * 2 + settle_max_ms * 2) / 1000.0
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
        self.runtime.ui.log(f"⏹ Rune session stopped — {state.stats['runes_made']} runes moved")


class HotkeyJobService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.key_map = self._build_key_map()

    def _build_key_map(self) -> dict:
        if not HAS_PYNPUT:
            return {}
        mapping = {f"F{i}": getattr(pynput_kb.Key, f"f{i}") for i in range(1, 13)}
        for label, attr_name in [
            ("ESC", "esc"),
            ("ENTER", "enter"),
            ("SPACE", "space"),
            ("TAB", "tab"),
            ("UP", "up"),
            ("DOWN", "down"),
            ("LEFT", "left"),
            ("RIGHT", "right"),
            ("HOME", "home"),
            ("END", "end"),
            ("DELETE", "delete"),
            ("INSERT", "insert"),
            ("PAGEUP", "page_up"),
            ("PAGEDOWN", "page_down"),
        ]:
            key_value = getattr(pynput_kb.Key, attr_name, None)
            if key_value is not None:
                mapping[label] = key_value
        for char in "abcdefghijklmnopqrstuvwxyz0123456789":
            mapping[char.upper()] = pynput_kb.KeyCode.from_char(char)
        return mapping

    def start_job(self, job: HotkeyJob) -> None:
        if job.running:
            return
        job.stop_evt.clear()
        job.running = True
        threading.Thread(target=self._worker, args=(job,), daemon=True).start()
        self.runtime.ui.job_state_changed(job)
        self.runtime.ui.set_status(f"Job #{job.job_id} ({job.key}) started", GREEN)

    def stop_job(self, job: HotkeyJob) -> None:
        job.stop_evt.set()

    def stop_all(self, stop_afk, stop_rclick, stop_alarm, stop_fishing, stop_rune) -> None:
        for job in list(self.runtime.state.jobs):
            self.stop_job(job)
        stop_afk()
        stop_rclick()
        stop_alarm()
        stop_fishing()
        stop_rune()
        if self.runtime.pause.paused:
            self.runtime.pause.toggle()
        self.runtime.ui.log("🛑 ALL STOPPED (stop_all hotkey)")
        self.runtime.ui.set_status("All stopped", RED)

    def _worker(self, job: HotkeyJob) -> None:
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            job.running = False
            return
        keyboard = pynput_kb.Controller()
        pressed_key = self.key_map.get(job.key.upper())
        if not pressed_key:
            self.runtime.ui.log(f"❌ Unknown key {job.key}")
            job.running = False
            return
        self.runtime.ui.log(f"▶ Job #{job.job_id} — key={job.key} {job.min_ms}–{job.max_ms}ms focus={job.use_focus}")
        while not job.stop_evt.is_set():
            self.runtime.pause.wait()
            delay = random.randint(job.min_ms, job.max_ms) / 1000.0
            if not self.runtime.pause.wait_interruptible(delay, job.stop_evt):
                break
            prev_hwnd = None
            if job.min_mana > 0:
                current_mana = self.runtime.state.char_status_mana
                if current_mana is not None and current_mana < job.min_mana:
                    continue
            if job.use_focus and job.window_name.strip():
                prev_hwnd = WindowService.get_foreground_hwnd()
                if not WindowService.focus_window_by_name(job.window_name.strip()):
                    self.runtime.ui.log(f"⚠️  Job #{job.job_id}: window '{job.window_name}' not found")
            if not self.runtime.execution.acquire(job.stop_evt, max_wait=0.45, module_id=f"job:{job.job_id}"):
                if job.stop_evt.is_set():
                    break
                continue
            if job.burst_enabled and random.random() < job.burst_chance:
                count = random.randint(job.burst_cnt_min, job.burst_cnt_max)
                sent = 0
                try:
                    for _ in range(count):
                        if job.stop_evt.is_set():
                            break
                        self._press_key(keyboard, pressed_key)
                        sent += 1
                        time.sleep(job.burst_int_ms / 1000.0)
                finally:
                    self.runtime.execution.release()
                with self.runtime.record_lock:
                    self.runtime.state.stats["hotkeys"] += sent
                    if sent:
                        self.runtime.state.stats["bursts"] += 1
                if sent:
                    self.runtime.ui.log(f"⚡ Job #{job.job_id} burst {job.key} ×{sent}")
            else:
                try:
                    self._press_key(keyboard, pressed_key)
                finally:
                    self.runtime.execution.release()
                with self.runtime.record_lock:
                    self.runtime.state.stats["hotkeys"] += 1
                self.runtime.ui.log(f"🎮 Job #{job.job_id} pressed {job.key}")
            if job.use_focus and job.restore_focus and prev_hwnd:
                time.sleep(0.05)
                WindowService.restore(prev_hwnd)
            self.runtime.ui.refresh_stats()
        job.running = False
        self.runtime.ui.log(f"⏹ Job #{job.job_id} stopped")
        self.runtime.ui.job_state_changed(job)

    @staticmethod
    def _press_key(keyboard, pressed_key) -> None:
        session = SafeKeyboardSession(keyboard)
        try:
            session.tap(pressed_key, hold_seconds=0.03)
        finally:
            session.release_all()


class HotkeyService:
    @staticmethod
    def key_str_to_pynput(key_str: str):
        if not HAS_PYNPUT:
            return None
        value = key_str.strip().lower()
        named = {}
        for key_name, attr_name in [
            ("f1", "f1"),
            ("f2", "f2"),
            ("f3", "f3"),
            ("f4", "f4"),
            ("f5", "f5"),
            ("f6", "f6"),
            ("f7", "f7"),
            ("f8", "f8"),
            ("f9", "f9"),
            ("f10", "f10"),
            ("f11", "f11"),
            ("f12", "f12"),
            ("home", "home"),
            ("end", "end"),
            ("esc", "esc"),
            ("enter", "enter"),
            ("space", "space"),
            ("tab", "tab"),
            ("delete", "delete"),
            ("insert", "insert"),
            ("page_up", "page_up"),
            ("page_down", "page_down"),
            ("up", "up"),
            ("down", "down"),
            ("left", "left"),
            ("right", "right"),
        ]:
            key_value = getattr(pynput_kb.Key, attr_name, None)
            if key_value is not None:
                named[key_name] = key_value
        if value in named:
            return named[value]
        if len(value) == 1:
            return pynput_kb.KeyCode.from_char(value)
        return None

    @staticmethod
    def pynput_key_to_str(key) -> str:
        try:
            if hasattr(key, "char") and key.char:
                return key.char.lower()
            return key.name.lower()
        except AttributeError:
            return str(key).lower().replace("key.", "")

    @staticmethod
    def matches(pressed_key, binding_str: str) -> bool:
        target = HotkeyService.key_str_to_pynput(binding_str)
        return target is not None and pressed_key == target
