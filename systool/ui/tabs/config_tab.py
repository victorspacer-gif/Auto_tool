"""Config tab UI for SystemMonitor — save/load + global input mode."""

from __future__ import annotations

import tkinter as tk

from ...theme import BG, BLUE, BOLD, FG, GREEN, MONO, MUTED, ORANGE, PANEL, SMALL, SMALL_B, TEAL


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
        left, right = self.helpers["create_responsive_columns"](wrapper)

        # ═══════════════════════════════════════════════════════════
        # LEFT COLUMN — Save / Load
        # ═══════════════════════════════════════════════════════════

        save_load = tk.LabelFrame(
            left, text=" 💾  Save / Load Config ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10
        )
        save_load.pack(fill="x", pady=(0, 12))

        tk.Label(
            save_load,
            text="Save / Load complete configuration\n(all jobs · hotkey bindings · rune maker · alarm · fishing · timers…)",
            font=SMALL, fg=FG, bg=PANEL, justify="center"
        ).pack(pady=(0, 10))

        btn_row = tk.Frame(save_load, bg=PANEL)
        btn_row.pack()
        self.helpers["btn"](btn_row, "💾  Save JSON", self.services["manual_save_profiles"], BLUE).pack(side="left", padx=6, ipadx=12)
        self.helpers["btn"](btn_row, "📂  Load", self.services["load_config"], ORANGE).pack(side="left", padx=6, ipadx=12)

        tk.Label(
            save_load,
            text="All timing inputs use milliseconds. The only exception is\nRight-Click Min food timer, which uses minutes.",
            font=SMALL, fg=MUTED, bg=PANEL, justify="center", wraplength=400
        ).pack(pady=(10, 0))

        # ═══════════════════════════════════════════════════════════
        # RIGHT COLUMN — Global Input Mode
        # ═══════════════════════════════════════════════════════════

        input_panel = tk.LabelFrame(
            right, text=" 🖱️  Global Input Mode ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10
        )
        input_panel.pack(fill="x", pady=(0, 12))

        tk.Label(
            input_panel,
            text="Controls how ALL automated services send mouse clicks\nand keyboard presses to the game.",
            font=SMALL, fg=MUTED, bg=PANEL, justify="center"
        ).pack(pady=(0, 8))

        # Mode selection
        self._input_mode_var = tk.StringVar(value=self.runtime.state.input_mode)

        modes_frame = tk.Frame(input_panel, bg=PANEL)
        modes_frame.pack(fill="x", pady=(0, 8))

        for text, value in [
            ("🔲  Hardware (physical cursor via pynput)", "hardware"),
            ("🎯  Direct (Win32 SendMessage to window)", "direct"),
        ]:
            rb = tk.Radiobutton(
                modes_frame, text=text, variable=self._input_mode_var, value=value,
                bg=PANEL, fg=FG, selectcolor=BG, font=SMALL_B,
                command=self._sync_input_mode,
                anchor="w", padx=10, pady=2
            )
            rb.pack(fill="x")

        # Mode details
        detail_frame = tk.Frame(input_panel, bg=PANEL)
        detail_frame.pack(fill="x", pady=(0, 8))

        hardware_detail = tk.Label(
            detail_frame,
            text="• Physical mouse cursor moves on screen\n• Game window must be in the foreground\n• Best for normal interactive play",
            font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w"
        )
        hardware_detail.pack(fill="x", pady=(0, 4))

        direct_detail = tk.Label(
            detail_frame,
            text="• Sends events directly to the game window via Win32 API\n• Cursor does NOT move — works in the background\n• Best for AFK automation while you do other tasks",
            font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w"
        )
        direct_detail.pack(fill="x")

        # Window detection
        sep = tk.Frame(input_panel, bg=MUTED, height=1)
        sep.pack(fill="x", pady=6)

        detect_label = tk.Label(
            input_panel, text="Direct Mode — Target Window:", font=BOLD, bg=PANEL, fg=FG
        )
        detect_label.pack(anchor="w", pady=(0, 4))

        hwnd_frame = tk.Frame(input_panel, bg=PANEL)
        hwnd_frame.pack(fill="x", pady=(0, 4))

        tk.Label(hwnd_frame, text="Title fragment:", font=SMALL, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        self._window_title_var = tk.StringVar(value=self.runtime.state.game_window_title)
        tk.Entry(
            hwnd_frame, textvariable=self._window_title_var, font=MONO, bg=BG, fg=FG,
            relief="flat", bd=2, width=20
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.helpers["btn"](hwnd_frame, "🔍  Detect", self._detect_window, TEAL).pack(side="left")

        hwnd_info = tk.Frame(input_panel, bg=PANEL)
        hwnd_info.pack(fill="x", pady=(4, 0))
        self._hwnd_label = tk.Label(
            hwnd_info,
            text=f"HWND: {self.runtime.state.game_hwnd or '—'}  |  Mode: {self.runtime.state.input_mode}",
            font=SMALL, bg=PANEL, fg=MUTED
        )
        self._hwnd_label.pack(side="left")

        help_text = tk.Label(
            input_panel,
            text="Enter a partial window title (e.g. \"Miracle\") and click Detect.\nThe HWND is stored in your config for future sessions.",
            font=SMALL, fg=MUTED, bg=PANEL, justify="center", wraplength=380
        )
        help_text.pack(pady=(4, 0))

    # ═══════════════════════════════════════════════════════════════
    # Input Mode Helpers
    # ═══════════════════════════════════════════════════════════════

    def _sync_input_mode(self) -> None:
        self.runtime.state.input_mode = self._input_mode_var.get()
        label = "direct (Win32)" if self._input_mode_var.get() == "direct" else "hardware (pynput)"
        self.runtime.ui.log(f"🖱️  Global input mode set to {label}")
        if self._hwnd_label:
            self._hwnd_label.config(text=f"HWND: {self.runtime.state.game_hwnd or '—'}  |  Mode: {self.runtime.state.input_mode}")

    def _detect_window(self) -> None:
        title = self._window_title_var.get().strip()
        if not title:
            self.runtime.ui.log("⚠️  Enter a window title fragment first")
            return
        try:
            import win32gui
            found = [None]

            def enum_cb(hwnd, _):
                if found[0]:
                    return
                try:
                    win_title = win32gui.GetWindowText(hwnd)
                    if title.lower() in win_title.lower() and win32gui.IsWindowVisible(hwnd):
                        found[0] = hwnd
                except Exception:
                    pass

            win32gui.EnumWindows(enum_cb, None)
            if found[0]:
                hwnd = found[0]
                self.runtime.state.game_hwnd = hwnd
                if self._hwnd_label:
                    self._hwnd_label.config(text=f"HWND: {hwnd}  |  Mode: {self.runtime.state.input_mode}")
                actual_title = win32gui.GetWindowText(hwnd)
                self.runtime.ui.log(f"✅ Detected window: '{actual_title}' (HWND {hwnd})")
            else:
                self.runtime.ui.log(f"❌ No visible window found matching '{title}'")
        except Exception as exc:
            self.runtime.ui.log(f"❌ Window detection error: {exc}")
