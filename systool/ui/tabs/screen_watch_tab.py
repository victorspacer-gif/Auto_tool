"""Screen watch tab UI for SystemMonitor."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog

from ...theme import BLUE, BOLD, FG, GREEN, MONO, MUTED, ORANGE, PANEL, PURPLE, RED, SMALL, TEAL


class ScreenWatchTab:
    """Owns the screen watch tab UI and tab-local behavior."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.alarm_region_label: tk.Label | None = None
        self.battle_region_label: tk.Label | None = None

        self._build()

    def _build(self) -> None:
        wrapper = self.helpers["create_scrollable_content"](self.parent, padx=16, pady=10)
        panel = tk.LabelFrame(wrapper, text=" Screen Change Watch ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=10, padx=14)
        panel.grid(row=0, column=0, sticky="ew")
        self.helpers["register_module_indicator"](panel, "alarm", self.runtime.state.alarm_active)
        area_row = tk.Frame(panel, bg=PANEL)
        area_row.pack(fill="x", pady=4)
        self.alarm_region_label = tk.Label(area_row, text="Area: centre 200x200 px (default)", font=MONO, fg=TEAL, bg=PANEL)
        self.alarm_region_label.pack(side="left")
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(0, 8))
        self.helpers["btn"](buttons, "Select Area (drag)", self.select_alarm_area, BLUE).pack(side="left", padx=(0, 6))
        self.helpers["btn"](buttons, "Reset", self.reset_alarm_area, ORANGE).pack(side="left")

        battle_section = tk.LabelFrame(panel, text=" Battle Window Reaction ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        battle_section.pack(fill="x", pady=(6, 10))
        battle_enabled = tk.BooleanVar(value=self.runtime.state.alarm_battle_enabled)
        self.ui_vars["battle_enabled_var"] = battle_enabled
        tk.Checkbutton(
            battle_section,
            text="Enable Battle Window Reaction (CTRL+Q)",
            variable=battle_enabled,
            font=BOLD,
            bg=PANEL,
            fg=TEAL,
            selectcolor=PANEL,
            activebackground=PANEL,
            activeforeground=TEAL,
        ).pack(anchor="w")
        battle_area_row = tk.Frame(battle_section, bg=PANEL)
        battle_area_row.pack(fill="x", pady=(6, 4))
        self.battle_region_label = tk.Label(battle_area_row, text="Battle Area: not selected", font=MONO, fg=TEAL, bg=PANEL)
        self.battle_region_label.pack(side="left")
        battle_buttons = tk.Frame(battle_section, bg=PANEL)
        battle_buttons.pack(fill="x", pady=(0, 6))
        self.helpers["btn"](battle_buttons, "Select Battle Area", self.select_battle_area, BLUE).pack(side="left", padx=(0, 6))
        battle_threshold = tk.StringVar(value=str(int(self.runtime.state.alarm_battle_threshold * 100)))
        self.ui_vars["battle_thresh_var"] = battle_threshold
        self.helpers["label_entry"](battle_section, "Battle Change Threshold (%):", battle_threshold, width=6)
        battle_popup_timeout = tk.StringVar(value=str(self.runtime.state.alarm.battle_logout_popup_timeout_sec))
        self.ui_vars["battle_popup_timeout_var"] = battle_popup_timeout
        self.helpers["label_entry"](battle_section, "Logout popup timeout (sec, 0=manual):", battle_popup_timeout, width=8)

        mp3_row = tk.Frame(panel, bg=PANEL)
        mp3_row.pack(fill="x", pady=4)
        tk.Label(mp3_row, text="Alert sound:", font=BOLD, fg=FG, bg=PANEL).pack(side="left")
        alarm_mp3 = tk.StringVar(value=self.runtime.state.alarm_mp3)
        self.ui_vars["alarm_mp3_var"] = alarm_mp3
        self.helpers["entry"](mp3_row, alarm_mp3, 32).pack(side="left", padx=6, fill="x", expand=True)
        self.helpers["btn"](mp3_row, "Browse", self.browse_alarm_sound, PURPLE).pack(side="left")

        alarm_threshold = tk.StringVar(value=str(int(self.runtime.state.alarm_threshold * 100)))
        alarm_hp_value = tk.StringVar(value=str(self.runtime.state.alarm_hp_value))
        alarm_mp_value = tk.StringVar(value=str(self.runtime.state.alarm_mp_value))
        alarm_cap_value = tk.StringVar(value=str(self.runtime.state.alarm_cap_value))
        self.ui_vars["alarm_thresh_var"] = alarm_threshold
        self.ui_vars["alarm_hp_value_var"] = alarm_hp_value
        self.ui_vars["alarm_mp_value_var"] = alarm_mp_value
        self.ui_vars["alarm_cap_value_var"] = alarm_cap_value
        self.helpers["label_entry"](panel, "Change threshold (%):", alarm_threshold, width=6)
        tk.Label(panel, text="- or -", font=SMALL, fg=MUTED, bg=PANEL).pack(anchor="w")
        self.helpers["label_entry"](panel, "Low HP alert (value):", alarm_hp_value, width=8)
        self.helpers["label_entry"](panel, "Low MP/Mana alert (value):", alarm_mp_value, width=8)
        self.helpers["label_entry"](panel, "Low Cap alert (value):", alarm_cap_value, width=8)
        auto_pause = tk.BooleanVar(value=self.runtime.state.alarm_auto_pause)
        self.ui_vars["alarm_auto_pause_var"] = auto_pause
        tk.Checkbutton(panel, text="Auto-pause all activities when screen watch triggers", variable=auto_pause, font=BOLD, bg=PANEL, fg=ORANGE, selectcolor=PANEL, activebackground=PANEL, activeforeground=ORANGE).pack(anchor="w", pady=(8, 2))
        tk.Label(panel, text="When enabled: all running features pause on screen change detection.\nWhen disabled: the alert sound plays and monitoring continues.", font=SMALL, fg=MUTED, bg=PANEL, justify="left").pack(anchor="w")

        flash_var = tk.BooleanVar(value=self.runtime.state.alarm_flash_window)
        self.ui_vars["alarm_flash_var"] = flash_var
        sys_sound_var = tk.BooleanVar(value=self.runtime.state.alarm_system_sound)
        self.ui_vars["alarm_sys_sound_var"] = sys_sound_var
        tk.Checkbutton(panel, text="Flash game window taskbar icon on alarm", variable=flash_var, font=BOLD, bg=PANEL, fg=TEAL, selectcolor=PANEL, activebackground=PANEL, activeforeground=TEAL).pack(anchor="w", pady=(8, 2))
        tk.Checkbutton(panel, text="Play Windows system sound (SystemAsterisk) on alarm", variable=sys_sound_var, font=BOLD, bg=PANEL, fg=TEAL, selectcolor=PANEL, activebackground=PANEL).pack(anchor="w")

        action_row = tk.Frame(panel, bg=PANEL)
        action_row.pack(fill="x", pady=(10, 0))
        self.helpers["btn"](action_row, "Start Watching", self.services["alarm_service"].start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self.helpers["btn"](action_row, "Stop", self.services["alarm_service"].stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def select_alarm_area(self) -> None:
        self.helpers["select_region"]("alarm_region", self.alarm_region_label, "Click & drag to select alarm area")

    def select_battle_area(self) -> None:
        self.helpers["select_region"]("alarm_battle_region", self.battle_region_label, "Click & drag to select battle area")

    def reset_alarm_area(self) -> None:
        self.runtime.state.alarm_region = None
        if self.alarm_region_label:
            self.alarm_region_label.config(text="Area: centre 200x200 px (default)")
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
                self.battle_region_label.config(text=f"Battle Area: ({x_val},{y_val}) {width}x{height} px")
            else:
                self.battle_region_label.config(text="Battle Area: not selected")
        if self.alarm_region_label:
            if state.alarm_region:
                x_val, y_val, width, height = state.alarm_region
                self.alarm_region_label.config(text=f"Area: ({x_val},{y_val}) {width}x{height} px")
            else:
                self.alarm_region_label.config(text="Area: centre 200x200 px (default)")
