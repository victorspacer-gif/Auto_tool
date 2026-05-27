"""Light control tab UI for SystemMonitor."""

from __future__ import annotations

import tkinter as tk

from ...theme import BG, BLUE, BOLD, FG, GREEN, ORANGE, PANEL, SMALL, SMALL_B, TEAL


class LightControlTab:
    """Owns the light control tab UI and tab-local behavior."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.light_status_label: tk.Label | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        wrapper = tk.Frame(content_frame, bg=BG)
        wrapper.columnconfigure(0, weight=1)
        wrapper.grid(row=0, column=0, sticky="nsew", padx=16, pady=10)
        panel = tk.LabelFrame(wrapper, text=" Light Memory Control - Alpha test ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=10, padx=14)
        panel.grid(row=0, column=0, sticky="ew")
        self.helpers["register_module_indicator"](panel, "light", self.runtime.state.light_freeze_enabled)
        light_process = tk.StringVar(value=self.runtime.state.light_process_name)
        light_direct_address = tk.StringVar(value=self.runtime.state.light_direct_address_hex)
        light_freeze_enabled = tk.BooleanVar(value=self.runtime.state.light_freeze_enabled)
        light_custom_color = tk.StringVar(value=str(self.runtime.state.light_custom_color_value))
        light_custom_intensity = tk.StringVar(value=str(self.runtime.state.light_custom_intensity_value))
        light_freeze_interval = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.light_freeze_interval_ms)))
        self.ui_vars["light_process_name_var"] = light_process
        self.ui_vars["light_direct_address_hex_var"] = light_direct_address
        self.ui_vars["light_freeze_enabled_var"] = light_freeze_enabled
        self.ui_vars["light_custom_color_value_var"] = light_custom_color
        self.ui_vars["light_custom_intensity_value_var"] = light_custom_intensity
        self.ui_vars["light_freeze_interval_ms_var"] = light_freeze_interval
        self.helpers["label_entry"](panel, "Process name:", light_process, width=22)
        self.helpers["label_entry"](panel, "Target color address (hex):", light_direct_address, width=18)
        custom_row = tk.Frame(panel, bg=PANEL)
        custom_row.pack(fill="x", pady=2)
        tk.Label(custom_row, text="Custom byte values:", font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        tk.Label(custom_row, text="Color", font=SMALL_B, fg=FG, bg=PANEL).pack(side="left", padx=(4, 3))
        tk.Entry(custom_row, textvariable=light_custom_color, width=5, bg=BG, fg=FG, font=SMALL, insertbackground=FG, relief="flat", bd=2).pack(side="left", padx=(0, 10))
        tk.Label(custom_row, text="Intensity", font=SMALL_B, fg=FG, bg=PANEL).pack(side="left", padx=(0, 3))
        tk.Entry(custom_row, textvariable=light_custom_intensity, width=5, bg=BG, fg=FG, font=SMALL, insertbackground=FG, relief="flat", bd=2).pack(side="left")
        unit = self.helpers["get_unit_label"]()
        self.helpers["label_entry"](panel, f"Freeze interval ({unit}):", light_freeze_interval, width=8)
        tk.Checkbutton(
            panel,
            text="Freeze",
            variable=light_freeze_enabled,
            command=self.toggle_light_freeze,
            font=BOLD,
            fg=FG,
            bg=PANEL,
            selectcolor=PANEL,
            activebackground=PANEL,
            activeforeground=FG,
        ).pack(anchor="w", pady=(4, 2))
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(8, 0))
        self.helpers["btn"](buttons, "Attach", self.attach_light_process, BLUE, padx=10, pady=3).pack(side="left", padx=(0, 6))
        self.helpers["btn"](buttons, "Default", self.apply_light_default, ORANGE, padx=10, pady=3).pack(side="left", padx=(0, 6))
        self.helpers["btn"](buttons, "Boosted", self.apply_light_boosted, GREEN, padx=10, pady=3).pack(side="left", padx=(0, 6))
        self.helpers["btn"](buttons, "Custom", self.apply_light_custom, GREEN, padx=10, pady=3).pack(side="left", padx=(0, 6))
        self.helpers["btn"](buttons, "Reset", self.reset_light_original, BLUE, padx=10, pady=3).pack(side="left")
        help_label = tk.Label(panel, text="Leave target color address blank to use the pointer list from Light Pointers.CT. Default writes color 215 and intensity 7. Boosted writes color 215 and intensity 8 to the next byte. Custom writes the byte values above. Reset restores the last unchanged pair that was captured before an apply.", font=SMALL, fg=self.helpers["muted"], bg=PANEL, justify="left", wraplength=860)
        help_label.pack(anchor="w", fill="x", pady=(10, 6))
        dep_text = "Light module ready" if self.services["has_light_module"] else "Install psutil and pymem to use this tab"
        self.light_status_label = tk.Label(panel, text=dep_text, font=SMALL_B, fg=TEAL if self.services["has_light_module"] else ORANGE, bg=PANEL, anchor="w", justify="left", wraplength=860)
        self.light_status_label.pack(fill="x")
        panel.bind("<Configure>", lambda event: self._wrap_light_text(event.width, help_label))

    def _set_light_status(self, success: bool, message: str) -> None:
        color = TEAL if success else ORANGE
        if self.light_status_label:
            self.light_status_label.config(text=message, fg=color)
        self.runtime.ui.log(("OK " if success else "FAIL ") + message)

    def attach_light_process(self) -> None:
        self.services["poll_settings_now"]()
        self.services["save_current_character_profile"](log_success=False)
        ok, message = self.services["light_service"].attach()
        if ok and self.services["hp_service"] is not None:
            try:
                hp_ok, hp_msg = self.services["hp_service"].attach()
                if hp_ok:
                    message += f" | {hp_msg}"
            except Exception as exc:
                message += f" | HP attach warning: {exc}"
        if ok and self.services["mp_service"] is not None:
            try:
                mp_ok, mp_msg = self.services["mp_service"].attach()
                if mp_ok:
                    message += f" | {mp_msg}"
            except Exception as exc:
                message += f" | MP attach warning: {exc}"
        if ok and self.services["cap_service"] is not None:
            try:
                cap_ok, cap_msg = self.services["cap_service"].attach()
                if cap_ok:
                    message += f" | {cap_msg}"
            except Exception as exc:
                message += f" | Cap attach warning: {exc}"
        if ok:
            try:
                profile_message = self.services["load_or_create_attached_character_profile"]()
                if profile_message:
                    message += f" | {profile_message}"
            except Exception as exc:
                message += f" | Character profile warning: {exc}"
        self._set_light_status(ok, message)

    def toggle_light_freeze(self) -> None:
        enabled = bool(self.ui_vars.get("light_freeze_enabled_var").get()) if "light_freeze_enabled_var" in self.ui_vars else False
        ok, message = self.services["light_service"].set_freeze_enabled(enabled)
        self.helpers["refresh_module_indicator"]("light", enabled and ok)
        self._set_light_status(ok, message)

    def apply_light_default(self) -> None:
        ok, message = self.services["light_service"].apply_default()
        self._set_light_status(ok, message)

    def apply_light_boosted(self) -> None:
        ok, message = self.services["light_service"].apply_boosted()
        self._set_light_status(ok, message)

    def apply_light_custom(self) -> None:
        self.services["poll_settings_now"]()
        ok, message = self.services["light_service"].apply_custom()
        self._set_light_status(ok, message)

    def reset_light_original(self) -> None:
        ok, message = self.services["light_service"].reset_original()
        self._set_light_status(ok, message)

    def _wrap_light_text(self, width: int, help_label: tk.Label) -> None:
        wraplength = max(220, width - 32)
        help_label.config(wraplength=wraplength)
        if self.light_status_label:
            self.light_status_label.config(wraplength=wraplength)

    def _get_byte_value(self, var_name: str, current_value: int) -> int:
        try:
            value = int(str(self.ui_vars[var_name].get()).strip())
        except (KeyError, TypeError, ValueError):
            return current_value
        return max(0, min(255, value))

    def poll_settings(self, state) -> None:
        if "light_process_name_var" in self.ui_vars:
            state.light_process_name = str(self.ui_vars["light_process_name_var"].get()).strip()
        if "light_direct_address_hex_var" in self.ui_vars:
            state.light_direct_address_hex = str(self.ui_vars["light_direct_address_hex_var"].get()).strip()
        state.light_custom_color_value = self._get_byte_value("light_custom_color_value_var", state.light_custom_color_value)
        state.light_custom_intensity_value = self._get_byte_value("light_custom_intensity_value_var", state.light_custom_intensity_value)
        if "light_freeze_enabled_var" in self.ui_vars:
            state.light_freeze_enabled = bool(self.ui_vars["light_freeze_enabled_var"].get())
        if "light_freeze_interval_ms_var" in self.ui_vars:
            state.light_freeze_interval_ms = max(30, self.helpers["get_ui_ms"]("light_freeze_interval_ms_var", state.light_freeze_interval_ms))

    def refresh_from_state(self) -> None:
        if "light_freeze_enabled_var" in self.ui_vars:
            self.ui_vars["light_freeze_enabled_var"].set(self.runtime.state.light_freeze_enabled)
        if "light_custom_color_value_var" in self.ui_vars:
            self.ui_vars["light_custom_color_value_var"].set(str(self.runtime.state.light_custom_color_value))
        if "light_custom_intensity_value_var" in self.ui_vars:
            self.ui_vars["light_custom_intensity_value_var"].set(str(self.runtime.state.light_custom_intensity_value))
