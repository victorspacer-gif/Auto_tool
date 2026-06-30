"""Luxe (CTk) config tab — ported from tkinter ConfigTab."""

from __future__ import annotations

import customtkinter as ctk


class ConfigTab:
    """Owns the config tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self._input_mode_var: ctk.StringVar | None = None
        self._sched_mode_var: ctk.StringVar | None = None
        self._window_title_var: ctk.StringVar | None = None
        self._hwnd_label: ctk.CTkLabel | None = None

        self._build()

    def _build(self) -> None:
        wrapper = self.helpers["create_scrollable_content"](self.parent, padx=30, pady=30)
        left, right = self.helpers["create_responsive_columns"](wrapper)

        # ════════════════════════════════════════════════
        # LEFT — Save / Load
        # ════════════════════════════════════════════════
        save_load = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        save_load.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(save_load, text="💾  Save / Load Config",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        ctk.CTkLabel(save_load, text="Save / Load complete configuration\n(all jobs · hotkey bindings · rune maker · alarm · fishing · timers…)",
                      font=ctk.CTkFont(size=10), text_color="#e8e8e8", justify="center").pack(pady=(0, 10))

        btn_row = ctk.CTkFrame(save_load, fg_color="transparent")
        btn_row.pack()
        self.helpers["btn"](btn_row, "💾  Save JSON", self.services["manual_save_profiles"], "#0a84ff").pack(side="left", padx=6, ipadx=12)
        self.helpers["btn"](btn_row, "📂  Load", self.services["load_config"], "#ff9f0a").pack(side="left", padx=6, ipadx=12)

        ctk.CTkLabel(save_load, text="All timing inputs use milliseconds. The only exception is\nRight-Click Min food timer, which uses minutes.",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="center", wraplength=400).pack(pady=(10, 10))

        # ════════════════════════════════════════════════
        # RIGHT — Global Input Mode
        # ════════════════════════════════════════════════
        input_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        input_panel.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(input_panel, text="🖱️  Global Input Mode",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        ctk.CTkLabel(input_panel, text="Controls how ALL automated services send mouse clicks\nand keyboard presses to the game.",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="center").pack(pady=(0, 8))

        self._input_mode_var = ctk.StringVar(value=self.runtime.state.input_mode)

        modes_frame = ctk.CTkFrame(input_panel, fg_color="transparent")
        modes_frame.pack(fill="x", padx=10, pady=(0, 8))

        for text, value in [
            ("🔲  Hardware (physical cursor via pynput)", "hardware"),
            ("🎯  Direct (Win32 SendMessage to window)", "direct"),
        ]:
            rb = ctk.CTkRadioButton(modes_frame, text=text, variable=self._input_mode_var, value=value,
                                     command=self._sync_input_mode,
                                     fg_color="#0a84ff", text_color="#e8e8e8",
                                     font=ctk.CTkFont(size=10, weight="bold"))
            rb.pack(anchor="w", padx=10, pady=2)

        detail_frame = ctk.CTkFrame(input_panel, fg_color="transparent")
        detail_frame.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(detail_frame, text="• Physical mouse cursor moves on screen\n• Game window must be in the foreground\n• Best for normal interactive play",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="left", anchor="w").pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(detail_frame, text="• Sends events directly to the game window via Win32 API\n• Cursor does NOT move — works in the background\n• Best for AFK automation while you do other tasks",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="left", anchor="w").pack(fill="x")

        # Direct Mode — Target Window
        sep = ctk.CTkFrame(input_panel, fg_color="#3a3a3a", height=1)
        sep.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(input_panel, text="Direct Mode — Target Window:",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(0, 4))

        hwnd_frame = ctk.CTkFrame(input_panel, fg_color="transparent")
        hwnd_frame.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(hwnd_frame, text="Title fragment:", font=ctk.CTkFont(size=10),
                      text_color="#e8e8e8").pack(side="left", padx=(0, 4))
        self._window_title_var = ctk.StringVar(value=self.runtime.state.game_window_title)
        ctk.CTkEntry(hwnd_frame, textvariable=self._window_title_var,
                      font=ctk.CTkFont(size=10, family="Consolas"),
                      fg_color="#1a1a1a", border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.helpers["btn"](hwnd_frame, "🔍  Detect", self._detect_window, "#5ac8fa").pack(side="left")

        hwnd_info = ctk.CTkFrame(input_panel, fg_color="transparent")
        hwnd_info.pack(fill="x", padx=10, pady=(4, 0))
        self._hwnd_label = ctk.CTkLabel(hwnd_info,
                                         text=f"HWND: {self.runtime.state.game_hwnd or '—'}  |  Mode: {self.runtime.state.input_mode}",
                                         font=ctk.CTkFont(size=10), text_color="#777777")
        self._hwnd_label.pack(side="left")

        ctk.CTkLabel(input_panel,
                      text="Enter a partial window title (e.g. \"Miracle\") and click Detect.\nThe HWND is stored in your config for future sessions.",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="center", wraplength=380).pack(padx=10, pady=(4, 10))

        # ════════════════════════════════════════════════
        # Scheduling Mode (FIFO vs Priority)
        # ════════════════════════════════════════════════
        sched_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        sched_panel.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(sched_panel, text="⏱️  Thread Scheduling Mode",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        ctk.CTkLabel(sched_panel,
                      text="Controls how concurrent automation threads share\nmouse and keyboard input ownership.",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="center").pack(pady=(0, 8))

        self._sched_mode_var = ctk.StringVar(value=self.runtime.state.scheduling_mode)

        sched_frame = ctk.CTkFrame(sched_panel, fg_color="transparent")
        sched_frame.pack(fill="x", padx=10, pady=(0, 8))

        for text, value in [
            ("📋  FIFO (first-come, first-served — equal priority)", "fifo"),
            ("⚔️  Priority (healer > combat > walker > background — OTibia_Bot-style)", "priority"),
        ]:
            rb = ctk.CTkRadioButton(sched_frame, text=text, variable=self._sched_mode_var, value=value,
                                     command=self._sync_scheduling_mode,
                                     fg_color="#0a84ff", text_color="#e8e8e8",
                                     font=ctk.CTkFont(size=10, weight="bold"))
            rb.pack(anchor="w", padx=10, pady=2)

        ctk.CTkLabel(sched_panel,
                      text="• FIFO: All threads equal — fair, no starvation\n• Priority: Healer always wins, combat preempts walker/runes/fishing\n• Priority mode mirrors OTibia_Bot's walker_Lock / attack_Lock model",
                      font=ctk.CTkFont(size=10), text_color="#777777", justify="left", anchor="w", wraplength=380).pack(padx=10, pady=(4, 10))

    # ── Input Mode Helpers ──

    def _sync_input_mode(self) -> None:
        if not self._input_mode_var:
            return
        self.runtime.state.input_mode = self._input_mode_var.get()
        label = "direct (Win32)" if self._input_mode_var.get() == "direct" else "hardware (pynput)"
        self.runtime.ui.log(f"🖱️  Global input mode set to {label}")
        if self._hwnd_label:
            self._hwnd_label.configure(text=f"HWND: {self.runtime.state.game_hwnd or '—'}  |  Mode: {self.runtime.state.input_mode}")

    def _sync_scheduling_mode(self) -> None:
        if not self._sched_mode_var:
            return
        self.runtime.state.scheduling_mode = self._sched_mode_var.get()
        label = "Priority (healer > combat > walker)" if self._sched_mode_var.get() == "priority" else "FIFO (first-come, first-served)"
        self.runtime.ui.log(f"⏱️  Scheduling mode set to {label}")

    def _detect_window(self) -> None:
        if not self._window_title_var:
            return
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
                    self._hwnd_label.configure(text=f"HWND: {hwnd}  |  Mode: {self.runtime.state.input_mode}")
                actual_title = win32gui.GetWindowText(hwnd)
                self.runtime.ui.log(f"✅ Detected window: '{actual_title}' (HWND {hwnd})")
            else:
                self.runtime.ui.log(f"❌ No visible window found matching '{title}'")
        except Exception as exc:
            self.runtime.ui.log(f"❌ Window detection error: {exc}")
