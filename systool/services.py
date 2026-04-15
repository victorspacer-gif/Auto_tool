"""Automation features and infrastructure services."""

from __future__ import annotations

import math
import os
import random
import threading
import time
from collections.abc import Callable

from .models import HotkeyJob
from .runtime import (
    AppRuntime,
    HAS_MSS,
    HAS_PYGAME,
    HAS_PYNPUT,
    HAS_WIN32,
    mss,
    np,
    pygame,
    pynput_kb,
    pynput_mouse,
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
    def drag(mouse, source: tuple[int, int], dest: tuple[int, int]) -> None:
        HumanMouse.move(mouse, source)
        time.sleep(random.uniform(0.06, 0.14))
        mouse.press(pynput_mouse.Button.left)
        time.sleep(random.uniform(0.05, 0.10))
        HumanMouse.move(mouse, dest)
        time.sleep(random.uniform(0.04, 0.09))
        mouse.release(pynput_mouse.Button.left)


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
            try:
                keyboard.press(pynput_kb.Key.ctrl)
                time.sleep(random.uniform(0.04, 0.08))
                keyboard.press(direction_key)
                time.sleep(random.uniform(0.03, 0.06))
                keyboard.release(direction_key)
                time.sleep(random.uniform(0.02, 0.04))
                keyboard.release(pynput_kb.Key.ctrl)
            except Exception as exc:
                self.runtime.ui.log(f"❌ AFK: {exc}")
                try:
                    keyboard.release(pynput_kb.Key.ctrl)
                except Exception:
                    pass
            with self.runtime.record_lock:
                state.stats["afk_moves"] += 1
            self.runtime.ui.log(f"🚶 AFK Ctrl+{direction_name}")
            self.runtime.ui.refresh_stats()
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
            if not self.runtime.pause.wait_interruptible(random.randint(min_ms, max_ms) / 1000.0, self.runtime.rclick_stop):
                break
            if not self.runtime.mouse.acquire(self.runtime.rclick_stop):
                break
            try:
                HumanMouse.move(mouse, target)
                time.sleep(random.uniform(0.06, 0.14))
                mouse.click(pynput_mouse.Button.right, 1)
            except Exception as exc:
                self.runtime.ui.log(f"❌ R-click: {exc}")
            finally:
                self.runtime.mouse.release()
            with self.runtime.record_lock:
                state.stats["right_clicks"] += 1
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
                try:
                    frame = np.array(sct.grab(get_region()))[:, :, :3]
                except Exception as exc:
                    self.runtime.ui.log(f"❌ Capture: {exc}")
                    continue
                if last_frame is not None and last_frame.shape == frame.shape:
                    now = time.monotonic()
                    if now >= cooldown_until:
                        with self.runtime.settings_lock:
                            threshold = state.alarm_threshold
                            auto_pause = state.alarm_auto_pause
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
            if not self.runtime.mouse.acquire(self.runtime.fish_stop):
                break
            try:
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
            return
        keyboard = pynput_kb.Controller()
        mouse = pynput_mouse.Controller()
        spell = HotkeyService.key_str_to_pynput(state.rune_spell_key)
        if not spell:
            self.runtime.ui.log(f"❌ Unknown spell key: {state.rune_spell_key}")
            return
        while not self.runtime.rune_stop.is_set():
            self.runtime.pause.wait()
            with self.runtime.settings_lock:
                hand = state.rune_hand_pos
                storage = state.rune_storage_pos
                blank = state.rune_blank_pos
                jitter = state.rune_jitter
                cast_delay_ms = state.rune_cast_delay_ms
                cycle_delay_ms = state.rune_cycle_delay_ms
            try:
                keyboard.press(spell)
                time.sleep(0.04)
                keyboard.release(spell)
            except Exception as exc:
                self.runtime.ui.log(f"❌ Spell cast: {exc}")
                break
            self.runtime.ui.log(f"✨ Spell cast ({state.rune_spell_key.upper()})")
            if not self.runtime.pause.wait_interruptible(cast_delay_ms / 1000.0, self.runtime.rune_stop):
                break
            if not self.runtime.mouse.acquire(self.runtime.rune_stop):
                break
            try:
                HumanMouse.drag(mouse, HumanMouse.jitter(hand, jitter), HumanMouse.jitter(storage, jitter))
                self.runtime.ui.log("📦 Rune moved → storage")
                time.sleep(random.uniform(0.12, 0.22))
                HumanMouse.drag(mouse, HumanMouse.jitter(blank, jitter), HumanMouse.jitter(hand, jitter))
                self.runtime.ui.log("📥 Blank rune → hand slot")
            except Exception as exc:
                self.runtime.ui.log(f"❌ Rune drag: {exc}")
                break
            finally:
                self.runtime.mouse.release()
            with self.runtime.record_lock:
                state.stats["runes_made"] += 1
            self.runtime.ui.refresh_stats()
            wait_s = cycle_delay_ms / 1000.0
            self.runtime.ui.log(f"⏳ Waiting {wait_s:.1f}s before next cast…")
            if not self.runtime.pause.wait_interruptible(wait_s, self.runtime.rune_stop):
                break
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
            if job.use_focus and job.window_name.strip():
                prev_hwnd = WindowService.get_foreground_hwnd()
                if not WindowService.focus_window_by_name(job.window_name.strip()):
                    self.runtime.ui.log(f"⚠️  Job #{job.job_id}: window '{job.window_name}' not found")
            if job.burst_enabled and random.random() < job.burst_chance:
                count = random.randint(job.burst_cnt_min, job.burst_cnt_max)
                for _ in range(count):
                    if job.stop_evt.is_set():
                        break
                    self._press_key(keyboard, pressed_key)
                    time.sleep(job.burst_int_ms / 1000.0)
                with self.runtime.record_lock:
                    self.runtime.state.stats["hotkeys"] += count
                    self.runtime.state.stats["bursts"] += 1
                self.runtime.ui.log(f"⚡ Job #{job.job_id} burst {job.key} ×{count}")
            else:
                self._press_key(keyboard, pressed_key)
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
        try:
            keyboard.press(pressed_key)
            keyboard.release(pressed_key)
        except Exception:
            pass


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
