"""Luxe (CTk) light control tab — ported from tkinter LightControlTab."""

from __future__ import annotations

import customtkinter as ctk


class LightControlTab:
    """Owns the light control tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.light_status_label: ctk.CTkLabel | None = None
        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent, padx=14, pady=10)
        wrapper = ctk.CTkFrame(content_frame, fg_color="transparent")
        wrapper.columnconfigure(0, weight=1)
        wrapper.grid(row=0, column=0, sticky="nsew", padx=16, pady=10)

        panel = ctk.CTkFrame(wrapper, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        panel.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(panel, text="Light Memory Control — Alpha test",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=14, pady=(10, 2))
        self.helpers["register_module_indicator"](panel, "light", self.runtime.state.light_freeze_enabled)

        light_process = ctk.StringVar(value=self.runtime.state.light_process_name)
        light_backend = ctk.StringVar(value=self.runtime.state.light_memory_backend)
        light_direct_address = ctk.StringVar(value=self.runtime.state.light_direct_address_hex)
        light_freeze_enabled = ctk.BooleanVar(value=self.runtime.state.light_freeze_enabled)
        light_custom_color = ctk.StringVar(value=str(self.runtime.state.light_custom_color_value))
        light_custom_intensity = ctk.StringVar(value=str(self.runtime.state.light_custom_intensity_value))
        light_freeze_interval = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.light_freeze_interval_ms)))

        self.ui_vars["light_process_name_var"] = light_process
        self.ui_vars["light_memory_backend_var"] = light_backend
        self.ui_vars["light_direct_address_hex_var"] = light_direct_address
        self.ui_vars["light_freeze_enabled_var"] = light_freeze_enabled
        self.ui_vars["light_custom_color_value_var"] = light_custom_color
        self.ui_vars["light_custom_intensity_value_var"] = light_custom_intensity
        self.ui_vars["light_freeze_interval_ms_var"] = light_freeze_interval

        self.helpers["label_entry"](panel, "Process name:", light_process, width=22)
        backend_row = ctk.CTkFrame(panel, fg_color="transparent")
        backend_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(backend_row, text="Memory backend:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", width=150, anchor="w").pack(side="left")
        backend_menu = ctk.CTkOptionMenu(backend_row, values=["dbvm", "studiomemuer", "pymem"],
                                          variable=light_backend,
                                          fg_color="#1a1a1a", button_color="#0a84ff",
                                          dropdown_fg_color="#252525", dropdown_text_color="#e8e8e8",
                                          dropdown_hover_color="#0a84ff")
        backend_menu.pack(side="left", padx=4)
        self.helpers["label_entry"](panel, "Target color address (hex):", light_direct_address, width=18)

        custom_row = ctk.CTkFrame(panel, fg_color="transparent")
        custom_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(custom_row, text="Custom byte values:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", width=150, anchor="w").pack(side="left")
        ctk.CTkLabel(custom_row, text="Color", font=ctk.CTkFont(size=10, weight="bold"),
                      text_color="#e8e8e8").pack(side="left", padx=(4, 3))
        ctk.CTkEntry(custom_row, textvariable=light_custom_color, width=60,
                      fg_color="#1a1a1a", border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=(0, 10))
        ctk.CTkLabel(custom_row, text="Intensity", font=ctk.CTkFont(size=10, weight="bold"),
                      text_color="#e8e8e8").pack(side="left", padx=(0, 3))
        ctk.CTkEntry(custom_row, textvariable=light_custom_intensity, width=60,
                      fg_color="#1a1a1a", border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left")

        unit = self.helpers["get_unit_label"]()
        self.helpers["label_entry"](panel, f"Freeze interval ({unit}):", light_freeze_interval, width=8)

        ctk.CTkCheckBox(panel, text="Freeze", variable=light_freeze_enabled,
                         command=self.toggle_light_freeze,
                         fg_color="#0a84ff", text_color="#e8e8e8",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=14, pady=(4, 2))

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(8, 0))
        self.helpers["btn"](buttons, "🔗  Attach", self.attach_light_process, "#0a84ff").pack(side="left", padx=2)
        self.helpers["btn"](buttons, "📖  Read Current", self.read_light_current, "#0a84ff").pack(side="left", padx=2)
        self.helpers["btn"](buttons, "Default", self.apply_light_default, "#ff9f0a").pack(side="left", padx=2)
        self.helpers["btn"](buttons, "Boosted", self.apply_light_boosted, "#30d158").pack(side="left", padx=2)
        self.helpers["btn"](buttons, "Custom", self.apply_light_custom, "#30d158").pack(side="left", padx=2)
        self.helpers["btn"](buttons, "Reset", self.reset_light_original, "#0a84ff").pack(side="left", padx=2)

        help_text = ("Leave target color address blank to use the pointer list from Light Pointers.CT. "
                     "Default writes color 215 and intensity 7. Boosted writes color 215 and intensity 8 "
                     "to the next byte. Custom writes the byte values above. Reset restores the last "
                     "unchanged pair that was captured before an apply.")
        ctk.CTkLabel(panel, text=help_text, font=ctk.CTkFont(size=10),
                      text_color="#777777", justify="left", wraplength=860).pack(padx=14, pady=(10, 4), fill="x")

        dep_text = ("Light module ready" if self.services["has_light_module"]
                    else "Install psutil and pymem to use this tab")
        self.light_status_label = ctk.CTkLabel(
            panel, text=dep_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#5ac8fa" if self.services["has_light_module"] else "#ff9f0a",
            anchor="w", justify="left", wraplength=860)
        self.light_status_label.pack(padx=14, pady=(0, 10), fill="x")

    def _set_light_status(self, success: bool, message: str) -> None:
        color = "#5ac8fa" if success else "#ff9f0a"
        if self.light_status_label:
            self.light_status_label.configure(text=message, text_color=color)
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

    def read_light_current(self) -> None:
        self.services["poll_settings_now"]()
        ok, message = self.services["light_service"].read_current()
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

    def _get_byte_value(self, var_name: str, current_value: int) -> int:
        try:
            value = int(str(self.ui_vars[var_name].get()).strip())
        except (KeyError, TypeError, ValueError):
            return current_value
        return max(0, min(255, value))

    def poll_settings(self, state) -> None:
        if "light_process_name_var" in self.ui_vars:
            state.light_process_name = str(self.ui_vars["light_process_name_var"].get()).strip()
        if "light_memory_backend_var" in self.ui_vars:
            backend = str(self.ui_vars["light_memory_backend_var"].get()).strip().lower()
            if backend == "pymem":
                state.light_memory_backend = "pymem"
            elif backend in ("studiomemuer", "driver"):
                state.light_memory_backend = "studiomemuer"
            else:
                state.light_memory_backend = "dbvm"
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
        if "light_memory_backend_var" in self.ui_vars:
            self.ui_vars["light_memory_backend_var"].set(self.runtime.state.light_memory_backend)
        if "light_custom_color_value_var" in self.ui_vars:
            self.ui_vars["light_custom_color_value_var"].set(str(self.runtime.state.light_custom_color_value))
        if "light_custom_intensity_value_var" in self.ui_vars:
            self.ui_vars["light_custom_intensity_value_var"].set(str(self.runtime.state.light_custom_intensity_value))
