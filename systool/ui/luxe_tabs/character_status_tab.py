"""Luxe (CTk) character status tab — ported from tkinter CharacterStatusTab."""

from __future__ import annotations

import time
import customtkinter as ctk
from tkinter import filedialog

from ...config import CHAR_STATUS_POLL_MS_MIN, NON_NEGATIVE_INT_MIN


class CharacterStatusTab:
    """Owns the character status tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.char_status_region_label: ctk.CTkLabel | None = None
        self.char_status_hp_region_label: ctk.CTkLabel | None = None
        self.char_status_mana_region_label: ctk.CTkLabel | None = None
        self.char_status_cap_region_label: ctk.CTkLabel | None = None
        self.char_status_tesseract_label: ctk.CTkLabel | None = None
        self.char_status_watch_label: ctk.CTkLabel | None = None
        self.char_status_level_label: ctk.CTkLabel | None = None
        self.char_status_hp_label: ctk.CTkLabel | None = None
        self.char_status_mana_label: ctk.CTkLabel | None = None
        self.char_status_cap_label: ctk.CTkLabel | None = None
        self.char_status_food_label: ctk.CTkLabel | None = None
        self.char_status_regen_label: ctk.CTkLabel | None = None
        self.char_status_seen_label: ctk.CTkLabel | None = None
        self.char_status_error_label: ctk.CTkLabel | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        # ── Status Window Watch ──
        watch_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        watch_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(watch_panel, text="📊  Status Window Watch",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.helpers["register_module_indicator"](watch_panel, "char_status", self.runtime.state.char_status_active)

        r = self.runtime.state.char_status_region
        region_text = f"Window: ({r[0]},{r[1]}) {r[2]}x{r[3]} px" if r else "Window: not selected"
        self.char_status_region_label = ctk.CTkLabel(watch_panel, text=region_text,
                                                      font=ctk.CTkFont(size=10, family="Consolas"),
                                                      text_color="#5ac8fa", anchor="w")
        self.char_status_region_label.pack(padx=10, pady=(0, 4))

        unit = self.helpers["get_unit_label"]()
        char_poll = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.char_status_poll_ms)))
        char_samples = ctk.StringVar(value=str(self.runtime.state.char_status_samples))
        char_sample_delay = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.char_status_sample_delay_ms)))
        tesseract_path = ctk.StringVar(value=self.runtime.state.char_status_tesseract_path)

        self.ui_vars["char_status_poll_var"] = char_poll
        self.ui_vars["char_status_samples_var"] = char_samples
        self.ui_vars["char_status_sample_delay_var"] = char_sample_delay
        self.ui_vars["char_status_tesseract_var"] = tesseract_path

        self.helpers["label_entry"](watch_panel, f"Refresh every ({unit}):", char_poll, width=90)
        self.helpers["label_entry"](watch_panel, "Samples per scan:", char_samples, width=90)
        self.helpers["label_entry"](watch_panel, f"Delay between samples ({unit}):", char_sample_delay, width=90)

        tesseract_row = ctk.CTkFrame(watch_panel, fg_color="transparent")
        tesseract_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(tesseract_row, text="Tesseract path:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", width=150, anchor="w").pack(side="left")
        ctk.CTkEntry(tesseract_row, textvariable=tesseract_path, width=240,
                      fg_color="#1a1a1a", border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=4, fill="x", expand=True)
        self.helpers["btn"](tesseract_row, "Browse", self.browse_tesseract_path, "#bf5af2").pack(side="left")

        self.char_status_tesseract_label = ctk.CTkLabel(watch_panel, text="",
                                                         font=ctk.CTkFont(size=10),
                                                         text_color="#777777", anchor="w", justify="left")
        self.char_status_tesseract_label.pack(padx=10, pady=(4, 0), fill="x")

        field_regions = ctk.CTkFrame(watch_panel, fg_color="transparent")
        field_regions.pack(fill="x", padx=10, pady=(6, 0))

        hp_r = self.runtime.state.char_status_hp_region
        self.char_status_hp_region_label = ctk.CTkLabel(
            field_regions,
            text=f"HP area: ({hp_r[0]},{hp_r[1]}) {hp_r[2]}x{hp_r[3]}" if hp_r else "HP area: not selected",
            font=ctk.CTkFont(size=10, family="Consolas"), text_color="#5ac8fa", anchor="w")
        self.char_status_hp_region_label.pack(fill="x", pady=1)

        mana_r = self.runtime.state.char_status_mana_region
        self.char_status_mana_region_label = ctk.CTkLabel(
            field_regions,
            text=f"Mana area: ({mana_r[0]},{mana_r[1]}) {mana_r[2]}x{mana_r[3]}" if mana_r else "Mana area: not selected",
            font=ctk.CTkFont(size=10, family="Consolas"), text_color="#5ac8fa", anchor="w")
        self.char_status_mana_region_label.pack(fill="x", pady=1)

        cap_r = self.runtime.state.char_status_cap_region
        self.char_status_cap_region_label = ctk.CTkLabel(
            field_regions,
            text=f"Cap area: ({cap_r[0]},{cap_r[1]}) {cap_r[2]}x{cap_r[3]}" if cap_r else "Cap area: not selected",
            font=ctk.CTkFont(size=10, family="Consolas"), text_color="#5ac8fa", anchor="w")
        self.char_status_cap_region_label.pack(fill="x", pady=1)

        button_row = ctk.CTkFrame(watch_panel, fg_color="transparent")
        button_row.pack(fill="x", padx=10, pady=(6, 0))
        self.helpers["btn"](button_row, "🖼  Select Window", self.select_character_status_region, "#0a84ff").pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](button_row, "❤️  HP", self.select_character_status_hp_region, "#bf5af2").pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](button_row, "💧  Mana", self.select_character_status_mana_region, "#bf5af2").pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](button_row, "📦  Cap", self.select_character_status_cap_region, "#bf5af2").pack(side="left", padx=2, expand=True, fill="x")

        button_row2 = ctk.CTkFrame(watch_panel, fg_color="transparent")
        button_row2.pack(fill="x", padx=10, pady=(6, 10))
        self.helpers["btn"](button_row2, "▶  Start", self.services["char_status_service"].start, "#30d158").pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](button_row2, "⏹  Stop", self.services["char_status_service"].stop, "#ff453a").pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](button_row2, "↺  Reset", self.reset_character_status_region, "#ff9f0a").pack(side="left", padx=2, expand=True, fill="x")

        # ── Live Values ──
        values_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        values_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(values_panel, text="🔎  Live Values",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.char_status_watch_label = ctk.CTkLabel(values_panel, text="Watcher: idle",
                                                     font=ctk.CTkFont(size=10, weight="bold"),
                                                     text_color="#ff9f0a", anchor="w")
        self.char_status_watch_label.pack(padx=10, pady=(0, 6))

        self.char_status_level_label = ctk.CTkLabel(values_panel, text="Level: —",
                                                     font=ctk.CTkFont(size=14, weight="bold"),
                                                     text_color="#5ac8fa", anchor="w")
        self.char_status_level_label.pack(padx=10, fill="x", pady=2)
        self.char_status_hp_label = ctk.CTkLabel(values_panel, text="HP: —",
                                                  font=ctk.CTkFont(size=14, weight="bold"),
                                                  text_color="#ff453a", anchor="w")
        self.char_status_hp_label.pack(padx=10, fill="x", pady=2)
        self.char_status_mana_label = ctk.CTkLabel(values_panel, text="Mana: —",
                                                    font=ctk.CTkFont(size=14, weight="bold"),
                                                    text_color="#0a84ff", anchor="w")
        self.char_status_mana_label.pack(padx=10, fill="x", pady=2)
        self.char_status_cap_label = ctk.CTkLabel(values_panel, text="Cap: —",
                                                   font=ctk.CTkFont(size=14, weight="bold"),
                                                   text_color="#5ac8fa", anchor="w")
        self.char_status_cap_label.pack(padx=10, fill="x", pady=2)
        self.char_status_food_label = ctk.CTkLabel(values_panel, text="Food: —",
                                                    font=ctk.CTkFont(size=14, weight="bold"),
                                                    text_color="#30d158", anchor="w")
        self.char_status_food_label.pack(padx=10, fill="x", pady=2)
        self.char_status_regen_label = ctk.CTkLabel(values_panel, text="Regen: HP 0.0/min | Mana 0.0/min",
                                                     font=ctk.CTkFont(size=10, family="Consolas"),
                                                     text_color="#777777", anchor="w")
        self.char_status_regen_label.pack(padx=10, fill="x", pady=2)
        self.char_status_seen_label = ctk.CTkLabel(values_panel, text="Last update: —",
                                                    font=ctk.CTkFont(size=10, family="Consolas"),
                                                    text_color="#777777", anchor="w")
        self.char_status_seen_label.pack(padx=10, fill="x", pady=(10, 2))
        self.char_status_error_label = ctk.CTkLabel(values_panel, text="OCR: waiting for a valid read",
                                                     font=ctk.CTkFont(size=10),
                                                     text_color="#777777", justify="left", anchor="w")
        self.char_status_error_label.pack(padx=10, fill="x", pady=(0, 10))

        # ── Help Panel (right column) ──
        help_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        help_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(help_panel, text="ℹ️  How It Works",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        for line in [
            "1. Best mode: select HP, Mana, and Cap areas individually.",
            "2. Fallback mode: select the full character status window if you want one-shot setup.",
            "3. Values stay in memory on runtime.state as char_status_hp / mana / cap.",
            "4. If OCR misses a frame, the last good values are kept until the next valid read.",
        ]:
            ctk.CTkLabel(help_panel, text=line, font=ctk.CTkFont(size=10),
                          text_color="#777777", justify="left", anchor="w").pack(padx=10, fill="x", pady=2)
        dependency_error = self.services["char_status_service"].get_dependency_error()
        dep_ready = dependency_error is None
        dep_text = "Python OCR packages loaded" if dep_ready else f"OCR dependency status: {dependency_error}"
        ctk.CTkLabel(help_panel, text=dep_text,
                      font=ctk.CTkFont(size=10, weight="bold"),
                      text_color="#5ac8fa" if dep_ready else "#ff9f0a",
                      justify="left", wraplength=300).pack(padx=10, pady=(10, 10), anchor="w")

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
                self.char_status_region_label.configure(text=f"Window: ({x_val},{y_val})  {width}×{height} px")
            else:
                self.char_status_region_label.configure(text="Window: not selected")
        self._refresh_region_label(self.char_status_hp_region_label, "HP area", state.char_status_hp_region)
        self._refresh_region_label(self.char_status_mana_region_label, "Mana area", state.char_status_mana_region)
        self._refresh_region_label(self.char_status_cap_region_label, "Cap area", state.char_status_cap_region)
        if self.char_status_tesseract_label:
            dependency_error = self.services["char_status_service"].get_dependency_error()
            backend_diag = self.services["char_status_service"].get_backend_diagnostic()
            if dependency_error == "Tesseract executable not found":
                self.char_status_tesseract_label.configure(
                    text=f"Tesseract: not found automatically. Set the full path to tesseract.exe here.\n{backend_diag}",
                    text_color="#ff9f0a",
                )
            elif dependency_error:
                self.char_status_tesseract_label.configure(text=f"Tesseract: {dependency_error}\n{backend_diag}", text_color="#ff9f0a")
            else:
                active_path = self.runtime.state.char_status_tesseract_path.strip() or "auto-detected"
                self.char_status_tesseract_label.configure(text=f"Tesseract: ready ({active_path})\n{backend_diag}", text_color="#5ac8fa")
        if self.char_status_watch_label:
            watch_text = "Watcher: active" if state.char_status_active else "Watcher: idle"
            watch_color = "#30d158" if state.char_status_active else "#ff9f0a"
            self.char_status_watch_label.configure(text=watch_text, text_color=watch_color)
        if self.char_status_level_label:
            self.char_status_level_label.configure(text=f"Level: {state.char_status_level if state.char_status_level is not None else '—'}")
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
            self.char_status_food_label.configure(text=f"Food: {self.helpers['format_food_timer'](state.char_status_food_seconds, state.char_status_food_text)}")
        if self.char_status_regen_label:
            self.char_status_regen_label.configure(text=f"Regen: HP {state.char_status_hp_regen_per_min:.1f}/min | Mana {state.char_status_mana_regen_per_min:.1f}/min")
        if self.char_status_seen_label:
            if state.char_status_last_seen:
                seen = time.strftime("%H:%M:%S", time.localtime(state.char_status_last_seen))
                peak_text = f"  |  HP max: {state.char_status_hp_peak}" if state.char_status_hp_peak else ""
                perf_text = self.services["char_status_service"].get_perf_summary()
                self.char_status_seen_label.configure(
                    text=f"Last update: {seen}  |  Reads: {state.char_status_reads}  |  Misses: {state.char_status_failures}{peak_text}\n{perf_text}"
                )
            else:
                self.char_status_seen_label.configure(text="Last update: —")
        if self.char_status_error_label:
            message = state.char_status_last_error or "OCR locked on the last good frame"
            color = "#ff9f0a" if state.char_status_last_error else "#777777"
            self.char_status_error_label.configure(text=f"OCR: {message}", text_color=color)

    @staticmethod
    def _refresh_region_label(label, title: str, region):
        if not label:
            return
        if region:
            x_val, y_val, width, height = region
            label.configure(text=f"{title}: ({x_val},{y_val}) {width}×{height}")
        else:
            label.configure(text=f"{title}: not selected")
