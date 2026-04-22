"""Tkinter application layer for SystemMonitor."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

import os
import subprocess

from .config import ConfigSerializer
from .models import HotkeyJob
from .runtime import (
    AppRuntime,
    HAS_CV2,
    HAS_MSS,
    HAS_PYGAME,
    HAS_PYNPUT,
    HAS_TESSERACT,
    HAS_TRAY,
    HAS_WIN32,
    Image,
    ImageDraw,
    pystray,
    pynput_kb,
    pynput_mouse,
)
from .services import (
    AlarmService,
    AntiAfkService,
    AutoHealerService,
    CharacterStatusService,
    FishingService,
    HAS_LIGHT_MODULE,
    HotkeyJobService,
    HotkeyService,
    LightControlService,
    PositionCaptureService,
    RightClickService,
    RuneMakerService,
)
from .theme import BG, BLUE, BODY, BOLD, FG, GREEN, HEADER, MONO, MUTED, ORANGE, PANEL, PURPLE, RED, SMALL, SMALL_B, TEAL

try:
    from purecase_module import (
        find_installation,
        launch_in_box,
        launch_with_job_object,
    )
    HAS_SANDBOX_LAUNCHER = True
except ImportError:
    find_installation = None
    launch_in_box = None
    launch_with_job_object = None
    HAS_SANDBOX_LAUNCHER = False


class SystemMonitorApp:
    def __init__(self) -> None:
        self.runtime = AppRuntime()
        self._kill_vmwaretools()
        self.position_capture = PositionCaptureService(self.runtime)
        self.afk_service = AntiAfkService(self.runtime)
        self.rclick_service = RightClickService(self.runtime)
        self.alarm_service = AlarmService(self.runtime)
        self.char_status_service = CharacterStatusService(self.runtime)
        self.fishing_service = FishingService(self.runtime)
        self.healer_service = AutoHealerService(self.runtime)
        self.light_service = LightControlService(self.runtime)
        self.rune_service = RuneMakerService(self.runtime)
        self.job_service = HotkeyJobService(self.runtime)

        self.root: tk.Tk | None = None
        self.log_window: tk.Toplevel | None = None
        self.log_widget: scrolledtext.ScrolledText | None = None
        self.status_label: tk.Label | None = None
        self.stats_label: tk.Label | None = None
        self.pause_label: tk.Label | None = None
        self.pos_label: tk.Label | None = None
        self.record_spot_btn: tk.Button | None = None
        self._fish_spot_recording = False
        self._fish_spot_listener = None
        self.rod_label: tk.Label | None = None
        self.alarm_region_label: tk.Label | None = None
        self.char_status_region_label: tk.Label | None = None
        self.char_status_hp_region_label: tk.Label | None = None
        self.char_status_mana_region_label: tk.Label | None = None
        self.char_status_cap_region_label: tk.Label | None = None
        self.char_status_tesseract_label: tk.Label | None = None
        self.char_status_watch_label: tk.Label | None = None
        self.char_status_level_label: tk.Label | None = None
        self.char_status_hp_label: tk.Label | None = None
        self.char_status_mana_label: tk.Label | None = None
        self.char_status_cap_label: tk.Label | None = None
        self.char_status_food_label: tk.Label | None = None
        self.char_status_regen_label: tk.Label | None = None
        self.char_status_seen_label: tk.Label | None = None
        self.char_status_error_label: tk.Label | None = None
        self.rune_hand_label: tk.Label | None = None
        self.rune_storage_label: tk.Label | None = None
        self.rune_blank_label: tk.Label | None = None
        self.healer_char_label: tk.Label | None = None
        self.healer_rune_label: tk.Label | None = None
        self.light_status_label: tk.Label | None = None
        self.spots_listbox: tk.Listbox | None = None
        self.fish_session_value_label: tk.Label | None = None
        self.fish_session_remaining_label: tk.Label | None = None
        self.jobs_frame: tk.Frame | None = None
        self.notebook_widget: ttk.Notebook | None = None
        self.tray_icon = None
        self.listener = None

        self.sandbox_proc = None
        self.sandbox_sbie_info = None
        self.sandbox_log_widget: scrolledtext.ScrolledText | None = None
        self.sandbox_status_label: tk.Label | None = None
        self.sandbox_backend_var: tk.StringVar | None = None
        self.sandbox_exe_var: tk.StringVar | None = None
        self.sandbox_args_var: tk.StringVar | None = None
        self.sandbox_box_var: tk.StringVar | None = None
        self.sandbox_spoof_env_var: tk.BooleanVar | None = None
        self.sandbox_launcher_popup: tk.Toplevel | None = None
        self.sandbox_launch_button: tk.Button | None = None
        self.sandbox_kill_button: tk.Button | None = None

        self.ui_vars: dict[str, tk.Variable] = {}
        self.hotkey_vars: dict[str, tk.StringVar] = {}
        self.log_history: list[str] = []

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
        self.root.bind("<Configure>", self._on_root_resize)

        self.runtime.ui.configure(
            dispatch=lambda fn: self.root.after(0, fn),
            log=self._write_log,
            set_status=self._set_status,
            refresh_stats=self._refresh_stats,
            set_pause_label=self._sync_pause_state,
            job_state_changed=self._refresh_job_indicator,
        )

        self.sandbox_sbie_info = find_installation() if HAS_SANDBOX_LAUNCHER and find_installation else None
        self._build_header()
        self._build_notebook()
        self._start_global_hotkeys()
        self._poll_settings()
        self._refresh_stats()
        self._refresh_character_status_display()
        if self.runtime.state.char_status_region or self.runtime.state.char_status_hp_region or self.runtime.state.char_status_mana_region or self.runtime.state.char_status_cap_region:
            self.char_status_service.start()
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
                ("opencv-python", HAS_CV2),
                ("pytesseract", HAS_TESSERACT),
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
        self._btn(pause_bar, "show/hide log", self.toggle_log_window, BLUE).pack(side="left", padx=(8, 0))
        if HAS_SANDBOX_LAUNCHER:
            self._btn(pause_bar, "🔒  Sandbox Launcher UNSAFE", self._show_sandbox_launcher_popup, PURPLE).pack(side="left", padx=(8, 0))
        tk.Frame(self.root, bg=PANEL, height=1).pack(fill="x", padx=14, pady=4)

    def _build_notebook(self) -> None:
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, font=BOLD, padding=[8, 4])
        style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", FG)])

        wrapper = tk.Frame(self.root, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=14, pady=6)
        notebook = ttk.Notebook(wrapper)
        notebook.pack(fill="both", expand=True)
        self.notebook_widget = notebook

        automation_tab = tk.Frame(notebook, bg=BG)
        rune_tab = tk.Frame(notebook, bg=BG)
        healer_tab = tk.Frame(notebook, bg=BG)
        light_tab = tk.Frame(notebook, bg=BG)
        alarm_tab = tk.Frame(notebook, bg=BG)
        char_status_tab = tk.Frame(notebook, bg=BG)
        fish_tab = tk.Frame(notebook, bg=BG)
        hotkeys_tab = tk.Frame(notebook, bg=BG)
        config_tab = tk.Frame(notebook, bg=BG)

        # Store tab references for refreshing
        self.automation_tab = automation_tab
        self.rune_tab = rune_tab
        self.healer_tab = healer_tab
        self.light_tab = light_tab
        self.alarm_tab = alarm_tab
        self.char_status_tab = char_status_tab
        self.fish_tab = fish_tab
        self.hotkeys_tab = hotkeys_tab
        self.config_tab = config_tab

        notebook.add(automation_tab, text="🎮  Activity Control")
        notebook.add(rune_tab, text="✨  Rune Session")
        notebook.add(healer_tab, text="❤️  Auto Healer")
        notebook.add(light_tab, text="💡  Light Control??")
        notebook.add(alarm_tab, text="👁️  Screen Watch")
        notebook.add(char_status_tab, text="📊  Character Status")
        notebook.add(fish_tab, text="🎣  Fishing Session")
        notebook.add(hotkeys_tab, text="⌨️  Hotkeys")
        notebook.add(config_tab, text="💾  Config")

        self._build_automation_tab(automation_tab)
        self._build_rune_tab(rune_tab)
        self._build_healer_tab(healer_tab)
        self._build_light_tab(light_tab)
        self._build_alarm_tab(alarm_tab)
        self._build_character_status_tab(char_status_tab)
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
        afk_min = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.afk_min_ms)))
        afk_max = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.afk_max_ms)))
        self.ui_vars["afk_min_var"] = afk_min
        self.ui_vars["afk_max_var"] = afk_max
        afk_min.trace_add("write", self._update_afk_min)
        afk_max.trace_add("write", self._update_afk_max)
        unit = self._get_unit_label()
        self._label_entry(panel, f"Timer Min ({unit}):", afk_min)
        self._label_entry(panel, f"Timer Max ({unit}):", afk_max)
        tk.Label(panel, text="Ctrl held down → arrow press → Ctrl released", font=SMALL, fg=MUTED, bg=PANEL).pack(anchor="w")
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 0))
        self._btn(buttons, "▶ Start", self.afk_service.start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self._btn(buttons, "⏹ Stop", self.afk_service.stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def _update_afk_min(self, *args) -> None:
        try:
            self.runtime.state.afk_min_ms = self._display_to_ms(float(self.ui_vars["afk_min_var"].get()))
        except ValueError:
            pass

    def _update_afk_max(self, *args) -> None:
        try:
            self.runtime.state.afk_max_ms = self._display_to_ms(float(self.ui_vars["afk_max_var"].get()))
        except ValueError:
            pass

    def _update_rclick_min(self, *args) -> None:
        try:
            self.runtime.state.rclick_min_ms = self._display_to_ms(float(self.ui_vars["rclick_min_var"].get()))
        except ValueError:
            pass

    def _update_rclick_max(self, *args) -> None:
        try:
            self.runtime.state.rclick_max_ms = self._display_to_ms(float(self.ui_vars["rclick_max_var"].get()))
        except ValueError:
            pass

    def _build_right_click_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(parent, text=" 🖱️  Right-Click Monitor ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        panel.pack(fill="x", pady=(0, 8))
        self.pos_label = tk.Label(panel, text="Pos: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.pos_label.pack(anchor="w", pady=(0, 4))
        self._btn(panel, "🎯 Record Position", self.record_rclick_pos, BLUE).pack(fill="x", pady=(0, 6))
        min_var = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rclick_min_ms)))
        max_var = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rclick_max_ms)))
        self.ui_vars["rclick_min_var"] = min_var
        self.ui_vars["rclick_max_var"] = max_var
        min_var.trace_add("write", self._update_rclick_min)
        max_var.trace_add("write", self._update_rclick_max)
        unit = self._get_unit_label()
        self._label_entry(panel, f"Timer Min ({unit}):", min_var)
        self._label_entry(panel, f"Timer Max ({unit}):", max_var)
        rclick_mode = tk.StringVar(value=self.runtime.state.rclick_mode)
        rclick_require_food = tk.BooleanVar(value=self.runtime.state.rclick_require_food)
        rclick_food_min = tk.StringVar(value=str(self.runtime.state.rclick_food_min_secs))
        rclick_food_burst_count = tk.StringVar(value=str(self.runtime.state.rclick_food_burst_count))
        rclick_food_burst_interval = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rclick_food_burst_interval_ms)))
        self.ui_vars["rclick_mode_var"] = rclick_mode
        self.ui_vars["rclick_require_food_var"] = rclick_require_food
        self.ui_vars["rclick_food_min_var"] = rclick_food_min
        self.ui_vars["rclick_food_burst_count_var"] = rclick_food_burst_count
        self.ui_vars["rclick_food_burst_interval_var"] = rclick_food_burst_interval
        mode_row = tk.Frame(panel, bg=PANEL)
        mode_row.pack(fill="x", pady=2)
        tk.Label(mode_row, text="Mode:", font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        mode_menu = tk.OptionMenu(mode_row, rclick_mode, "timer", "food")
        mode_menu.config(font=BODY, bg=PANEL, fg=FG, activebackground=BLUE, bd=0, relief="flat", highlightthickness=0)
        mode_menu["menu"].config(bg=PANEL, fg=FG, activebackground=BLUE, activeforeground="white")
        mode_menu.pack(side="left", padx=4)
        tk.Checkbutton(panel, text="Timer checks food threshold first", variable=rclick_require_food, font=BOLD, fg=FG, bg=PANEL, selectcolor=PANEL, activebackground=PANEL).pack(anchor="w", pady=(2, 2))
        self._label_entry(panel, "Min food timer (sec):", rclick_food_min, width=6)
        self._label_entry(panel, "Food burst clicks:", rclick_food_burst_count, width=6)
        self._label_entry(panel, f"Burst interval ({unit}):", rclick_food_burst_interval, width=6)
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 0))
        self._btn(buttons, "▶ Start", self.rclick_service.start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self._btn(buttons, "⏹ Stop", self.rclick_service.stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def _build_rune_tab(self, parent: tk.Frame) -> None:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        v_scroll = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        content_frame = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        left = tk.Frame(content_frame, bg=BG)
        right = tk.Frame(content_frame, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(6, 3), pady=6)
        right.pack(side="right", fill="both", expand=True, padx=(3, 6), pady=6)

        spell_panel = tk.LabelFrame(left, text=" ✨  Rune Session Timing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        spell_panel.pack(fill="x", pady=(0, 8))
        unit = self._get_unit_label()
        rune_spell = tk.StringVar(value=self.runtime.state.rune_spell_key)
        rune_cycle = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_cycle_delay_ms)))
        rune_cycle_variation = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_cycle_delay_variation_ms)))
        rune_jitter = tk.StringVar(value=str(self.runtime.state.rune_jitter))
        rune_cast = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_cast_delay_ms)))
        rune_blank_cycles = tk.StringVar(value=str(self.runtime.state.rune_available_blank_runes))
        rune_move_min = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_mouse_move_min_ms)))
        rune_move_max = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_mouse_move_max_ms)))
        rune_press_min = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_mouse_press_min_ms)))
        rune_press_max = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_mouse_press_max_ms)))
        rune_settle_min = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_mouse_settle_min_ms)))
        rune_settle_max = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.rune_mouse_settle_max_ms)))
        self.ui_vars["rune_spell_key_var"] = rune_spell
        self.ui_vars["rune_cycle_delay_var"] = rune_cycle
        self.ui_vars["rune_cycle_variation_var"] = rune_cycle_variation
        self.ui_vars["rune_jitter_var"] = rune_jitter
        self.ui_vars["rune_cast_delay_var"] = rune_cast
        self.ui_vars["rune_blank_cycles_var"] = rune_blank_cycles
        self.ui_vars["rune_move_min_var"] = rune_move_min
        self.ui_vars["rune_move_max_var"] = rune_move_max
        self.ui_vars["rune_press_min_var"] = rune_press_min
        self.ui_vars["rune_press_max_var"] = rune_press_max
        self.ui_vars["rune_settle_min_var"] = rune_settle_min
        self.ui_vars["rune_settle_max_var"] = rune_settle_max
        self._label_entry(spell_panel, "Spell hotkey:", rune_spell, width=6)
        self._label_entry(spell_panel, f"Cast settle delay ({unit}):", rune_cast, width=7)
        self._label_entry(spell_panel, f"Cycle delay base ({unit}):", rune_cycle, width=7)
        self._label_entry(spell_panel, f"Cycle variation ({unit}):", rune_cycle_variation, width=7)
        self._label_entry(spell_panel, "Position jitter (px ±):", rune_jitter, width=5)
        rune_min_mana = tk.StringVar(value=str(self.runtime.state.rune_min_mana))
        self.ui_vars["rune_min_mana_var"] = rune_min_mana
        self._label_entry(spell_panel, "Min mana to cast:", rune_min_mana, width=7)
        self._label_entry(spell_panel, "avb blank runes:", rune_blank_cycles, width=7)
        cycle_label = tk.Label(spell_panel, text="≈ Cycle time: —", font=SMALL_B, fg=TEAL, bg=PANEL)
        cycle_label.pack(anchor="w", pady=(6, 0))

        def update_cycle_preview(*_args):
            try:
                base_ms = self._display_to_ms(float(rune_cycle.get()))
                variation_ms = self._display_to_ms(float(rune_cycle_variation.get()))
                min_seconds = max(0.0, (base_ms - variation_ms) / 1000.0)
                max_seconds = (base_ms + variation_ms) / 1000.0
                cycle_label.config(
                    text=f"≈ {min_seconds:.1f}–{max_seconds:.1f} s between casts"
                )
            except ValueError:
                cycle_label.config(text="≈ Cycle time: —")

        rune_cycle.trace_add("write", update_cycle_preview)
        rune_cycle_variation.trace_add("write", update_cycle_preview)
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
            f"2.  Wait cast settle delay ({unit})",
            "3.  Acquire mouse lock",
            "4.  Drag rune: Hand → Finished storage",
            "5.  Drag blank: Blank stack → Hand slot",
            "6.  Release mouse lock",
            f"7.  Wait cycle delay ({unit})",
            "8.  Repeat",
        ]:
            tk.Label(how_panel, text=step, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x")
        timing_panel = tk.LabelFrame(right, text=" 🖱️  Mouse Timing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        timing_panel.pack(fill="x", pady=(0, 8))
        self._label_entry(timing_panel, f"Move min ({unit}):", rune_move_min, width=6)
        self._label_entry(timing_panel, f"Move max ({unit}):", rune_move_max, width=6)
        self._label_entry(timing_panel, f"Press min ({unit}):", rune_press_min, width=6)
        self._label_entry(timing_panel, f"Press max ({unit}):", rune_press_max, width=6)
        self._label_entry(timing_panel, f"Settle min ({unit}):", rune_settle_min, width=6)
        self._label_entry(timing_panel, f"Settle max ({unit}):", rune_settle_max, width=6)
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
        alarm_hp_percent = tk.StringVar(value=str(self.runtime.state.alarm_hp_percent))
        self.ui_vars["alarm_thresh_var"] = alarm_threshold
        self.ui_vars["alarm_hp_percent_var"] = alarm_hp_percent
        self._label_entry(panel, "Change threshold (%):", alarm_threshold, width=6)
        self._label_entry(panel, "Low HP alert (%):", alarm_hp_percent, width=6)
        auto_pause = tk.BooleanVar(value=self.runtime.state.alarm_auto_pause)
        self.ui_vars["alarm_auto_pause_var"] = auto_pause
        tk.Checkbutton(panel, text="Auto-pause all activities when screen watch triggers", variable=auto_pause, font=BOLD, bg=PANEL, fg=ORANGE, selectcolor=PANEL, activebackground=PANEL, activeforeground=ORANGE).pack(anchor="w", pady=(8, 2))
        tk.Label(panel, text="When enabled: all running features pause on screen change detection.\nWhen disabled: the alert sound plays and monitoring continues.", font=SMALL, fg=MUTED, bg=PANEL, justify="left").pack(anchor="w")
        action_row = tk.Frame(panel, bg=PANEL)
        action_row.pack(fill="x", pady=(10, 0))
        self._btn(action_row, "▶ Start Watching", self.alarm_service.start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self._btn(action_row, "⏹ Stop", self.alarm_service.stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def _build_healer_tab(self, parent: tk.Frame) -> None:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        v_scroll = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        content_frame = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        left = tk.Frame(content_frame, bg=BG)
        right = tk.Frame(content_frame, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(6, 3), pady=6)
        right.pack(side="right", fill="both", expand=True, padx=(3, 6), pady=6)

        mode_panel = tk.LabelFrame(left, text=" ❤️  Healing Mode ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        mode_panel.pack(fill="x", pady=(0, 8))
        healer_mode = tk.StringVar(value=self.runtime.state.healer_mode)
        healer_spell_key = tk.StringVar(value=self.runtime.state.healer_spell_key)
        healer_use_percent = tk.BooleanVar(value=self.runtime.state.healer_use_percent)
        healer_hp_percent = tk.StringVar(value=str(self.runtime.state.healer_hp_percent))
        healer_hp_value = tk.StringVar(value=str(self.runtime.state.healer_hp_value))
        healer_min_mana = tk.StringVar(value=str(self.runtime.state.healer_min_mana))
        self.ui_vars["healer_mode_var"] = healer_mode
        self.ui_vars["healer_spell_key_var"] = healer_spell_key
        self.ui_vars["healer_use_percent_var"] = healer_use_percent
        self.ui_vars["healer_hp_percent_var"] = healer_hp_percent
        self.ui_vars["healer_hp_value_var"] = healer_hp_value
        self.ui_vars["healer_min_mana_var"] = healer_min_mana
        mode_row = tk.Frame(mode_panel, bg=PANEL)
        mode_row.pack(fill="x", pady=2)
        tk.Label(mode_row, text="Heal with:", font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        mode_menu = tk.OptionMenu(mode_row, healer_mode, "spell", "rune")
        mode_menu.config(font=BODY, bg=PANEL, fg=FG, activebackground=BLUE, bd=0, relief="flat", highlightthickness=0)
        mode_menu["menu"].config(bg=PANEL, fg=FG, activebackground=BLUE, activeforeground="white")
        mode_menu.pack(side="left", padx=4)
        self._label_entry(mode_panel, "Spell hotkey:", healer_spell_key, width=6)
        tk.Checkbutton(mode_panel, text="Use HP percentage threshold", variable=healer_use_percent, font=BOLD, bg=PANEL, fg=FG, selectcolor=PANEL, activebackground=PANEL).pack(anchor="w", pady=(4, 2))
        self._label_entry(mode_panel, "Heal below HP %:", healer_hp_percent, width=6)
        self._label_entry(mode_panel, "Heal below HP value:", healer_hp_value, width=6)
        self._label_entry(mode_panel, "Min mana to heal:", healer_min_mana, width=6)

        rune_panel = tk.LabelFrame(left, text=" 🧿  Rune Healing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        rune_panel.pack(fill="x", pady=(0, 8))
        self.healer_char_label = tk.Label(rune_panel, text="Character center: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.healer_char_label.pack(anchor="w", pady=(0, 4))
        self.healer_rune_label = tk.Label(rune_panel, text="Healing rune: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.healer_rune_label.pack(anchor="w", pady=(0, 4))
        healer_mouse_speed = tk.StringVar(value=str(self.runtime.state.healer_mouse_speed))
        unit = self._get_unit_label()
        healer_rune_delay = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.healer_rune_delay_ms)))
        self.ui_vars["healer_mouse_speed_var"] = healer_mouse_speed
        self.ui_vars["healer_rune_delay_var"] = healer_rune_delay
        row = tk.Frame(rune_panel, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        self._btn(row, "🎯 Record Character", self.record_healer_character_pos, BLUE).pack(side="left", padx=(0, 4), expand=True, fill="x")
        self._btn(row, "🎯 Record Rune", self.record_healer_rune_pos, PURPLE).pack(side="left", padx=4, expand=True, fill="x")
        self._label_entry(rune_panel, "Mouse speed factor:", healer_mouse_speed, width=6)
        self._label_entry(rune_panel, f"Rune delay ({unit}):", healer_rune_delay, width=6)

        buttons = tk.Frame(left, bg=BG)
        buttons.pack(fill="x", pady=(0, 8))
        self._btn(buttons, "▶ Start Auto Healer", self.healer_service.start, GREEN).pack(fill="x", pady=2)
        self._btn(buttons, "⏹ Stop Auto Healer", self.healer_service.stop, RED).pack(fill="x", pady=2)

        help_panel = tk.LabelFrame(right, text=" ℹ️  Flow ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        help_panel.pack(fill="both", expand=True, pady=(0, 8))
        for line in [
            "1. Character Status provides the live HP values.",
            "2. Spell mode presses a game hotkey like F1/F2 when healing is needed.",
            "3. Rune mode right-clicks the recorded rune and then left-clicks your recorded character center.",
            "4. Rune healing uses the shared mouse lock so it will not fight fishing or rune maker.",
        ]:
            tk.Label(help_panel, text=line, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x", pady=2)

    def _build_light_tab(self, parent: tk.Frame) -> None:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        v_scroll = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        content_frame = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        wrapper = tk.Frame(content_frame, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=16, pady=10)
        panel = tk.LabelFrame(wrapper, text=" 💡  Light Memory Control - Alpha test ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=10, padx=14)
        panel.pack(fill="x")
        light_process = tk.StringVar(value=self.runtime.state.light_process_name)
        light_direct_address = tk.StringVar(value=self.runtime.state.light_direct_address_hex)
        light_freeze_enabled = tk.BooleanVar(value=self.runtime.state.light_freeze_enabled)
        light_freeze_interval = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.light_freeze_interval_ms)))
        self.ui_vars["light_process_name_var"] = light_process
        self.ui_vars["light_direct_address_hex_var"] = light_direct_address
        self.ui_vars["light_freeze_enabled_var"] = light_freeze_enabled
        self.ui_vars["light_freeze_interval_ms_var"] = light_freeze_interval
        self._label_entry(panel, "Process name:", light_process, width=22)
        self._label_entry(panel, "Target color address (hex):", light_direct_address, width=18)
        unit = self._get_unit_label()
        self._label_entry(panel, f"Freeze interval ({unit}):", light_freeze_interval, width=8)
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
        self._btn(buttons, "Attach", self.attach_light_process, BLUE).pack(side="left", padx=2, expand=True, fill="x")
        self._btn(buttons, "Apply Default", self.apply_light_default, ORANGE).pack(side="left", padx=2, expand=True, fill="x")
        self._btn(buttons, "Apply Boosted", self.apply_light_boosted, GREEN).pack(side="left", padx=2, expand=True, fill="x")
        self._btn(buttons, "Reset", self.reset_light_original, BLUE).pack(side="left", padx=2, expand=True, fill="x")
        tk.Label(panel, text="Leave target color address blank to use the pointer list from Light Pointers.CT. Apply Default writes color 215 and intensity 7. Apply Boosted writes color 215 and intensity 8 to the next byte. Reset restores the last unchanged pair that was captured before an apply.", font=SMALL, fg=MUTED, bg=PANEL, justify="left", wraplength=860).pack(anchor="w", pady=(10, 6))
        dep_text = "Light module ready" if HAS_LIGHT_MODULE else "Install psutil and pymem to use this tab"
        self.light_status_label = tk.Label(panel, text=dep_text, font=SMALL_B, fg=TEAL if HAS_LIGHT_MODULE else ORANGE, bg=PANEL, anchor="w", justify="left")
        self.light_status_label.pack(fill="x")

    def _build_fish_tab(self, parent: tk.Frame) -> None:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        v_scroll = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        content_frame = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        left = tk.Frame(content_frame, bg=BG)
        right = tk.Frame(content_frame, bg=BG)
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
        self.record_spot_btn = self._btn(spot_buttons, "+ Start Recording", self.record_spot, BLUE)
        self.record_spot_btn.pack(side="left", padx=2)
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
        unit = self._get_unit_label()
        cast_min = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.fish_cast_min_ms)))
        cast_max = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.fish_cast_max_ms)))
        wait_min = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.fish_wait_min_ms)))
        wait_max = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.fish_wait_max_ms)))
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
        self._label_entry(timing_panel, f"Cast delay Min ({unit}):", cast_min)
        self._label_entry(timing_panel, f"Cast delay Max ({unit}):", cast_max)
        self._label_entry(timing_panel, f"Wait for bite Min ({unit}):", wait_min)
        self._label_entry(timing_panel, f"Wait for bite Max ({unit}):", wait_max)
        fish_min_cap = tk.StringVar(value=str(self.runtime.state.fish_min_cap))
        self.ui_vars["fish_min_cap_var"] = fish_min_cap
        self._label_entry(timing_panel, "Stop below cap:", fish_min_cap, width=6)

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
            to=60,
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
        tk.Label(right, text="Quick toggle hotkey: see Hotkeys tab (fish_stop)", font=SMALL, fg=ORANGE, bg=BG).pack(anchor="w")

        help_panel = tk.LabelFrame(right, text=" ℹ️  How It Works ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        help_panel.pack(fill="both", expand=True, pady=(8, 0))
        help_text = (
            "Fishing automation simulates rod casting, waits for a bite, moves to the spot, "
            "reels in, then repeats with the next saved waypoint."
        )
        tk.Label(help_panel, text=help_text, font=SMALL, fg=FG, bg=PANEL, justify="left", wraplength=380).pack(anchor="w", pady=(0, 6))
        for line in [
            "1. Record the rod position first.",
            "2. Use F12 to save one or more fishing spots.",
            f"3. Recording stops 5 seconds after the last F12 press.",
            "4. Start the session; the automation repeats until stopped.",
            f"5. Timing values display in {self._get_unit_label()} and update instantly when toggled.",
        ]:
            tk.Label(help_panel, text=line, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x", pady=2)


    def _build_character_status_tab(self, parent: tk.Frame) -> None:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        v_scroll = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        content_frame = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        left = tk.Frame(content_frame, bg=BG)
        right = tk.Frame(content_frame, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(6, 3), pady=6)
        right.pack(side="right", fill="both", expand=True, padx=(3, 6), pady=6)

        watch_panel = tk.LabelFrame(left, text=" 📊  Status Window Watch ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        watch_panel.pack(fill="x", pady=(0, 8))
        self.char_status_region_label = tk.Label(
            watch_panel,
            text="Window: not selected",
            font=MONO,
            fg=TEAL,
            bg=PANEL,
        )
        self.char_status_region_label.pack(anchor="w", pady=(0, 4))
        unit = self._get_unit_label()
        char_poll = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.char_status_poll_ms)))
        char_samples = tk.StringVar(value=str(self.runtime.state.char_status_samples))
        char_sample_delay = tk.StringVar(value=str(self._ms_to_display(self.runtime.state.char_status_sample_delay_ms)))
        tesseract_path = tk.StringVar(value=self.runtime.state.char_status_tesseract_path)
        self.ui_vars["char_status_poll_var"] = char_poll
        self.ui_vars["char_status_samples_var"] = char_samples
        self.ui_vars["char_status_sample_delay_var"] = char_sample_delay
        self.ui_vars["char_status_tesseract_var"] = tesseract_path
        self._label_entry(watch_panel, f"Refresh every ({unit}):", char_poll, width=6)
        self._label_entry(watch_panel, "Samples per scan:", char_samples, width=6)
        self._label_entry(watch_panel, f"Delay between samples ({unit}):", char_sample_delay, width=6)
        tesseract_row = tk.Frame(watch_panel, bg=PANEL)
        tesseract_row.pack(fill="x", pady=2)
        tk.Label(tesseract_row, text="Tesseract path:", font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        self._entry(tesseract_row, tesseract_path, 28).pack(side="left", padx=4, fill="x", expand=True)
        self._btn(tesseract_row, "Browse", self.browse_tesseract_path, PURPLE).pack(side="left")
        self.char_status_tesseract_label = tk.Label(watch_panel, text="", font=SMALL, fg=MUTED, bg=PANEL, anchor="w", justify="left")
        self.char_status_tesseract_label.pack(fill="x", pady=(4, 0))
        field_regions = tk.Frame(watch_panel, bg=PANEL)
        field_regions.pack(fill="x", pady=(6, 0))
        self.char_status_hp_region_label = tk.Label(field_regions, text="HP area: not selected", font=MONO, fg=TEAL, bg=PANEL, anchor="w")
        self.char_status_hp_region_label.pack(fill="x", pady=1)
        self.char_status_mana_region_label = tk.Label(field_regions, text="Mana area: not selected", font=MONO, fg=TEAL, bg=PANEL, anchor="w")
        self.char_status_mana_region_label.pack(fill="x", pady=1)
        self.char_status_cap_region_label = tk.Label(field_regions, text="Cap area: not selected", font=MONO, fg=TEAL, bg=PANEL, anchor="w")
        self.char_status_cap_region_label.pack(fill="x", pady=1)
        button_row = tk.Frame(watch_panel, bg=PANEL)
        button_row.pack(fill="x", pady=(6, 0))
        self._btn(button_row, "🖼 Select Window", self.select_character_status_region, BLUE).pack(side="left", padx=(0, 4), expand=True, fill="x")
        self._btn(button_row, "HP", self.select_character_status_hp_region, PURPLE).pack(side="left", padx=4, expand=True, fill="x")
        self._btn(button_row, "Mana", self.select_character_status_mana_region, PURPLE).pack(side="left", padx=4, expand=True, fill="x")
        self._btn(button_row, "Cap", self.select_character_status_cap_region, PURPLE).pack(side="left", padx=4, expand=True, fill="x")
        button_row2 = tk.Frame(watch_panel, bg=PANEL)
        button_row2.pack(fill="x", pady=(6, 0))
        self._btn(button_row2, "▶ Start", self.char_status_service.start, GREEN).pack(side="left", padx=4, expand=True, fill="x")
        self._btn(button_row2, "⏹ Stop", self.char_status_service.stop, RED).pack(side="left", padx=4, expand=True, fill="x")
        self._btn(button_row2, "↺ Reset", self.reset_character_status_region, ORANGE).pack(side="left", padx=(4, 0), expand=True, fill="x")

        values_panel = tk.LabelFrame(left, text=" 🔎  Live Values ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        values_panel.pack(fill="both", expand=True, pady=(0, 8))
        self.char_status_watch_label = tk.Label(values_panel, text="Watcher: idle", font=SMALL_B, fg=ORANGE, bg=PANEL)
        self.char_status_watch_label.pack(anchor="w", pady=(0, 8))
        self.char_status_level_label = tk.Label(values_panel, text="Level: —", font=HEADER, fg=TEAL, bg=PANEL, anchor="w")
        self.char_status_level_label.pack(fill="x", pady=2)
        self.char_status_hp_label = tk.Label(values_panel, text="HP: —", font=HEADER, fg=RED, bg=PANEL, anchor="w")
        self.char_status_hp_label.pack(fill="x", pady=2)
        self.char_status_mana_label = tk.Label(values_panel, text="Mana: —", font=HEADER, fg=BLUE, bg=PANEL, anchor="w")
        self.char_status_mana_label.pack(fill="x", pady=2)
        self.char_status_cap_label = tk.Label(values_panel, text="Cap: —", font=HEADER, fg=TEAL, bg=PANEL, anchor="w")
        self.char_status_cap_label.pack(fill="x", pady=2)
        self.char_status_food_label = tk.Label(values_panel, text="Food: —", font=HEADER, fg=GREEN, bg=PANEL, anchor="w")
        self.char_status_food_label.pack(fill="x", pady=2)
        self.char_status_regen_label = tk.Label(values_panel, text="Regen: HP 0.0/min | Mana 0.0/min", font=MONO, fg=MUTED, bg=PANEL, anchor="w")
        self.char_status_regen_label.pack(fill="x", pady=2)
        self.char_status_seen_label = tk.Label(values_panel, text="Last update: —", font=MONO, fg=MUTED, bg=PANEL, anchor="w")
        self.char_status_seen_label.pack(fill="x", pady=(10, 2))
        self.char_status_error_label = tk.Label(values_panel, text="OCR: waiting for a valid read", font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w")
        self.char_status_error_label.pack(fill="x")

        help_panel = tk.LabelFrame(right, text=" ℹ️  How It Works ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        help_panel.pack(fill="both", expand=True, pady=(0, 8))
        for line in [
            "1. Best mode: select HP, Mana, and Cap areas individually.",
            "2. Fallback mode: select the full character status window if you want one-shot setup.",
            "3. Values stay in memory on runtime.state as char_status_hp / mana / cap.",
            "4. If OCR misses a frame, the last good values are kept until the next valid read.",
        ]:
            tk.Label(help_panel, text=line, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x", pady=2)
        dep_text = "Python OCR packages loaded" if (HAS_MSS and HAS_CV2 and HAS_TESSERACT) else "Install mss, opencv-python, and pytesseract to use this tab"
        tk.Label(help_panel, text=dep_text, font=SMALL_B, fg=TEAL if (HAS_MSS and HAS_CV2 and HAS_TESSERACT) else ORANGE, bg=PANEL, justify="left").pack(anchor="w", pady=(10, 0))

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
#        self._btn(buttons, "💾 Save XML", self.save_config_xml, PURPLE).pack(side="left", padx=8, ipadx=12)
        self._btn(buttons, "📂 Load", self.load_config, ORANGE).pack(side="left", padx=8, ipadx=12)

        # Time unit toggle
        toggle_frame = tk.Frame(wrapper, bg=BG)
        toggle_frame.pack(pady=(20, 0))
        tk.Label(toggle_frame, text="Timer Units:", font=BOLD, fg=FG, bg=BG).pack(side="left", padx=(0, 10))
        self.time_unit_var = tk.StringVar(value=self.runtime.state.time_unit)
        ms_btn = tk.Radiobutton(toggle_frame, text="Milliseconds", variable=self.time_unit_var, value="ms", bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, command=self._on_time_unit_change)
        ms_btn.pack(side="left", padx=(0, 10))
        s_btn = tk.Radiobutton(toggle_frame, text="Seconds", variable=self.time_unit_var, value="s", bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, command=self._on_time_unit_change)
        s_btn.pack(side="left")

    def _on_time_unit_change(self) -> None:
        new_unit = self.time_unit_var.get()
        if self.runtime.state.time_unit == new_unit:
            return
        # Force a poll with the current unit to save anything the user typed
        self._root_poll_settings_now()
        
        self.runtime.state.time_unit = new_unit
        self.runtime.ui.log(f"Timer units changed to {self.runtime.state.time_unit}")
        # Refresh all tabs to update displayed values
        self._refresh_all_tabs()

    def _root_poll_settings_now(self) -> None:
        self._poll_settings(schedule_next=False)
        for job in self.runtime.state.jobs:
            if hasattr(job, "row_frame") and job.row_frame:
                self._read_job_vars(job)

    def _ms_to_display(self, ms: int) -> float:
        if self.runtime.state.time_unit == "s":
            return ms / 1000.0
        return float(ms)

    def _display_to_ms(self, display: float) -> int:
        if self.runtime.state.time_unit == "s":
            return int(display * 1000)
        return int(display)

    def _get_unit_label(self) -> str:
        return "s" if self.runtime.state.time_unit == "s" else "ms"

    def _refresh_all_tabs(self) -> None:
        # Rebuild all tabs to reflect the new time unit
        notebook = self.notebook_widget
        if notebook is None:
            return

        for tab_name in notebook.tabs():
            tab = notebook.nametowidget(tab_name)
            for child in tab.winfo_children():
                child.destroy()
        
        # Rebuild each tab
        self._build_automation_tab(self.automation_tab)
        self._build_rune_tab(self.rune_tab)
        self._build_healer_tab(self.healer_tab)
        self._build_light_tab(self.light_tab)
        self._build_alarm_tab(self.alarm_tab)
        self._build_character_status_tab(self.char_status_tab)
        self._build_fish_tab(self.fish_tab)
        self._build_hotkeys_tab(self.hotkeys_tab)
        self._build_config_tab(self.config_tab)
        
        # Restore lists and labels from state
        self._sync_ui_from_state()

    def toggle_log_window(self) -> None:
        if self.log_window and self.log_window.winfo_exists() and self.log_window.state() != "withdrawn":
            self._hide_log_window()
            return
        self._show_log_window()

    def _show_log_window(self) -> None:
        if not self.root:
            return
        if not self.log_window or not self.log_window.winfo_exists():
            self.log_window = tk.Toplevel(self.root)
            self.log_window.title("SystemMonitor Live Log")
            self.log_window.configure(bg=BG)
            self.log_window.geometry("780x320")
            self.log_window.minsize(520, 220)
            self.log_window.protocol("WM_DELETE_WINDOW", self._hide_log_window)
            frame = tk.Frame(self.log_window, bg=BG)
            frame.pack(fill="both", expand=True, padx=12, pady=12)
            tk.Label(frame, text="Live Activity Log", font=BOLD, fg=MUTED, bg=BG).pack(anchor="w")
            self.log_widget = scrolledtext.ScrolledText(
                frame,
                height=14,
                bg=PANEL,
                fg=FG,
                font=MONO,
                relief="flat",
                bd=4,
                state="disabled",
            )
            self.log_widget.pack(fill="both", expand=True, pady=(6, 0))
            for line in self.log_history:
                self._append_log_line(line)
        else:
            self.log_window.deiconify()
        self.log_window.lift()
        self.log_window.focus_force()

    def _hide_log_window(self) -> None:
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.withdraw()

    def _show_sandbox_launcher_popup(self) -> None:
        if not self.root:
            return
        if not self.sandbox_launcher_popup or not self.sandbox_launcher_popup.winfo_exists():
            self.sandbox_launcher_popup = tk.Toplevel(self.root)
            self.sandbox_launcher_popup.title("PureCase")
            self.sandbox_launcher_popup.configure(bg=BG)
            self.sandbox_launcher_popup.geometry("700x650")
            self.sandbox_launcher_popup.minsize(600, 500)
            self.sandbox_launcher_popup.protocol("WM_DELETE_WINDOW", self._hide_sandbox_launcher_popup)
            
            frame = tk.Frame(self.sandbox_launcher_popup, bg=BG)
            frame.pack(fill="both", expand=True, padx=12, pady=12)
            
            # Detection status
            if self.sandbox_sbie_info:
                tk.Label(frame, text=f"✅ Sandboxie-Plus detected at: {self.sandbox_sbie_info.root}", font=SMALL_B, fg=TEAL, bg=BG).pack(anchor="w", pady=(0, 8))
            else:
                tk.Label(frame, text="⚠️  Sandboxie-Plus not detected; using Job Object backend.", font=SMALL_B, fg=ORANGE, bg=BG).pack(anchor="w", pady=(0, 8))
            
            tk.Label(frame, text="Sandbox Launcher Configuration", font=BOLD, fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 8))
            
            # Executable selection
            exe_frame = tk.Frame(frame, bg=PANEL)
            exe_frame.pack(fill="x", pady=4)
            tk.Label(exe_frame, text="Executable:", font=BOLD, fg=FG, bg=PANEL, width=16, anchor="w").pack(side="left", padx=4, pady=4)
            self.sandbox_exe_var = tk.StringVar(value=self.runtime.state.sandbox_exe_path)
            exe_entry = tk.Entry(exe_frame, textvariable=self.sandbox_exe_var, bg=BG, fg=FG, font=BODY, insertbackground=FG, relief="flat", bd=2)
            exe_entry.pack(side="left", padx=4, pady=4, fill="x", expand=True)
            self._btn(exe_frame, "Browse", self._browse_sandbox_exe, BLUE).pack(side="left", padx=(4, 4))
            
            # Backend selection
            backend_frame = tk.Frame(frame, bg=PANEL)
            backend_frame.pack(fill="x", pady=4)
            tk.Label(backend_frame, text="Backend:", font=BOLD, fg=FG, bg=PANEL, width=16, anchor="w").pack(side="left", padx=4, pady=4)
            self.sandbox_backend_var = tk.StringVar(value=self.runtime.state.sandbox_backend)
            backend_combo = ttk.Combobox(
                backend_frame,
                textvariable=self.sandbox_backend_var,
                values=["jobobj", "sandboxie"],
                state="readonly",
                width=20,
            )
            backend_combo.pack(side="left", padx=4, pady=4)
            backend_combo.bind("<<ComboboxSelected>>", lambda e: self._on_sandbox_backend_change())
            
            # Sandboxie box name (initially hidden)
            self.sandbox_box_frame = tk.Frame(frame, bg=PANEL)
            tk.Label(self.sandbox_box_frame, text="Box Name:", font=BOLD, fg=FG, bg=PANEL, width=16, anchor="w").pack(side="left", padx=4, pady=4)
            self.sandbox_box_var = tk.StringVar(value=self.runtime.state.sandbox_box_name)
            box_entry = tk.Entry(self.sandbox_box_frame, textvariable=self.sandbox_box_var, bg=BG, fg=FG, font=BODY, insertbackground=FG, relief="flat", bd=2, width=28)
            box_entry.pack(side="left", padx=4, pady=4, fill="x", expand=True)
            if not (self.sandbox_sbie_info):
                self.sandbox_box_frame.pack_forget()
            else:
                self.sandbox_box_frame.pack(fill="x", pady=4)
            
            # Arguments
            args_frame = tk.Frame(frame, bg=PANEL)
            args_frame.pack(fill="x", pady=4)
            tk.Label(args_frame, text="Arguments:", font=BOLD, fg=FG, bg=PANEL, width=16, anchor="w").pack(side="left", padx=4, pady=4)
            self.sandbox_args_var = tk.StringVar(value=self.runtime.state.sandbox_args)
            args_entry = tk.Entry(args_frame, textvariable=self.sandbox_args_var, bg=BG, fg=FG, font=BODY, insertbackground=FG, relief="flat", bd=2)
            args_entry.pack(side="left", padx=4, pady=4, fill="x", expand=True)
            
            # Options
            options_frame = tk.Frame(frame, bg=PANEL)
            options_frame.pack(fill="x", pady=4)
            tk.Label(options_frame, text="Options:", font=BOLD, fg=FG, bg=PANEL, width=16, anchor="w").pack(side="left", padx=4, pady=4, anchor="nw")
            
            opts_col = tk.Frame(options_frame, bg=PANEL)
            opts_col.pack(side="left", padx=4, pady=4, fill="both", expand=True)
            
            self.sandbox_spoof_env_var = tk.BooleanVar(value=self.runtime.state.sandbox_spoof_env)
            tk.Checkbutton(opts_col, text="Spoof Environment", variable=self.sandbox_spoof_env_var, bg=PANEL, fg=FG, selectcolor=PANEL, activebackground=PANEL).pack(anchor="w")
            
            # Update UI based on current backend
            self._on_sandbox_backend_change()
            
            # Log area
            tk.Label(frame, text="Launch Log:", font=SMALL_B, fg=MUTED, bg=BG).pack(anchor="w", pady=(8, 0))
            self.sandbox_log_widget = scrolledtext.ScrolledText(
                frame,
                height=12,
                bg=PANEL,
                fg=TEAL,
                font=MONO,
                relief="flat",
                bd=4,
                state="disabled",
            )
            self.sandbox_log_widget.pack(fill="both", expand=True, pady=(4, 8))
            
            # Control buttons
            btn_frame = tk.Frame(frame, bg=BG)
            btn_frame.pack(fill="x", pady=(4, 0))
            self.sandbox_launch_button = self._btn(btn_frame, "▶ Launch", self._launch_sandbox, GREEN)
            self.sandbox_launch_button.pack(side="left", padx=4, expand=True, fill="x")
            self.sandbox_kill_button = self._btn(btn_frame, "⏹ Terminate", self._terminate_sandbox, RED)
            self.sandbox_kill_button.pack(side="left", padx=4, expand=True, fill="x")
            self.sandbox_kill_button.config(state="disabled")
            
            self.ui_vars["sandbox_exe_path_var"] = self.sandbox_exe_var
            self.ui_vars["sandbox_args_var"] = self.sandbox_args_var
            self.ui_vars["sandbox_backend_var"] = self.sandbox_backend_var
            self.ui_vars["sandbox_box_name_var"] = self.sandbox_box_var
            self.ui_vars["sandbox_spoof_env_var"] = self.sandbox_spoof_env_var
        else:
            self.sandbox_launcher_popup.deiconify()
        self.sandbox_launcher_popup.lift()
        self.sandbox_launcher_popup.focus_force()

    def _hide_sandbox_launcher_popup(self) -> None:
        if self.sandbox_launcher_popup and self.sandbox_launcher_popup.winfo_exists():
            self.sandbox_launcher_popup.withdraw()

    def _browse_sandbox_exe(self) -> None:
        if not self.sandbox_exe_var:
            return
        path = filedialog.askopenfilename(
            title="Select executable",
            filetypes=[("Executables", "*.exe *.bat *.cmd"), ("All files", "*.*")],
        )
        if path:
            self.sandbox_exe_var.set(path.replace("/", "\\"))
            self.runtime.save_config()  # Save immediately after selection

    def _on_sandbox_backend_change(self) -> None:
        if self.sandbox_backend_var and self.sandbox_box_frame:
            if self.sandbox_backend_var.get() == "sandboxie" and self.sandbox_sbie_info:
                self.sandbox_box_frame.pack(fill="x", pady=(0, 8))
            else:
                self.sandbox_box_frame.pack_forget()

    def _append_sandbox_log_line(self, line: str) -> None:
        if not self.sandbox_log_widget or not self.sandbox_log_widget.winfo_exists():
            return
        self.sandbox_log_widget.configure(state="normal")
        self.sandbox_log_widget.insert("end", f"{line}\n")
        self.sandbox_log_widget.see("end")
        self.sandbox_log_widget.configure(state="disabled")

    def _sandbox_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self._append_sandbox_log_line(line)

    def _launch_sandbox(self) -> None:
        if not self.sandbox_exe_var:
            return
        exe = self.sandbox_exe_var.get().strip()
        if not exe:
            messagebox.showwarning("No executable", "Please select an executable first.")
            return
        if not os.path.isfile(exe):
            messagebox.showerror("File not found", f"Cannot find:\n{exe}")
            return

        backend = self.sandbox_backend_var.get() if self.sandbox_backend_var else "jobobj"
        use_sandboxie = backend == "sandboxie" and self.sandbox_sbie_info is not None
        box_name = self.sandbox_box_var.get().strip() if self.sandbox_box_var else "LauncherBox"
        args = self.sandbox_args_var.get().strip() if self.sandbox_args_var else ""
        drop_admin = False  # Removed checkbox, always False
        spoof_env = bool(self.sandbox_spoof_env_var.get()) if self.sandbox_spoof_env_var else True

        self.sandbox_launch_button.config(state="disabled")
        self.sandbox_kill_button.config(state="normal")
        self._sandbox_log("Launching sandboxed process...")

        def worker() -> None:
            try:
                if use_sandboxie:
                    self._sandbox_log("Backend: Sandboxie-Plus")
                    proc = launch_in_box(
                        installation=self.sandbox_sbie_info,
                        box_name=box_name,
                        executable=exe,
                        args=args,
                        drop_admin=drop_admin,
                        ensure=True,
                        log_callback=self._sandbox_log,
                    )
                else:
                    self._sandbox_log("Backend: Job Object")
                    proc = launch_with_job_object(
                        executable=exe,
                        args=args,
                        drop_admin=drop_admin,
                        spoof_env=spoof_env,
                        log_callback=self._sandbox_log,
                    )
                self.sandbox_proc = proc
                self._sandbox_log(f"Process started: PID={proc.pid}")
            except Exception as exc:
                self._sandbox_log(f"Launch failed: {exc}")
                self.sandbox_launch_button.config(state="normal")
                self.sandbox_kill_button.config(state="disabled")

        threading.Thread(target=worker, daemon=True).start()

    def _terminate_sandbox(self) -> None:
        if not self.sandbox_proc:
            return
        try:
            self.sandbox_proc.terminate()
            self._sandbox_log("Terminate requested.")
        except Exception as exc:
            self._sandbox_log(f"Terminate failed: {exc}")
        finally:
            self.sandbox_launch_button.config(state="normal")
            self.sandbox_kill_button.config(state="disabled")

    def _append_log_line(self, line: str) -> None:
        if not self.log_widget or not self.log_widget.winfo_exists():
            return
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", f"{line}\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

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
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.log_history.append(line)
        self._append_log_line(line)

    def _set_status(self, text: str, color: str) -> None:
        if self.status_label:
            self.status_label.config(text=text, fg=color)
            self.status_label.config(wraplength=max(320, self.root.winfo_width() - 48))

    def _on_root_resize(self, event) -> None:
        if event.widget is not self.root:
            return
        if self.status_label:
            self.status_label.config(wraplength=max(320, event.width - 48))

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
                f"Fish: {stats['fish_casts']}  |  Runes: {stats['runes_made']}  |  Heals: {stats['heals']}  |  "
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
        if self._fish_spot_recording:
            self._stop_fish_spot_recording()
            return

        self.runtime.state.fish_spots.clear()
        if self.spots_listbox:
            self.spots_listbox.delete(0, "end")

        self._fish_spot_recording = True
        if self.record_spot_btn:
            self.record_spot_btn.config(text="⏹ Stop Recording", bg=RED)
        self.runtime.ui.log("🎣 Fishing spot recording started. Press F12 to save each waypoint.")
        self.runtime.ui.set_status("Fishing spot recording active", ORANGE)
        self._start_fish_spot_listener()

    def _start_fish_spot_listener(self) -> None:
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing. Cannot record fishing spots.")
            self._fish_spot_recording = False
            if self.record_spot_btn:
                self.record_spot_btn.config(text="+ Start Recording", bg=BLUE)
            return

        self._fish_spot_listener = pynput_kb.Listener(on_press=self._on_fish_spot_key)
        self._fish_spot_listener.daemon = True
        self._fish_spot_listener.start()

    def _on_fish_spot_key(self, key) -> None:
        if not self._fish_spot_recording:
            return

        if HotkeyService.matches(key, self.runtime.state.hotkey_bindings.get("record_pos", "f12")):
            pos = pynput_mouse.Controller().position
            if self.root:
                self.root.after(0, lambda: self._add_fish_spot(pos))

    def _stop_fish_spot_recording(self) -> None:
        self._fish_spot_recording = False
        if self._fish_spot_listener:
            try:
                self._fish_spot_listener.stop()
            except Exception:
                pass
            self._fish_spot_listener = None
        if self.record_spot_btn:
            self.record_spot_btn.config(text="+ Start Recording", bg=BLUE)
        count = len(self.runtime.state.fish_spots)
        self.runtime.ui.log(f"🎣 Fishing spot recording stopped. {count} positions saved.")
        self.runtime.ui.set_status(f"Recording stopped: {count} spots", BLUE)

    def _add_fish_spot(self, pos: tuple[int, int] | None = None) -> None:
        def on_done(captured_pos: tuple[int, int]) -> None:
            self.runtime.state.fish_spots.append(captured_pos)
            count = len(self.runtime.state.fish_spots)
            self.runtime.ui.log(f"✅ Spot #{count}: {captured_pos}")
            self.runtime.ui.set_status(f"Spot #{count} added", GREEN)
            if self.spots_listbox:
                self.spots_listbox.insert("end", f"#{count}  {captured_pos[0]},{captured_pos[1]}")

        if pos is not None:
            on_done(pos)
            return

        next_index = len(self.runtime.state.fish_spots) + 1
        self.position_capture.capture(on_done, f"fishing spot #{next_index}")

    def _start_recording_timer(self) -> None:
        self._recording_timer = self.root.after(5000, self._stop_recording)

    def _reset_recording_timer(self) -> None:
        if hasattr(self, '_recording_timer') and self._recording_timer:
            self.root.after_cancel(self._recording_timer)
        self._start_recording_timer()

    def _stop_recording(self) -> None:
        self._recording_timer = None
        count = len(self.runtime.state.fish_spots)
        self.runtime.ui.log(f"🎣 Recording stopped. {count} fishing positions saved.")
        self.runtime.ui.set_status(f"Recording complete: {count} spots", BLUE)

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

    def record_healer_character_pos(self) -> None:
        self._record_generic_position("healer_character_pos", self.healer_char_label, "Character center", "Character center")

    def record_healer_rune_pos(self) -> None:
        self._record_generic_position("healer_rune_pos", self.healer_rune_label, "Healing rune", "Healing rune")

    def _record_rune_position(self, attr_name: str, label: tk.Label | None, label_text: str) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            setattr(self.runtime.state, attr_name, pos)
            self.runtime.ui.log(f"✅ {label_text}: {pos}")
            self.runtime.ui.set_status(f"{label_text} captured", GREEN)
            if label:
                label.config(text=f"{label_text}: {pos[0]},{pos[1]}")

        self.position_capture.capture(on_done, label_text)

    def _record_generic_position(self, attr_name: str, label: tk.Label | None, label_text: str, capture_label: str) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            setattr(self.runtime.state, attr_name, pos)
            self.runtime.ui.log(f"✅ {label_text}: {pos}")
            self.runtime.ui.set_status(f"{label_text} captured", GREEN)
            if label:
                label.config(text=f"{label_text}: {pos[0]}, {pos[1]}")

        self.position_capture.capture(on_done, capture_label)

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
        unit = self._get_unit_label()
        for label, name, default in [
            (f"Min ({unit}):", "min", str(self._ms_to_display(job.min_ms))),
            (f"Max ({unit}):", "max", str(self._ms_to_display(job.max_ms))),
        ]:
            tk.Label(row1, text=label, font=BOLD, fg=FG, bg=PANEL).pack(side="left", padx=(8, 0))
            value = tk.StringVar(value=default)
            self._entry(row1, value, 6).pack(side="left", padx=4)
            outer._vars[name] = value
        tk.Label(row1, text="Min mana:", font=BOLD, fg=FG, bg=PANEL).pack(side="left", padx=(8, 0))
        min_mana_var = tk.StringVar(value=str(job.min_mana))
        self._entry(row1, min_mana_var, 6).pack(side="left", padx=4)
        outer._vars["min_mana"] = min_mana_var
        indicator = tk.Label(row1, text="●", font=BOLD, fg=MUTED, bg=PANEL)
        indicator.pack(side="right", padx=4)
        outer._indicator = indicator

        row2 = tk.Frame(outer, bg=PANEL)
        row2.pack(fill="x", pady=2)
        burst_var = tk.BooleanVar(value=job.burst_enabled)
        outer._vars["burst"] = burst_var
        tk.Checkbutton(row2, text="Burst", variable=burst_var, font=BODY, bg=PANEL, fg=FG, selectcolor=PANEL, activebackground=PANEL).pack(side="left")
        for label, name, default in [
            ("Chance%:", "b_chance", str(int(job.burst_chance * 100))),
            ("Cnt min:", "b_cmin", str(job.burst_cnt_min)),
            ("Cnt max:", "b_cmax", str(job.burst_cnt_max)),
            (f"Int ({unit}):", "b_int", str(self._ms_to_display(job.burst_int_ms))),
        ]:
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
            job.min_ms = self._display_to_ms(float(vars_map["min"].get()))
            job.max_ms = self._display_to_ms(float(vars_map["max"].get()))
            job.min_mana = int(vars_map["min_mana"].get())
            job.burst_enabled = vars_map["burst"].get()
            job.burst_chance = int(vars_map["b_chance"].get()) / 100.0
            job.burst_cnt_min = int(vars_map["b_cmin"].get())
            job.burst_cnt_max = int(vars_map["b_cmax"].get())
            job.burst_int_ms = self._display_to_ms(float(vars_map["b_int"].get()))
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
                    self.root.after(0, lambda: self.fishing_service.stop() if state.fish_active else self.fishing_service.start())
                elif HotkeyService.matches(key, bindings.get("rune_stop", "f10")):
                    self.root.after(0, lambda: self.rune_service.stop() if state.rune_active else self.rune_service.start())
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
        self.healer_service.stop()

    def reset_alarm_area(self) -> None:
        self.runtime.state.alarm_region = None
        if self.alarm_region_label:
            self.alarm_region_label.config(text="Area: centre 200×200 px (default)")
        self.runtime.ui.log("ℹ️  Screen watch area reset")

    def reset_character_status_region(self) -> None:
        self.char_status_service.stop()
        state = self.runtime.state
        state.char_status_region = None
        state.char_status_hp_region = None
        state.char_status_mana_region = None
        state.char_status_cap_region = None
        state.char_status_level = None
        state.char_status_hp = None
        state.char_status_mana = None
        state.char_status_cap = None
        state.char_status_food_seconds = None
        state.char_status_food_text = ""
        state.char_status_hp_peak = 0
        state.char_status_hp_regen_per_min = 0.0
        state.char_status_mana_regen_per_min = 0.0
        state.char_status_last_seen = None
        state.char_status_last_error = ""
        self._refresh_character_status_display()
        self.runtime.ui.log("ℹ️  Character status window reset")

    def browse_alarm_sound(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.ogg"), ("All", "*.*")])
        if path:
            self.runtime.state.alarm_mp3 = path
            self.ui_vars["alarm_mp3_var"].set(path)

    def browse_tesseract_path(self) -> None:
        path = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("Tesseract", "tesseract.exe"), ("Executables", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.runtime.state.char_status_tesseract_path = path
            self.ui_vars["char_status_tesseract_var"].set(path)
            self._refresh_character_status_display()

    def attach_light_process(self) -> None:
        ok, message = self.light_service.attach()
        self._set_light_status(ok, message)

    def toggle_light_freeze(self) -> None:
        enabled = bool(self.ui_vars.get("light_freeze_enabled_var").get()) if "light_freeze_enabled_var" in self.ui_vars else False
        ok, message = self.light_service.set_freeze_enabled(enabled)
        self._set_light_status(ok, message)

    def apply_light_default(self) -> None:
        ok, message = self.light_service.apply_default()
        self._set_light_status(ok, message)

    def apply_light_boosted(self) -> None:
        ok, message = self.light_service.apply_boosted()
        self._set_light_status(ok, message)

    def reset_light_original(self) -> None:
        ok, message = self.light_service.reset_original()
        self._set_light_status(ok, message)

    def _set_light_status(self, success: bool, message: str) -> None:
        color = TEAL if success else ORANGE
        if self.light_status_label:
            self.light_status_label.config(text=message, fg=color)
        self.runtime.ui.log(("✅ " if success else "❌ ") + message)

    def select_alarm_area(self) -> None:
        self._select_screen_region(
            title="Click & drag to select alarm area  |  Esc = cancel",
            on_done=self._apply_alarm_region,
        )

    def select_character_status_region(self) -> None:
        self._select_screen_region(
            title="Select the full character status window  |  Esc = cancel",
            on_done=self._apply_character_status_region,
        )

    def select_character_status_hp_region(self) -> None:
        self._select_screen_region(
            title="Select HP number area  |  Esc = cancel",
            on_done=lambda region: self._apply_character_status_field_region("hp", region),
        )

    def select_character_status_mana_region(self) -> None:
        self._select_screen_region(
            title="Select Mana number area  |  Esc = cancel",
            on_done=lambda region: self._apply_character_status_field_region("mana", region),
        )

    def select_character_status_cap_region(self) -> None:
        self._select_screen_region(
            title="Select Cap text/number area  |  Esc = cancel",
            on_done=lambda region: self._apply_character_status_field_region("cap", region),
        )

    def _apply_alarm_region(self, region: tuple[int, int, int, int]) -> None:
        x_val, y_val, width, height = region
        self.runtime.state.alarm_region = region
        text = f"Area: ({x_val},{y_val})  {width}×{height} px"
        self.runtime.ui.log(f"✅ Screen watch area: {text}")
        self.runtime.ui.set_status(f"Screen watch area: {text}", TEAL)
        if self.alarm_region_label:
            self.alarm_region_label.config(text=text)

    def _apply_character_status_region(self, region: tuple[int, int, int, int]) -> None:
        self.runtime.state.char_status_region = region
        self._refresh_character_status_display()
        self.runtime.ui.log(f"✅ Character status window selected: {region}")
        self.runtime.ui.set_status("Character status window selected", TEAL)
        self.char_status_service.restart_if_needed()

    def _apply_character_status_field_region(self, key: str, region: tuple[int, int, int, int]) -> None:
        setattr(self.runtime.state, f"char_status_{key}_region", region)
        self._refresh_character_status_display()
        self.runtime.ui.log(f"✅ Character status {key.upper()} area selected: {region}")
        self.runtime.ui.set_status(f"Character status {key.upper()} area selected", TEAL)
        self.char_status_service.restart_if_needed()

    def _select_screen_region(self, title: str, on_done) -> None:
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.30)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="black")
        overlay.overrideredirect(True)
        canvas = tk.Canvas(overlay, cursor="crosshair", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        tk.Label(canvas, text=f"  {title}  ", font=BOLD, fg=TEAL, bg="black").place(x=20, y=20)
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
            overlay.destroy()
            if width < 10 or height < 10:
                return
            on_done((x_val, y_val, width, height))

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
            if self.runtime.state.char_status_region or self.runtime.state.char_status_hp_region or self.runtime.state.char_status_mana_region or self.runtime.state.char_status_cap_region:
                self.char_status_service.restart_if_needed()
            else:
                self.char_status_service.stop()
            self.runtime.ui.log(f"📂 Loaded: {path}")
            self.runtime.ui.log("✅ Config applied")
            self.runtime.ui.set_status("Config loaded", GREEN)
        except Exception as exc:
            self.runtime.ui.log(f"❌ Load failed: {exc}")

    def _sync_ui_from_state(self) -> None:
        state = self.runtime.state
        ms_mappings = {
            "afk_min_var": state.afk_min_ms,
            "afk_max_var": state.afk_max_ms,
            "rclick_min_var": state.rclick_min_ms,
            "rclick_max_var": state.rclick_max_ms,
            "char_status_poll_var": state.char_status_poll_ms,
            "char_status_sample_delay_var": state.char_status_sample_delay_ms,
            "fish_cast_min_var": state.fish_cast_min_ms,
            "fish_cast_max_var": state.fish_cast_max_ms,
            "fish_wait_min_var": state.fish_wait_min_ms,
            "fish_wait_max_var": state.fish_wait_max_ms,
            "rclick_food_burst_interval_var": state.rclick_food_burst_interval_ms,
            "rune_cycle_delay_var": state.rune_cycle_delay_ms,
            "rune_cycle_variation_var": state.rune_cycle_delay_variation_ms,
            "rune_cast_delay_var": state.rune_cast_delay_ms,
            "rune_move_min_var": state.rune_mouse_move_min_ms,
            "rune_move_max_var": state.rune_mouse_move_max_ms,
            "rune_press_min_var": state.rune_mouse_press_min_ms,
            "rune_press_max_var": state.rune_mouse_press_max_ms,
            "rune_settle_min_var": state.rune_mouse_settle_min_ms,
            "rune_settle_max_var": state.rune_mouse_settle_max_ms,
            "healer_rune_delay_var": state.healer_rune_delay_ms,
            "light_freeze_interval_ms_var": state.light_freeze_interval_ms,
        }
        for name, value in ms_mappings.items():
            if name in self.ui_vars:
                # Convert correctly into strings via ms_to_display
                self.ui_vars[name].set(str(self._ms_to_display(value)))

        mappings = {
            "alarm_mp3_var": state.alarm_mp3,
            "alarm_thresh_var": int(state.alarm_threshold * 100),
            "alarm_hp_percent_var": state.alarm_hp_percent,
            "char_status_tesseract_var": state.char_status_tesseract_path,
            "char_status_samples_var": state.char_status_samples,
            "fish_min_cap_var": state.fish_min_cap,
            "fish_rod_jit_var": state.fish_rod_jitter,
            "fish_spot_jit_var": state.fish_spot_jitter,
            "fish_session_var": state.fish_session_minutes,
            "rclick_mode_var": state.rclick_mode,
            "rclick_food_min_var": state.rclick_food_min_secs,
            "rclick_require_food_var": state.rclick_require_food,
            "rclick_food_burst_count_var": state.rclick_food_burst_count,
            "rune_spell_key_var": state.rune_spell_key,
            "rune_jitter_var": state.rune_jitter,
            "rune_min_mana_var": state.rune_min_mana,
            "rune_blank_cycles_var": state.rune_available_blank_runes,
            "healer_mode_var": state.healer_mode,
            "healer_spell_key_var": state.healer_spell_key,
            "healer_use_percent_var": state.healer_use_percent,
            "healer_hp_percent_var": state.healer_hp_percent,
            "healer_hp_value_var": state.healer_hp_value,
            "healer_min_mana_var": state.healer_min_mana,
            "healer_mouse_speed_var": state.healer_mouse_speed,
            "healer_rune_delay_var": state.healer_rune_delay_ms,
            "light_process_name_var": state.light_process_name,
            "light_direct_address_hex_var": state.light_direct_address_hex,
            "light_freeze_interval_ms_var": state.light_freeze_interval_ms,
        }
        for name, value in mappings.items():
            if name in self.ui_vars:
                self.ui_vars[name].set(str(value))
        if "alarm_auto_pause_var" in self.ui_vars:
            self.ui_vars["alarm_auto_pause_var"].set(state.alarm_auto_pause)
        if "healer_use_percent_var" in self.ui_vars:
            self.ui_vars["healer_use_percent_var"].set(state.healer_use_percent)
        if "light_freeze_enabled_var" in self.ui_vars:
            self.ui_vars["light_freeze_enabled_var"].set(state.light_freeze_enabled)
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
        if self.healer_char_label:
            self.healer_char_label.config(text=f"Character center: {state.healer_character_pos[0]}, {state.healer_character_pos[1]}")
        if self.healer_rune_label:
            self.healer_rune_label.config(text=f"Healing rune: {state.healer_rune_pos[0]}, {state.healer_rune_pos[1]}")
        if self.alarm_region_label:
            if state.alarm_region:
                x_val, y_val, width, height = state.alarm_region
                self.alarm_region_label.config(text=f"Area: ({x_val},{y_val}) {width}×{height} px")
            else:
                self.alarm_region_label.config(text="Area: centre 200×200 px (default)")
        self._refresh_character_status_display()
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

    def _poll_settings(self, schedule_next: bool = True) -> None:
        state = self.runtime.state

        def get_int(name: str, default: int) -> int:
            try:
                return int(self.ui_vars[name].get()) if name in self.ui_vars else default
            except ValueError:
                return default

        def get_ms(name: str, default: int) -> int:
            try:
                return self._display_to_ms(float(self.ui_vars[name].get())) if name in self.ui_vars else default
            except (ValueError, KeyError):
                return default

        with self.runtime.settings_lock:
            state.afk_min_ms = get_ms("afk_min_var", state.afk_min_ms)
            state.afk_max_ms = get_ms("afk_max_var", state.afk_max_ms)
            state.rclick_min_ms = get_ms("rclick_min_var", state.rclick_min_ms)
            state.rclick_max_ms = get_ms("rclick_max_var", state.rclick_max_ms)
            if "rclick_mode_var" in self.ui_vars:
                state.rclick_mode = str(self.ui_vars["rclick_mode_var"].get()).strip().lower() or "timer"
            state.rclick_food_min_secs = max(0, get_int("rclick_food_min_var", state.rclick_food_min_secs))
            state.rclick_food_burst_count = max(1, get_int("rclick_food_burst_count_var", state.rclick_food_burst_count))
            state.rclick_food_burst_interval_ms = max(50, get_ms("rclick_food_burst_interval_var", state.rclick_food_burst_interval_ms))
            state.alarm_threshold = get_int("alarm_thresh_var", int(state.alarm_threshold * 100)) / 100.0
            state.alarm_hp_percent = max(0, min(100, get_int("alarm_hp_percent_var", state.alarm_hp_percent)))
            state.char_status_poll_ms = max(250, get_ms("char_status_poll_var", state.char_status_poll_ms))
            state.char_status_samples = max(1, get_int("char_status_samples_var", state.char_status_samples))
            state.char_status_sample_delay_ms = max(0, get_ms("char_status_sample_delay_var", state.char_status_sample_delay_ms))
            # Scale samples according to frequency: more frequent scans get fewer samples
            if "char_status_samples_var" not in self.ui_vars:  # If not manually set, scale
                state.char_status_samples = max(1, 2000 // state.char_status_poll_ms)
            if "alarm_auto_pause_var" in self.ui_vars:
                state.alarm_auto_pause = bool(self.ui_vars["alarm_auto_pause_var"].get())
            if "alarm_mp3_var" in self.ui_vars:
                state.alarm_mp3 = str(self.ui_vars["alarm_mp3_var"].get())
            if "char_status_tesseract_var" in self.ui_vars:
                state.char_status_tesseract_path = str(self.ui_vars["char_status_tesseract_var"].get()).strip()
            state.fish_cast_min_ms = get_ms("fish_cast_min_var", state.fish_cast_min_ms)
            state.fish_cast_max_ms = get_ms("fish_cast_max_var", state.fish_cast_max_ms)
            state.fish_wait_min_ms = get_ms("fish_wait_min_var", state.fish_wait_min_ms)
            state.fish_wait_max_ms = get_ms("fish_wait_max_var", state.fish_wait_max_ms)
            state.fish_min_cap = max(0, get_int("fish_min_cap_var", state.fish_min_cap))
            state.fish_rod_jitter = get_int("fish_rod_jit_var", state.fish_rod_jitter)
            state.fish_spot_jitter = get_int("fish_spot_jit_var", state.fish_spot_jitter)
            state.fish_session_minutes = max(1, min(60, get_int("fish_session_var", state.fish_session_minutes)))
            if "rune_spell_key_var" in self.ui_vars:
                state.rune_spell_key = str(self.ui_vars["rune_spell_key_var"].get()).lower().strip()
            state.rune_cycle_delay_ms = get_ms("rune_cycle_delay_var", state.rune_cycle_delay_ms)
            state.rune_cycle_delay_variation_ms = max(0, get_ms("rune_cycle_variation_var", state.rune_cycle_delay_variation_ms))
            state.rune_jitter = get_int("rune_jitter_var", state.rune_jitter)
            state.rune_cast_delay_ms = get_ms("rune_cast_delay_var", state.rune_cast_delay_ms)
            state.rune_min_mana = max(0, get_int("rune_min_mana_var", state.rune_min_mana))
            state.rune_available_blank_runes = max(0, get_int("rune_blank_cycles_var", state.rune_available_blank_runes))
            state.rune_mouse_move_min_ms = max(20, get_ms("rune_move_min_var", state.rune_mouse_move_min_ms))
            state.rune_mouse_move_max_ms = max(state.rune_mouse_move_min_ms, get_ms("rune_move_max_var", state.rune_mouse_move_max_ms))
            state.rune_mouse_press_min_ms = max(10, get_ms("rune_press_min_var", state.rune_mouse_press_min_ms))
            state.rune_mouse_press_max_ms = max(state.rune_mouse_press_min_ms, get_ms("rune_press_max_var", state.rune_mouse_press_max_ms))
            state.rune_mouse_settle_min_ms = max(10, get_ms("rune_settle_min_var", state.rune_mouse_settle_min_ms))
            state.rune_mouse_settle_max_ms = max(state.rune_mouse_settle_min_ms, get_ms("rune_settle_max_var", state.rune_mouse_settle_max_ms))
            if "healer_mode_var" in self.ui_vars:
                state.healer_mode = str(self.ui_vars["healer_mode_var"].get()).strip().lower() or "spell"
            if "healer_spell_key_var" in self.ui_vars:
                state.healer_spell_key = str(self.ui_vars["healer_spell_key_var"].get()).lower().strip()
            if "healer_use_percent_var" in self.ui_vars:
                state.healer_use_percent = bool(self.ui_vars["healer_use_percent_var"].get())
            state.healer_hp_percent = max(1, min(100, get_int("healer_hp_percent_var", state.healer_hp_percent)))
            state.healer_hp_value = max(1, get_int("healer_hp_value_var", state.healer_hp_value))
            state.healer_min_mana = max(0, get_int("healer_min_mana_var", state.healer_min_mana))
            try:
                state.healer_mouse_speed = max(0.2, min(3.0, float(self.ui_vars["healer_mouse_speed_var"].get())))
            except (KeyError, ValueError):
                pass
            state.healer_rune_delay_ms = max(50, get_ms("healer_rune_delay_var", state.healer_rune_delay_ms))
            if "light_process_name_var" in self.ui_vars:
                state.light_process_name = str(self.ui_vars["light_process_name_var"].get()).strip()
            if "light_direct_address_hex_var" in self.ui_vars:
                state.light_direct_address_hex = str(self.ui_vars["light_direct_address_hex_var"].get()).strip()
            if "light_freeze_enabled_var" in self.ui_vars:
                state.light_freeze_enabled = bool(self.ui_vars["light_freeze_enabled_var"].get())
            if "light_freeze_interval_ms_var" in self.ui_vars:
                state.light_freeze_interval_ms = max(30, get_ms("light_freeze_interval_ms_var", state.light_freeze_interval_ms))
        self._refresh_character_status_display()
        self._refresh_fish_session_display()
        if schedule_next:
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

    def _refresh_character_status_display(self) -> None:
        state = self.runtime.state
        if self.char_status_region_label:
            if state.char_status_region:
                x_val, y_val, width, height = state.char_status_region
                self.char_status_region_label.config(
                    text=f"Window: ({x_val},{y_val})  {width}×{height} px"
                )
            else:
                self.char_status_region_label.config(text="Window: not selected")
        self._refresh_character_status_region_label(self.char_status_hp_region_label, "HP area", state.char_status_hp_region)
        self._refresh_character_status_region_label(self.char_status_mana_region_label, "Mana area", state.char_status_mana_region)
        self._refresh_character_status_region_label(self.char_status_cap_region_label, "Cap area", state.char_status_cap_region)
        if self.char_status_tesseract_label:
            dependency_error = self.char_status_service.get_dependency_error()
            if dependency_error == "Tesseract executable not found":
                self.char_status_tesseract_label.config(
                    text="Tesseract: not found automatically. Set the full path to tesseract.exe here.",
                    fg=ORANGE,
                )
            elif dependency_error:
                self.char_status_tesseract_label.config(text=f"Tesseract: {dependency_error}", fg=ORANGE)
            else:
                active_path = self.runtime.state.char_status_tesseract_path.strip() or "auto-detected"
                self.char_status_tesseract_label.config(text=f"Tesseract: ready ({active_path})", fg=TEAL)
        if self.char_status_watch_label:
            watch_text = "Watcher: active" if state.char_status_active else "Watcher: idle"
            watch_color = GREEN if state.char_status_active else ORANGE
            self.char_status_watch_label.config(text=watch_text, fg=watch_color)
        if self.char_status_level_label:
            self.char_status_level_label.config(text=f"Level: {state.char_status_level if state.char_status_level is not None else '—'}")
        if self.char_status_hp_label:
            self.char_status_hp_label.config(text=f"HP: {state.char_status_hp if state.char_status_hp is not None else '—'}")
        if self.char_status_mana_label:
            self.char_status_mana_label.config(text=f"Mana: {state.char_status_mana if state.char_status_mana is not None else '—'}")
        if self.char_status_cap_label:
            self.char_status_cap_label.config(text=f"Cap: {state.char_status_cap if state.char_status_cap is not None else '—'}")
        if self.char_status_food_label:
            self.char_status_food_label.config(text=f"Food: {state.char_status_food_text or '—'}")
        if self.char_status_regen_label:
            self.char_status_regen_label.config(
                text=f"Regen: HP {state.char_status_hp_regen_per_min:.1f}/min | Mana {state.char_status_mana_regen_per_min:.1f}/min"
            )
        if self.char_status_seen_label:
            if state.char_status_last_seen:
                seen = time.strftime("%H:%M:%S", time.localtime(state.char_status_last_seen))
                peak_text = f"  |  HP max: {state.char_status_hp_peak}" if state.char_status_hp_peak else ""
                self.char_status_seen_label.config(
                    text=f"Last update: {seen}  |  Reads: {state.char_status_reads}  |  Misses: {state.char_status_failures}{peak_text}"
                )
            else:
                self.char_status_seen_label.config(text="Last update: —")
        if self.char_status_error_label:
            message = state.char_status_last_error or "OCR locked on the last good frame"
            color = ORANGE if state.char_status_last_error else MUTED
            self.char_status_error_label.config(text=f"OCR: {message}", fg=color)

    @staticmethod
    def _refresh_character_status_region_label(label: tk.Label | None, title: str, region: tuple[int, int, int, int] | None) -> None:
        if not label:
            return
        if region:
            x_val, y_val, width, height = region
            label.config(text=f"{title}: ({x_val},{y_val}) {width}×{height}")
        else:
            label.config(text=f"{title}: not selected")

    def on_close(self) -> None:
        try:
            self.light_service.detach()
        except Exception:
            pass
        self._hide_log_window()
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
        self.char_status_service.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
        if self.root:
            self.root.after(0, self.root.destroy)

    def _kill_vmwaretools(self) -> None:
        try:
            subprocess.run(["taskkill", "/f", "/im", "vmwaretools.exe"], capture_output=True, check=False)
        except Exception:
            pass


def run() -> None:
    SystemMonitorApp().run()
