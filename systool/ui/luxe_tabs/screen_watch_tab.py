"""Luxe (CTk) screen watch tab — ported from tkinter ScreenWatchTab."""

from __future__ import annotations

import os
import customtkinter as ctk
from tkinter import filedialog


class ScreenWatchTab:
    """Owns the screen watch tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.alarm_region_label: ctk.CTkLabel | None = None
        self.battle_region_label: ctk.CTkLabel | None = None

        self._build()

    def _build(self) -> None:
        wrapper = self.helpers["create_scrollable_content"](self.parent, padx=16, pady=10)

        panel = ctk.CTkFrame(wrapper, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        panel.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(panel, text="Screen Change Watch",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=14, pady=(10, 2))
        self.helpers["register_module_indicator"](panel, "alarm", self.runtime.state.alarm_active)

        area_row = ctk.CTkFrame(panel, fg_color="transparent")
        area_row.pack(fill="x", padx=14, pady=4)
        r = self.runtime.state.alarm_region
        label_text = f"Area: ({r[0]},{r[1]}) {r[2]}x{r[3]} px" if r else "Area: centre 200x200 px (default)"
        self.alarm_region_label = ctk.CTkLabel(area_row, text=label_text,
                                                font=ctk.CTkFont(size=10, family="Consolas"),
                                                text_color="#5ac8fa", anchor="w")
        self.alarm_region_label.pack(side="left")

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 6))
        self.helpers["btn"](buttons, "🖱  Select Area (drag)", self.select_alarm_area, "#0a84ff").pack(side="left", padx=2)
        self.helpers["btn"](buttons, "↺  Reset", self.reset_alarm_area, "#ff9f0a").pack(side="left", padx=2)

        # ── Battle Window Reaction ──
        battle_section = ctk.CTkFrame(panel, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        battle_section.pack(fill="x", padx=14, pady=(6, 10))
        ctk.CTkLabel(battle_section, text="Battle Window Reaction",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(6, 2))
        battle_enabled = ctk.BooleanVar(value=self.runtime.state.alarm_battle_enabled)
        self.ui_vars["battle_enabled_var"] = battle_enabled
        ctk.CTkCheckBox(battle_section, text="Enable Battle Window Reaction (CTRL+Q)",
                         variable=battle_enabled,
                         fg_color="#0a84ff", text_color="#5ac8fa",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10)

        battle_area_row = ctk.CTkFrame(battle_section, fg_color="transparent")
        battle_area_row.pack(fill="x", padx=10, pady=(6, 4))
        b = self.runtime.state.alarm_battle_region
        battle_label = f"Battle Area: ({b[0]},{b[1]}) {b[2]}x{b[3]} px" if b else "Battle Area: not selected"
        self.battle_region_label = ctk.CTkLabel(battle_area_row, text=battle_label,
                                                 font=ctk.CTkFont(size=10, family="Consolas"),
                                                 text_color="#5ac8fa", anchor="w")
        self.battle_region_label.pack(side="left")

        battle_buttons = ctk.CTkFrame(battle_section, fg_color="transparent")
        battle_buttons.pack(fill="x", padx=10, pady=(0, 6))
        self.helpers["btn"](battle_buttons, "🎯 Select Battle Area", self.select_battle_area, "#0a84ff").pack(side="left", padx=2)

        battle_threshold = ctk.StringVar(value=str(int(self.runtime.state.alarm_battle_threshold * 100)))
        self.ui_vars["battle_thresh_var"] = battle_threshold
        self.helpers["label_entry"](battle_section, "Battle Change Threshold (%):", battle_threshold, width=6)

        battle_popup_timeout = ctk.StringVar(value=str(self.runtime.state.alarm.battle_logout_popup_timeout_sec))
        self.ui_vars["battle_popup_timeout_var"] = battle_popup_timeout
        self.helpers["label_entry"](battle_section, "Logout popup timeout (sec, 0=manual):", battle_popup_timeout, width=8)

        # ── Alert settings ──
        mp3_row = ctk.CTkFrame(panel, fg_color="transparent")
        mp3_row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(mp3_row, text="Alert sound:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8").pack(side="left")
        alarm_mp3 = ctk.StringVar(value=self.runtime.state.alarm_mp3)
        self.ui_vars["alarm_mp3_var"] = alarm_mp3
        ctk.CTkEntry(mp3_row, textvariable=alarm_mp3, width=280,
                      fg_color="#1a1a1a", border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=6, fill="x", expand=True)
        self.helpers["btn"](mp3_row, "Browse", self.browse_alarm_sound, "#bf5af2").pack(side="left")

        alarm_threshold = ctk.StringVar(value=str(int(self.runtime.state.alarm_threshold * 100)))
        alarm_hp_value = ctk.StringVar(value=str(self.runtime.state.alarm_hp_value))
        alarm_mp_value = ctk.StringVar(value=str(self.runtime.state.alarm_mp_value))
        alarm_cap_value = ctk.StringVar(value=str(self.runtime.state.alarm_cap_value))
        self.ui_vars["alarm_thresh_var"] = alarm_threshold
        self.ui_vars["alarm_hp_value_var"] = alarm_hp_value
        self.ui_vars["alarm_mp_value_var"] = alarm_mp_value
        self.ui_vars["alarm_cap_value_var"] = alarm_cap_value
        self.helpers["label_entry"](panel, "Change threshold (%):", alarm_threshold, width=6)
        ctk.CTkLabel(panel, text="— or —", font=ctk.CTkFont(size=10),
                      text_color="#777777", anchor="w").pack(padx=14)
        self.helpers["label_entry"](panel, "Low HP alert (value):", alarm_hp_value, width=8)
        self.helpers["label_entry"](panel, "Low MP/Mana alert (value):", alarm_mp_value, width=8)
        self.helpers["label_entry"](panel, "Low Cap alert (value):", alarm_cap_value, width=8)

        auto_pause = ctk.BooleanVar(value=self.runtime.state.alarm_auto_pause)
        self.ui_vars["alarm_auto_pause_var"] = auto_pause
        ctk.CTkCheckBox(panel, text="Auto-pause all activities when screen watch triggers",
                         variable=auto_pause, fg_color="#ff9f0a", text_color="#ff9f0a",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=14, pady=(8, 2))
        ctk.CTkLabel(panel,
                      text="When enabled: all running features pause on screen change detection.\nWhen disabled: the alert sound plays and monitoring continues.",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="left").pack(anchor="w", padx=14)

        flash_var = ctk.BooleanVar(value=self.runtime.state.alarm_flash_window)
        self.ui_vars["alarm_flash_var"] = flash_var
        sys_sound_var = ctk.BooleanVar(value=self.runtime.state.alarm_system_sound)
        self.ui_vars["alarm_sys_sound_var"] = sys_sound_var
        ctk.CTkCheckBox(panel, text="Flash game window taskbar icon on alarm (DANGEROUS)",
                         variable=flash_var, fg_color="#5ac8fa", text_color="#5ac8fa",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=14, pady=(8, 2))
        ctk.CTkCheckBox(panel, text="Play Windows system sound (SystemAsterisk) on alarm",
                         variable=sys_sound_var, fg_color="#5ac8fa", text_color="#5ac8fa",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=14)

        action_row = ctk.CTkFrame(panel, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(10, 10))
        self.helpers["btn"](action_row, "▶  Start Watching", self.services["alarm_service"].start, "#30d158").pack(side="left", expand=True, fill="x", padx=2)
        self.helpers["btn"](action_row, "⏹  Stop", self.services["alarm_service"].stop, "#ff453a").pack(side="left", expand=True, fill="x", padx=2)

    def select_alarm_area(self) -> None:
        self.helpers["select_region"]("alarm_region", self.alarm_region_label, "Click & drag to select alarm area")

    def select_battle_area(self) -> None:
        self.helpers["select_region"]("alarm_battle_region", self.battle_region_label, "Click & drag to select battle area")

    def reset_alarm_area(self) -> None:
        self.runtime.state.alarm_region = None
        if self.alarm_region_label:
            self.alarm_region_label.configure(text="Area: centre 200x200 px (default)")
        self.runtime.ui.log("Screen watch area reset")

    def browse_alarm_sound(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.ogg"), ("All", "*.*")])
        if path:
            normalized = os.path.abspath(os.path.expanduser(path))
            self.runtime.state.alarm_mp3 = normalized
            self.ui_vars["alarm_mp3_var"].set(normalized)

    def poll_settings(self, state) -> None:
        state.alarm_threshold = self.helpers["get_ui_int"]("alarm_thresh_var", int(state.alarm_threshold * 100)) / 100.0
        state.alarm_hp_value = max(0, self.helpers["get_ui_int"]("alarm_hp_value_var", state.alarm_hp_value))
        state.alarm_mp_value = max(0, self.helpers["get_ui_int"]("alarm_mp_value_var", state.alarm_mp_value))
        state.alarm_cap_value = max(0, self.helpers["get_ui_int"]("alarm_cap_value_var", state.alarm_cap_value))
        if "alarm_auto_pause_var" in self.ui_vars:
            state.alarm_auto_pause = bool(self.ui_vars["alarm_auto_pause_var"].get())
        if "alarm_mp3_var" in self.ui_vars:
            state.alarm_mp3 = str(self.ui_vars["alarm_mp3_var"].get())
        if "alarm_flash_var" in self.ui_vars:
            state.alarm_flash_window = bool(self.ui_vars["alarm_flash_var"].get())
        if "alarm_sys_sound_var" in self.ui_vars:
            state.alarm_system_sound = bool(self.ui_vars["alarm_sys_sound_var"].get())
        if "battle_enabled_var" in self.ui_vars:
            state.alarm_battle_enabled = bool(self.ui_vars["battle_enabled_var"].get())
        if "battle_thresh_var" in self.ui_vars:
            battle_threshold_percent = self.helpers["get_ui_int"]("battle_thresh_var", int(state.alarm_battle_threshold * 100))
            state.alarm_battle_threshold = max(0, min(100, battle_threshold_percent)) / 100.0
        if "battle_popup_timeout_var" in self.ui_vars:
            state.alarm.battle_logout_popup_timeout_sec = max(0, self.helpers["get_ui_int"]("battle_popup_timeout_var", state.alarm.battle_logout_popup_timeout_sec))

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.battle_region_label:
            if state.alarm_battle_region:
                x_val, y_val, width, height = state.alarm_battle_region
                self.battle_region_label.configure(text=f"Battle Area: ({x_val},{y_val}) {width}x{height} px")
            else:
                self.battle_region_label.configure(text="Battle Area: not selected")
        if self.alarm_region_label:
            if state.alarm_region:
                x_val, y_val, width, height = state.alarm_region
                self.alarm_region_label.configure(text=f"Area: ({x_val},{y_val}) {width}x{height} px")
            else:
                self.alarm_region_label.configure(text="Area: centre 200x200 px (default)")
