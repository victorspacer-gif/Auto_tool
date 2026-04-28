"""Hotkey mapping and job automation services."""

from __future__ import annotations

import random
import threading
import time

from ..models import HotkeyJob
from ..runtime import AppRuntime, HAS_PYNPUT, pynput_kb
from ..theme import GREEN, RED
from .input_services import SafeKeyboardSession, WindowService

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
        if not job.running:
            return
        job.stop_evt.set()
        job.running = False
        self.runtime.ui.job_state_changed(job)
        self.runtime.ui.log(f"⏹ Job #{job.job_id} ({job.key}) stopped")
        self.runtime.ui.set_status(f"Job #{job.job_id} stopped", RED)

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
                # Use pointer-based MP first, fall back to OCR
                current_mana = None
                if self.runtime.mp_service is not None:
                    try:
                        current_mana = self.runtime.mp_service.get_mp()
                    except Exception:
                        pass
                if current_mana is None:
                    with self.runtime.settings_lock:
                        current_mana = self.runtime.state.char_status_mana
                if current_mana is not None:
                    # Pick a random threshold between min and max (if max set), otherwise use min
                    threshold = random.randint(job.min_mana, job.max_mana) if job.max_mana > job.min_mana else job.min_mana
                    if current_mana < threshold:
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
                        # Add slight random variation between burst clicks for natural rhythm
                        inter_click = max(0.02, job.burst_int_ms / 1000.0 + random.uniform(-0.05, 0.08))
                        time.sleep(inter_click)
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
