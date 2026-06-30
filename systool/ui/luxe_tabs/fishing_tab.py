"""Luxe (CTk) fishing tab — ported from tkinter FishingTab."""

from __future__ import annotations

import logging
import customtkinter as ctk

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

logger = logging.getLogger(__name__)


class FishingTab:
    """Owns the fishing tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.rod_label: ctk.CTkLabel | None = None
        self.record_spot_btn: ctk.CTkButton | None = None
        self.spots_textbox: ctk.CTkTextbox | None = None
        self.fish_session_value_label: ctk.CTkLabel | None = None
        self.fish_session_remaining_label: ctk.CTkLabel | None = None
        self._fish_spot_recording = False
        self._fish_spot_listener = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        # ── Rod Position ──
        rod_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        rod_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(rod_panel, text="🎣  Rod Position",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.helpers["register_module_indicator"](rod_panel, "fish", self.runtime.state.fish_active)
        self.rod_label = ctk.CTkLabel(rod_panel,
                                       text=f"Rod: {self.runtime.state.fish_rod_pos[0]}, {self.runtime.state.fish_rod_pos[1]}",
                                       font=ctk.CTkFont(size=10, family="Consolas"),
                                       text_color="#5ac8fa", anchor="w")
        self.rod_label.pack(padx=10, pady=(0, 4))

        rod_btn_row = ctk.CTkFrame(rod_panel, fg_color="transparent")
        rod_btn_row.pack(fill="x", padx=10, pady=(0, 4))
        self.helpers["btn"](rod_btn_row, "🎯  Record Rod Pos", self.record_rod_pos, "#0a84ff").pack(side="left", padx=2)
        self.helpers["btn"](rod_btn_row, "🔍  Auto Detect Rod", self._auto_detect_rod, "#30d158").pack(side="left", padx=2)

        rod_jitter = ctk.StringVar(value=str(self.runtime.state.fish_rod_jitter))
        self.ui_vars["fish_rod_jit_var"] = rod_jitter
        self.helpers["label_entry"](rod_panel, "Rod jitter (px ±):", rod_jitter, width=5)

        # ── Fishing Positions ──
        spots_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        spots_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(spots_panel, text="🗺️  Fishing Positions",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        spot_buttons = ctk.CTkFrame(spots_panel, fg_color="transparent")
        spot_buttons.pack(fill="x", padx=10, pady=(0, 6))
        self.record_spot_btn = self.helpers["btn"](spot_buttons, "+  Start Recording", self.record_spot, "#0a84ff")
        self.record_spot_btn.pack(side="left", padx=2)
        self.helpers["btn"](spot_buttons, "✕  Remove", self.remove_selected_spot, "#ff9f0a").pack(side="left", padx=2)
        self.helpers["btn"](spot_buttons, "🗑  Clear", self.clear_spots, "#ff453a").pack(side="left", padx=2)

        self.spots_textbox = ctk.CTkTextbox(spots_panel, fg_color="#1a1a1a", text_color="#e8e8e8",
                                             font=ctk.CTkFont(size=10, family="Consolas"),
                                             border_width=1, border_color="#3a3a3a", height=140)
        self.spots_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        self._refresh_spots_display()

        spot_jitter = ctk.StringVar(value=str(self.runtime.state.fish_spot_jitter))
        self.ui_vars["fish_spot_jit_var"] = spot_jitter
        self.helpers["label_entry"](spots_panel, "Spot jitter (px ±):", spot_jitter, width=5)

        # ── Timing ──
        timing_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        timing_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(timing_panel, text="⏱️  Timing",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        unit = self.helpers["get_unit_label"]()
        cast_min = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_cast_min_ms)))
        cast_max = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_cast_max_ms)))
        wait_min = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_wait_min_ms)))
        wait_max = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.fish_wait_max_ms)))
        fish_session = ctk.IntVar(value=self.runtime.state.fish_session_minutes)
        self.ui_vars.update({
            "fish_cast_min_var": cast_min,
            "fish_cast_max_var": cast_max,
            "fish_wait_min_var": wait_min,
            "fish_wait_max_var": wait_max,
            "fish_session_var": fish_session,
        })
        self.helpers["label_entry"](timing_panel, f"Cast delay Min ({unit}):", cast_min)
        self.helpers["label_entry"](timing_panel, f"Cast delay Max ({unit}):", cast_max)
        self.helpers["label_entry"](timing_panel, f"Wait for bite Min ({unit}):", wait_min)
        self.helpers["label_entry"](timing_panel, f"Wait for bite Max ({unit}):", wait_max)
        fish_min_cap = ctk.StringVar(value=str(self.runtime.state.fish_min_cap))
        self.ui_vars["fish_min_cap_var"] = fish_min_cap
        self.helpers["label_entry"](timing_panel, "Stop below cap:", fish_min_cap, width=6)

        fish_auto_restart_enabled = ctk.BooleanVar(value=self.runtime.state.fish_auto_restart_enabled)
        fish_auto_restart_food_secs = ctk.StringVar(value=str(self.runtime.state.fish_auto_restart_food_min_secs))
        self.ui_vars["fish_auto_restart_enabled_var"] = fish_auto_restart_enabled
        self.ui_vars["fish_auto_restart_food_secs_var"] = fish_auto_restart_food_secs

        ar_frame = ctk.CTkFrame(timing_panel, fg_color="transparent")
        ar_frame.pack(fill="x", padx=10, pady=2)
        ctk.CTkCheckBox(ar_frame, text="", variable=fish_auto_restart_enabled,
                         command=lambda: self._on_fish_auto_restart_toggle(fish_auto_restart_food_secs),
                         fg_color="#0a84ff").pack(side="left")
        ctk.CTkLabel(ar_frame, text="Auto-restart session when food drops below:",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8").pack(side="left", padx=(8, 4))
        ctk.CTkEntry(ar_frame, textvariable=fish_auto_restart_food_secs, width=60,
                      fg_color="#1a1a1a", border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left")
        ctk.CTkLabel(ar_frame, text="sec", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#5ac8fa").pack(side="left", padx=2)

        # Mouse speed
        fish_mouse_speed_var = ctk.StringVar(value=str(self.runtime.state.fish_mouse_speed))
        self.ui_vars["fish_mouse_speed_var"] = fish_mouse_speed_var
        ms_frame = ctk.CTkFrame(timing_panel, fg_color="transparent")
        ms_frame.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(ms_frame, text="Mouse Speed (×):", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8").pack(side="left")
        ctk.CTkEntry(ms_frame, textvariable=fish_mouse_speed_var, width=60,
                      fg_color="#1a1a1a", border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=(8, 4))
        ctk.CTkLabel(ms_frame, text=f"(range: {FISH_MOUSE_SPEED_MIN}–{FISH_MOUSE_SPEED_MAX})",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#777777").pack(side="left")

        # ── Fishing Session ──
        session_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        session_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(session_panel, text="⏲️  Fishing Session",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.fish_session_value_label = ctk.CTkLabel(
            session_panel,
            text=f"Selected duration: {self.runtime.state.fish_session_minutes} min",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#5ac8fa", anchor="w")
        self.fish_session_value_label.pack(padx=10, pady=(0, 6))

        slider = ctk.CTkSlider(session_panel, from_=1, to=60,
                                variable=fish_session, number_of_steps=59,
                                fg_color="#3a3a3a", progress_color="#0a84ff",
                                command=lambda v: self._update_session_label(v, fish_session))
        slider.pack(fill="x", padx=10)

        self.fish_session_remaining_label = ctk.CTkLabel(
            session_panel,
            text="Session remaining: 00:00",
            font=ctk.CTkFont(size=10, family="Consolas"),
            text_color="#ff9f0a", anchor="w")
        self.fish_session_remaining_label.pack(padx=10, pady=(6, 8))

        fish_session.trace_add("write", lambda *_args: self._update_session_label(int(fish_session.get()), fish_session))

        buttons = ctk.CTkFrame(right, fg_color="transparent")
        buttons.pack(fill="x", pady=(0, 8))
        self.helpers["btn"](buttons, "▶  Start Fishing Session", self.services["fishing_service"].start, "#30d158").pack(fill="x", pady=2)
        self.helpers["btn"](buttons, "⏹  Stop Fishing Session", self.services["fishing_service"].stop, "#ff453a").pack(fill="x", pady=2)
        ctk.CTkLabel(right, text="Quick toggle hotkey: see Hotkeys tab (fish_stop)",
                      font=ctk.CTkFont(size=10), text_color="#ff9f0a", anchor="w").pack(padx=10)

        # ── Help ──
        help_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        help_panel.pack(fill="both", expand=True, pady=(8, 0))
        ctk.CTkLabel(help_panel, text="ℹ️  How It Works",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        help_text = ("Fishing automation simulates rod casting, waits for a bite, moves to the spot, "
                     "reels in, then repeats with the next saved waypoint.")
        ctk.CTkLabel(help_panel, text=help_text, font=ctk.CTkFont(size=10),
                      text_color="#e8e8e8", justify="left", wraplength=380).pack(padx=10, pady=(0, 6))
        for line in [
            "1. Record the rod position first.",
            "2. Use F12 to save one or more fishing spots.",
            "3. Recording stops 5 seconds after the last F12 press.",
            "4. Start the session; the automation repeats until stopped.",
            f"5. Timing values display in {self.helpers['get_unit_label']()}.",
        ]:
            ctk.CTkLabel(help_panel, text=line, font=ctk.CTkFont(size=10),
                          text_color="#777777", justify="left", anchor="w").pack(padx=10, fill="x", pady=2)

    def _refresh_spots_display(self) -> None:
        if not self.spots_textbox:
            return
        self.spots_textbox.delete("0.0", "end")
        for idx, spot in enumerate(self.runtime.state.fish_spots, start=1):
            self.spots_textbox.insert("end", f"#{idx}  {spot[0]},{spot[1]}\n")

    def _update_session_label(self, value, fish_session=None) -> None:
        if self.fish_session_value_label:
            self.fish_session_value_label.configure(text=f"Selected duration: {int(fish_session.get()) if fish_session else value} min")

    def _on_fish_auto_restart_toggle(self, food_secs_var: ctk.StringVar) -> None:
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
            self.runtime.ui.set_status(f"Rod pos: {pos}", "#30d158")
            if self.rod_label:
                self.rod_label.configure(text=f"Rod: {pos[0]}, {pos[1]}")

        self.services["position_capture"].capture(on_done, "fishing rod in bag")

    def _auto_detect_rod(self) -> None:
        from ...services.image_finder import find_item_in_inventory, list_available_tools, HAS_CV2

        if not HAS_CV2:
            self.runtime.ui.log("❌ OpenCV not available — cannot auto-detect")
            return

        tools = list_available_tools()
        rod_images = [t for t in tools if "rod" in t.lower() or "FishingRod" == t]
        if not rod_images:
            self.runtime.ui.log("⚠️  No rod images found in images/Items/Frames/Tools/")
            return

        rod_name = rod_images[0]
        self.runtime.ui.log(f"🔍 Searching for {rod_name} in inventory...")
        pos = find_item_in_inventory(rod_name, inventory_region=None, precision=0.85, use_frame=True)
        if pos is None:
            pos = find_item_in_inventory(rod_name, inventory_region=None, precision=0.8, use_frame=False)

        if pos is not None:
            self.runtime.state.fish_rod_pos = pos
            self.runtime.ui.log(f"✅ Rod auto-detected at {pos}")
            self.runtime.ui.set_status(f"Rod auto-detected: {pos}", "#30d158")
            if self.rod_label:
                self.rod_label.configure(text=f"Rod: {pos[0]}, {pos[1]}")
        else:
            self.runtime.ui.log("❌ Could not find fishing rod on screen. Make sure your inventory is visible.")
            self.runtime.ui.set_status("Rod not found", "#ff9f0a")

    def record_spot(self) -> None:
        if self._fish_spot_recording:
            self._stop_fish_spot_recording()
            return

        self.runtime.state.fish_spots.clear()
        if self.spots_textbox:
            self.spots_textbox.delete("0.0", "end")

        self._fish_spot_recording = True
        if self.record_spot_btn:
            self.record_spot_btn.configure(text="⏹  Stop Recording", fg_color="#ff453a")
        self.runtime.ui.log("🎣 Fishing spot recording started. Press F12 to save each waypoint.")
        self.runtime.ui.set_status("Fishing spot recording active", "#ff9f0a")
        self._start_fish_spot_listener()

    def _start_fish_spot_listener(self) -> None:
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing. Cannot record fishing spots.")
            self._fish_spot_recording = False
            if self.record_spot_btn:
                self.record_spot_btn.configure(text="+  Start Recording", fg_color="#0a84ff")
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
            self.record_spot_btn.configure(text="+  Start Recording", fg_color="#0a84ff")
        count = len(self.runtime.state.fish_spots)
        self.runtime.ui.log(f"🎣 Fishing spot recording stopped. {count} positions saved.")
        self.runtime.ui.set_status(f"Recording stopped: {count} spots", "#ff453a")

    def _add_fish_spot(self, pos: tuple[int, int] | None = None) -> None:
        def on_done(captured_pos: tuple[int, int]) -> None:
            self.runtime.state.fish_spots.append(captured_pos)
            count = len(self.runtime.state.fish_spots)
            self.runtime.ui.log(f"✅ Spot #{count}: {captured_pos}")
            self.runtime.ui.set_status(f"Spot #{count} added", "#30d158")
            if self.spots_textbox:
                self.spots_textbox.insert("end", f"#{count}  {captured_pos[0]},{captured_pos[1]}\n")

        if pos is not None:
            on_done(pos)
            return

        next_index = len(self.runtime.state.fish_spots) + 1
        self.services["position_capture"].capture(on_done, f"fishing spot #{next_index}")

    def remove_selected_spot(self) -> None:
        if not self.spots_textbox:
            return
        try:
            cursor_pos = self.spots_textbox.index("insert")
            line = int(cursor_pos.split(".")[0])
        except Exception:
            return
        spots = self.runtime.state.fish_spots
        if 1 <= line <= len(spots):
            spots.pop(line - 1)
        self._refresh_spots_display()

    def clear_spots(self) -> None:
        self.runtime.state.fish_spots.clear()
        if self.spots_textbox:
            self.spots_textbox.delete("0.0", "end")
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
        if "fish_mouse_speed_var" in self.ui_vars:
            try:
                ui_val = float(self.ui_vars["fish_mouse_speed_var"].get())
            except (ValueError, TypeError):
                ui_val = state.fishing.mouse_speed
            state.fishing.mouse_speed = max(FISH_MOUSE_SPEED_MIN, min(FISH_MOUSE_SPEED_MAX, ui_val))

    def refresh_session_display(self) -> None:
        if self.fish_session_value_label:
            self.fish_session_value_label.configure(text=f"Selected duration: {self.runtime.state.fish_session_minutes} min")
        if self.fish_session_remaining_label:
            total_seconds = self.runtime.state.fish_session_remaining_secs
            if self.runtime.state.fish_active and self.runtime.state.fish_session_deadline is not None:
                total_seconds = max(0, int(self.runtime.state.fish_session_deadline - self.helpers["monotonic"]() + 0.999))
            minutes, seconds = divmod(max(0, total_seconds), 60)
            self.fish_session_remaining_label.configure(text=f"Session remaining: {minutes:02d}:{seconds:02d}")

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.rod_label:
            self.rod_label.configure(text=f"Rod: {state.fish_rod_pos[0]}, {state.fish_rod_pos[1]}")
        self._refresh_spots_display()
        if "fish_mouse_speed_var" in self.ui_vars:
            try:
                current = float(self.ui_vars["fish_mouse_speed_var"].get())
            except (ValueError, TypeError):
                current = state.fishing.mouse_speed
            if abs(current - state.fishing.mouse_speed) > 0.1:
                self.ui_vars["fish_mouse_speed_var"].set(str(round(state.fishing.mouse_speed, 1)))
        self.refresh_session_display()
