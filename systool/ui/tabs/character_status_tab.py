"""Character status tab UI for SystemMonitor."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog

from ...config import CHAR_STATUS_POLL_MS_MIN, NON_NEGATIVE_INT_MIN
from ...theme import BLUE, BOLD, FG, GREEN, HEADER, MONO, MUTED, ORANGE, PANEL, PURPLE, RED, SMALL, SMALL_B, TEAL


class CharacterStatusTab:
    """Owns the character status tab UI and tab-local behavior."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

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

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        watch_panel = tk.LabelFrame(left, text=" 📊  Status Window Watch ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        watch_panel.pack(fill="x", pady=(0, 8))
        self.helpers["register_module_indicator"](watch_panel, "char_status", self.runtime.state.char_status_active)
        self.char_status_region_label = tk.Label(watch_panel, text="Window: not selected", font=MONO, fg=TEAL, bg=PANEL)
        self.char_status_region_label.pack(anchor="w", pady=(0, 4))

        unit = self.helpers["get_unit_label"]()
        char_poll = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.char_status_poll_ms)))
        char_samples = tk.StringVar(value=str(self.runtime.state.char_status_samples))
        char_sample_delay = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.char_status_sample_delay_ms)))
        tesseract_path = tk.StringVar(value=self.runtime.state.char_status_tesseract_path)

        self.ui_vars["char_status_poll_var"] = char_poll
        self.ui_vars["char_status_samples_var"] = char_samples
        self.ui_vars["char_status_sample_delay_var"] = char_sample_delay
        self.ui_vars["char_status_tesseract_var"] = tesseract_path

        self.helpers["label_entry"](watch_panel, f"Refresh every ({unit}):", char_poll, width=6)
        self.helpers["label_entry"](watch_panel, "Samples per scan:", char_samples, width=6)
        self.helpers["label_entry"](watch_panel, f"Delay between samples ({unit}):", char_sample_delay, width=6)

        tesseract_row = tk.Frame(watch_panel, bg=PANEL)
        tesseract_row.pack(fill="x", pady=2)
        tk.Label(tesseract_row, text="Tesseract path:", font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        self.helpers["entry"](tesseract_row, tesseract_path, 28).pack(side="left", padx=4, fill="x", expand=True)
        self.helpers["btn"](tesseract_row, "Browse", self.browse_tesseract_path, PURPLE).pack(side="left")

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
        self.helpers["btn"](button_row, "🖼 Select Window", self.select_character_status_region, BLUE).pack(side="left", padx=(0, 4), expand=True, fill="x")
        self.helpers["btn"](button_row, "HP", self.select_character_status_hp_region, PURPLE).pack(side="left", padx=4, expand=True, fill="x")
        self.helpers["btn"](button_row, "Mana", self.select_character_status_mana_region, PURPLE).pack(side="left", padx=4, expand=True, fill="x")
        self.helpers["btn"](button_row, "Cap", self.select_character_status_cap_region, PURPLE).pack(side="left", padx=4, expand=True, fill="x")

        button_row2 = tk.Frame(watch_panel, bg=PANEL)
        button_row2.pack(fill="x", pady=(6, 0))
        self.helpers["btn"](button_row2, "▶ Start", self.services["char_status_service"].start, GREEN).pack(side="left", padx=4, expand=True, fill="x")
        self.helpers["btn"](button_row2, "⏹ Stop", self.services["char_status_service"].stop, RED).pack(side="left", padx=4, expand=True, fill="x")
        self.helpers["btn"](button_row2, "↺ Reset", self.reset_character_status_region, ORANGE).pack(side="left", padx=(4, 0), expand=True, fill="x")

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
        dependency_error = self.services["char_status_service"].get_dependency_error()
        dep_ready = dependency_error is None
        dep_text = "Python OCR packages loaded" if dep_ready else f"OCR dependency status: {dependency_error}"
        tk.Label(help_panel, text=dep_text, font=SMALL_B, fg=TEAL if dep_ready else ORANGE, bg=PANEL, justify="left", wraplength=300).pack(anchor="w", pady=(10, 0))

    def browse_tesseract_path(self) -> None:
        path = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("Tesseract", "tesseract.exe"), ("Executables", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.runtime.state.char_status_tesseract_path = path
            self.ui_vars["char_status_tesseract_var"].set(path)
            self.refresh_display()

    def select_character_status_region(self) -> None:
        self.helpers["select_region"]("char_status_region", self.char_status_region_label, "Select the full character status window")

    def select_character_status_hp_region(self) -> None:
        self.helpers["select_region"]("char_status_hp_region", self.char_status_hp_region_label, "Select HP number area")

    def select_character_status_mana_region(self) -> None:
        self.helpers["select_region"]("char_status_mana_region", self.char_status_mana_region_label, "Select Mana number area")

    def select_character_status_cap_region(self) -> None:
        self.helpers["select_region"]("char_status_cap_region", self.char_status_cap_region_label, "Select Cap text/number area")

    def reset_character_status_region(self) -> None:
        self.services["char_status_service"].stop()
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
        self.refresh_display()
        self.runtime.ui.log("ℹ️  Character status window reset")

    def poll_settings(self, state) -> None:
        state.char_status_poll_ms = max(CHAR_STATUS_POLL_MS_MIN, self.helpers["get_ui_ms"]("char_status_poll_var", state.char_status_poll_ms))
        state.char_status_samples = max(1, self.helpers["get_ui_int"]("char_status_samples_var", state.char_status_samples))
        state.char_status_sample_delay_ms = max(NON_NEGATIVE_INT_MIN, self.helpers["get_ui_ms"]("char_status_sample_delay_var", state.char_status_sample_delay_ms))
        if "char_status_samples_var" not in self.ui_vars:
            state.char_status_samples = max(1, 2000 // state.char_status_poll_ms)
        if "char_status_tesseract_var" in self.ui_vars:
            state.char_status_tesseract_path = str(self.ui_vars["char_status_tesseract_var"].get()).strip()

    def refresh_display(self) -> None:
        state = self.runtime.state
        if self.char_status_region_label:
            if state.char_status_region:
                x_val, y_val, width, height = state.char_status_region
                self.char_status_region_label.config(text=f"Window: ({x_val},{y_val})  {width}×{height} px")
            else:
                self.char_status_region_label.config(text="Window: not selected")
        self._refresh_region_label(self.char_status_hp_region_label, "HP area", state.char_status_hp_region)
        self._refresh_region_label(self.char_status_mana_region_label, "Mana area", state.char_status_mana_region)
        self._refresh_region_label(self.char_status_cap_region_label, "Cap area", state.char_status_cap_region)
        if self.char_status_tesseract_label:
            dependency_error = self.services["char_status_service"].get_dependency_error()
            backend_diag = self.services["char_status_service"].get_backend_diagnostic()
            if dependency_error == "Tesseract executable not found":
                self.char_status_tesseract_label.config(
                    text=f"Tesseract: not found automatically. Set the full path to tesseract.exe here.\n{backend_diag}",
                    fg=ORANGE,
                )
            elif dependency_error:
                self.char_status_tesseract_label.config(text=f"Tesseract: {dependency_error}\n{backend_diag}", fg=ORANGE)
            else:
                active_path = self.runtime.state.char_status_tesseract_path.strip() or "auto-detected"
                self.char_status_tesseract_label.config(text=f"Tesseract: ready ({active_path})\n{backend_diag}", fg=TEAL)
        if self.char_status_watch_label:
            watch_text = "Watcher: active" if state.char_status_active else "Watcher: idle"
            watch_color = GREEN if state.char_status_active else ORANGE
            self.char_status_watch_label.config(text=watch_text, fg=watch_color)
        if self.char_status_level_label:
            self.char_status_level_label.config(text=f"Level: {state.char_status_level if state.char_status_level is not None else '—'}")
        if self.char_status_hp_label:
            hp_display = state.hp_value if state.hp_value is not None else state.char_status_hp
            self.helpers["set_stat_label"](self.char_status_hp_label, hp_display, state.hp_source if state.hp_value is not None else None)
        if self.char_status_mana_label:
            mp_display = state.mp_value if state.mp_value is not None else state.char_status_mana
            self.helpers["set_stat_label"](self.char_status_mana_label, mp_display, state.mp_source if state.mp_value is not None else None)
        if self.char_status_cap_label:
            cap_display = state.cap_value if state.cap_value is not None else state.char_status_cap
            self.helpers["set_stat_label"](self.char_status_cap_label, cap_display, state.cap_source if state.cap_value is not None else None)
        if self.char_status_food_label:
            self.char_status_food_label.config(text=f"Food: {self.helpers['format_food_timer'](state.char_status_food_seconds, state.char_status_food_text)}")
        if self.char_status_regen_label:
            self.char_status_regen_label.config(text=f"Regen: HP {state.char_status_hp_regen_per_min:.1f}/min | Mana {state.char_status_mana_regen_per_min:.1f}/min")
        if self.char_status_seen_label:
            if state.char_status_last_seen:
                seen = time.strftime("%H:%M:%S", time.localtime(state.char_status_last_seen))
                peak_text = f"  |  HP max: {state.char_status_hp_peak}" if state.char_status_hp_peak else ""
                perf_text = self.services["char_status_service"].get_perf_summary()
                self.char_status_seen_label.config(
                    text=f"Last update: {seen}  |  Reads: {state.char_status_reads}  |  Misses: {state.char_status_failures}{peak_text}\n{perf_text}"
                )
            else:
                self.char_status_seen_label.config(text="Last update: —")
        if self.char_status_error_label:
            message = state.char_status_last_error or "OCR locked on the last good frame"
            color = ORANGE if state.char_status_last_error else MUTED
            self.char_status_error_label.config(text=f"OCR: {message}", fg=color)

    @staticmethod
    def _refresh_region_label(label: tk.Label | None, title: str, region: tuple[int, int, int, int] | None) -> None:
        if not label:
            return
        if region:
            x_val, y_val, width, height = region
            label.config(text=f"{title}: ({x_val},{y_val}) {width}×{height}")
        else:
            label.config(text=f"{title}: not selected")
