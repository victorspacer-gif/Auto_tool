"""Fishing tab UI for SystemMonitor."""

from __future__ import annotations

import logging
import tkinter as tk

from ...config import (
    FISH_AUTO_RESTART_FOOD_MIN_SECS_DEFAULT,
    FISH_AUTO_RESTART_FOOD_MIN_SECS_MAX,
    FISH_AUTO_RESTART_FOOD_MIN_SECS_MIN,
    FISH_MOUSE_SPEED_DEFAULT,
    FISH_MOUSE_SPEED_MAX,
    FISH_MOUSE_SPEED_MIN,
    NON_NEGATIVE_INT_MIN,
)
from ...runtime import HAS_PYNPUT, pynput_kb, pynput_mouse
from ...services import HotkeyService
from ...theme import BG, BLUE, BOLD, FG, GREEN, MONO, MUTED, ORANGE, PANEL, RED, SMALL, SMALL_B, TEAL

logger = logging.getLogger(__name__)


class FishingTab:
    """Owns the fishing tab UI and tab-local behavior."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.rod_label: tk.Label | None = None
        self.record_spot_btn: tk.Button | None = None
        self.spots_listbox: tk.Listbox | None = None
        self.fish_session_value_label: tk.Label | None = None
        self.fish_session_remaining_label: tk.Label | None = None
        self._fish_spot_recording = False
        self._fish_spot_listener = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        rod_panel = tk.LabelFrame(left, text=" 🎣  Rod Position ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        rod_panel.pack(fill="x", pady=(0, 8))
        self.helpers["register_module_indicator"](rod_panel, "fish", self.runtime.state.fish_active)
        self.rod_label = tk.Label(rod_panel, text="Rod: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.rod_label.pack(anchor="w", pady=(0, 4))
        self.helpers["btn"](rod_panel, "🎯 Record Rod Pos", self.record_rod_pos, BLUE).pack(fill="x")
        rod_jitter = tk.StringVar(value=str(self.runtime.state.fish_rod_jitter))
        self.ui_vars["fish_rod_jit_var"] = rod_jitter
        self.helpers["label_entry"](rod_panel, "Rod jitter (px ±):", rod_jitter, width=5)

        spots_panel = tk.LabelFrame(left, text=" 🗺️  Fishing Positions ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        spots_panel.pack(fill="both", expand=True, pady=(0, 8))
        spot_buttons = tk.Frame(spots_panel, bg=PANEL)
        spot_buttons.pack(fill="x", pady=(0, 6))
        self.record_spot_btn = self.helpers["btn"](spot_buttons, "+ Start Recording", self.record_spot, BLUE)
        self.record_spot_btn.pack(side="left", padx=2)
        self.helpers["btn"](spot_buttons, "✕ Remove", self.remove_selected_spot, ORANGE).pack(side="left", padx=2)
        self.helpers["btn"](spot_buttons, "🗑 Clear", self.clear_spots, RED).pack(side="left", padx=2)

        list_frame = tk.Frame(spots_panel, bg=PANEL)
        list_frame.pack(fill="both", expand=True)
        self.spots_listbox = tk.Listbox(list_frame, bg=BG, fg=FG, font=MONO, selectbackground=BLUE, selectforeground="white", relief="flat", bd=2, height=8)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.spots_listbox.yview)
        self.spots_listbox.configure(yscrollcommand=scrollbar.set)
        self.spots_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.helpers["register_mousewheel_target"](list_frame, self.spots_listbox)
        self.helpers["register_mousewheel_target"](self.spots_listbox, self.spots_listbox)

        spot_jitter = tk.StringVar(value=str(self.runtime.state.fish_spot_jitter))
        self.ui_vars["fish_spot_jit_var"] = spot_jitter
        self.helpers["label_entry"](spots_panel, "Spot jitter (px ±):", spot_jitter, width=5)

        timing_panel = tk.LabelFrame(right, text=" ⏱️  Timing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        timing_panel.pack(fill="x", pady=(0, 8))
        unit = self.helpers["get_unit_label"]()
        cast_min = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_cast_min_ms)))
        cast_max = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_cast_max_ms)))
        wait_min = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_wait_min_ms)))
        wait_max = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_wait_max_ms)))
        fish_session = tk.IntVar(value=self.runtime.state.fish_session_minutes)
        self.ui_vars.update(
            {
                "fish_cast_min_var": cast_min,
                "fish_cast_max_var": cast_max,
                "fish_wait_min_var": wait_min,
                "fish_wait_max_var": wait_max,
                "fish_session_var": fish_session,
            }
        )
        self.helpers["label_entry"](timing_panel, f"Cast delay Min ({unit}):", cast_min)
        self.helpers["label_entry"](timing_panel, f"Cast delay Max ({unit}):", cast_max)
        self.helpers["label_entry"](timing_panel, f"Wait for bite Min ({unit}):", wait_min)
        self.helpers["label_entry"](timing_panel, f"Wait for bite Max ({unit}):", wait_max)
        fish_min_cap = tk.StringVar(value=str(self.runtime.state.fish_min_cap))
        self.ui_vars["fish_min_cap_var"] = fish_min_cap
        self.helpers["label_entry"](timing_panel, "Stop below cap:", fish_min_cap, width=6)

        fish_auto_restart_enabled = tk.BooleanVar(value=self.runtime.state.fish_auto_restart_enabled)
        fish_auto_restart_food_secs = tk.StringVar(value=str(self.runtime.state.fish_auto_restart_food_min_secs))
        self.ui_vars["fish_auto_restart_enabled_var"] = fish_auto_restart_enabled
        self.ui_vars["fish_auto_restart_food_secs_var"] = fish_auto_restart_food_secs

        ar_frame = tk.Frame(timing_panel, bg=PANEL)
        ar_frame.pack(fill="x", pady=2)
        tk.Checkbutton(
            ar_frame,
            variable=fish_auto_restart_enabled,
            command=lambda: self._on_fish_auto_restart_toggle(fish_auto_restart_food_secs),
            bg=PANEL,
            fg=FG,
            font=BOLD,
            activebackground=PANEL,
            activeforeground=TEAL,
        ).pack(side="left")
        tk.Label(ar_frame, text="Auto-restart session when food drops below:", font=BOLD, fg=FG, bg=PANEL).pack(side="left", padx=(8, 4))
        self.helpers["entry"](ar_frame, fish_auto_restart_food_secs, width=5).pack(side="left")
        tk.Label(ar_frame, text="sec", font=BOLD, fg=TEAL, bg=PANEL).pack(side="left", padx=(2, 0))

        # ── Mouse speed multiplier (0.5–3.0) — higher = faster movement ──
        fish_mouse_speed_var = tk.StringVar(value=str(self.runtime.state.fish_mouse_speed))
        self.ui_vars["fish_mouse_speed_var"] = fish_mouse_speed_var
        ms_frame = tk.Frame(timing_panel, bg=PANEL)
        ms_frame.pack(fill="x", pady=2)
        tk.Label(ms_frame, text="Mouse Speed (×):", font=BOLD, fg=FG, bg=PANEL).pack(side="left")
        self.helpers["entry"](ms_frame, fish_mouse_speed_var, width=5).pack(side="left", padx=(8, 4))
        tk.Label(
            ms_frame,
            text=f"(range: {FISH_MOUSE_SPEED_MIN}–{FISH_MOUSE_SPEED_MAX})",
            font=BOLD,
            fg=MUTED,
            bg=PANEL,
        ).pack(side="left", padx=(2, 0))

        session_panel = tk.LabelFrame(right, text=" ⏲️  Fishing Session ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        session_panel.pack(fill="x", pady=(0, 8))
        self.fish_session_value_label = tk.Label(
            session_panel,
            text=f"Selected duration: {self.runtime.state.fish_session_minutes} min",
            font=SMALL_B,
            fg=TEAL,
            bg=PANEL,
        )
        self.fish_session_value_label.pack(anchor="w", pady=(0, 6))

        scale = tk.Scale(
            session_panel,
            from_=1,
            to=60,
            orient="horizontal",
            variable=fish_session,
            resolution=1,
            showvalue=False,
            bg=PANEL,
            fg=FG,
            troughcolor=BG,
            activebackground=BLUE,
            highlightthickness=0,
        )
        scale.pack(fill="x")

        self.fish_session_remaining_label = tk.Label(
            session_panel,
            text="Session remaining: 00:00",
            font=MONO,
            fg=ORANGE,
            bg=PANEL,
        )
        self.fish_session_remaining_label.pack(anchor="w", pady=(6, 0))

        fish_session.trace_add("write", lambda *_args: self._update_session_label(fish_session))
        self._update_session_label(fish_session)

        buttons = tk.Frame(right, bg=BG)
        buttons.pack(fill="x", pady=(0, 8))
        self.helpers["btn"](buttons, "▶ Start Fishing Session", self.services["fishing_service"].start, GREEN).pack(fill="x", pady=2)
        self.helpers["btn"](buttons, "⏹ Stop Fishing Session", self.services["fishing_service"].stop, RED).pack(fill="x", pady=2)
        tk.Label(right, text="Quick toggle hotkey: see Hotkeys tab (fish_stop)", font=SMALL, fg=ORANGE, bg=BG).pack(anchor="w")

        help_panel = tk.LabelFrame(right, text=" ℹ️  How It Works ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        help_panel.pack(fill="both", expand=True, pady=(8, 0))
        help_text = (
            "Fishing automation simulates rod casting, waits for a bite, moves to the spot, "
            "reels in, then repeats with the next saved waypoint."
        )
        tk.Label(help_panel, text=help_text, font=SMALL, fg=FG, bg=PANEL, justify="left", wraplength=380).pack(anchor="w", pady=(0, 6))
        for line in [
            "1. Record the rod position first.",
            "2. Use F12 to save one or more fishing spots.",
            "3. Recording stops 5 seconds after the last F12 press.",
            "4. Start the session; the automation repeats until stopped.",
            f"5. Timing values display in {self.helpers['get_unit_label']()}.",
        ]:
            tk.Label(help_panel, text=line, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x", pady=2)

    def _update_session_label(self, fish_session) -> None:
        if self.fish_session_value_label:
            self.fish_session_value_label.config(text=f"Selected duration: {fish_session.get()} min")

    def _on_fish_auto_restart_toggle(self, food_secs_var: tk.StringVar) -> None:
        state = self.runtime.state
        if not state.fish_auto_restart_enabled:
            food_secs_var.set("")
        else:
            try:
                val = int(food_secs_var.get())
                if val < FISH_AUTO_RESTART_FOOD_MIN_SECS_MIN:
                    food_secs_var.set(str(FISH_AUTO_RESTART_FOOD_MIN_SECS_MIN))
                elif val > FISH_AUTO_RESTART_FOOD_MIN_SECS_MAX:
                    food_secs_var.set(str(FISH_AUTO_RESTART_FOOD_MIN_SECS_MAX))
            except (ValueError, TypeError):
                food_secs_var.set(str(FISH_AUTO_RESTART_FOOD_MIN_SECS_DEFAULT))

    def record_rod_pos(self) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            self.runtime.state.fish_rod_pos = pos
            self.runtime.ui.log(f"✅ Rod pos: {pos}")
            self.runtime.ui.set_status(f"Rod pos: {pos}", GREEN)
            if self.rod_label:
                self.rod_label.config(text=f"Rod: {pos[0]}, {pos[1]}")

        self.services["position_capture"].capture(on_done, "fishing rod in bag")

    def record_spot(self) -> None:
        if self._fish_spot_recording:
            self._stop_fish_spot_recording()
            return

        self.runtime.state.fish_spots.clear()
        if self.spots_listbox:
            self.spots_listbox.delete(0, "end")

        self._fish_spot_recording = True
        if self.record_spot_btn:
            self.record_spot_btn.config(text="⏹ Stop Recording", bg=RED)
        self.runtime.ui.log("🎣 Fishing spot recording started. Press F12 to save each waypoint.")
        self.runtime.ui.set_status("Fishing spot recording active", ORANGE)
        self._start_fish_spot_listener()

    def _start_fish_spot_listener(self) -> None:
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing. Cannot record fishing spots.")
            self._fish_spot_recording = False
            if self.record_spot_btn:
                self.record_spot_btn.config(text="+ Start Recording", bg=BLUE)
            return

        self._fish_spot_listener = pynput_kb.Listener(on_press=self._on_fish_spot_key)
        self._fish_spot_listener.daemon = True
        self._fish_spot_listener.start()

    def _on_fish_spot_key(self, key) -> None:
        if not self._fish_spot_recording:
            return
        if HotkeyService.matches(key, self.runtime.state.hotkey_bindings.get("record_pos", "f12")):
            pos = pynput_mouse.Controller().position
            self.parent.after(0, lambda: self._add_fish_spot(pos))

    def _stop_fish_spot_recording(self) -> None:
        self._fish_spot_recording = False
        if self._fish_spot_listener:
            try:
                self._fish_spot_listener.stop()
            except Exception:
                logger.debug("Failed to stop fish spot listener")
            self._fish_spot_listener = None
        if self.record_spot_btn:
            self.record_spot_btn.config(text="+ Start Recording", bg=BLUE)
        count = len(self.runtime.state.fish_spots)
        self.runtime.ui.log(f"🎣 Fishing spot recording stopped. {count} positions saved.")
        self.runtime.ui.set_status(f"Recording stopped: {count} spots", RED)

    def _add_fish_spot(self, pos: tuple[int, int] | None = None) -> None:
        def on_done(captured_pos: tuple[int, int]) -> None:
            self.runtime.state.fish_spots.append(captured_pos)
            count = len(self.runtime.state.fish_spots)
            self.runtime.ui.log(f"✅ Spot #{count}: {captured_pos}")
            self.runtime.ui.set_status(f"Spot #{count} added", GREEN)
            if self.spots_listbox:
                self.spots_listbox.insert("end", f"#{count}  {captured_pos[0]},{captured_pos[1]}")

        if pos is not None:
            on_done(pos)
            return

        next_index = len(self.runtime.state.fish_spots) + 1
        self.services["position_capture"].capture(on_done, f"fishing spot #{next_index}")

    def remove_selected_spot(self) -> None:
        if not self.spots_listbox:
            return
        selection = self.spots_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.runtime.state.fish_spots):
            self.runtime.state.fish_spots.pop(index)
        self.spots_listbox.delete(index)
        items = list(self.spots_listbox.get(0, "end"))
        self.spots_listbox.delete(0, "end")
        for idx, item in enumerate(items):
            coords = item.split("  ", 1)[-1]
            self.spots_listbox.insert("end", f"#{idx + 1}  {coords}")

    def clear_spots(self) -> None:
        self.runtime.state.fish_spots.clear()
        if self.spots_listbox:
            self.spots_listbox.delete(0, "end")
        self.runtime.ui.log("🗑️  Spots cleared")

    def poll_settings(self, state) -> None:
        state.fish_cast_min_ms = self.helpers["get_ui_ms"]("fish_cast_min_var", state.fish_cast_min_ms)
        state.fish_cast_max_ms = self.helpers["get_ui_ms"]("fish_cast_max_var", state.fish_cast_max_ms)
        state.fish_wait_min_ms = self.helpers["get_ui_ms"]("fish_wait_min_var", state.fish_wait_min_ms)
        state.fish_wait_max_ms = self.helpers["get_ui_ms"]("fish_wait_max_var", state.fish_wait_max_ms)
        state.fish_min_cap = max(NON_NEGATIVE_INT_MIN, self.helpers["get_ui_int"]("fish_min_cap_var", state.fish_min_cap))
        state.fish_rod_jitter = self.helpers["get_ui_int"]("fish_rod_jit_var", state.fish_rod_jitter)
        state.fish_spot_jitter = self.helpers["get_ui_int"]("fish_spot_jit_var", state.fish_spot_jitter)
        state.fish_session_minutes = max(1, min(60, self.helpers["get_ui_int"]("fish_session_var", state.fish_session_minutes)))
        if "fish_auto_restart_enabled_var" in self.ui_vars:
            state.fish_auto_restart_enabled = bool(self.ui_vars["fish_auto_restart_enabled_var"].get())
        if "fish_auto_restart_food_secs_var" in self.ui_vars:
            value = self.helpers["get_ui_int"]("fish_auto_restart_food_secs_var", state.fish_auto_restart_food_min_secs)
            state.fish_auto_restart_food_min_secs = max(FISH_AUTO_RESTART_FOOD_MIN_SECS_MIN, min(FISH_AUTO_RESTART_FOOD_MIN_SECS_MAX, value))
        # Mouse speed multiplier — stored as raw float in UI, clamped to valid range.
        if "fish_mouse_speed_var" in self.ui_vars:
            try:
                ui_val = float(self.ui_vars["fish_mouse_speed_var"].get())
            except (ValueError, TypeError):
                ui_val = state.fishing.mouse_speed
            state.fishing.mouse_speed = max(FISH_MOUSE_SPEED_MIN, min(FISH_MOUSE_SPEED_MAX, ui_val))

    def refresh_session_display(self) -> None:
        if self.fish_session_value_label:
            self.fish_session_value_label.config(text=f"Selected duration: {self.runtime.state.fish_session_minutes} min")
        if self.fish_session_remaining_label:
            total_seconds = self.runtime.state.fish_session_remaining_secs
            if self.runtime.state.fish_active and self.runtime.state.fish_session_deadline is not None:
                total_seconds = max(0, int(self.runtime.state.fish_session_deadline - self.helpers["monotonic"]() + 0.999))
            minutes, seconds = divmod(max(0, total_seconds), 60)
            self.fish_session_remaining_label.config(text=f"Session remaining: {minutes:02d}:{seconds:02d}")

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.rod_label:
            self.rod_label.config(text=f"Rod: {state.fish_rod_pos[0]}, {state.fish_rod_pos[1]}")
        if self.spots_listbox:
            self.spots_listbox.delete(0, "end")
            for index, spot in enumerate(state.fish_spots, start=1):
                self.spots_listbox.insert("end", f"#{index}  {spot[0]},{spot[1]}")
        # Sync mouse speed input field back from state (in case config changed externally).
        if "fish_mouse_speed_var" in self.ui_vars:
            try:
                current = float(self.ui_vars["fish_mouse_speed_var"].get())
            except (ValueError, TypeError):
                current = state.fishing.mouse_speed
            # Only update if the values differ significantly (>0.1) to avoid flicker.
            if abs(current - state.fishing.mouse_speed) > 0.1:
                self.ui_vars["fish_mouse_speed_var"].set(str(round(state.fishing.mouse_speed, 1)))
        self.refresh_session_display()
