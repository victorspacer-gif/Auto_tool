"""Position capture service."""

from __future__ import annotations

import threading
from collections.abc import Callable

from ..runtime import AppRuntime, HAS_PYNPUT, pynput_kb, pynput_mouse
from ..theme import ORANGE
from .hotkeys import HotkeyService

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
