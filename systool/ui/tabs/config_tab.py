"""Config tab UI for SystemMonitor."""

from __future__ import annotations

import tkinter as tk

from ...theme import BG, BLUE, BOLD, FG, MUTED, ORANGE, SMALL


class ConfigTab:
    """Owns the config tab UI."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self._build()

    def _build(self) -> None:
        wrapper = self.helpers["create_scrollable_content"](self.parent, padx=30, pady=30)
        tk.Label(wrapper, text="Save / Load complete configuration\n(all jobs · hotkey bindings · rune maker · alarm · fishing · timers...)", font=BOLD, fg=FG, bg=BG, justify="center").grid(row=0, column=0, pady=(0, 20), sticky="ew")
        buttons = tk.Frame(wrapper, bg=BG)
        buttons.grid(row=1, column=0)
        self.helpers["btn"](buttons, "Save JSON", self.services["manual_save_profiles"], BLUE).pack(side="left", padx=8, ipadx=12)
        self.helpers["btn"](buttons, "Load", self.services["load_config"], ORANGE).pack(side="left", padx=8, ipadx=12)
        tk.Label(
            wrapper,
            text="All timing inputs use milliseconds. The only exception is Right-Click Min food timer, which uses minutes.",
            font=SMALL,
            fg=MUTED,
            bg=BG,
            justify="center",
            wraplength=680,
        ).grid(row=2, column=0, pady=(20, 0), sticky="ew")
