"""Tkinter application layer for SystemMonitor."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

from .config import ConfigSerializer
from .models import HotkeyJob
from .runtime import (
    AppRuntime,
    HAS_MSS,
    HAS_PYGAME,
    HAS_PYNPUT,
    HAS_TRAY,
    HAS_WIN32,
    Image,
    ImageDraw,
    pystray,
    pynput_kb,
)
from .services import (
    AlarmService,
    AntiAfkService,
    FishingService,
    HotkeyJobService,
    HotkeyService,
    PositionCaptureService,
    RightClickService,
    RuneMakerService,
)
from .theme import BG, BLUE, BODY, BOLD, FG, GREEN, HEADER, MONO, MUTED, ORANGE, PANEL, PURPLE, RED, SMALL, SMALL_B, TEAL


class SystemMonitorApp:
    def __init__(self) -> None:
        self.runtime = AppRuntime()
        self.position_capture = PositionCaptureService(self.runtime)
        self.afk_service = AntiAfkService(self.runtime)
        self.rclick_service = RightClickService(self.runtime)
        self.alarm_service = AlarmService(self.runtime)
        self.fishing_service = FishingService(self.runtime)
        self.rune_service = RuneMakerService(self.runtime)
        self.job_service = HotkeyJobService(self.runtime)

        self.root: tk.Tk | None = None
        self.log_widget: scrolledtext.ScrolledText | None = None
        self.status_label: tk.Label | None = None
        self.stats_label: tk.Label | None = None
        self.pause_label: tk.Label | None = None
        self.pos_label: tk.Label | None = None
        self.rod_label: tk.Label | None = None
        self.alarm_region_label: tk.Label | None = None
        self.rune_hand_label: tk.Label | None = None
        self.rune_storage_label: tk.Label | None = None
        self.rune_blank_label: tk.Label | None = None
        self.spots_listbox: tk.Listbox | None = None
        self.fish_session_value_label: tk.Label | None = None
        self.fish_session_remaining_label: tk.Label | None = None
        self.jobs_frame: tk.Frame | None = None
        self.tray_icon = None
        self.listener = None

        self.ui_vars: dict[str, tk.Variable] = {}
        self.hotkey_vars: dict[str, tk.StringVar] = {}

    def run(self) -> None:
        self.build_ui()
        self.root.mainloop()

    def build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.wm_attributes("-toolwindow", True)
        self.root.title("SystemMonitor")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(960, 720)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.runtime.ui.configure(
            dispatch=lambda fn: self.root.after(0, fn),
            log=self._write_log,
            set_status=self._set_status,
            refresh_stats=self._refresh_stats,
            set_pause_label=self._sync_pause_state,
            job_state_changed=self._refresh_job_indicator,
        )

        self._build_header()
        self._build_notebook()
        self._build_log()
        self._start_global_hotkeys()
        self._poll_settings()
        self._refresh_stats()
        if HAS_TRAY:
            self._start_tray()

        missing = [
            name
            for name, installed in [
                ("pynput", HAS_PYNPUT),
                ("mss+numpy", HAS_MSS),
                ("pygame", HAS_PYGAME),
                ("pystray+pillow", HAS_TRAY),
                ("pywin32", HAS_WIN32),
            ]
            if not installed
        ]
        self._write_log("✅ SystemMonitor ready" + (f"  — missing: {', '.join(missing)}" if missing else ""))
        self._write_log("   All hotkeys are configurable in the Hotkeys tab. HOME = stop everything.")

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=PANEL, pady=10)
        header.pack(fill="x")
        header_top = tk.Frame(header, bg=PANEL)
        header_top.pack()
        tk.Label(header_top, text="⚡  SystemMonitor", font=HEADER, bg=PANEL, fg=FG).pack(side="left", padx=(0, 16))
        self.pause_label = tk.Label(header_top, text="Running", font=BOLD, bg=PANEL, fg=GREEN)
        self.pause_label.pack(side="left")
        tk.Label(
            header,
            text="F5 Pause/Resume  |  F8 Activity Monitor  |  F7 Right-Click Monitor  |  F6 Screen Watch  |  F12 Record positions  |  HOME Stop all",
            font=("Segoe UI", 8),
            bg=PANEL,
            fg=MUTED,
        ).pack(pady=(4, 0))
        tk.Frame(self.root, bg=MUTED, height=1).pack(fill="x")

        status_frame = tk.Frame(self.root, bg=BG, pady=5)
        status_frame.pack(fill="x", padx=14)
        self.status_label = tk.Label(status_frame, text="Ready", font=BOLD, fg=TEAL, bg=BG, wraplength=920)
        self.status_label.pack()
        self.stats_label = tk.Label(status_frame, text="", font=SMALL, fg=MUTED, bg=BG)
        self.stats_label.pack()

        pause_bar = tk.Frame(self.root, bg=BG)
        pause_bar.pack(fill="x", padx=14, pady=(2, 0))
        self._btn(pause_bar, "⏸  Pause / Resume", self.runtime.pause.toggle, ORANGE).pack(side="left")
        tk.Frame(self.root, bg=PANEL, height=1).pack(fill="x", padx=14, pady=4)

    def _build_notebook(self) -> None:
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, font=BOLD, padding=[12, 6])
        style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", FG)])

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=14, pady=6)

        automation_tab = tk.Frame(notebook, bg=BG)
        rune_tab = tk.Frame(notebook, bg=BG)
        alarm_tab = tk.Frame(notebook, bg=BG)
        fish_tab = tk.Frame(notebook, bg=BG)
        hotkeys_tab = tk.Frame(notebook, bg=BG)
        config_tab = tk.Frame(notebook, bg=BG)

        notebook.add(automation_tab, text="🎮  Activity Control")
        notebook.add(rune_tab, text="✨  Rune Session")
        notebook.add(alarm_tab, text="👁️  Screen Watch")
        notebook.add(fish_tab, text="🎣  Fishing Session")
        notebook.add(hotkeys_tab, text="⌨️  Hotkeys")
        notebook.add(config_tab, text="💾  Config")

        self._build_automation_tab(automation_tab)
        self._build_rune_tab(rune_tab)
        self._build_alarm_tab(alarm_tab)
        self._build_fish_tab(fish_tab)
        self._build_hotkeys_tab(hotkeys_tab)
        self._build_config_tab(config_tab)

    def _build_automation_tab(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=BG)
        right = tk.Frame(parent, bg=BG, width=340)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=6)
        right.pack(side="right", fill="both", expand=False, padx=(0, 2), pady=6)

        jobs_frame = tk.LabelFrame(left, text=" 🎮  Hotkey Tasks — independent threads ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=6, padx=8)
        jobs_frame.pack(fill="both", expand=True)
        top = tk.Frame(jobs_frame, bg=PANEL)
        top.pack(fill="x", pady=(0, 6))
        self._btn(top, "+ Add Job", self.add_job, BLUE).pack(side="left", padx=2)
        tk.Label(top, text="Enable 'Focus window' to direct keys to a selected app window", font=SMALL, fg=MUTED, bg=PANEL).pack(side="left", padx=10)
        canvas = tk.Canvas(jobs_frame, bg=PANEL, highlightthickness=0)
        scrollbar = tk.Scrollbar(jobs_frame, orient="vertical", command=canvas.yview)
        self.jobs_frame = tk.Frame(canvas, bg=PANEL)
        self.jobs_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.jobs_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._build_afk_panel(right)
        self._build_right_click_panel(right)

    def _build_afk_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(parent, text=" 🚶  Activity Monitor ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        panel.pack(fill="x", pady=(0, 8))
        afk_min = tk.StringVar(value=str(self.runtime.state.afk_min_ms))
        afk_max = tk.StringVar(value=str(self.runtime.state.afk_max_ms))
        self.ui_vars["afk_min_var"] = afk_min
        self.ui_vars["afk_max_var"] = afk_max
        self._label_entry(panel, "Timer Min (ms):", afk_min)
        self._label_entry(panel, "Timer Max (ms):", afk_max)
        tk.Label(panel, text="Ctrl held down → arrow press → Ctrl released", font=SMALL, fg=MUTED, bg=PANEL).pack(anchor="w")
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 0))
        self._btn(buttons, "▶ Start", self.afk_service.start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self._btn(buttons, "⏹ Stop", self.afk_service.stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def _build_right_click_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(parent, text=" 🖱️  Right-Click Monitor ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        panel.pack(fill="x", pady=(0, 8))
        self.pos_label = tk.Label(panel, text="Pos: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.pos_label.pack(anchor="w", pady=(0, 4))
        self._btn(panel, "🎯 Record Position", self.record_rclick_pos, BLUE).pack(fill="x", pady=(0, 6))
        min_var = tk.StringVar(value=str(self.runtime.state.rclick_min_ms))
        max_var = tk.StringVar(value=str(self.runtime.state.rclick_max_ms))
        self.ui_vars["rclick_min_var"] = min_var
        self.ui_vars["rclick_max_var"] = max_var
        self._label_entry(panel, "Timer Min (ms):", min_var)
        self._label_entry(panel, "Timer Max (ms):", max_var)
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 0))
        self._btn(buttons, "▶ Start", self.rclick_service.start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self._btn(buttons, "⏹ Stop", self.rclick_service.stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def _build_rune_tab(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=BG)
        right = tk.Frame(parent, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(6, 3), pady=6)
        right.pack(side="right", fill="both", expand=True, padx=(3, 6), pady=6)

        spell_panel = tk.LabelFrame(left, text=" ✨  Rune Session Timing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        spell_panel.pack(fill="x", pady=(0, 8))
        rune_spell = tk.StringVar(value=self.runtime.state.rune_spell_key)
        rune_cycle = tk.StringVar(value=str(self.runtime.state.rune_cycle_delay_ms))
        rune_jitter = tk.StringVar(value=str(self.runtime.state.rune_jitter))
        rune_cast = tk.StringVar(value=str(self.runtime.state.rune_cast_delay_ms))
        self.ui_vars["rune_spell_key_var"] = rune_spell
        self.ui_vars["rune_cycle_delay_var"] = rune_cycle
        self.ui_vars["rune_jitter_var"] = rune_jitter
        self.ui_vars["rune_cast_delay_var"] = rune_cast
        self._label_entry(spell_panel, "Spell hotkey:", rune_spell, width=6)
        self._label_entry(spell_panel, "Cast settle delay (ms):", rune_cast, width=7)
        self._label_entry(spell_panel, "Cycle delay (ms):", rune_cycle, width=7)
        self._label_entry(spell_panel, "Position jitter (px ±):", rune_jitter, width=5)
        cycle_label = tk.Label(spell_panel, text="≈ Cycle time: —", font=SMALL_B, fg=TEAL, bg=PANEL)
        cycle_label.pack(anchor="w", pady=(6, 0))

        def update_cycle_preview(*_args):
            try:
                seconds = int(rune_cycle.get()) / 1000.0
                cycle_label.config(text=f"≈ {seconds:.1f} s between casts  ({seconds / 60:.2f} min)")
            except ValueError:
                cycle_label.config(text="≈ Cycle time: —")

        rune_cycle.trace_add("write", update_cycle_preview)
        update_cycle_preview()

        positions_panel = tk.LabelFrame(left, text=" 🎯  Position Recording ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        positions_panel.pack(fill="both", expand=True, pady=(0, 8))
        self._build_position_row(positions_panel, "Record Hand", "Hand slot", self.record_rune_hand)
        self._build_position_row(positions_panel, "Record Storage", "Finished storage pos", self.record_rune_storage)
        self._build_position_row(positions_panel, "Record Blank", "Blank rune backpack pos", self.record_rune_blank)

        how_panel = tk.LabelFrame(right, text=" ℹ️  Cycle flow ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        how_panel.pack(fill="x", pady=(0, 8))
        for step in [
            "1.  Press spell hotkey → rune appears in hand",
            "2.  Wait cast settle delay (ms)",
            "3.  Acquire mouse lock",
            "4.  Drag rune: Hand → Finished storage",
            "5.  Drag blank: Blank stack → Hand slot",
            "6.  Release mouse lock",
            "7.  Wait cycle delay (ms)",
            "8.  Repeat",
        ]:
            tk.Label(how_panel, text=step, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x")
        buttons = tk.Frame(right, bg=BG)
        buttons.pack(fill="x", pady=(0, 8))
        self._btn(buttons, "▶ Start Rune Session", self.rune_service.start, GREEN).pack(fill="x", pady=2)
        self._btn(buttons, "⏹ Stop Rune Session", self.rune_service.stop, RED).pack(fill="x", pady=2)

    def _build_alarm_tab(self, parent: tk.Frame) -> None:
        wrapper = tk.Frame(parent, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=16, pady=10)
        panel = tk.LabelFrame(wrapper, text=" 👁️  Screen Change Watch ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=10, padx=14)
        panel.pack(fill="x")
        area_row = tk.Frame(panel, bg=PANEL)
        area_row.pack(fill="x", pady=4)
        self.alarm_region_label = tk.Label(area_row, text="Area: centre 200×200 px (default)", font=MONO, fg=TEAL, bg=PANEL)
        self.alarm_region_label.pack(side="left")
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(0, 8))
        self._btn(buttons, "🖼  Select Area (drag)", self.select_alarm_area, BLUE).pack(side="left", padx=(0, 6))
        self._btn(buttons, "↺ Reset", self.reset_alarm_area, ORANGE).pack(side="left")

        mp3_row = tk.Frame(panel, bg=PANEL)
        mp3_row.pack(fill="x", pady=4)
        tk.Label(mp3_row, text="Alert sound:", font=BOLD, fg=FG, bg=PANEL).pack(side="left")
        alarm_mp3 = tk.StringVar(value=self.runtime.state.alarm_mp3)
        self.ui_vars["alarm_mp3_var"] = alarm_mp3
        self._entry(mp3_row, alarm_mp3, 32).pack(side="left", padx=6, fill="x", expand=True)
        self._btn(mp3_row, "Browse", self.browse_alarm_sound, PURPLE).pack(side="left")

        alarm_threshold = tk.StringVar(value=str(int(self.runtime.state.alarm_threshold * 100)))
        self.ui_vars["alarm_thresh_var"] = alarm_threshold
        self._label_entry(panel, "Change threshold (%):", alarm_threshold, width=6)
        auto_pause = tk.BooleanVar(value=self.runtime.state.alarm_auto_pause)
        self.ui_vars["alarm_auto_pause_var"] = auto_pause
        tk.Checkbutton(panel, text="Auto-pause all activities when screen watch triggers", variable=auto_pause, font=BOLD, bg=PANEL, fg=ORANGE, selectcolor=PANEL, activebackground=PANEL, activeforeground=ORANGE).pack(anchor="w", pady=(8, 2))
        tk.Label(panel, text="When enabled: all running features pause on screen change detection.\nWhen disabled: the alert sound plays and monitoring continues.", font=SMALL, fg=MUTED, bg=PANEL, justify="left").pack(anchor="w")
        action_row = tk.Frame(panel, bg=PANEL)
        action_row.pack(fill="x", pady=(10, 0))
        self._btn(action_row, "▶ Start Watching", self.alarm_service.start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self._btn(action_row, "⏹ Stop", self.alarm_service.stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def _build_fish_tab(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=BG)
        right = tk.Frame(parent, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(6, 3), pady=6)
        right.pack(side="right", fill="both", expand=True, padx=(3, 6), pady=6)

        rod_panel = tk.LabelFrame(left, text=" 🎣  Rod Position ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        rod_panel.pack(fill="x", pady=(0, 8))
        self.rod_label = tk.Label(rod_panel, text="Rod: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.rod_label.pack(anchor="w", pady=(0, 4))
        self._btn(rod_panel, "🎯 Record Rod Pos", self.record_rod_pos, BLUE).pack(fill="x")
        rod_jitter = tk.StringVar(value=str(self.runtime.state.fish_rod_jitter))
        self.ui_vars["fish_rod_jit_var"] = rod_jitter
        self._label_entry(rod_panel, "Rod jitter (px ±):", rod_jitter, width=5)

        spots_panel = tk.LabelFrame(left, text=" 🗺️  Fishing Positions ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        spots_panel.pack(fill="both", expand=True, pady=(0, 8))
        spot_buttons = tk.Frame(spots_panel, bg=PANEL)
        spot_buttons.pack(fill="x", pady=(0, 6))
        self._btn(spot_buttons, "+ Add Spot", self.record_spot, BLUE).pack(side="left", padx=2)
        self._btn(spot_buttons, "✕ Remove", self.remove_selected_spot, ORANGE).pack(side="left", padx=2)
        self._btn(spot_buttons, "🗑 Clear", self.clear_spots, RED).pack(side="left", padx=2)
        list_frame = tk.Frame(spots_panel, bg=PANEL)
        list_frame.pack(fill="both", expand=True)
        self.spots_listbox = tk.Listbox(list_frame, bg=BG, fg=FG, font=MONO, selectbackground=BLUE, selectforeground="white", relief="flat", bd=2, height=8)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.spots_listbox.yview)
        self.spots_listbox.configure(yscrollcommand=scrollbar.set)
        self.spots_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        spot_jitter = tk.StringVar(value=str(self.runtime.state.fish_spot_jitter))
        self.ui_vars["fish_spot_jit_var"] = spot_jitter
        self._label_entry(spots_panel, "Spot jitter (px ±):", spot_jitter, width=5)

        timing_panel = tk.LabelFrame(right, text=" ⏱️  Timing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        timing_panel.pack(fill="x", pady=(0, 8))
        cast_min = tk.StringVar(value=str(self.runtime.state.fish_cast_min_ms))
        cast_max = tk.StringVar(value=str(self.runtime.state.fish_cast_max_ms))
        wait_min = tk.StringVar(value=str(self.runtime.state.fish_wait_min_ms))
        wait_max = tk.StringVar(value=str(self.runtime.state.fish_wait_max_ms))
        fish_session = tk.IntVar(value=self.runtime.state.fish_session_minutes)
        self.ui_vars.update(
            {
                "fish_cast_min_var": cast_min,
                "fish_cast_max_var": cast_max,
                "fish_wait_min_var": wait_min,
                "fish_wait_max_var": wait_max,
                "fish_session_var": fish_session,
            }
        )
        self._label_entry(timing_panel, "Cast delay Min (ms):", cast_min)
        self._label_entry(timing_panel, "Cast delay Max (ms):", cast_max)
        self._label_entry(timing_panel, "Wait for bite Min (ms):", wait_min)
        self._label_entry(timing_panel, "Wait for bite Max (ms):", wait_max)
        session_panel = tk.LabelFrame(right, text=" ⏲️  Fishing Session ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        session_panel.pack(fill="x", pady=(0, 8))
        self.fish_session_value_label = tk.Label(
            session_panel,
            text=f"Selected duration: {self.runtime.state.fish_session_minutes} min",
            font=SMALL_B,
            fg=TEAL,
            bg=PANEL,
        )
        self.fish_session_value_label.pack(anchor="w", pady=(0, 6))
        scale = tk.Scale(
            session_panel,
            from_=1,
            to=40,
            orient="horizontal",
            variable=fish_session,
            resolution=1,
            showvalue=False,
            bg=PANEL,
            fg=FG,
            troughcolor=BG,
            activebackground=BLUE,
            highlightthickness=0,
        )
        scale.pack(fill="x")
        self.fish_session_remaining_label = tk.Label(
            session_panel,
            text="Session remaining: 00:00",
            font=MONO,
            fg=ORANGE,
            bg=PANEL,
        )
        self.fish_session_remaining_label.pack(anchor="w", pady=(6, 0))

        def update_session_label(*_args):
            if self.fish_session_value_label:
                self.fish_session_value_label.config(text=f"Selected duration: {fish_session.get()} min")

        fish_session.trace_add("write", update_session_label)
        update_session_label()
        buttons = tk.Frame(right, bg=BG)
        buttons.pack(fill="x", pady=(0, 8))
        self._btn(buttons, "▶ Start Fishing Session", self.fishing_service.start, GREEN).pack(fill="x", pady=2)
        self._btn(buttons, "⏹ Stop Fishing Session", self.fishing_service.stop, RED).pack(fill="x", pady=2)
        tk.Label(right, text="Quick stop hotkey: see Hotkeys tab (fish_stop)", font=SMALL, fg=ORANGE, bg=BG).pack(anchor="w")

    def _build_hotkeys_tab(self, parent: tk.Frame) -> None:
        wrapper = tk.Frame(parent, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=20, pady=16)
        tk.Label(wrapper, text="Click Rebind then press any key to reassign a hotkey.\nConflicts are detected automatically.", font=BOLD, fg=FG, bg=BG, justify="center").pack(pady=(0, 16))
        inner = tk.LabelFrame(wrapper, text=" ⌨️  Current Bindings ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=10, padx=14)
        inner.pack(fill="x")
        for action, label in self.runtime.state.hotkey_labels.items():
            row = tk.Frame(inner, bg=PANEL)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, font=BOLD, fg=FG, bg=PANEL, width=28, anchor="w").pack(side="left")
            value_var = tk.StringVar(value=self.runtime.state.hotkey_bindings.get(action, "—").upper())
            self.hotkey_vars[action] = value_var
            tk.Label(row, textvariable=value_var, font=MONO, fg=TEAL, bg=PANEL, width=10, anchor="w").pack(side="left", padx=8)
            self._btn(row, "Rebind", lambda a=action: self.begin_rebind(a), BLUE).pack(side="left", padx=4)

    def _build_config_tab(self, parent: tk.Frame) -> None:
        wrapper = tk.Frame(parent, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=30, pady=30)
        tk.Label(wrapper, text="Save / Load complete configuration\n(all jobs · hotkey bindings · rune maker · alarm · fishing · timers…)", font=BOLD, fg=FG, bg=BG, justify="center").pack(pady=(0, 20))
        buttons = tk.Frame(wrapper, bg=BG)
        buttons.pack()
        self._btn(buttons, "💾 Save JSON", self.save_config_json, BLUE).pack(side="left", padx=8, ipadx=12)
        self._btn(buttons, "💾 Save XML", self.save_config_xml, PURPLE).pack(side="left", padx=8, ipadx=12)
        self._btn(buttons, "📂 Load", self.load_config, ORANGE).pack(side="left", padx=8, ipadx=12)

    def _build_log(self) -> None:
        tk.Frame(self.root, bg=PANEL, height=1).pack(fill="x", padx=14, pady=2)
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="both", expand=False, padx=14, pady=(0, 10))
        tk.Label(frame, text="Activity Log", font=BOLD, fg=MUTED, bg=BG).pack(anchor="w")
        self.log_widget = scrolledtext.ScrolledText(frame, height=8, bg=PANEL, fg=FG, font=MONO, relief="flat", bd=4, state="disabled")
        self.log_widget.pack(fill="both", expand=True)

    def _btn(self, parent, text, command, bg=GREEN, **kwargs):
        return tk.Button(parent, text=text, command=command, font=BOLD, bg=bg, fg="white", activebackground=bg, activeforeground="white", bd=0, relief="flat", cursor="hand2", pady=6, **kwargs)

    def _entry(self, parent, var, width=8):
        return tk.Entry(parent, textvariable=var, width=width, bg=BG, fg=FG, font=BODY, insertbackground=FG, relief="flat", bd=2)

    def _label_entry(self, parent, label, var, width=8, pady=2):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=pady)
        tk.Label(row, text=label, font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        self._entry(row, var, width).pack(side="left", padx=4)
        return row

    def _build_position_row(self, parent: tk.Frame, title: str, label_text: str, command) -> None:
        frame = tk.Frame(parent, bg=PANEL)
        frame.pack(fill="x", pady=4)
        label = tk.Label(frame, text=f"{label_text}: 0, 0", font=MONO, fg=TEAL, bg=PANEL, width=26, anchor="w")
        label.pack(side="left")
        if "Hand" in title:
            self.rune_hand_label = label
        elif "Storage" in title:
            self.rune_storage_label = label
        else:
            self.rune_blank_label = label
        self._btn(frame, f"📍 {title}", command, BLUE).pack(side="left", padx=6)

    def _write_log(self, message: str) -> None:
        if not self.log_widget:
            return
        timestamp = time.strftime("%H:%M:%S")
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", f"[{timestamp}] {message}\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        if self.status_label:
            self.status_label.config(text=text, fg=color)

    def _sync_pause_state(self, paused: bool) -> None:
        if paused:
            self._set_status("⏸  PAUSED — press pause hotkey to resume", ORANGE)
            if self.pause_label:
                self.pause_label.config(text="⏸  PAUSED", fg=ORANGE)
        else:
            self._set_status("▶  Resumed", GREEN)
            if self.pause_label:
                self.pause_label.config(text="Running", fg=GREEN)

    def _refresh_stats(self) -> None:
        if not self.stats_label:
            return
        stats = self.runtime.state.stats
        self.stats_label.config(
            text=(
                f"Hotkey: {stats['hotkeys']}  |  Bursts: {stats['bursts']}  |  "
                f"AFK: {stats['afk_moves']}  |  R-click: {stats['right_clicks']}  |  "
                f"Fish: {stats['fish_casts']}  |  Runes: {stats['runes_made']}  |  "
                f"Alarms: {stats['alarms']}"
            )
        )

    def _refresh_job_indicator(self, job: HotkeyJob) -> None:
        indicator = getattr(job.row_frame, "_indicator", None)
        if indicator:
            indicator.config(fg=GREEN if job.running else MUTED)

    def record_rclick_pos(self) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            self.runtime.state.rclick_pos = pos
            self.runtime.ui.log(f"✅ Right-click pos: {pos}")
            self.runtime.ui.set_status(f"Pos: {pos}", GREEN)
            if self.pos_label:
                self.pos_label.config(text=f"Pos: {pos[0]}, {pos[1]}")

        self.position_capture.capture(on_done, "right-click target")

    def record_rod_pos(self) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            self.runtime.state.fish_rod_pos = pos
            self.runtime.ui.log(f"✅ Rod pos: {pos}")
            self.runtime.ui.set_status(f"Rod pos: {pos}", GREEN)
            if self.rod_label:
                self.rod_label.config(text=f"Rod: {pos[0]}, {pos[1]}")

        self.position_capture.capture(on_done, "fishing rod in bag")

    def record_spot(self) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            self.runtime.state.fish_spots.append(pos)
            count = len(self.runtime.state.fish_spots)
            self.runtime.ui.log(f"✅ Spot #{count}: {pos}")
            self.runtime.ui.set_status(f"Spot #{count} added", GREEN)
            if self.spots_listbox:
                self.spots_listbox.insert("end", f"#{count}  {pos[0]},{pos[1]}")

        next_index = len(self.runtime.state.fish_spots) + 1
        self.position_capture.capture(on_done, f"fishing spot #{next_index}")

    def remove_selected_spot(self) -> None:
        if not self.spots_listbox:
            return
        selection = self.spots_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.runtime.state.fish_spots):
            self.runtime.state.fish_spots.pop(index)
        self.spots_listbox.delete(index)
        items = list(self.spots_listbox.get(0, "end"))
        self.spots_listbox.delete(0, "end")
        for idx, item in enumerate(items):
            coords = item.split("  ", 1)[-1]
            self.spots_listbox.insert("end", f"#{idx + 1}  {coords}")

    def clear_spots(self) -> None:
        self.runtime.state.fish_spots.clear()
        if self.spots_listbox:
            self.spots_listbox.delete(0, "end")
        self.runtime.ui.log("🗑️  Spots cleared")

    def record_rune_hand(self) -> None:
        self._record_rune_position("rune_hand_pos", self.rune_hand_label, "Hand slot")

    def record_rune_storage(self) -> None:
        self._record_rune_position("rune_storage_pos", self.rune_storage_label, "Finished storage pos")

    def record_rune_blank(self) -> None:
        self._record_rune_position("rune_blank_pos", self.rune_blank_label, "Blank rune backpack pos")

    def _record_rune_position(self, attr_name: str, label: tk.Label | None, label_text: str) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            setattr(self.runtime.state, attr_name, pos)
            self.runtime.ui.log(f"✅ {label_text}: {pos}")
            self.runtime.ui.set_status(f"{label_text} captured", GREEN)
            if label:
                label.config(text=f"{label_text}: {pos[0]},{pos[1]}")

        self.position_capture.capture(on_done, label_text)

    def add_job(self) -> None:
        self.runtime.state.job_counter += 1
        job = HotkeyJob(job_id=self.runtime.state.job_counter)
        self.runtime.state.jobs.append(job)
        self._build_job_row(job)

    def _build_job_row(self, job: HotkeyJob) -> None:
        outer = tk.LabelFrame(self.jobs_frame, text=f" Job #{job.job_id} ", font=SMALL_B, fg=TEAL, bg=PANEL, bd=1, padx=8, pady=6)
        outer.pack(fill="x", pady=4)
        outer._vars = {}
        job.row_frame = outer

        row1 = tk.Frame(outer, bg=PANEL)
        row1.pack(fill="x", pady=2)
        tk.Label(row1, text="Key:", font=BOLD, fg=FG, bg=PANEL).pack(side="left")
        key_var = tk.StringVar(value=job.key)
        menu = tk.OptionMenu(row1, key_var, *([f"F{i}" for i in range(1, 13)] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")))
        menu.config(font=BODY, bg=PANEL, fg=FG, activebackground=BLUE, bd=0, relief="flat", highlightthickness=0)
        menu["menu"].config(bg=PANEL, fg=FG, activebackground=BLUE, activeforeground="white")
        menu.pack(side="left", padx=6)
        outer._vars["key"] = key_var
        for label, name, default in [("Min ms:", "min", str(job.min_ms)), ("Max ms:", "max", str(job.max_ms))]:
            tk.Label(row1, text=label, font=BOLD, fg=FG, bg=PANEL).pack(side="left", padx=(8, 0))
            value = tk.StringVar(value=default)
            self._entry(row1, value, 6).pack(side="left", padx=4)
            outer._vars[name] = value
        indicator = tk.Label(row1, text="●", font=BOLD, fg=MUTED, bg=PANEL)
        indicator.pack(side="right", padx=4)
        outer._indicator = indicator

        row2 = tk.Frame(outer, bg=PANEL)
        row2.pack(fill="x", pady=2)
        burst_var = tk.BooleanVar(value=job.burst_enabled)
        outer._vars["burst"] = burst_var
        tk.Checkbutton(row2, text="Burst", variable=burst_var, font=BODY, bg=PANEL, fg=FG, selectcolor=PANEL, activebackground=PANEL).pack(side="left")
        for label, name, default in [("Chance%:", "b_chance", str(int(job.burst_chance * 100))), ("Cnt min:", "b_cmin", str(job.burst_cnt_min)), ("Cnt max:", "b_cmax", str(job.burst_cnt_max)), ("Int ms:", "b_int", str(job.burst_int_ms))]:
            tk.Label(row2, text=label, font=SMALL, fg=MUTED, bg=PANEL).pack(side="left", padx=(8, 0))
            value = tk.StringVar(value=default)
            self._entry(row2, value, 4).pack(side="left", padx=2)
            outer._vars[name] = value

        row3 = tk.Frame(outer, bg=PANEL)
        row3.pack(fill="x", pady=2)
        focus_var = tk.BooleanVar(value=job.use_focus)
        restore_var = tk.BooleanVar(value=job.restore_focus)
        outer._vars["focus"] = focus_var
        outer._vars["restore"] = restore_var
        tk.Checkbutton(row3, text="Focus window:", variable=focus_var, font=BODY, bg=PANEL, fg=FG, selectcolor=PANEL, activebackground=PANEL).pack(side="left")
        window_var = tk.StringVar(value=job.window_name)
        outer._vars["win_name"] = window_var
        tk.Entry(row3, textvariable=window_var, width=18, bg=BG, fg=FG, font=BODY, insertbackground=FG, relief="flat", bd=2).pack(side="left", padx=4)
        tk.Checkbutton(row3, text="Restore focus", variable=restore_var, font=SMALL, bg=PANEL, fg=MUTED, selectcolor=PANEL, activebackground=PANEL).pack(side="left", padx=6)
        if not HAS_WIN32:
            tk.Label(row3, text="(pywin32 missing)", font=SMALL, fg=RED, bg=PANEL).pack(side="left")

        row4 = tk.Frame(outer, bg=PANEL)
        row4.pack(fill="x", pady=(4, 0))
        self._btn(row4, "▶ Start", lambda j=job: self.start_job(j), GREEN).pack(side="left", padx=2, expand=True, fill="x")
        self._btn(row4, "⏹ Stop", lambda j=job: self.job_service.stop_job(j), RED).pack(side="left", padx=2, expand=True, fill="x")
        self._btn(row4, "✕ Remove", lambda j=job: self.remove_job(j), ORANGE).pack(side="left", padx=2, expand=True, fill="x")

    def start_job(self, job: HotkeyJob) -> None:
        self._read_job_vars(job)
        self.job_service.start_job(job)

    def _read_job_vars(self, job: HotkeyJob) -> None:
        vars_map = job.row_frame._vars
        try:
            job.key = vars_map["key"].get()
            job.min_ms = int(vars_map["min"].get())
            job.max_ms = int(vars_map["max"].get())
            job.burst_enabled = vars_map["burst"].get()
            job.burst_chance = int(vars_map["b_chance"].get()) / 100.0
            job.burst_cnt_min = int(vars_map["b_cmin"].get())
            job.burst_cnt_max = int(vars_map["b_cmax"].get())
            job.burst_int_ms = int(vars_map["b_int"].get())
            job.use_focus = vars_map["focus"].get()
            job.window_name = vars_map["win_name"].get()
            job.restore_focus = vars_map["restore"].get()
        except (ValueError, tk.TclError):
            pass

    def remove_job(self, job: HotkeyJob) -> None:
        self.job_service.stop_job(job)
        if job in self.runtime.state.jobs:
            self.runtime.state.jobs.remove(job)
        if job.row_frame:
            job.row_frame.destroy()

    def _start_global_hotkeys(self) -> None:
        if not HAS_PYNPUT:
            return

        def on_press(key):
            state = self.runtime.state
            if state.rebind_active and state.rebind_target:
                key_str = HotkeyService.pynput_key_to_str(key)
                if key_str != "esc":
                    self.root.after(0, lambda: self.apply_rebind(key_str))
                return False
            bindings = state.hotkey_bindings
            try:
                if HotkeyService.matches(key, bindings.get("stop_all", "home")):
                    self.root.after(0, self.stop_all)
                elif HotkeyService.matches(key, bindings.get("pause", "f5")):
                    self.root.after(0, self.runtime.pause.toggle)
                elif HotkeyService.matches(key, bindings.get("afk", "f8")):
                    self.root.after(0, lambda: self.afk_service.stop() if state.afk_active else self.afk_service.start())
                elif HotkeyService.matches(key, bindings.get("rclick", "f7")):
                    self.root.after(0, lambda: self.rclick_service.stop() if state.rclick_active else self.rclick_service.start())
                elif HotkeyService.matches(key, bindings.get("alarm", "f6")):
                    self.root.after(0, lambda: self.alarm_service.stop() if state.alarm_active else self.alarm_service.start())
                elif HotkeyService.matches(key, bindings.get("fish_stop", "f9")):
                    self.root.after(0, self.fishing_service.stop)
                elif HotkeyService.matches(key, bindings.get("rune_stop", "f10")):
                    self.root.after(0, self.rune_service.stop)
            except Exception:
                pass

        self.listener = pynput_kb.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    def _restart_global_listener(self) -> None:
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self._start_global_hotkeys()

    def begin_rebind(self, action: str) -> None:
        state = self.runtime.state
        if state.rebind_active:
            return
        state.rebind_active = True
        state.rebind_target = action
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.runtime.ui.log(f"🎹 Press the key to bind to: {state.hotkey_labels.get(action, action)}")
        self.runtime.ui.set_status(f"Press any key to bind to '{state.hotkey_labels.get(action, action)}'…", ORANGE)
        self._start_global_hotkeys()

    def apply_rebind(self, key_str: str) -> None:
        state = self.runtime.state
        action = state.rebind_target
        state.rebind_active = False
        state.rebind_target = None
        conflicts = [name for name, binding in state.hotkey_bindings.items() if binding == key_str and name != action]
        if conflicts:
            self.runtime.ui.log(f"⚠️  Key '{key_str}' is already used by: {', '.join(conflicts)}")
            self.runtime.ui.set_status(f"Key conflict: '{key_str}' already bound", ORANGE)
            self._restart_global_listener()
            return
        if action:
            state.hotkey_bindings[action] = key_str
            if action in self.hotkey_vars:
                self.hotkey_vars[action].set(key_str.upper())
            self.runtime.ui.log(f"✅ Rebound '{state.hotkey_labels.get(action, action)}' → {key_str.upper()}")
            self.runtime.ui.set_status(f"Hotkey updated: {key_str.upper()}", GREEN)
        self._restart_global_listener()

    def stop_all(self) -> None:
        self.job_service.stop_all(
            stop_afk=self.afk_service.stop,
            stop_rclick=self.rclick_service.stop,
            stop_alarm=self.alarm_service.stop,
            stop_fishing=self.fishing_service.stop,
            stop_rune=self.rune_service.stop,
        )

    def reset_alarm_area(self) -> None:
        self.runtime.state.alarm_region = None
        if self.alarm_region_label:
            self.alarm_region_label.config(text="Area: centre 200×200 px (default)")
        self.runtime.ui.log("ℹ️  Screen watch area reset")

    def browse_alarm_sound(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.ogg"), ("All", "*.*")])
        if path:
            self.runtime.state.alarm_mp3 = path
            self.ui_vars["alarm_mp3_var"].set(path)

    def select_alarm_area(self) -> None:
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.30)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="black")
        overlay.overrideredirect(True)
        canvas = tk.Canvas(overlay, cursor="crosshair", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        tk.Label(canvas, text="  Click & drag to select alarm area  |  Esc = cancel  ", font=BOLD, fg=TEAL, bg="black").place(x=20, y=20)
        start_xy = [None]
        rect_id = [None]

        def on_press(event):
            start_xy[0] = (event.x, event.y)
            if rect_id[0]:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=TEAL, width=2, dash=(6, 3))

        def on_drag(event):
            if start_xy[0] and rect_id[0]:
                canvas.coords(rect_id[0], start_xy[0][0], start_xy[0][1], event.x, event.y)

        def on_release(event):
            if not start_xy[0]:
                overlay.destroy()
                return
            x1, y1 = start_xy[0]
            x2, y2 = event.x, event.y
            x_val, y_val = min(x1, x2), min(y1, y2)
            width, height = abs(x2 - x1), abs(y2 - y1)
            if width < 10 or height < 10:
                overlay.destroy()
                return
            self.runtime.state.alarm_region = (x_val, y_val, width, height)
            overlay.destroy()
            text = f"Area: ({x_val},{y_val})  {width}×{height} px"
            self.runtime.ui.log(f"✅ Screen watch area: {text}")
            self.runtime.ui.set_status(f"Screen watch area: {text}", TEAL)
            if self.alarm_region_label:
                self.alarm_region_label.config(text=text)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", lambda _e: overlay.destroy())
        overlay.focus_force()

    def save_config_json(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json"), ("All", "*.*")], initialfile=f"autotool_{time.strftime('%Y%m%d_%H%M%S')}.json")
        if not path:
            return
        try:
            ConfigSerializer.save_json(path, self.runtime.state)
            self.runtime.ui.log(f"💾 Saved: {path}")
        except Exception as exc:
            self.runtime.ui.log(f"❌ Save failed: {exc}")

    def save_config_xml(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML", "*.xml"), ("All", "*.*")], initialfile=f"autotool_{time.strftime('%Y%m%d_%H%M%S')}.xml")
        if not path:
            return
        try:
            ConfigSerializer.save_xml(path, self.runtime.state)
            self.runtime.ui.log(f"💾 Saved: {path}")
        except Exception as exc:
            self.runtime.ui.log(f"❌ Save failed: {exc}")

    def load_config(self) -> None:
        path = filedialog.askopenfilename(title="Load Config", filetypes=[("Config", "*.json *.xml"), ("JSON", "*.json"), ("XML", "*.xml"), ("All", "*.*")])
        if not path:
            return
        try:
            payload = ConfigSerializer.load_file(path)
            ConfigSerializer.apply_loaded(self.runtime.state, payload)
            self._sync_ui_from_state()
            self._restart_global_listener()
            self.runtime.ui.log(f"📂 Loaded: {path}")
            self.runtime.ui.log("✅ Config applied")
            self.runtime.ui.set_status("Config loaded", GREEN)
        except Exception as exc:
            self.runtime.ui.log(f"❌ Load failed: {exc}")

    def _sync_ui_from_state(self) -> None:
        state = self.runtime.state
        mappings = {
            "afk_min_var": state.afk_min_ms,
            "afk_max_var": state.afk_max_ms,
            "rclick_min_var": state.rclick_min_ms,
            "rclick_max_var": state.rclick_max_ms,
            "alarm_mp3_var": state.alarm_mp3,
            "alarm_thresh_var": int(state.alarm_threshold * 100),
            "fish_cast_min_var": state.fish_cast_min_ms,
            "fish_cast_max_var": state.fish_cast_max_ms,
            "fish_wait_min_var": state.fish_wait_min_ms,
            "fish_wait_max_var": state.fish_wait_max_ms,
            "fish_rod_jit_var": state.fish_rod_jitter,
            "fish_spot_jit_var": state.fish_spot_jitter,
            "fish_session_var": state.fish_session_minutes,
            "rune_spell_key_var": state.rune_spell_key,
            "rune_cycle_delay_var": state.rune_cycle_delay_ms,
            "rune_jitter_var": state.rune_jitter,
            "rune_cast_delay_var": state.rune_cast_delay_ms,
        }
        for name, value in mappings.items():
            if name in self.ui_vars:
                self.ui_vars[name].set(str(value))
        if "alarm_auto_pause_var" in self.ui_vars:
            self.ui_vars["alarm_auto_pause_var"].set(state.alarm_auto_pause)
        if self.pos_label:
            self.pos_label.config(text=f"Pos: {state.rclick_pos[0]}, {state.rclick_pos[1]}")
        if self.rod_label:
            self.rod_label.config(text=f"Rod: {state.fish_rod_pos[0]}, {state.fish_rod_pos[1]}")
        if self.rune_hand_label:
            self.rune_hand_label.config(text=f"Hand slot: {state.rune_hand_pos[0]},{state.rune_hand_pos[1]}")
        if self.rune_storage_label:
            self.rune_storage_label.config(text=f"Finished storage pos: {state.rune_storage_pos[0]},{state.rune_storage_pos[1]}")
        if self.rune_blank_label:
            self.rune_blank_label.config(text=f"Blank rune backpack pos: {state.rune_blank_pos[0]},{state.rune_blank_pos[1]}")
        if self.alarm_region_label:
            if state.alarm_region:
                x_val, y_val, width, height = state.alarm_region
                self.alarm_region_label.config(text=f"Area: ({x_val},{y_val}) {width}×{height} px")
            else:
                self.alarm_region_label.config(text="Area: centre 200×200 px (default)")
        if self.spots_listbox:
            self.spots_listbox.delete(0, "end")
            for index, spot in enumerate(state.fish_spots, start=1):
                self.spots_listbox.insert("end", f"#{index}  {spot[0]},{spot[1]}")
        self._refresh_fish_session_display()
        for child in list(self.jobs_frame.winfo_children()):
            child.destroy()
        for job in self.runtime.state.jobs:
            self._build_job_row(job)
        for action, binding in state.hotkey_bindings.items():
            if action in self.hotkey_vars:
                self.hotkey_vars[action].set(binding.upper())

    def _poll_settings(self) -> None:
        state = self.runtime.state

        def get_int(name: str, default: int) -> int:
            try:
                return int(self.ui_vars[name].get()) if name in self.ui_vars else default
            except ValueError:
                return default

        with self.runtime.settings_lock:
            state.afk_min_ms = get_int("afk_min_var", state.afk_min_ms)
            state.afk_max_ms = get_int("afk_max_var", state.afk_max_ms)
            state.rclick_min_ms = get_int("rclick_min_var", state.rclick_min_ms)
            state.rclick_max_ms = get_int("rclick_max_var", state.rclick_max_ms)
            state.alarm_threshold = get_int("alarm_thresh_var", int(state.alarm_threshold * 100)) / 100.0
            if "alarm_auto_pause_var" in self.ui_vars:
                state.alarm_auto_pause = bool(self.ui_vars["alarm_auto_pause_var"].get())
            if "alarm_mp3_var" in self.ui_vars:
                state.alarm_mp3 = str(self.ui_vars["alarm_mp3_var"].get())
            state.fish_cast_min_ms = get_int("fish_cast_min_var", state.fish_cast_min_ms)
            state.fish_cast_max_ms = get_int("fish_cast_max_var", state.fish_cast_max_ms)
            state.fish_wait_min_ms = get_int("fish_wait_min_var", state.fish_wait_min_ms)
            state.fish_wait_max_ms = get_int("fish_wait_max_var", state.fish_wait_max_ms)
            state.fish_rod_jitter = get_int("fish_rod_jit_var", state.fish_rod_jitter)
            state.fish_spot_jitter = get_int("fish_spot_jit_var", state.fish_spot_jitter)
            state.fish_session_minutes = max(1, min(40, get_int("fish_session_var", state.fish_session_minutes)))
            if "rune_spell_key_var" in self.ui_vars:
                state.rune_spell_key = str(self.ui_vars["rune_spell_key_var"].get()).lower().strip()
            state.rune_cycle_delay_ms = get_int("rune_cycle_delay_var", state.rune_cycle_delay_ms)
            state.rune_jitter = get_int("rune_jitter_var", state.rune_jitter)
            state.rune_cast_delay_ms = get_int("rune_cast_delay_var", state.rune_cast_delay_ms)
        self._refresh_fish_session_display()
        self.root.after(500, self._poll_settings)

    def _refresh_fish_session_display(self) -> None:
        if self.fish_session_value_label:
            self.fish_session_value_label.config(
                text=f"Selected duration: {self.runtime.state.fish_session_minutes} min"
            )
        if self.fish_session_remaining_label:
            total_seconds = self.runtime.state.fish_session_remaining_secs
            if self.runtime.state.fish_active and self.runtime.state.fish_session_deadline is not None:
                total_seconds = max(
                    0,
                    int(self.runtime.state.fish_session_deadline - time.monotonic() + 0.999),
                )
            minutes, seconds = divmod(max(0, total_seconds), 60)
            self.fish_session_remaining_label.config(
                text=f"Session remaining: {minutes:02d}:{seconds:02d}"
            )

    def on_close(self) -> None:
        self.root.withdraw()

    def _make_tray_image(self):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([4, 4, 60, 60], fill=(48, 209, 88, 255))
        draw.rectangle([20, 28, 44, 36], fill=(255, 255, 255, 220))
        draw.rectangle([28, 20, 36, 44], fill=(255, 255, 255, 220))
        return image

    def _start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Show SystemMonitor", self.show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause / Resume", lambda: self.root.after(0, self.runtime.pause.toggle)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.exit_app),
        )
        self.tray_icon = pystray.Icon("SystemMonitor", self._make_tray_image(), "SystemMonitor", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, *args) -> None:
        self.root.after(0, lambda: (self.root.deiconify(), self.root.lift(), self.root.focus_force()))

    def exit_app(self, *args) -> None:
        if self.tray_icon:
            self.tray_icon.stop()
        if self.root:
            self.root.after(0, self.root.destroy)


def run() -> None:
    SystemMonitorApp().run()
