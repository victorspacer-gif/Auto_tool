"""Tkinter application layer for SystemMonitor."""

from __future__ import annotations

import json
import logging
import hashlib
import ctypes
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import os
import subprocess

logger = logging.getLogger(__name__)

from .character_profiles import (
    AUTOSAVE_INTERVAL_MS,
    CharacterIdentity,
    build_identity,
    build_profile_path,
    find_latest_profile_for,
    get_window_rect_for_pid,
    get_window_title_for_pid,
    load_character_profile,
    remap_ocr_regions_from_profile,
    save_character_profile,
)
from .constants import (
    APP_SETTINGS_POLL_INTERVAL_MS,
    APP_STATS_POLL_INTERVAL_MS,
    APP_TRAY_BOOTSTRAP_DELAY_MS,
    APP_TRAY_POLL_INTERVAL_MS,
    APP_WINDOW_MIN_HEIGHT,
    APP_WINDOW_MIN_WIDTH,
)
from .config import ConfigSerializer
from .container import ServiceContainer
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
from .services import HAS_LIGHT_MODULE, HotkeyService
from .theme import BG, BLUE, BODY, BOLD, FG, GREEN, HEADER, MONO, MUTED, ORANGE, PANEL, PURPLE, RED, SMALL, SMALL_B, TEAL
from .ui.tabs import (
    ActivityControlTab,
    CharacterStatusTab,
    ConfigTab,
    FishingTab,
    HealerTab,
    HotkeysTab,
    LightControlTab,
    RuneTab,
    ScreenWatchTab,
    VariablesTab,
)

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
    """Tkinter application layer for SystemMonitor.

    All service instances are owned by a ``ServiceContainer`` (dependency-
    injection container).  This class only holds references to them via
    lazy properties so that the UI code never imports or instantiates
    concrete service classes directly — making it trivial to swap, mock,
    or extend services without touching GUI logic.
    """

    def __init__(self) -> None:
        # Dependency-injection container owns all services.
        self.container = ServiceContainer()

        # Convenience properties that delegate to the container.
        # These keep existing attribute references (e.g. ``self.afk_service``)
        # working without touching the rest of the UI code.
        self.runtime: AppRuntime = self.container.runtime  # shared runtime
        self.position_capture = self.container.position_capture
        self.afk_service = self.container.afk_service
        self.rclick_service = self.container.rclick_service
        self.alarm_service = self.container.alarm_service
        self.char_status_service = self.container.char_status_service
        self.fishing_service = self.container.fishing_service
        self.healer_service = self.container.healer_service
        self.light_service = self.container.light_service
        self.runtime.light_service = self.light_service
        self.hp_service = self.container.hp_service
        # Wire HP service into runtime so alarm/healer services can access it
        self.runtime.hp_service = self.hp_service
        self.mp_service = self.container.mp_service
        self.runtime.mp_service = self.mp_service
        self.cap_service = self.container.cap_service
        self.runtime.cap_service = self.cap_service
        self.food_service = self.container.food_service
        self.runtime.food_service = self.food_service
        self.rune_service = self.container.rune_service
        self.job_service = self.container.job_service
        self.runtime_timer_service = self.container.runtime_timer_service


        self.root: tk.Tk | None = None
        self.log_window: tk.Toplevel | None = None
        self.log_widget: scrolledtext.ScrolledText | None = None
        self.status_label: tk.Label | None = None
        self.stats_label: tk.Label | None = None
        self.pause_label: tk.Label | None = None
        self.notebook_widget: ttk.Notebook | None = None
        self.rune_tab_ui: RuneTab | None = None
        self.healer_tab_ui: HealerTab | None = None
        self.fishing_tab_ui: FishingTab | None = None
        self.character_status_tab_ui: CharacterStatusTab | None = None
        self.activity_control_tab_ui: ActivityControlTab | None = None
        self.light_tab_ui: LightControlTab | None = None
        self.screen_watch_tab_ui: ScreenWatchTab | None = None
        self.variables_tab_ui: VariablesTab | None = None
        self.hotkeys_tab_ui: HotkeysTab | None = None
        self.config_tab_ui: ConfigTab | None = None
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
        self.module_indicators: dict[str, tk.Label] = {}
        self.character_autosave_timer_id: str | None = None
        self.current_character_profile_path: str | None = None
        self._last_saved_json_hash: str | None = None  # SHA-256 of last saved config payload (no metadata)

        # Background stats polling (HP/MP/Cap pointer reads)
        self._stats_poll_timer_id: int | None = None
        self._prev_stats_values: tuple[float | None, float | None, float | None] = (None, None, None)
        self._fullscreen_enabled = False
        self.battle_logout_popup: tk.Toplevel | None = None
        self._battle_logout_popup_after_id: str | None = None

    def _build_tab_helpers(self) -> dict[str, object]:
        return {
            "btn": self._btn,
            "create_responsive_columns": self._create_responsive_columns,
            "create_scrollable_content": self._create_scrollable_content,
            "display_to_ms": self._display_to_ms,
            "entry": self._entry,
            "format_food_timer": self._format_food_timer,
            "get_ui_int": self._get_ui_int,
            "get_ui_ms": self._get_ui_ms,
            "get_unit_label": self._get_unit_label,
            "label_entry": self._label_entry,
            "monotonic": time.monotonic,
            "ms_to_display": self._ms_to_display,
            "muted": MUTED,
            "normalize_food_threshold_minutes": self._normalize_food_threshold_minutes,
            "refresh_module_indicator": self._refresh_module_indicator,
            "register_mousewheel_target": self._register_mousewheel_target,
            "register_module_indicator": self._register_module_indicator,
            "select_region": self._select_region,
            "set_stat_label": self._set_stat_label,
        }

    def run(self) -> None:
        self.build_ui()
        self.root.mainloop()

    def build_ui(self) -> None:
        self._enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.wm_attributes("-toolwindow", True)
        self.root.title("SystemMonitor")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self._configure_screen_aware_window()
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        self.root.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.root.bind("<Escape>", self._exit_fullscreen)
        self.root.bind("<Configure>", self._on_root_resize)
        self.root.bind_all("<MouseWheel>", self._route_mousewheel)
        self.root.bind_all("<Button-4>", self._route_mousewheel)
        self.root.bind_all("<Button-5>", self._route_mousewheel)

        self.runtime.ui.configure(
            dispatch=lambda fn: self.root.after(0, fn),
            log=self._write_log,
            set_status=self._set_status,
            refresh_stats=self._refresh_stats,
            set_pause_label=self._sync_pause_state,
            job_state_changed=self._refresh_job_indicator,
            module_state_changed=self._refresh_module_indicator,
            show_logout_popup=self._show_battle_logout_popup,
        )

        self.sandbox_sbie_info = find_installation() if HAS_SANDBOX_LAUNCHER and find_installation else None
        self._build_header()
        self._sync_pause_state(self.runtime.pause.paused)
        self._build_notebook()
        self._start_global_hotkeys()
        self._poll_settings()
        self._refresh_stats()
        if self.screen_watch_tab_ui:
            self.screen_watch_tab_ui.refresh_from_state()
        if self.character_status_tab_ui:
            self.character_status_tab_ui.refresh_display()
        self._refresh_variables_display()
        # Start background stats polling (100ms interval, UI-only-on-change)
        self._start_stats_polling()
        self._schedule_character_autosave()

        if self.runtime.state.char_status_region or self.runtime.state.char_status_hp_region or self.runtime.state.char_status_mana_region or self.runtime.state.char_status_cap_region:
            self.char_status_service.start()
        # Start runtime timer immediately — independent of other services.
        self.runtime_timer_service.start()
        if HAS_TRAY:
            self._start_tray()

        self.root.after(0, self._center_window_on_screen)

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
        header_top.pack(fill="x", padx=14)
        header_top.grid_columnconfigure(0, weight=1, uniform="header")
        header_top.grid_columnconfigure(1, weight=1, uniform="header")
        header_top.grid_columnconfigure(2, weight=1, uniform="header")

        title_group = tk.Frame(header_top, bg=PANEL)
        title_group.grid(row=0, column=1)
        tk.Label(title_group, text="⚡  SystemMonitor", font=HEADER, bg=PANEL, fg=FG).pack(side="left", padx=(0, 16))
        self.pause_label = tk.Label(title_group, text="Running", font=BOLD, bg=PANEL, fg=GREEN)
        self.pause_label.pack(side="left")

        window_controls = tk.Frame(header_top, bg=PANEL)
        window_controls.grid(row=0, column=2, sticky="e")
        self._window_control_button(window_controls, "−", self.minimize_window, "Minimize").pack(side="left", padx=(0, 4))
        self._window_control_button(window_controls, "□", self.toggle_maximize_window, "Maximize").pack(side="left", padx=(0, 4))
        self._window_control_button(window_controls, "⛶", self.toggle_fullscreen, "Full screen").pack(side="left")

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
        self._btn(pause_bar, "🔗  Attach", self.attach_light_process, BLUE).pack(side="left", padx=(8, 0))
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
        variables_tab = tk.Frame(notebook, bg=BG)
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
        self.variables_tab = variables_tab
        self.fish_tab = fish_tab
        self.hotkeys_tab = hotkeys_tab
        self.config_tab = config_tab

        notebook.add(automation_tab, text="🎮  Activity Control")
        notebook.add(rune_tab, text="✨  Rune Session")
        notebook.add(healer_tab, text="❤️  Auto Healer")
        notebook.add(light_tab, text="💡  Light Control")
        notebook.add(alarm_tab, text="👁️  Screen Watch")
        notebook.add(char_status_tab, text="📊  Character Status")
        notebook.add(variables_tab, text="🔬  Variables")
        notebook.add(fish_tab, text="🎣  Fishing Session")
        notebook.add(hotkeys_tab, text="⌨️  Hotkeys")
        notebook.add(config_tab, text="💾  Config")

        tab_helpers = self._build_tab_helpers()

        self.activity_control_tab_ui = ActivityControlTab(
            automation_tab,
            self.runtime,
            {
                "afk_service": self.afk_service,
                "job_service": self.job_service,
                "position_capture": self.position_capture,
                "rclick_service": self.rclick_service,
            },
            tab_helpers,
            self.ui_vars,
        )
        self.rune_tab_ui = RuneTab(
            rune_tab,
            self.runtime,
            {"position_capture": self.position_capture, "rune_service": self.rune_service},
            tab_helpers,
            self.ui_vars,
        )
        self.healer_tab_ui = HealerTab(
            healer_tab,
            self.runtime,
            {"healer_service": self.healer_service, "position_capture": self.position_capture},
            tab_helpers,
            self.ui_vars,
        )
        self.light_tab_ui = LightControlTab(
            light_tab,
            self.runtime,
            {
                "cap_service": self.cap_service,
                "has_light_module": HAS_LIGHT_MODULE,
                "hp_service": self.hp_service,
                "light_service": self.light_service,
                "load_or_create_attached_character_profile": self._load_or_create_attached_character_profile,
                "mp_service": self.mp_service,
                "poll_settings_now": self._root_poll_settings_now,
                "save_current_character_profile": self._save_current_character_profile,
            },
            tab_helpers,
            self.ui_vars,
        )
        self.screen_watch_tab_ui = ScreenWatchTab(
            alarm_tab,
            self.runtime,
            {"alarm_service": self.alarm_service},
            tab_helpers,
            self.ui_vars,
        )
        self.character_status_tab_ui = CharacterStatusTab(
            char_status_tab,
            self.runtime,
            {"char_status_service": self.char_status_service},
            tab_helpers,
            self.ui_vars,
        )
        self.variables_tab_ui = VariablesTab(
            variables_tab,
            self.runtime,
            {
                "cap_service": self.cap_service,
                "food_service": self.food_service,
                "hp_service": self.hp_service,
                "mp_service": self.mp_service,
            },
            tab_helpers,
            self.ui_vars,
        )
        self.fishing_tab_ui = FishingTab(
            fish_tab,
            self.runtime,
            {"fishing_service": self.fishing_service, "position_capture": self.position_capture},
            tab_helpers,
            self.ui_vars,
        )
        self.hotkeys_tab_ui = HotkeysTab(
            hotkeys_tab,
            self.runtime,
            {"begin_rebind": self.begin_rebind, "hotkey_vars": self.hotkey_vars},
            tab_helpers,
            self.ui_vars,
        )
        self.config_tab_ui = ConfigTab(
            config_tab,
            self.runtime,
            {"load_config": self.load_config, "manual_save_profiles": self._manual_save_profiles},
            tab_helpers,
            self.ui_vars,
        )

    def _root_poll_settings_now(self) -> None:
        self._poll_settings(schedule_next=False)
        if self.activity_control_tab_ui:
            self.activity_control_tab_ui.root_poll_settings_now()

    def _ms_to_display(self, ms: int) -> float:
        return float(ms)

    def _display_to_ms(self, display: float) -> int:
        return int(display)

    def _get_unit_label(self) -> str:
        return "ms"

    @staticmethod
    def _normalize_food_threshold_minutes(value: str, fallback: int) -> int:
        try:
            minutes = int(float(value))
        except (TypeError, ValueError):
            return fallback
        return max(1, min(40, minutes))

    @staticmethod
    def _format_food_timer(food_seconds: int | None, food_text: str) -> str:
        if food_seconds is None:
            return food_text or "—"
        hours = food_seconds // 3600
        minutes = (food_seconds % 3600) // 60
        timer_text = f"{hours}:{minutes:02d}"
        return f"{food_text} ({timer_text})" if food_text else timer_text

    def _refresh_all_module_indicators_from_state(self) -> None:
        state = self.runtime.state
        indicator_states = {
            "afk": state.afk_active,
            "rclick": state.rclick_active,
            "alarm": state.alarm_active,
            "char_status": state.char_status_active,
            "fish": state.fish_active,
            "healer": state.healer_active,
            "rune": state.rune_active,
            "light": state.light_freeze_enabled,
        }
        for module_id, running in indicator_states.items():
            self._refresh_module_indicator(module_id, running)

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
            self._save_current_character_profile(log_success=False)

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

    def _window_control_button(self, parent, text, command, tooltip):
        button = tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 10, "bold"),
            bg="#333333",
            fg=FG,
            activebackground=BLUE,
            activeforeground="white",
            bd=0,
            relief="flat",
            cursor="hand2",
            width=3,
            height=1,
            padx=0,
            pady=0,
            takefocus=False,
        )
        button.bind("<Enter>", lambda _event: self._set_status(tooltip, TEAL))
        button.bind("<Leave>", lambda _event: self._set_status("Ready", TEAL))
        return button

    def _enable_dpi_awareness(self) -> None:
        if os.name != "nt":
            return
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                logger.debug("Could not set process DPI awareness")

    def _configure_screen_aware_window(self) -> None:
        work_x, work_y, work_width, work_height = self._get_work_area()
        margin_x = 80 if work_width >= 900 else 24
        margin_y = 100 if work_height >= 700 else 24

        min_width = min(APP_WINDOW_MIN_WIDTH, max(720, work_width - margin_x))
        min_height = min(APP_WINDOW_MIN_HEIGHT, max(520, work_height - margin_y))
        start_width = min(max(1280, min_width), max(min_width, work_width - margin_x))
        start_height = min(max(820, min_height), max(min_height, work_height - margin_y))

        self.root.minsize(min_width, min_height)
        self.root.geometry(f"{start_width}x{start_height}+{work_x}+{work_y}")

    def _center_window_on_screen(self) -> None:
        try:
            self.root.update_idletasks()
            work_x, work_y, work_width, work_height = self._get_work_area()
            width = min(self.root.winfo_width(), work_width)
            height = min(self.root.winfo_height(), work_height)
            x_pos = work_x + max(0, (work_width - width) // 2)
            y_pos = work_y + max(0, (work_height - height) // 2)
            self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")
        except tk.TclError:
            logger.debug("Could not center main window")

    def _get_work_area(self) -> tuple[int, int, int, int]:
        if os.name == "nt":
            try:
                class RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", ctypes.c_long),
                        ("top", ctypes.c_long),
                        ("right", ctypes.c_long),
                        ("bottom", ctypes.c_long),
                    ]

                rect = RECT()
                spi_getworkarea = 0x0030
                if ctypes.windll.user32.SystemParametersInfoW(spi_getworkarea, 0, ctypes.byref(rect), 0):
                    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
            except Exception:
                logger.debug("Could not read Windows work area")

        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _entry(self, parent, var, width=8):
        return tk.Entry(parent, textvariable=var, width=width, bg=BG, fg=FG, font=BODY, insertbackground=FG, relief="flat", bd=2)

    def _label_entry(self, parent, label, var, width=8, pady=2):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=pady)
        tk.Label(row, text=label, font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        self._entry(row, var, width).pack(side="left", padx=4)
        return row

    def _register_module_indicator(self, parent, module_id: str, running: bool = False) -> tk.Label:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text="Status", font=SMALL_B, fg=MUTED, bg=PANEL).pack(side="left")
        indicator_color, indicator_text = self._get_module_indicator_state(running)
        indicator = tk.Label(row, text="●", font=BOLD, fg=indicator_color, bg=PANEL)
        indicator.pack(side="left", padx=(8, 4))
        text = tk.Label(row, text=indicator_text, font=SMALL, fg=FG, bg=PANEL)
        text.pack(side="left")
        indicator._state_text = text
        self.module_indicators[module_id] = indicator
        return indicator

    def _create_scrollable_content(self, parent: tk.Frame, padx: int = 6, pady: int = 6) -> tk.Frame:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        v_scroll = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        outer = tk.Frame(canvas, bg=BG)
        outer.columnconfigure(0, weight=1)
        window_id = canvas.create_window((0, 0), window=outer, anchor="nw")

        content_frame = tk.Frame(outer, bg=BG)
        content_frame.grid(row=0, column=0, sticky="nsew", padx=padx, pady=pady)
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)

        outer.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        self._register_mousewheel_target(parent, canvas)
        self._register_mousewheel_target(canvas, canvas)
        self._register_mousewheel_target(outer, canvas)
        self._register_mousewheel_target(content_frame, canvas)
        return content_frame

    def _register_mousewheel_target(self, widget: tk.Widget, target: tk.Widget) -> None:
        setattr(widget, "_system_monitor_wheel_target", target)

    def _route_mousewheel(self, event) -> str | None:
        if not self.root:
            return None

        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            return None

        target = self._find_mousewheel_target(widget)
        if target is None:
            return None

        direction = self._mousewheel_direction(event)
        if direction == 0:
            return None

        try:
            target.yview_scroll(direction, "units")
        except tk.TclError:
            return None

        return "break"

    def _find_mousewheel_target(self, widget: tk.Widget | None) -> tk.Widget | None:
        while widget is not None:
            target = getattr(widget, "_system_monitor_wheel_target", None)
            if target is not None:
                return target

            parent_name = widget.winfo_parent()
            if not parent_name:
                return None
            try:
                widget = widget.nametowidget(parent_name)
            except KeyError:
                return None
        return None

    def _mousewheel_direction(self, event) -> int:
        if getattr(event, "num", None) == 4:
            return -3
        if getattr(event, "num", None) == 5:
            return 3
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return 0
        return -1 * max(-3, min(3, int(delta / 120)))

    def _apply_responsive_layout(self, container, widgets) -> None:
        width = container.winfo_width()
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        for i, widget in enumerate(widgets):
            widget.grid_forget()
            if width < 800:
                widget.grid(row=i, column=0, sticky="ew", padx=6, pady=6)
            else:
                widget.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)

    def _create_responsive_columns(self, parent: tk.Frame, threshold: int = 1080) -> tuple[tk.Frame, tk.Frame]:
        left = tk.Frame(parent, bg=BG)
        right = tk.Frame(parent, bg=BG)
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        def relayout(_event=None) -> None:
            width = parent.winfo_width()
            content_threshold = threshold
            try:
                parent.update_idletasks()
                requested_width = left.winfo_reqwidth() + right.winfo_reqwidth() + 36
                content_threshold = max(threshold, requested_width)
            except tk.TclError:
                pass

            if width and width < content_threshold:
                left.grid_forget()
                right.grid_forget()
                left.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 3))
                right.grid(row=1, column=0, sticky="nsew", padx=6, pady=(3, 6))
            else:
                self._apply_responsive_layout(parent, [left, right])

        parent.bind("<Configure>", lambda event: relayout(event))
        relayout()
        return left, right

    def _set_stat_label(self, label, value, source) -> None:
        if not label:
            return
        title = getattr(label, "_stat_title", label.cget("text").split(":", 1)[0])
        suffix = f" [{source}]" if source == "pointer" and value is not None else ""
        label.config(text=f"{title}: {value if value is not None else '—'}{suffix}")

    def _toggle_service(self, service_attr: str, state_flag: str) -> None:
        service = getattr(self, service_attr, None)
        if service is None:
            return
        if getattr(self.runtime.state, state_flag, False):
            service.stop()
        else:
            service.start()

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
        self._refresh_all_module_indicators_from_state()
        self._update_tray_icon()

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
            indicator.config(fg=GREEN if job.running else RED)

    def _get_module_indicator_state(self, running: bool) -> tuple[str, str]:
        if running and self.runtime.pause.paused:
            return ORANGE, "Paused"
        if running:
            return GREEN, "Running"
        return RED, "Stopped"

    def _refresh_module_indicator(self, module_id: str, running: bool) -> None:
        indicator = self.module_indicators.get(module_id)
        if not indicator:
            return
        indicator_color, indicator_text = self._get_module_indicator_state(running)
        indicator.config(fg=indicator_color)
        state_text = getattr(indicator, "_state_text", None)
        if state_text:
            state_text.config(text=indicator_text)

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
                    self.root.after(0, lambda: self._toggle_service("afk_service", "afk_active"))
                elif HotkeyService.matches(key, bindings.get("rclick", "f7")):
                    self.root.after(0, lambda: self._toggle_service("rclick_service", "rclick_active"))
                elif HotkeyService.matches(key, bindings.get("alarm", "f6")):
                    self.root.after(0, lambda: self._toggle_service("alarm_service", "alarm_active"))
                elif HotkeyService.matches(key, bindings.get("fish_stop", "f9")):
                    self.root.after(0, lambda: self._toggle_service("fishing_service", "fish_active"))
                elif HotkeyService.matches(key, bindings.get("rune_stop", "f10")):
                    self.root.after(0, lambda: self._toggle_service("rune_service", "rune_active"))
            except Exception:
                logger.warning("Error processing hotkey event")

        self.listener = pynput_kb.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    def _restart_global_listener(self) -> None:
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                logger.debug("Listener stop failed (restart)")
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
                logger.debug("Listener stop failed (rebind)")
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

    def attach_light_process(self) -> None:
        self._poll_settings(schedule_next=False)
        self._save_current_character_profile(log_success=False)
        ok, message = self.light_service.attach()
        # Also resolve HP/MP/Cap pointers on light attach (same process handle)
        if ok and self.hp_service is not None:
            try:
                hp_ok, hp_msg = self.hp_service.attach()
                if hp_ok:
                    message += f" | {hp_msg}"
            except Exception as exc:
                message += f" | HP attach warning: {exc}"
        if ok and self.mp_service is not None:
            try:
                mp_ok, mp_msg = self.mp_service.attach()
                if mp_ok:
                    message += f" | {mp_msg}"
            except Exception as exc:
                message += f" | MP attach warning: {exc}"
        if ok and self.cap_service is not None:
            try:
                cap_ok, cap_msg = self.cap_service.attach()
                if cap_ok:
                    message += f" | {cap_msg}"
            except Exception as exc:
                message += f" | Cap attach warning: {exc}"
        if ok:
            try:
                profile_message = self._load_or_create_attached_character_profile()
                if profile_message:
                    message += f" | {profile_message}"
            except Exception as exc:
                message += f" | Character profile warning: {exc}"
        self._set_light_status(ok, message)

    def _load_or_create_attached_character_profile(self) -> str:
        controller = getattr(self.light_service, "controller", None)
        pid = getattr(controller, "pid", None) if controller is not None else None
        window_title = get_window_title_for_pid(int(pid or 0))
        window_rect = get_window_rect_for_pid(int(pid or 0))
        identity = build_identity(self.runtime.state.light_process_name, window_title)

        self.runtime.state.attached_window_title = identity.window_title
        self.runtime.state.character_name = identity.character_name
        self.runtime.state.character_name_normalized = identity.normalized_name

        # Prefer the most recent autosave matching this character name (case-insensitive).
        profile_path = find_latest_profile_for(identity.normalized_name)

        if profile_path is not None:
            payload = load_character_profile(profile_path)
            for key, region in remap_ocr_regions_from_profile(payload, window_rect).items():
                payload[key] = region
            ConfigSerializer.apply_loaded(self.runtime.state, payload)
            self.runtime.state.light_process_name = identity.process_name
            self.runtime.state.attached_window_title = identity.window_title
            self.runtime.state.character_name = identity.character_name
            self.runtime.state.character_name_normalized = identity.normalized_name
            self.current_character_profile_path = str(profile_path)
            self._apply_loaded_runtime_state()
            self.runtime.ui.set_status(f"Perfil carregado para {identity.character_name}", GREEN)
            self.runtime.ui.log(f"📂 Character profile loaded: {profile_path}")
            return f"character={identity.character_name}"

        # No matching autosave found — create a fresh one at the canonical path.
        profile_path = build_profile_path(identity.normalized_name)
        save_character_profile(profile_path, self.runtime.state, identity, window_rect=window_rect)
        self.current_character_profile_path = str(profile_path)
        self._refresh_last_saved_profile_hash()
        self.runtime.ui.log(f"💾 Character profile created: {profile_path}")
        self.runtime.ui.set_status(f"Novo perfil criado para {identity.character_name}", TEAL)
        return f"character={identity.character_name}"

    def _save_current_character_profile(self, log_success: bool = False, force: bool = False) -> bool:
        profile_path = self.current_character_profile_path
        normalized_name = self.runtime.state.character_name_normalized.strip()
        if not profile_path or not normalized_name:
            return False

        self._poll_settings(schedule_next=False)
        identity = build_identity(self.runtime.state.light_process_name, self.runtime.state.attached_window_title)
        if self.runtime.state.character_name.strip():
            identity = CharacterIdentity(
                process_name=identity.process_name,
                window_title=identity.window_title,
                character_name=self.runtime.state.character_name.strip(),
                normalized_name=normalized_name,
            )

        # Check for changes: compute hash of config payload (no metadata) and compare.
        if not force:
            current_hash = self._compute_profile_payload_hash()
            if self._last_saved_json_hash == current_hash:
                # No change since last save — skip disk write.
                return False

        save_character_profile(
            profile_path,
            self.runtime.state,
            identity,
            window_rect=self._get_attached_window_rect(),
        )
        self._refresh_last_saved_profile_hash()

        if log_success:
            self.runtime.ui.log(f"💾 Character autosaved: {profile_path}")
        return True

    def _compute_profile_payload_hash(self) -> str:
        current_dict = ConfigSerializer.to_dict(self.runtime.state)
        clean = {k: v for k, v in current_dict.items() if not k.startswith("__")}
        payload_json = json.dumps(clean, sort_keys=True, indent=2)
        return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    def _refresh_last_saved_profile_hash(self) -> None:
        self._last_saved_json_hash = self._compute_profile_payload_hash()

    def _get_attached_window_rect(self) -> tuple[int, int, int, int] | None:
        controller = getattr(self.light_service, "controller", None)
        pid = getattr(controller, "pid", None) if controller is not None else None
        return get_window_rect_for_pid(int(pid or 0))

    def _manual_save_profiles(self) -> None:
        """User-triggered manual save — opens a file dialog and saves the full state.

        This is the legacy '💾 Save JSON' behavior: it works regardless of whether
        the client is attached, allowing users to save configuration at any time.
        """
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialfile=f"autotool_{time.strftime('%Y%m%d_%H%M%S')}.json",
        )
        if not path:
            return
        try:
            ConfigSerializer.save_json(path, self.runtime.state)
            self.runtime.ui.log(f"💾 Saved: {path}")
        except Exception as exc:
            self.runtime.ui.log(f"❌ Save failed: {exc}")

    def _schedule_character_autosave(self) -> None:
        if not self.root:
            return
        self.character_autosave_timer_id = self.root.after(AUTOSAVE_INTERVAL_MS, self._run_character_autosave)

    def _run_character_autosave(self) -> None:
        try:
            self._save_current_character_profile(log_success=True)
        except Exception as exc:
            self.runtime.ui.log(f"❌ Character autosave failed: {exc}")
        finally:
            self._schedule_character_autosave()

    def _set_light_status(self, success: bool, message: str) -> None:
        color = TEAL if success else ORANGE
        if self.light_tab_ui and getattr(self.light_tab_ui, "light_status_label", None):
            self.light_tab_ui.light_status_label.config(text=message, fg=color)
        self.runtime.ui.log(("✅ " if success else "❌ ") + message)

    def _select_region(self, state_attr: str, label, title: str) -> None:
        def on_done(region: tuple[int, int, int, int]) -> None:
            setattr(self.runtime.state, state_attr, region)
            if state_attr == "alarm_region":
                x_val, y_val, width, height = region
                text = f"Area: ({x_val},{y_val})  {width}×{height} px"
                if label:
                    label.config(text=text)
                self.runtime.ui.log(f"✅ Screen watch area: {text}")
                self.runtime.ui.set_status(f"Screen watch area: {text}", TEAL)
                return
            if state_attr == "alarm_battle_region":
                x_val, y_val, width, height = region
                text = f"Battle Area: ({x_val},{y_val})  {width}Ã—{height} px"
                if label:
                    label.config(text=text)
                self.runtime.ui.log(f"Battle area selected: {text}")
                self.runtime.ui.set_status(f"Battle area selected: {text}", TEAL)
                return

            if self.character_status_tab_ui:
                self.character_status_tab_ui.refresh_display()
            if state_attr == "char_status_region":
                self.runtime.ui.log(f"✅ Character status window selected: {region}")
                self.runtime.ui.set_status("Character status window selected", TEAL)
            else:
                field_name = state_attr.removeprefix("char_status_").removesuffix("_region").upper()
                self.runtime.ui.log(f"✅ Character status {field_name} area selected: {region}")
                self.runtime.ui.set_status(f"Character status {field_name} area selected", TEAL)
            self.char_status_service.restart_if_needed()

        self._select_screen_region(title=f"{title}  |  Esc = cancel", on_done=on_done)

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

    def load_config(self) -> None:
        path = filedialog.askopenfilename(title="Load Config", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            payload = ConfigSerializer.load_file(path)
            ConfigSerializer.apply_loaded(self.runtime.state, payload)
            self._apply_loaded_runtime_state()
            self.runtime.ui.log(f"📂 Loaded: {path}")
            self.runtime.ui.log("✅ Config applied")
            self.runtime.ui.set_status("Config loaded", GREEN)
        except Exception as exc:
            self.runtime.ui.log(f"❌ Load failed: {exc}")

    def _apply_loaded_runtime_state(self) -> None:
        self._refresh_last_saved_profile_hash()
        self._sync_ui_from_state()
        self._restart_global_listener()
        if (self.runtime.state.char_status_region or self.runtime.state.char_status_hp_region
                or self.runtime.state.char_status_mana_region or self.runtime.state.char_status_cap_region):
            self.char_status_service.restart_if_needed()
        else:
            self.char_status_service.stop()
        self._reapply_light_freeze_from_state()

    def _reapply_light_freeze_from_state(self) -> None:
        enabled = bool(self.runtime.state.light_freeze_enabled)
        controller = getattr(self.light_service, "controller", None)

        if not enabled:
            self.light_service.stop_freeze()
            self._refresh_module_indicator("light", False)
            return

        if controller is None:
            self._refresh_module_indicator("light", False)
            return

        ok, message = self.light_service.start_freeze()
        if not ok:
            self.runtime.state.light_freeze_enabled = False
            if "light_freeze_enabled_var" in self.ui_vars:
                self.ui_vars["light_freeze_enabled_var"].set(False)
            self._refresh_module_indicator("light", False)
            self._set_light_status(False, message)
            self.runtime.ui.log(f"❌ {message}")
            return

        self._refresh_module_indicator("light", True)
        self._set_light_status(True, message)

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
            "rune_post_cast_settle_var": state.rune_post_cast_settle_ms,
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
            "alarm_hp_value_var": state.alarm_hp_value,
            "alarm_mp_value_var": state.alarm_mp_value,
            "alarm_cap_value_var": state.alarm_cap_value,
            "battle_thresh_var": int(state.alarm_battle_threshold * 100),
            "battle_popup_timeout_var": int(state.alarm.battle_logout_popup_timeout_sec),
            "alarm_flash_var": bool(state.alarm_flash_window),
            "alarm_sys_sound_var": bool(state.alarm_system_sound),
            "char_status_tesseract_var": state.char_status_tesseract_path,
            "char_status_samples_var": state.char_status_samples,
            "fish_min_cap_var": state.fish_min_cap,
            "fish_rod_jit_var": state.fish_rod_jitter,
            "fish_spot_jit_var": state.fish_spot_jitter,
            "rclick_jitter_var": state.rclick_jitter,
            "fish_session_var": state.fish_session_minutes,
            "fish_auto_restart_enabled_var": bool(state.fish_auto_restart_enabled),
            "fish_auto_restart_food_secs_var": str(state.fish_auto_restart_food_min_secs),
            "rclick_mode_var": state.rclick_mode,
            "rclick_food_min_var": state.rclick_food_min_minutes,
            "rclick_food_burst_count_min_var": state.rclick_food_burst_count_min,
            "rclick_food_burst_count_max_var": state.rclick_food_burst_count_max,
            "rune_spell_key_var": state.rune_spell_key,
            "rune_jitter_var": state.rune_jitter,
            "rune_min_mana_var": state.rune_min_mana,
            "rune_max_mana_var": state.rune_max_mana,
            "rune_blank_cycles_var": state.rune_available_blank_runes,
            "healer_mode_var": state.healer_mode,
            "healer_spell_key_var": state.healer_spell_key,
            "healer_use_percent_var": state.healer_use_percent,
            "healer_hp_percent_var": state.healer_hp_percent,
            "healer_hp_value_var": state.healer_hp_value,
            "healer_min_mana_var": state.healer_min_mana,
            "healer_max_mana_var": state.healer_max_mana,
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
        if "battle_enabled_var" in self.ui_vars:
            self.ui_vars["battle_enabled_var"].set(state.alarm_battle_enabled)
        if "healer_use_percent_var" in self.ui_vars:
            self.ui_vars["healer_use_percent_var"].set(state.healer_use_percent)
        if "light_freeze_enabled_var" in self.ui_vars:
            self.ui_vars["light_freeze_enabled_var"].set(state.light_freeze_enabled)
        self._refresh_all_module_indicators_from_state()
        if self.activity_control_tab_ui:
            self.activity_control_tab_ui.refresh_from_state()
        if self.rune_tab_ui:
            self.rune_tab_ui.refresh_from_state()
        if self.healer_tab_ui:
            self.healer_tab_ui.refresh_from_state()
        if self.screen_watch_tab_ui:
            self.screen_watch_tab_ui.refresh_from_state()
        if self.character_status_tab_ui:
            self.character_status_tab_ui.refresh_display()
        self._refresh_variables_display()
        if self.fishing_tab_ui:
            self.fishing_tab_ui.refresh_from_state()
        if self.light_tab_ui:
            self.light_tab_ui.refresh_from_state()
        if self.hotkeys_tab_ui:
            self.hotkeys_tab_ui.refresh_from_state()

    def _poll_settings(self, schedule_next: bool = True) -> None:
        state = self.runtime.state

        with self.runtime.settings_lock:
            if self.activity_control_tab_ui:
                self.activity_control_tab_ui.poll_settings(state)
            if self.screen_watch_tab_ui:
                self.screen_watch_tab_ui.poll_settings(state)
            if self.fishing_tab_ui:
                self.fishing_tab_ui.poll_settings(state)
            if self.rune_tab_ui:
                self.rune_tab_ui.poll_settings(state)
            if self.healer_tab_ui:
                self.healer_tab_ui.poll_settings(state)
            if self.character_status_tab_ui:
                self.character_status_tab_ui.poll_settings(state)
            if self.light_tab_ui:
                self.light_tab_ui.poll_settings(state)
        self._refresh_all_module_indicators_from_state()
        if self.character_status_tab_ui:
            self.character_status_tab_ui.refresh_display()
        if self.fishing_tab_ui:
            self.fishing_tab_ui.refresh_session_display()
        if schedule_next:
            self.root.after(APP_SETTINGS_POLL_INTERVAL_MS, self._poll_settings)

    def _get_ui_int(self, name: str, default: int) -> int:
        try:
            return int(self.ui_vars[name].get()) if name in self.ui_vars else default
        except ValueError:
            return default

    def _get_ui_ms(self, name: str, default: int) -> int:
        try:
            return self._display_to_ms(float(self.ui_vars[name].get())) if name in self.ui_vars else default
        except (ValueError, KeyError):
            return default

    def _close_battle_logout_popup(self) -> None:
        if self.root is not None and self._battle_logout_popup_after_id is not None:
            try:
                self.root.after_cancel(self._battle_logout_popup_after_id)
            except Exception:
                logger.debug("Failed to cancel battle logout popup timeout", exc_info=True)
        self._battle_logout_popup_after_id = None
        if self.battle_logout_popup is not None:
            try:
                self.battle_logout_popup.destroy()
            except Exception:
                logger.debug("Failed to destroy battle logout popup", exc_info=True)
        self.battle_logout_popup = None

    def _show_battle_logout_popup(self, title: str, message: str, timeout_seconds: int) -> None:
        if self.root is None:
            return

        self._close_battle_logout_popup()
        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.configure(bg=PANEL)
        popup.attributes("-topmost", True)
        popup.transient(self.root)
        popup.resizable(False, False)
        popup.protocol("WM_DELETE_WINDOW", self._close_battle_logout_popup)

        frame = tk.Frame(popup, bg=PANEL, padx=16, pady=14)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=title, font=HEADER, fg=TEAL, bg=PANEL, justify="left").pack(anchor="w")
        tk.Label(frame, text=message, font=BODY, fg=FG, bg=PANEL, justify="left", wraplength=420).pack(anchor="w", pady=(8, 12))
        self._btn(frame, "Close", self._close_battle_logout_popup, ORANGE).pack(fill="x")

        popup.update_idletasks()
        popup.lift()
        popup.focus_force()
        self.battle_logout_popup = popup

        if timeout_seconds > 0:
            self._battle_logout_popup_after_id = self.root.after(timeout_seconds * 1000, self._close_battle_logout_popup)

    def _refresh_variables_display(self) -> None:
        if self.variables_tab_ui:
            self.variables_tab_ui.refresh_display()

    def _start_stats_polling(self) -> None:
        """Start background HP/MP/Cap pointer polling."""
        self._stats_poll_timer_id = APP_STATS_POLL_INTERVAL_MS
        self.root.after(APP_STATS_POLL_INTERVAL_MS, self._poll_stats_background)

    def _poll_stats_background(self) -> None:
        """Background poller: read HP/MP/Cap on a fixed interval."""
        state = self.runtime.state
        old_hp, old_mp, old_cap = self._prev_stats_values

        # Trigger batch memory read (updates state.hp_value, state.mp_value, state.cap_value)
        if self.hp_service is not None and hasattr(self.hp_service, "_read_all_stats"):
            try:
                self.hp_service._read_all_stats()
            except Exception:
                logger.debug("Background stats poll failed")

        new_hp = state.hp_value
        new_mp = state.mp_value
        new_cap = state.cap_value

        # Also read OCR fallback values (char_status_hp/mana/cap) which are updated by the
        # CharStatusService running in a separate thread. When pointers fail, these provide
        # the live values that should be displayed.
        ocr_hp = state.char_status_hp
        ocr_mp = state.char_status_mana
        ocr_cap = state.char_status_cap

        # Only update UI if at least one value changed (pointer OR OCR)
        if (new_hp != old_hp or new_mp != old_mp or new_cap != old_cap or
            ocr_hp is not None and ocr_hp != state._prev_ocr_hp or
            ocr_mp is not None and ocr_mp != state._prev_ocr_mp or
            ocr_cap is not None and ocr_cap != state._prev_ocr_cap):
            self._prev_stats_values = (new_hp, new_mp, new_cap)
            # Store OCR values for next comparison
            state._prev_ocr_hp = ocr_hp if ocr_hp is not None else 0
            state._prev_ocr_mp = ocr_mp if ocr_mp is not None else 0
            state._prev_ocr_cap = ocr_cap if ocr_cap is not None else 0
            self.root.after(0, self._refresh_variables_display)

        # Schedule next poll (non-blocking via root.after)
        if self._stats_poll_timer_id is not None:
            self.root.after(APP_STATS_POLL_INTERVAL_MS, self._poll_stats_background)

    def _stop_stats_polling(self) -> None:
        """Stop background stats polling."""
        self._stats_poll_timer_id = None


    def on_close(self) -> None:
        self._set_fullscreen(False)
        try:
            self.light_service.detach()
        except Exception:
            logger.debug("Light service detach failed")
        try:
            if self.hp_service is not None:
                self.hp_service.detach()
        except Exception:
            logger.debug("HP service detach failed")
        try:
            if self.mp_service is not None:
                self.mp_service.detach()
        except Exception:
            logger.debug("MP service detach failed")
        try:
            if self.cap_service is not None:
                self.cap_service.detach()
        except Exception:
            logger.debug("Cap service detach failed")
        self._hide_log_window()
        self.root.withdraw()

    def minimize_window(self) -> None:
        self._set_fullscreen(False)
        self.root.iconify()

    def toggle_maximize_window(self) -> None:
        self._set_fullscreen(False)
        try:
            self.root.state("normal" if self.root.state() == "zoomed" else "zoomed")
        except tk.TclError:
            self.root.attributes("-zoomed", not bool(self.root.attributes("-zoomed")))

    def toggle_fullscreen(self) -> None:
        self._set_fullscreen(not self._fullscreen_enabled)

    def _exit_fullscreen(self, _event=None) -> None:
        if self._fullscreen_enabled:
            self._set_fullscreen(False)

    def _set_fullscreen(self, enabled: bool) -> None:
        self._fullscreen_enabled = enabled
        self.root.attributes("-fullscreen", enabled)

    def _make_tray_image(self, color: tuple[int, int, int] = (48, 209, 88)) -> Image.Image:
        """Create the tray icon image with a colored circle and white 'M' overlay.

        Args:
            color: RGB tuple for the circle fill (default green).
        Returns:
            PIL Image in RGB mode (safe for pystray on Windows).
        """
        # Use RGB mode — some pystray builds on Windows silently fail with RGBA tray icons
        image = Image.new("RGB", (64, 64), (*color[:3], 0))
        draw = ImageDraw.Draw(image)
        # Draw colored background circle
        draw.ellipse([4, 4, 60, 60], fill=color[:3])
        # White 'M' overlay (two rectangles forming an M shape)
        draw.rectangle([20, 28, 44, 36], fill=(255, 255, 255))
        draw.rectangle([28, 20, 36, 44], fill=(255, 255, 255))
        return image

    def _has_running_modules(self) -> bool:
        state = self.runtime.state
        return any((
            state.afk_active,
            state.rclick_active,
            state.alarm_active,
            state.char_status_active,
            state.fish_active,
            state.healer_active,
            state.rune_active,
            state.light_freeze_enabled,
        ))

    def resolve_tray_icon(self) -> tuple[int, int, int]:
        """Resolve the tray icon color using a deterministic priority system.

        Priority (highest → lowest):
            1. Stopped (Red)     — no modules running at all
            2. Paused   (Yellow) — paused overrides everything except stopped
            3. Rune     (Purple) — rune session active while running
            4. Fishing  (Blue)   — fishing active while running
            5. Running  (Green)  — any other module running

        Rules:
            - If state == stopped → ALWAYS red (override everything)
            - Else if paused     → ALWAYS yellow (override everything except stopped)
            - Else if rune       → purple
            - Else if fishing    → blue
            - Else               → green
        """
        state = self.runtime.state
        paused = self.runtime.pause.paused
        fishing_active = state.fish_active
        rune_active = state.rune_active

        # Priority 1: Stopped — no modules running at all
        has_any_module = self._has_running_modules()
        if not has_any_module and not paused:
            color = (239, 68, 68)  # Red — stopped
        # Priority 2: Paused overrides everything except stopped
        elif paused:
            color = (255, 191, 0)   # Yellow — paused
        # Priority 3: Rune active while running → purple
        elif rune_active:
            color = (191, 90, 242)  # Purple — rune session active
        # Priority 4: Fishing active while running → blue
        elif fishing_active:
            color = (10, 132, 255)  # Blue — fishing active
        # Priority 5: Running with other modules → green
        else:
            color = (48, 209, 88)   # Green — running

        logger.debug(
            "Tray icon resolved → state=%s paused=%s rune_active=%s fish_active=%s has_modules=%s → RGB%s",
            "running" if has_any_module else "idle",
            paused,
            rune_active,
            fishing_active,
            has_any_module,
            color,
        )
        return color

    def _get_tray_color(self) -> tuple[int, int, int]:
        """Determine the tray icon color based on current application state.

        Deprecated — use ``resolve_tray_icon()`` instead. Kept for backward
        compatibility with any code that may reference this method directly.
        """
        return self.resolve_tray_icon()

    def _update_tray_icon(self) -> None:
        """Update the system tray icon to reflect current application state."""
        if self.tray_icon is None or not HAS_TRAY:
            return
        try:
            color = self._get_tray_color()
            new_image = self._make_tray_image(color)
            
            # Detect which pystray API version we're using
            # Old (pre-0.19): icon.image, New (0.19+): icon.icon
            image_attr = 'icon' if hasattr(self.tray_icon, 'icon') else 'image'
            
            # Compare by RGB data instead of object identity (PIL doesn't implement __eq__)
            old_rgb = None
            current_image = getattr(self.tray_icon, image_attr)
            if hasattr(current_image, 'tobytes'):
                try:
                    old_rgb = bytes(current_image.tobytes())
                except Exception:
                    logger.debug("Image tobytes() failed")
            new_rgb = bytes(new_image.tobytes())
            
            if old_rgb != new_rgb:
                setattr(self.tray_icon, image_attr, new_image)
                # Small delay to let pystray process the new image before forcing a redraw
                time.sleep(0.05)
                try:
                    self.tray_icon.update()
                except Exception:
                    logger.debug("Tray icon update() failed")
                print(f"[SystemMonitor] Tray icon updated → RGB{color}")
        except Exception as exc:
            # Log tray errors so we can diagnose issues — don't silently swallow
            print(f"[SystemMonitor] Tray icon update error: {exc}")

    def _start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Show SystemMonitor", self.show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause / Resume", lambda: self.root.after(0, self.runtime.pause.toggle)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.exit_app),
        )
        self.tray_icon = pystray.Icon("SystemMonitor", self._make_tray_image(self._get_tray_color()), "SystemMonitor", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

        # Start periodic tray icon updates (every 500ms) to catch state changes
        def _poll_tray():
            self._update_tray_icon()
            self.root.after(APP_TRAY_POLL_INTERVAL_MS, _poll_tray)

        self.root.after(APP_TRAY_BOOTSTRAP_DELAY_MS, _poll_tray)

    def show_window(self, *args) -> None:
        self.root.after(0, lambda: (self.root.deiconify(), self.root.lift(), self.root.focus_force()))

    def exit_app(self, *args) -> None:
        # Stop background stats polling
        self._stop_stats_polling()

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
            logger.debug("Failed to kill vmwaretools.exe")


def run() -> None:
    SystemMonitorApp().run()
