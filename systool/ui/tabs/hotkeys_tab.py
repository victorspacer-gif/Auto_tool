"""Hotkeys tab UI for SystemMonitor."""

from __future__ import annotations

import tkinter as tk

from ...theme import BG, BLUE, BOLD, FG, MONO, PANEL, TEAL


class HotkeysTab:
    """Owns the hotkeys tab UI and tab-local behavior."""

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
        tk.Label(wrapper, text="Click Rebind then press any key to reassign a hotkey.\nConflicts are detected automatically.", font=BOLD, fg=FG, bg=BG, justify="center").grid(row=0, column=0, pady=(0, 16), sticky="ew")
        inner = tk.LabelFrame(wrapper, text=" Current Bindings ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=10, padx=14)
        inner.grid(row=1, column=0, sticky="ew")
        for action, label in self.runtime.state.hotkey_labels.items():
            row = tk.Frame(inner, bg=PANEL)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, font=BOLD, fg=FG, bg=PANEL, width=28, anchor="w").pack(side="left")
            value_var = tk.StringVar(value=self.runtime.state.hotkey_bindings.get(action, "-").upper())
            self.hotkey_vars[action] = value_var
            tk.Label(row, textvariable=value_var, font=MONO, fg=TEAL, bg=PANEL, width=10, anchor="w").pack(side="left", padx=8)
            self.helpers["btn"](row, "Rebind", lambda a=action: self.services["begin_rebind"](a), BLUE).pack(side="left", padx=4)

    def refresh_from_state(self) -> None:
        for action, binding in self.runtime.state.hotkey_bindings.items():
            if action in self.hotkey_vars:
                self.hotkey_vars[action].set(binding.upper())
