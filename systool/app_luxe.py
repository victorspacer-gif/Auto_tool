"""Luxe (CustomTkinter) application layer for SystemMonitor.

A modern, aesthetically pleasing UI built with CustomTkinter,
running alongside the original tkinter interface.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import tkinter as tk

import customtkinter as ctk
import os
import ctypes

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
    PROFILE_BLOCKED_CFG_KEYS,
    remap_ocr_regions_from_profile,
    save_character_profile,
)
from .constants import (
    APP_SETTINGS_POLL_INTERVAL_MS,
    APP_STATS_POLL_INTERVAL_MS,
    APP_TRAY_BOOTSTRAP_DELAY_MS,
    APP_TRAY_POLL_INTERVAL_MS,
    APP_WINDOW_MIN_WIDTH,
    APP_WINDOW_MIN_HEIGHT,
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
from .ui.luxe_tabs import (
    ActivityControlTab,
    CharacterStatusTab,
    ConfigTab,
    FishingTab,
    HotkeysTab,
    LightControlTab,
    ScreenWatchTab,
    VariablesTab,
)

try:
    from purecase_module import (
        find_installation,
        launch_in_box,
        launch_with_job_object,
        terminate_box,
    )
    HAS_SANDBOX_LAUNCHER = True
except ImportError:
    find_installation = None
    launch_in_box = None
    launch_with_job_object = None
    terminate_box = None
    HAS_SANDBOX_LAUNCHER = False

# ── Color palette (CTk theme overrides) ─────────────────
BG = "#121212"
PANEL = "#1e1e1e"
SURFACE = "#2a2a2a"
FG = "#e8e8e8"
MUTED = "#888888"
GREEN = "#30d158"
RED = "#ff453a"
ORANGE = "#ff9f0a"
BLUE = "#0a84ff"
PURPLE = "#bf5af2"
TEAL = "#5ac8fa"

# ── Helper functions for CTk hover behavior ──
def _ctk_btn(parent, text, command, color=GREEN, **kwargs):
    """Create a modern CTkButton with the given color."""
    btn = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        fg_color=color,
        hover_color=_darken(color, 0.2),
        text_color="#ffffff",
        font=ctk.CTkFont(size=11, weight="bold"),
        corner_radius=6,
        border_width=0,
        **kwargs,
    )
    return btn


def _darken(hex_color: str, amount: float) -> str:
    """Darken a hex color by the given amount (0-1)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f"#{r:02x}{g:02x}{b:02x}"


