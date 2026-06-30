"""Luxe (CTk) hotkeys tab — ported from tkinter HotkeysTab."""

from __future__ import annotations

import customtkinter as ctk


class HotkeysTab:
    """Owns the hotkeys tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars
        self.hotkey_vars = services["hotkey_vars"]

        self._build()

    def _build(self) -> None:
        wrapper = self.helpers["create_scrollable_content"](self.parent, padx=20, pady=16)
        ctk.CTkLabel(wrapper, text="Click Rebind then press any key to reassign a hotkey.\nConflicts are detected automatically.",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", justify="center").grid(row=0, column=0, pady=(0, 16), sticky="ew")

        inner = ctk.CTkFrame(wrapper, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        inner.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(inner, text="Current Bindings",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=14, pady=(10, 4))

        for action, label in self.runtime.state.hotkey_labels.items():
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11, weight="bold"),
                          text_color="#e8e8e8", width=200, anchor="w").pack(side="left")
            value_var = ctk.StringVar(value=self.runtime.state.hotkey_bindings.get(action, "-").upper())
            self.hotkey_vars[action] = value_var
            ctk.CTkLabel(row, textvariable=value_var, font=ctk.CTkFont(size=10, family="Consolas"),
                          text_color="#5ac8fa", width=80, anchor="w").pack(side="left", padx=8)
            self.helpers["btn"](row, "Rebind", lambda a=action: self.services["begin_rebind"](a), "#0a84ff").pack(side="left", padx=4)

    def refresh_from_state(self) -> None:
        for action, binding in self.runtime.state.hotkey_bindings.items():
            if action in self.hotkey_vars:
                self.hotkey_vars[action].set(binding.upper())