class SystemMonitorLuxeApp:
    """CustomTkinter application layer for SystemMonitor Luxe."""

    def __init__(self) -> None:
        self.container = ServiceContainer()

        self.runtime: AppRuntime = self.container.runtime
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
        self.runtime.hp_service = self.hp_service
        self.mp_service = self.container.mp_service
        self.runtime.mp_service = self.mp_service
        self.cap_service = self.container.cap_service
        self.runtime.cap_service = self.cap_service
        self.food_service = self.container.food_service
        self.runtime.food_service = self.food_service
        self.rune_service = self.container.rune_service
        self.job_service = self.container.job_service
        self.cavebot_service = self.container.cavebot_service
        self.chase_target_service = self.container.chase_target_service
        self.auto_looter_service = self.container.auto_looter_service
        self.cavebot_service.chase_target_service = self.chase_target_service
        self.cavebot_service.auto_looter_service = self.auto_looter_service
        self.input_router = self.container.input_router
        self.runtime.input_router = self.input_router
        self.runtime_timer_service = self.container.runtime_timer_service

        self.root: ctk.CTk | None = None
        self.log_window: ctk.CTkToplevel | None = None
        self.log_widget: ctk.CTkTextbox | None = None
        self.status_label: ctk.CTkLabel | None = None
        self.stats_label: ctk.CTkLabel | None = None
        self.pause_label: ctk.CTkLabel | None = None
        self.tabview: ctk.CTkTabview | None = None
        self.module_indicators: dict[str, ctk.CTkLabel] = {}
        self.tray_icon = None
        self.listener = None

        self.ui_vars: dict[str, ctk.Variable] = {}
        self.hotkey_vars: dict[str, ctk.StringVar] = {}
        self.log_history: list[str] = []
        self.character_autosave_timer_id: str | None = None
        self.current_character_profile_path: str | None = None
        self._last_saved_json_hash: str | None = None

        self._stats_poll_timer_id: int | None = None
        self._prev_stats_values: tuple = (None, None, None)
        self._fullscreen_enabled = False
        self.battle_logout_popup: ctk.CTkToplevel | None = None
        self._battle_logout_popup_after_id: str | None = None

    def run(self) -> None:
        self.build_ui()
        self.root.mainloop()

    def build_ui(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._enable_dpi_awareness()
        self.root = ctk.CTk()
        self.root.title("SystemMonitor Luxe")
        self.root.configure(fg_color=BG)
        self.root.resizable(True, True)
        self._configure_screen_aware_window()
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        self.root.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.root.bind("<Escape>", self._exit_fullscreen)

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

        self._build_header()
        self._sync_pause_state(self.runtime.pause.paused)
        self._build_tabview()
        self._start_global_hotkeys()
        self._poll_settings()
        self._refresh_stats()
        self._refresh_variables_display()
        self._start_stats_polling()
        self._schedule_character_autosave()

        if any([self.runtime.state.char_status_region,
                self.runtime.state.char_status_hp_region,
                self.runtime.state.char_status_mana_region,
                self.runtime.state.char_status_cap_region]):
            self.char_status_service.start()

        self.runtime_timer_service.start()

        if HAS_TRAY:
            self._start_tray()

        self.root.after(100, self._center_window_on_screen)

        missing = [
            name for name, installed in [
                ("pynput", HAS_PYNPUT), ("mss+numpy", HAS_MSS),
                ("pygame", HAS_PYGAME), ("pystray+pillow", HAS_TRAY),
                ("pywin32", HAS_WIN32), ("opencv-python", HAS_CV2),
                ("pytesseract", HAS_TESSERACT),
            ] if not installed
        ]
        self._write_log("✨ SystemMonitor Luxe ready" + (f"  — missing: {', '.join(missing)}" if missing else ""))

    def _build_header(self) -> None:
        """Build a beautiful modern header bar."""
        header = ctk.CTkFrame(self.root, fg_color=PANEL, height=60, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=8)

        # Left: Logo + title
        title_frame = ctk.CTkFrame(inner, fg_color="transparent")
        title_frame.pack(side="left")
        ctk.CTkLabel(title_frame, text="⚡", font=ctk.CTkFont(size=20),
                      text_color=TEAL).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(title_frame, text="SystemMonitor",
                      font=ctk.CTkFont(size=16, weight="bold"),
                      text_color=FG).pack(side="left")

        self.pause_label = ctk.CTkLabel(title_frame, text="Running",
                                         font=ctk.CTkFont(size=11, weight="bold"),
                                         text_color=GREEN)
        self.pause_label.pack(side="left", padx=(12, 0))

        # Center: status/stats
        status_frame = ctk.CTkFrame(inner, fg_color="transparent")
        status_frame.pack(side="left", fill="x", expand=True, padx=16)
        self.status_label = ctk.CTkLabel(status_frame, text="Ready",
                                          font=ctk.CTkFont(size=10),
                                          text_color=TEAL, anchor="w")
        self.status_label.pack(fill="x")
        self.stats_label = ctk.CTkLabel(status_frame, text="",
                                         font=ctk.CTkFont(size=9),
                                         text_color=MUTED, anchor="w")
        self.stats_label.pack(fill="x")

        # Right: window controls
        ctrl = ctk.CTkFrame(inner, fg_color="transparent")
        ctrl.pack(side="right")
        for text, cmd in [("—", self.minimize_window), ("□", self.toggle_maximize_window), ("⛶", self.toggle_fullscreen)]:
            ctk.CTkButton(ctrl, text=text, width=32, height=28,
                          command=cmd, fg_color=SURFACE,
                          hover_color=BLUE, text_color=FG,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          corner_radius=4).pack(side="left", padx=2)

        # Separator
        ctk.CTkFrame(self.root, fg_color=SURFACE, height=1, corner_radius=0).pack(fill="x")

        # Hotkey legend
        legend = ctk.CTkFrame(self.root, fg_color=BG, height=26, corner_radius=0)
        legend.pack(fill="x")
        legend.pack_propagate(False)
        ctk.CTkLabel(legend,
                      text="F5 Pause/Resume  |  F8 Activity Monitor  |  F7 Right-Click  |  F6 Screen Watch  |  F12 Record  |  HOME Stop all",
                      font=ctk.CTkFont(size=9), text_color=MUTED).pack(pady=2)

        # Action bar
        bar = ctk.CTkFrame(self.root, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(6, 2))
        _ctk_btn(bar, "▶  START!", self._show_start_popup, GREEN).pack(side="left", padx=2)
        _ctk_btn(bar, "⏸  Pause / Resume", self.runtime.pause.toggle, ORANGE).pack(side="left", padx=2)
        _ctk_btn(bar, "🔗  Attach", self.attach_light_process, BLUE).pack(side="left", padx=2)
        _ctk_btn(bar, "📋  Log", self.toggle_log_window, BLUE).pack(side="left", padx=2)
        if HAS_SANDBOX_LAUNCHER:
            _ctk_btn(bar, "🔒  Sandbox", self._show_sandbox_launcher_popup, PURPLE).pack(side="left", padx=2)

        ctk.CTkFrame(self.root, fg_color=SURFACE, height=1, corner_radius=0).pack(fill="x", padx=14, pady=4)

    def _build_tabview(self) -> None:
        """Build the tab view with CustomTkinter's modern tab system."""
        wrapper = ctk.CTkFrame(self.root, fg_color="transparent")
        wrapper.pack(fill="both", expand=True, padx=14, pady=6)

        self.tabview = ctk.CTkTabview(wrapper, fg_color="transparent",
                                       segmented_button_fg_color=PANEL,
                                       segmented_button_selected_color=BLUE,
                                       segmented_button_selected_hover_color=_darken(BLUE, 0.2),
                                       segmented_button_unselected_color=PANEL,
                                       segmented_button_unselected_hover_color=SURFACE,
                                       text_color=FG, text_color_disabled=MUTED,
                                       corner_radius=8,
                                       anchor="nw")
        self.tabview.pack(fill="both", expand=True)

        # Define tabs (no healer/rune/cavebot)
        tab_specs = [
            ("activity", "🎮  Activity Control"),
            ("light", "💡  Light Control"),
            ("alarm", "👁️  Screen Watch"),
            ("char_status", "📊  Character Status"),
            ("variables", "🔬  Variables"),
            ("fish", "🎣  Fishing Session"),
            ("hotkeys", "⌨️  Hotkeys"),
            ("config", "💾  Config"),
        ]

        self.tab_frames = {}
        for tab_id, label in tab_specs:
            self.tabview.add(label)
            frame = self.tabview.tab(label)
            frame.configure(fg_color="transparent")
            self.tab_frames[tab_id] = frame

        helpers = self._build_tab_helpers()

        # Instantiate tab UIs
        self.activity_control_tab_ui = ActivityControlTab(
            self.tab_frames["activity"], self.runtime,
            {"afk_service": self.afk_service, "job_service": self.job_service,
             "position_capture": self.position_capture, "rclick_service": self.rclick_service},
            helpers, self.ui_vars)

        self.light_tab_ui = LightControlTab(
            self.tab_frames["light"], self.runtime,
            {"cap_service": self.cap_service, "has_light_module": HAS_LIGHT_MODULE,
             "hp_service": self.hp_service, "light_service": self.light_service,
             "load_or_create_attached_character_profile": self._load_or_create_attached_character_profile,
             "mp_service": self.mp_service, "poll_settings_now": self._root_poll_settings_now,
             "save_current_character_profile": self._save_current_character_profile},
            helpers, self.ui_vars)

        self.screen_watch_tab_ui = ScreenWatchTab(
            self.tab_frames["alarm"], self.runtime,
            {"alarm_service": self.alarm_service},
            helpers, self.ui_vars)

        self.character_status_tab_ui = CharacterStatusTab(
            self.tab_frames["char_status"], self.runtime,
            {"char_status_service": self.char_status_service},
            helpers, self.ui_vars)

        self.variables_tab_ui = VariablesTab(
            self.tab_frames["variables"], self.runtime,
            {"cap_service": self.cap_service, "food_service": self.food_service,
             "hp_service": self.hp_service, "mp_service": self.mp_service},
            helpers, self.ui_vars)

        self.fishing_tab_ui = FishingTab(
            self.tab_frames["fish"], self.runtime,
            {"fishing_service": self.fishing_service, "position_capture": self.position_capture},
            helpers, self.ui_vars)

        self.hotkeys_tab_ui = HotkeysTab(
            self.tab_frames["hotkeys"], self.runtime,
            {"begin_rebind": self.begin_rebind, "hotkey_vars": self.hotkey_vars},
            helpers, self.ui_vars)

        self.config_tab_ui = ConfigTab(
            self.tab_frames["config"], self.runtime,
            {"load_config": self.load_config, "manual_save_profiles": self._manual_save_profiles},
            helpers, self.ui_vars)

    def _build_tab_helpers(self) -> dict:
        return {
            "btn": _ctk_btn,
            "create_responsive_columns": self._create_responsive_columns,
            "create_scrollable_content": self._create_scrollable_content,
            "display_to_ms": self._display_to_ms,
            "entry": self._ctk_entry,
            "format_food_timer": self._format_food_timer,
            "get_ui_int": self._get_ui_int,
            "get_ui_ms": self._get_ui_ms,
            "get_unit_label": self._get_unit_label,
            "label_entry": self._ctk_label_entry,
            "monotonic": time.monotonic,
            "ms_to_display": self._ms_to_display,
            "muted": MUTED,
            "normalize_food_threshold_minutes": self._normalize_food_threshold_minutes,
            "refresh_module_indicator": self._refresh_module_indicator,
            "register_mousewheel_target": lambda w, t: None,
            "register_module_indicator": self._register_module_indicator,
            "select_region": self._select_region,
            "set_stat_label": self._set_stat_label,
        }

    def _ctk_entry(self, parent, var, width=100):
        return ctk.CTkEntry(parent, textvariable=var, width=width,
                             fg_color="#1a1a1a", border_color="#3a3a3a",
                             text_color=FG, font=ctk.CTkFont(size=11),
                             corner_radius=4, border_width=1)

    def _ctk_label_entry(self, parent, label, var, width=100, pady=2):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=pady)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=FG, width=150, anchor="w").pack(side="left")
        entry = self._ctk_entry(row, var, width)
        entry.pack(side="left", padx=4)
        return row

    def _create_scrollable_content(self, parent, padx=6, pady=6):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent",
                                         corner_radius=0, scrollbar_button_color=SURFACE,
                                         scrollbar_button_hover_color=BLUE)
        scroll.pack(fill="both", expand=True, padx=padx, pady=pady)
        return scroll

    def _create_responsive_columns(self, parent, threshold=1080):
        left = ctk.CTkFrame(parent, fg_color="transparent")
        right = ctk.CTkFrame(parent, fg_color="transparent")
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        return left, right

    # ── Helper passthroughs ────────────────────────────────

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

    # ── Module indicators ──────────────────────────────────

    def _register_module_indicator(self, parent, module_id: str, running: bool = False) -> ctk.CTkLabel:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(row, text="Status", font=ctk.CTkFont(size=9, weight="bold"),
                      text_color=MUTED).pack(side="left")
        indicator_color, indicator_text = self._get_module_indicator_state(running)
        indicator = ctk.CTkLabel(row, text="●", font=ctk.CTkFont(size=14, weight="bold"),
                                  text_color=indicator_color)
        indicator.pack(side="left", padx=(8, 4))
        text = ctk.CTkLabel(row, text=indicator_text, font=ctk.CTkFont(size=10),
                              text_color=FG)
        text.pack(side="left")
        indicator._state_text = text
        self.module_indicators[module_id] = indicator
        return indicator

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
        indicator.configure(text_color=indicator_color)
        state_text = getattr(indicator, "_state_text", None)
        if state_text:
            state_text.configure(text=indicator_text)

    def _refresh_all_module_indicators_from_state(self) -> None:
        state = self.runtime.state
        for module_id, running in {
            "afk": state.afk_active, "rclick": state.rclick_active,
            "alarm": state.alarm_active, "char_status": state.char_status_active,
            "fish": state.fish_active, "light": state.light_freeze_enabled,
        }.items():
            self._refresh_module_indicator(module_id, running)

    # ── Logging ────────────────────────────────────────────

    def _write_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.log_history.append(line)
        if self.log_widget and self.log_widget.winfo_exists():
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", f"{line}\n")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        if self.status_label:
            self.status_label.configure(text=text, text_color=color)

    def toggle_log_window(self) -> None:
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
            self.log_window = None
            self.log_widget = None
            return
        self._show_log_window()

    def _show_log_window(self) -> None:
        if not self.root:
            return
        self.log_window = ctk.CTkToplevel(self.root)
        self.log_window.title("SystemMonitor Luxe — Live Log")
        self.log_window.geometry("780x320")
        self.log_window.minsize(520, 220)
        self.log_window.configure(fg_color=BG)

        frame = ctk.CTkFrame(self.log_window, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text="Live Activity Log", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=MUTED).pack(anchor="w")

        self.log_widget = ctk.CTkTextbox(frame, fg_color=PANEL, text_color=FG,
                                          font=ctk.CTkFont(size=10, family="Consolas"),
                                          border_width=0, corner_radius=6)
        self.log_widget.pack(fill="both", expand=True, pady=(6, 0))
        for line in self.log_history:
            self.log_widget.insert("end", f"{line}\n")
        self.log_widget.configure(state="disabled")

        self.log_window.protocol("WM_DELETE_WINDOW", lambda: (
            setattr(self, "log_window", None),
            setattr(self, "log_widget", None),
            self.log_window.destroy() if self.log_window else None,
        ))

    # ── Stats ──────────────────────────────────────────────

    def _refresh_stats(self) -> None:
        if not self.stats_label:
            return
        stats = self.runtime.state.stats
        self.stats_label.configure(
            text=(f"Hotkey: {stats['hotkeys']}  |  Bursts: {stats['bursts']}  |  "
                  f"AFK: {stats['afk_moves']}  |  R-click: {stats['right_clicks']}  |  "
                  f"Fish: {stats['fish_casts']}  |  Heals: {stats['heals']}  |  "
                  f"Alarms: {stats['alarms']}")
        )

    def _refresh_job_indicator(self, job: HotkeyJob) -> None:
        indicator = getattr(job.row_frame, "_indicator", None)
        if indicator:
            indicator.configure(text_color=GREEN if job.running else RED)

    def _set_stat_label(self, label, value, source) -> None:
        if not label:
            return
        title = getattr(label, "_stat_title", label.cget("text").split(":", 1)[0])
        suffix = f" [{source}]" if source == "pointer" and value is not None else ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        label.configure(text=f"{title}: {value if value is not None else '—'}{suffix}")

    # ── Pause ──────────────────────────────────────────────

    def _sync_pause_state(self, paused: bool) -> None:
        if paused:
            self._set_status("⏸  PAUSED — press pause hotkey to resume", ORANGE)
            if self.pause_label:
                self.pause_label.configure(text="⏸  PAUSED", text_color=ORANGE)
        else:
            self._set_status("▶  Resumed", GREEN)
            if self.pause_label:
                self.pause_label.configure(text="Running", text_color=GREEN)
        self._refresh_all_module_indicators_from_state()

    # ── Settings polling ───────────────────────────────────

    def _poll_settings(self, schedule_next: bool = True) -> None:
        state = self.runtime.state
        with self.runtime.settings_lock:
            if hasattr(self, "activity_control_tab_ui") and self.activity_control_tab_ui:
                self.activity_control_tab_ui.poll_settings(state)
            if hasattr(self, "screen_watch_tab_ui") and self.screen_watch_tab_ui:
                self.screen_watch_tab_ui.poll_settings(state)
            if hasattr(self, "fishing_tab_ui") and self.fishing_tab_ui:
                self.fishing_tab_ui.poll_settings(state)
            if hasattr(self, "character_status_tab_ui") and self.character_status_tab_ui:
                self.character_status_tab_ui.poll_settings(state)
            if hasattr(self, "light_tab_ui") and self.light_tab_ui:
                self.light_tab_ui.poll_settings(state)
        self._refresh_all_module_indicators_from_state()
        if hasattr(self, "character_status_tab_ui") and self.character_status_tab_ui:
            self.character_status_tab_ui.refresh_display()
        if hasattr(self, "fishing_tab_ui") and self.fishing_tab_ui:
            self.fishing_tab_ui.refresh_session_display()
        if schedule_next:
            self.root.after(APP_SETTINGS_POLL_INTERVAL_MS, self._poll_settings)

    def _root_poll_settings_now(self) -> None:
        self._poll_settings(schedule_next=False)
        if hasattr(self, "activity_control_tab_ui") and self.activity_control_tab_ui:
            self.activity_control_tab_ui.root_poll_settings_now()

    # ── UI helpers ─────────────────────────────────────────

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

    def _refresh_variables_display(self) -> None:
        if hasattr(self, "variables_tab_ui") and self.variables_tab_ui:
            self.variables_tab_ui.refresh_display()

    # ── Stats polling ──────────────────────────────────────

    def _start_stats_polling(self) -> None:
        self._stats_poll_timer_id = APP_STATS_POLL_INTERVAL_MS
        self.root.after(APP_STATS_POLL_INTERVAL_MS, self._poll_stats_background)

    def _poll_stats_background(self) -> None:
        state = self.runtime.state
        old_hp, old_mp, old_cap = self._prev_stats_values

        if self.hp_service is not None and hasattr(self.hp_service, "_read_all_stats"):
            try:
                self.hp_service._read_all_stats()
            except Exception:
                logger.debug("Background stats poll failed")

        new_hp, new_mp, new_cap = state.hp_value, state.mp_value, state.cap_value
        ocr_hp = state.char_status_hp
        ocr_mp = state.char_status_mana
        ocr_cap = state.char_status_cap

        if (new_hp != old_hp or new_mp != old_mp or new_cap != old_cap or
                (ocr_hp is not None and ocr_hp != state._prev_ocr_hp) or
                (ocr_mp is not None and ocr_mp != state._prev_ocr_mp) or
                (ocr_cap is not None and ocr_cap != state._prev_ocr_cap)):
            self._prev_stats_values = (new_hp, new_mp, new_cap)
            state._prev_ocr_hp = ocr_hp if ocr_hp is not None else 0
            state._prev_ocr_mp = ocr_mp if ocr_mp is not None else 0
            state._prev_ocr_cap = ocr_cap if ocr_cap is not None else 0
            self.root.after(0, self._refresh_variables_display)

        if self._stats_poll_timer_id is not None:
            self.root.after(APP_STATS_POLL_INTERVAL_MS, self._poll_stats_background)

    def _stop_stats_polling(self) -> None:
        self._stats_poll_timer_id = None

    # ── Battle logout popup ────────────────────────────────

    def _show_battle_logout_popup(self, title: str, message: str, timeout_seconds: int) -> None:
        self._close_battle_logout_popup()
        if not self.root:
            return
        popup = ctk.CTkToplevel(self.root)
        popup.title(title)
        popup.configure(fg_color=PANEL)
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.protocol("WM_DELETE_WINDOW", self._close_battle_logout_popup)

        frame = ctk.CTkFrame(popup, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=14)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                      text_color=TEAL, justify="left").pack(anchor="w")
        ctk.CTkLabel(frame, text=message, font=ctk.CTkFont(size=11),
                      text_color=FG, justify="left", wraplength=420).pack(anchor="w", pady=(8, 12))
        _ctk_btn(frame, "Close", self._close_battle_logout_popup, ORANGE).pack(fill="x")

        popup.update_idletasks()
        popup.lift()
        popup.focus_force()
        self.battle_logout_popup = popup

        if timeout_seconds > 0:
            self._battle_logout_popup_after_id = self.root.after(timeout_seconds * 1000, self._close_battle_logout_popup)

    def _close_battle_logout_popup(self) -> None:
        if self.root is not None and self._battle_logout_popup_after_id is not None:
            try:
                self.root.after_cancel(self._battle_logout_popup_after_id)
            except Exception:
                pass
        self._battle_logout_popup_after_id = None
        if self.battle_logout_popup is not None:
            try:
                self.battle_logout_popup.destroy()
            except Exception:
                pass
        self.battle_logout_popup = None

    # ── Global hotkeys ─────────────────────────────────────

    def _start_global_hotkeys(self) -> None:
        if not HAS_PYNPUT:
            return

        def on_press(key):
            state = self.runtime.state
            if state.rebind_active and state.rebind_target:
                try:
                    key_str = HotkeyService.pynput_key_to_str(key)
                    if key_str != "esc":
                        self.root.after(0, lambda: self.apply_rebind(key_str))
                    else:
                        state.rebind_active = False
                        state.rebind_target = None
                        self.runtime.ui.log("🎹 Rebind cancelled")
                        self.root.after(0, self._restart_global_listener)
                except Exception:
                    logger.warning("Error processing rebind hotkey")
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
        self._schedule_listener_check()

    def _schedule_listener_check(self) -> None:
        if not HAS_PYNPUT:
            return
        try:
            if self.listener and not self.listener.is_alive():
                logger.warning("Global hotkey listener died — restarting")
                self._start_global_hotkeys()
                return
        except Exception:
            pass
        self.root.after(5000, self._schedule_listener_check)

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

    def _toggle_service(self, service_attr: str, state_flag: str) -> None:
        service = getattr(self, service_attr, None)
        if service is None:
            return
        if getattr(self.runtime.state, state_flag, False):
            service.stop()
        else:
            service.start()

    def stop_all(self) -> None:
        self.job_service.stop_all(
            stop_afk=self.afk_service.stop,
            stop_rclick=self.rclick_service.stop,
            stop_alarm=self.alarm_service.stop,
            stop_fishing=self.fishing_service.stop,
            stop_rune=self.rune_service.stop,
        )
        self.healer_service.stop()
        self.cavebot_service.stop()
        self.chase_target_service.stop()
        self.auto_looter_service.stop()

    # ── START popup ────────────────────────────────────────

    _STARTUP_MODULE_DEFS = [
        ("afk", "Activity Monitor (AFK)", lambda self: self.afk_service.start()),
        ("rclick", "Right-Click Monitor", lambda self: self.rclick_service.start()),
        ("alarm", "Screen Watch (Alarm)", lambda self: self.alarm_service.start()),
        ("char_status", "Character Status OCR", lambda self: self.char_status_service.start()),
        ("fish", "Fishing Session", lambda self: self.fishing_service.start()),
        ("healer", "Auto Healer", lambda self: self.healer_service.start()),
        ("rune", "Rune Session", lambda self: self.rune_service.start()),
        ("cavebot", "CaveBot", lambda self: self.cavebot_service.start()),
        ("chase_target", "Chase Target", lambda self: self.chase_target_service.start()),
        ("auto_looter", "Auto Looter", lambda self: self.auto_looter_service.start()),
        ("light_freeze", "Light Freeze", None),
        ("battle_reaction", "Enable Battle Window Reaction", None),
    ]

    def _start_selected_module(self, module_id: str) -> None:
        for mid, _display, starter_fn in self._STARTUP_MODULE_DEFS:
            if mid != module_id:
                continue
            if starter_fn is not None:
                starter_fn(self)
            elif mid == "light_freeze":
                state = self.runtime.state
                if getattr(self.light_service, "controller", None) is None:
                    self.runtime.ui.log("⚠️  Light Freeze: attach to a game process first")
                    self.runtime.ui.set_status("Attach first to use Light Freeze", ORANGE)
                    return
                ok, message = self.light_service.start_freeze()
                if ok:
                    state.light_freeze_enabled = True
                    self._refresh_module_indicator("light", True)
                else:
                    self.runtime.ui.log(f"❌ Light Freeze: {message}")
            elif mid == "battle_reaction":
                self.runtime.state.alarm.battle_enabled = True
                self.runtime.ui.log("✅ Battle Window Reaction enabled")
                self.runtime.ui.set_status("Battle Window Reaction enabled", GREEN)
                if "battle_enabled_var" in self.ui_vars:
                    self.ui_vars["battle_enabled_var"].set(True)
            return

    def _show_start_popup(self) -> None:
        if not self.root:
            return
        state = self.runtime.state
        popup = ctk.CTkToplevel(self.root)
        popup.title("START! — Select Modules")
        popup.configure(fg_color=BG)
        popup.geometry("420x480")
        popup.minsize(360, 400)
        popup.transient(self.root)
        popup.grab_set()

        frame = ctk.CTkFrame(popup, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(frame, text="Select which modules to start:",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=FG).pack(anchor="w", pady=(0, 10))

        prev_saved = set(state.startup_modules)
        vars_list: list[tuple[str, ctk.BooleanVar]] = []

        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent",
                                         scrollbar_button_color=SURFACE,
                                         scrollbar_button_hover_color=BLUE)
        scroll.pack(fill="both", expand=True)

        for mid, display_name, _ in self._STARTUP_MODULE_DEFS:
            var = ctk.BooleanVar(value=mid in prev_saved)
            cb = ctk.CTkCheckBox(scroll, text=display_name, variable=var,
                                  fg_color=BLUE, text_color=FG,
                                  font=ctk.CTkFont(size=11))
            cb.pack(anchor="w", pady=2, padx=4)
            vars_list.append((mid, var))

        def select_all():
            for _, var in vars_list:
                var.set(True)

        def deselect_all():
            for _, var in vars_list:
                var.set(False)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))
        _ctk_btn(btn_frame, "☑  All", select_all, BLUE).pack(side="left", padx=2, expand=True, fill="x")
        _ctk_btn(btn_frame, "☐  None", deselect_all, MUTED).pack(side="left", padx=2, expand=True, fill="x")

        def on_start():
            selected = [mid for mid, var in vars_list if var.get()]
            state.startup_modules = list(selected)
            for mid in selected:
                self._start_selected_module(mid)
            self._save_current_character_profile(log_success=True, force=True)
            popup.destroy()

        _ctk_btn(frame, "▶  START", on_start, GREEN).pack(fill="x", pady=(6, 0), ipady=6)
        popup.bind("<Escape>", lambda e: popup.destroy())
        popup.focus_force()

    # ── Attach / light process ─────────────────────────────

    def attach_light_process(self) -> None:
        self._poll_settings(schedule_next=False)
        self._save_current_character_profile(log_success=False)
        ok, message = self.light_service.attach()
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
        color = TEAL if ok else ORANGE
        self.runtime.ui.set_status(message, color)
        self.runtime.ui.log(("✅ " if ok else "❌ ") + message)

    def _load_or_create_attached_character_profile(self) -> str:
        controller = getattr(self.light_service, "controller", None)
        pid = getattr(controller, "pid", None) if controller is not None else None
        window_title = get_window_title_for_pid(int(pid or 0))
        window_rect = get_window_rect_for_pid(int(pid or 0))
        identity = build_identity(self.runtime.state.light_process_name, window_title)

        self.runtime.state.attached_window_title = identity.window_title
        self.runtime.state.character_name = identity.character_name
        self.runtime.state.character_name_normalized = identity.normalized_name

        try:
            from .character_profiles import find_game_window
            hwnd = find_game_window(
                pid=int(pid or 0),
                process_name=self.runtime.state.light_process_name,
                preferred_title=identity.window_title,
            )
            if hwnd:
                self.runtime.state.game_hwnd = int(hwnd)
                self.runtime.state.game_window_title = identity.window_title
        except Exception:
            pass

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
            self._sync_ui_from_state()
            self.runtime.ui.set_status(f"Perfil carregado para {identity.character_name}", GREEN)
            self.runtime.ui.log(f"📂 Character profile loaded: {profile_path}")
            return f"character={identity.character_name}"

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

        if not force:
            current_hash = self._compute_profile_payload_hash()
            if self._last_saved_json_hash == current_hash:
                return False

        save_character_profile(
            profile_path, self.runtime.state, identity,
            window_rect=self._get_attached_window_rect(),
        )
        self._refresh_last_saved_profile_hash()

        if log_success:
            self.runtime.ui.log(f"💾 Character autosaved: {profile_path}")
        return True

    def _compute_profile_payload_hash(self) -> str:
        current_dict = ConfigSerializer.to_dict(self.runtime.state)
        clean = {k: v for k, v in current_dict.items()
                 if not k.startswith("__") and k not in PROFILE_BLOCKED_CFG_KEYS}
        payload_json = json.dumps(clean, sort_keys=True, indent=2)
        return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    def _refresh_last_saved_profile_hash(self) -> None:
        self._last_saved_json_hash = self._compute_profile_payload_hash()

    def _get_attached_window_rect(self):
        controller = getattr(self.light_service, "controller", None)
        pid = getattr(controller, "pid", None) if controller is not None else None
        return get_window_rect_for_pid(int(pid or 0))

    def _manual_save_profiles(self) -> None:
        from tkinter import filedialog
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

    def _apply_loaded_runtime_state(self) -> None:
        self._refresh_last_saved_profile_hash()
        self._restart_global_listener()
        if (self.runtime.state.char_status_region or self.runtime.state.char_status_hp_region
                or self.runtime.state.char_status_mana_region or self.runtime.state.char_status_cap_region):
            self.char_status_service.restart_if_needed()
        else:
            self.char_status_service.stop()

    def _sync_ui_from_state(self) -> None:
        state = self.runtime.state
        ms_mappings = {
            "afk_min_var": state.afk_min_ms, "afk_max_var": state.afk_max_ms,
            "rclick_min_var": state.rclick_min_ms, "rclick_max_var": state.rclick_max_ms,
            "char_status_poll_var": state.char_status_poll_ms,
            "char_status_sample_delay_var": state.char_status_sample_delay_ms,
            "fish_cast_min_var": state.fish_cast_min_ms, "fish_cast_max_var": state.fish_cast_max_ms,
            "fish_wait_min_var": state.fish_wait_min_ms, "fish_wait_max_var": state.fish_wait_max_ms,
            "rclick_food_burst_interval_var": state.rclick_food_burst_interval_ms,
        }
        for name, value in ms_mappings.items():
            if name in self.ui_vars:
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
        if "light_freeze_enabled_var" in self.ui_vars:
            self.ui_vars["light_freeze_enabled_var"].set(state.light_freeze_enabled)
        self._refresh_all_module_indicators_from_state()

    # ── Config tab helpers ─────────────────────────────────

    def load_config(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="Load Config", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            payload = ConfigSerializer.load_file(path)
            ConfigSerializer.apply_loaded(self.runtime.state, payload)
            self._apply_loaded_runtime_state()
            self._sync_ui_from_state()
            self.runtime.ui.log(f"📂 Loaded: {path}")
            self.runtime.ui.log("✅ Config applied")
            self.runtime.ui.set_status("Config loaded", GREEN)
        except Exception as exc:
            self.runtime.ui.log(f"❌ Load failed: {exc}")

    # ── Region selection ───────────────────────────────────

    def _select_region(self, state_attr: str, label, title: str) -> None:
        def on_done(region: tuple[int, int, int, int]) -> None:
            setattr(self.runtime.state, state_attr, region)
            if state_attr == "alarm_region":
                x_val, y_val, width, height = region
                text = f"Area: ({x_val},{y_val})  {width}×{height} px"
                if label:
                    label.configure(text=text)
                self.runtime.ui.log(f"✅ Screen watch area: {text}")
                self.runtime.ui.set_status(f"Screen watch area: {text}", TEAL)
                return
            if state_attr == "alarm_battle_region":
                x_val, y_val, width, height = region
                text = f"Battle Area: ({x_val},{y_val}) {width}x{height} px"
                if label:
                    label.configure(text=text)
                self.runtime.ui.log(f"Battle area selected: {text}")
                self.runtime.ui.set_status(f"Battle area selected: {text}", TEAL)
                return
            if hasattr(self, "character_status_tab_ui") and self.character_status_tab_ui:
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
        overlay = ctk.CTkToplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.30)
        overlay.attributes("-topmost", True)
        overlay.configure(fg_color="black")
        overlay.overrideredirect(True)

        canvas = tk.Canvas(overlay, cursor="crosshair", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(20, 20, text=f"  {title}  ", font=("Segoe UI", 10, "bold"),
                           fill=TEAL, anchor="nw")
        start_xy = [None]
        rect_id = [None]

        def on_press(event):
            start_xy[0] = (event.x, event.y)
            if rect_id[0]:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                  outline=TEAL, width=2, dash=(6, 3))

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

    # ── Window management ──────────────────────────────────

    def _enable_dpi_awareness(self) -> None:
        if os.name != "nt":
            return
        try:
            import ctypes as _ct
            _ct.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                import ctypes as _ct
                _ct.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

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
        except Exception:
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

    def minimize_window(self) -> None:
        self._set_fullscreen(False)
        self.root.iconify()

    def toggle_maximize_window(self) -> None:
        self._set_fullscreen(False)
        if self.root.state() == "normal":
            self.root.state("zoomed")
        else:
            self.root.state("normal")

    def toggle_fullscreen(self) -> None:
        self._set_fullscreen(not self._fullscreen_enabled)

    def _exit_fullscreen(self, _event=None) -> None:
        if self._fullscreen_enabled:
            self._set_fullscreen(False)

    def _set_fullscreen(self, enabled: bool) -> None:
        self._fullscreen_enabled = enabled
        self.root.attributes("-fullscreen", enabled)

    # ── Sandbox launcher (minimal CTk version) ─────────────

    def _show_sandbox_launcher_popup(self) -> None:
        self.runtime.ui.log("🔒 Sandbox Launcher not yet ported to Luxe UI — use the original interface")

    # ── Tray icon ──────────────────────────────────────────

    def _make_tray_image(self, color=(48, 209, 88)):
        image = Image.new("RGB", (64, 64), (*color[:3], 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([4, 4, 60, 60], fill=color[:3])
        draw.rectangle([20, 28, 44, 36], fill=(255, 255, 255))
        draw.rectangle([28, 20, 36, 44], fill=(255, 255, 255))
        return image

    def _get_tray_color(self):
        return self.resolve_tray_icon()

    def resolve_tray_icon(self):
        state = self.runtime.state
        paused = self.runtime.pause.paused
        has_modules = any((
            state.afk_active, state.rclick_active, state.alarm_active,
            state.char_status_active, state.fish_active, state.healer_active,
            state.rune_active, state.light_freeze_enabled,
        ))
        if not has_modules and not paused:
            return (239, 68, 68)
        if paused:
            return (255, 191, 0)
        if state.rune_active:
            return (191, 90, 242)
        if state.fish_active:
            return (10, 132, 255)
        return (48, 209, 88)

    def _update_tray_icon(self) -> None:
        if self.tray_icon is None or not HAS_TRAY:
            return
        try:
            color = self._get_tray_color()
            new_image = self._make_tray_image(color)
            image_attr = 'icon' if hasattr(self.tray_icon, 'icon') else 'image'
            current_image = getattr(self.tray_icon, image_attr)
            old_rgb = None
            if hasattr(current_image, 'tobytes'):
                try:
                    old_rgb = bytes(current_image.tobytes())
                except Exception:
                    pass
            new_rgb = bytes(new_image.tobytes())
            if old_rgb != new_rgb:
                setattr(self.tray_icon, image_attr, new_image)
                time.sleep(0.05)
                try:
                    self.tray_icon.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Show SystemMonitor Luxe", self.show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause / Resume", lambda: self.root.after(0, self.runtime.pause.toggle)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.exit_app),
        )
        self.tray_icon = pystray.Icon("SystemMonitorLuxe", self._make_tray_image(self._get_tray_color()),
                                       "SystemMonitor Luxe", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

        def _poll_tray():
            self._update_tray_icon()
            self.root.after(APP_TRAY_POLL_INTERVAL_MS, _poll_tray)

        self.root.after(APP_TRAY_BOOTSTRAP_DELAY_MS, _poll_tray)

    def show_window(self, *args) -> None:
        self.root.after(0, lambda: (self.root.deiconify(), self.root.lift(), self.root.focus_force()))

    def exit_app(self, *args) -> None:
        self._stop_stats_polling()
        self.char_status_service.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.root:
            self.root.destroy()


def run() -> None:
    SystemMonitorLuxeApp().run()
