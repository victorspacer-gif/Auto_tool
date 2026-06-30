"""Luxe (CTk) activity control tab — ported from tkinter ActivityControlTab."""

from __future__ import annotations

import customtkinter as ctk

from ...models import HotkeyJob
from ...runtime import HAS_WIN32


class ActivityControlTab:
    """Owns the activity control tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.jobs_frame: ctk.CTkScrollableFrame | None = None
        self.pos_label: ctk.CTkLabel | None = None
        self.rclick_food_mode_container: ctk.CTkFrame | None = None

        self._build()

    def _build(self) -> None:
        """Build the activity control tab."""
        content_frame = self.helpers["create_scrollable_content"](self.parent, padx=14, pady=10)
        left, right = self.helpers["create_responsive_columns"](content_frame, threshold=1360)

        # ── Hotkey Tasks ──
        jobs_frame = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        jobs_frame.pack(fill="both", expand=True)
        ctk.CTkLabel(jobs_frame, text="Hotkey Tasks — independent threads",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 4))

        top = ctk.CTkFrame(jobs_frame, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(0, 6))
        self.helpers["btn"](top, "+ Add Job", self.add_job, "#0a84ff").pack(side="left", padx=2)
        ctk.CTkLabel(top, text="Enable 'Focus window' to direct keys to a selected app window",
                      font=ctk.CTkFont(size=10), text_color="#777777").pack(side="left", padx=10)

        self.jobs_frame = ctk.CTkScrollableFrame(jobs_frame, fg_color="transparent")
        self.jobs_frame.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        self._build_afk_panel(right)
        self._build_right_click_panel(right)

    def _build_afk_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(panel, text="Activity Monitor",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.helpers["register_module_indicator"](panel, "afk", self.runtime.state.afk_active)

        unit = self.helpers["get_unit_label"]()
        afk_min = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.afk_min_ms)))
        afk_max = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.afk_max_ms)))
        self.ui_vars["afk_min_var"] = afk_min
        self.ui_vars["afk_max_var"] = afk_max
        afk_min.trace_add("write", self._update_afk_min)
        afk_max.trace_add("write", self._update_afk_max)
        self.helpers["label_entry"](panel, f"Timer Min ({unit}):", afk_min)
        self.helpers["label_entry"](panel, f"Timer Max ({unit}):", afk_max)

        ctk.CTkLabel(panel, text="Ctrl held down → arrow press → Ctrl released",
                      font=ctk.CTkFont(size=10), text_color="#777777", anchor="w").pack(padx=10, pady=(2, 0))
        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(fill="x", padx=10, pady=(6, 8))
        self.helpers["btn"](buttons, "▶  Start", self.services["afk_service"].start, "#30d158").pack(side="left", expand=True, fill="x", padx=2)
        self.helpers["btn"](buttons, "⏹  Stop", self.services["afk_service"].stop, "#ff453a").pack(side="left", expand=True, fill="x", padx=2)

    def _build_right_click_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(panel, text="Right-Click Monitor",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.helpers["register_module_indicator"](panel, "rclick", self.runtime.state.rclick_active)

        f1 = ctk.CTkFrame(panel, fg_color="transparent")
        f1.pack(fill="x", padx=10, pady=(2, 4))
        self.pos_label = ctk.CTkLabel(f1, text=f"Pos: {self.runtime.state.rclick_pos[0]}, {self.runtime.state.rclick_pos[1]}",
                                       font=ctk.CTkFont(size=10, family="Consolas"),
                                       text_color="#5ac8fa", anchor="w")
        self.pos_label.pack(side="left")
        self.helpers["btn"](f1, "🎯 Record Position", self.record_rclick_pos, "#0a84ff").pack(side="right", padx=2)

        unit = self.helpers["get_unit_label"]()
        rclick_jitter = ctk.StringVar(value=str(self.runtime.state.rclick_jitter))
        self.ui_vars["rclick_jitter_var"] = rclick_jitter
        self.helpers["label_entry"](panel, "Click jitter (px ±):", rclick_jitter, width=5)

        min_var = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_min_ms)))
        max_var = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_max_ms)))
        self.ui_vars["rclick_min_var"] = min_var
        self.ui_vars["rclick_max_var"] = max_var
        min_var.trace_add("write", self._update_rclick_min)
        max_var.trace_add("write", self._update_rclick_max)

        r1 = ctk.CTkFrame(panel, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=2)
        self.helpers["label_entry"](r1, f"Timer Min ({unit}):", min_var).pack(side="left")
        self.helpers["label_entry"](r1, f"Timer Max ({unit}):", max_var).pack(side="left", padx=(8, 0))

        rclick_food_burst_count_min = ctk.StringVar(value=str(self.runtime.state.rclick_food_burst_count_min))
        rclick_food_burst_count_max = ctk.StringVar(value=str(self.runtime.state.rclick_food_burst_count_max))
        self.ui_vars["rclick_food_burst_count_min_var"] = rclick_food_burst_count_min
        self.ui_vars["rclick_food_burst_count_max_var"] = rclick_food_burst_count_max
        r2 = ctk.CTkFrame(panel, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=2)
        self.helpers["label_entry"](r2, "Burst clicks min:", rclick_food_burst_count_min, width=6).pack(side="left")
        self.helpers["label_entry"](r2, "Burst clicks max:", rclick_food_burst_count_max, width=6).pack(side="left", padx=(8, 0))

        rclick_food_burst_interval = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_food_burst_interval_ms)))
        click_delay_min = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_click_delay_min_ms)))
        self.ui_vars["rclick_food_burst_interval_var"] = rclick_food_burst_interval
        self.ui_vars["rclick_click_delay_min_var"] = click_delay_min
        r3 = ctk.CTkFrame(panel, fg_color="transparent")
        r3.pack(fill="x", padx=10, pady=2)
        self.helpers["label_entry"](r3, f"Burst interval ({unit}):", rclick_food_burst_interval, width=6).pack(side="left")
        self.helpers["label_entry"](r3, f"Click delay min ({unit}):", click_delay_min, width=6).pack(side="left", padx=(8, 0))

        click_delay_max = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_click_delay_max_ms)))
        post_settle = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_post_click_settle_ms)))
        self.ui_vars["rclick_click_delay_max_var"] = click_delay_max
        self.ui_vars["rclick_post_settle_ms_var"] = post_settle
        r4 = ctk.CTkFrame(panel, fg_color="transparent")
        r4.pack(fill="x", padx=10, pady=2)
        self.helpers["label_entry"](r4, f"Click delay max ({unit}):", click_delay_max, width=6).pack(side="left")
        self.helpers["label_entry"](r4, f"Post-click settle ({unit}):", post_settle, width=6).pack(side="left", padx=(8, 0))

        rclick_mode = ctk.StringVar(value=self.runtime.state.rclick_mode)
        rclick_food_min = ctk.StringVar(value=str(self.runtime.state.rclick_food_min_minutes))
        self.ui_vars["rclick_mode_var"] = rclick_mode
        self.ui_vars["rclick_food_min_var"] = rclick_food_min
        mode_row = ctk.CTkFrame(panel, fg_color="transparent")
        mode_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(mode_row, text="Mode:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", width=150, anchor="w").pack(side="left")
        mode_menu = ctk.CTkOptionMenu(mode_row, values=["timer", "food"], variable=rclick_mode,
                                       fg_color="#1a1a1a", button_color="#0a84ff",
                                       dropdown_fg_color="#252525", dropdown_text_color="#e8e8e8",
                                       dropdown_hover_color="#0a84ff")
        mode_menu.pack(side="left", padx=4)

        self.rclick_food_mode_container = ctk.CTkFrame(panel, fg_color="transparent")
        self.rclick_food_mode_container.pack(fill="x", padx=10)
        self.helpers["label_entry"](self.rclick_food_mode_container, "Min food timer (minutes):", rclick_food_min, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Burst interval ({unit}):", rclick_food_burst_interval, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Click delay min ({unit}):", click_delay_min, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Click delay max ({unit}):", click_delay_max, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Post-click settle ({unit}):", post_settle, width=6)

        rclick_mode.trace_add("write", self._update_rclick_mode_controls)
        self._update_rclick_mode_controls()

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(fill="x", padx=10, pady=(6, 8))
        self.helpers["btn"](buttons, "▶  Start", self.services["rclick_service"].start, "#30d158").pack(side="left", expand=True, fill="x", padx=2)
        self.helpers["btn"](buttons, "⏹  Stop", self.services["rclick_service"].stop, "#ff453a").pack(side="left", expand=True, fill="x", padx=2)

    def _update_afk_min(self, *_args) -> None:
        try:
            self.runtime.state.afk_min_ms = self.helpers["display_to_ms"](float(self.ui_vars["afk_min_var"].get()))
        except ValueError:
            pass

    def _update_afk_max(self, *_args) -> None:
        try:
            self.runtime.state.afk_max_ms = self.helpers["display_to_ms"](float(self.ui_vars["afk_max_var"].get()))
        except ValueError:
            pass

    def _update_rclick_min(self, *_args) -> None:
        try:
            self.runtime.state.rclick_min_ms = self.helpers["display_to_ms"](float(self.ui_vars["rclick_min_var"].get()))
        except ValueError:
            pass

    def _update_rclick_max(self, *_args) -> None:
        try:
            self.runtime.state.rclick_max_ms = self.helpers["display_to_ms"](float(self.ui_vars["rclick_max_var"].get()))
        except ValueError:
            pass

    def _update_rclick_mode_controls(self, *_args) -> None:
        mode_var = self.ui_vars.get("rclick_mode_var")
        mode = str(mode_var.get()).strip().lower() if mode_var is not None else "timer"
        if self.rclick_food_mode_container is None:
            return
        if mode == "food":
            self.rclick_food_mode_container.pack(fill="x", padx=10)
        else:
            self.rclick_food_mode_container.pack_forget()

    def record_rclick_pos(self) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            self.runtime.state.rclick_pos = pos
            self.runtime.ui.log(f"Right-click pos: {pos}")
            self.runtime.ui.set_status(f"Pos: {pos}", "#30d158")
            if self.pos_label:
                self.pos_label.configure(text=f"Pos: {pos[0]}, {pos[1]}")

        self.services["position_capture"].capture(on_done, "right-click target")

    def add_job(self) -> None:
        self.runtime.state.job_counter += 1
        job = HotkeyJob(job_id=self.runtime.state.job_counter)
        self.runtime.state.jobs.append(job)
        self._build_job_row(job)

    def _build_job_row(self, job: HotkeyJob) -> None:
        if self.jobs_frame is None:
            return
        outer = ctk.CTkFrame(self.jobs_frame, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        outer.pack(fill="x", pady=4, padx=2)
        outer._vars = {}
        job.row_frame = outer

        ctk.CTkLabel(outer, text=f"Job #{job.job_id}", font=ctk.CTkFont(size=10, weight="bold"),
                      text_color="#5ac8fa", anchor="w").pack(padx=8, pady=(4, 0))

        row1 = ctk.CTkFrame(outer, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(row1, text="Key:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8").pack(side="left")
        key_var = ctk.StringVar(value=job.key)
        menu = ctk.CTkOptionMenu(row1, values=[f"F{i}" for i in range(1, 13)] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
                                  variable=key_var, fg_color="#1a1a1a", button_color="#0a84ff",
                                  dropdown_fg_color="#252525", dropdown_text_color="#e8e8e8",
                                  dropdown_hover_color="#0a84ff", width=70)
        menu.pack(side="left", padx=6)
        outer._vars["key"] = key_var

        unit = self.helpers["get_unit_label"]()
        for label, name, default in [
            (f"Min ({unit}):", "min", str(self.helpers["ms_to_display"](job.min_ms))),
            (f"Max ({unit}):", "max", str(self.helpers["ms_to_display"](job.max_ms))),
        ]:
            ctk.CTkLabel(row1, text=label, font=ctk.CTkFont(size=11, weight="bold"),
                          text_color="#e8e8e8").pack(side="left", padx=(8, 0))
            value = ctk.StringVar(value=default)
            entry = ctk.CTkEntry(row1, textvariable=value, width=70, fg_color="#1a1a1a",
                                  border_color="#3a3a3a", text_color="#e8e8e8")
            entry.pack(side="left", padx=4)
            outer._vars[name] = value

        ctk.CTkLabel(row1, text="Min mana:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8").pack(side="left", padx=(8, 0))
        min_mana_var = ctk.StringVar(value=str(job.min_mana))
        ctk.CTkEntry(row1, textvariable=min_mana_var, width=70, fg_color="#1a1a1a",
                      border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=4)
        outer._vars["min_mana"] = min_mana_var
        ctk.CTkLabel(row1, text="Max mana:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8").pack(side="left", padx=(8, 0))
        max_mana_var = ctk.StringVar(value=str(job.max_mana))
        ctk.CTkEntry(row1, textvariable=max_mana_var, width=70, fg_color="#1a1a1a",
                      border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=4)
        outer._vars["max_mana"] = max_mana_var
        indicator = ctk.CTkLabel(row1, text="●", font=ctk.CTkFont(size=14, weight="bold"),
                                  text_color="#777777")
        indicator.pack(side="right", padx=4)
        outer._indicator = indicator

        row2 = ctk.CTkFrame(outer, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=2)
        burst_var = ctk.BooleanVar(value=job.burst_enabled)
        outer._vars["burst"] = burst_var
        ctk.CTkCheckBox(row2, text="Burst", variable=burst_var, fg_color="#0a84ff",
                         text_color="#e8e8e8", font=ctk.CTkFont(size=11)).pack(side="left")
        for label, name, default in [
            ("Chance%:", "b_chance", str(int(job.burst_chance * 100))),
            ("Cnt min:", "b_cmin", str(job.burst_cnt_min)),
            ("Cnt max:", "b_cmax", str(job.burst_cnt_max)),
            (f"Int ({unit}):", "b_int", str(self.helpers["ms_to_display"](job.burst_int_ms))),
        ]:
            ctk.CTkLabel(row2, text=label, font=ctk.CTkFont(size=10), text_color="#777777").pack(side="left", padx=(8, 0))
            value = ctk.StringVar(value=default)
            ctk.CTkEntry(row2, textvariable=value, width=50, fg_color="#1a1a1a",
                          border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=2)
            outer._vars[name] = value

        row3 = ctk.CTkFrame(outer, fg_color="transparent")
        row3.pack(fill="x", padx=8, pady=2)
        focus_var = ctk.BooleanVar(value=job.use_focus)
        restore_var = ctk.BooleanVar(value=job.restore_focus)
        outer._vars["focus"] = focus_var
        outer._vars["restore"] = restore_var
        ctk.CTkCheckBox(row3, text="Focus window:", variable=focus_var, fg_color="#0a84ff",
                         text_color="#e8e8e8", font=ctk.CTkFont(size=11)).pack(side="left")
        window_var = ctk.StringVar(value=job.window_name)
        outer._vars["win_name"] = window_var
        ctk.CTkEntry(row3, textvariable=window_var, width=150, fg_color="#1a1a1a",
                      border_color="#3a3a3a", text_color="#e8e8e8").pack(side="left", padx=4)
        ctk.CTkCheckBox(row3, text="Restore focus", variable=restore_var, fg_color="#0a84ff",
                         text_color="#777777", font=ctk.CTkFont(size=10)).pack(side="left", padx=6)
        if not HAS_WIN32:
            ctk.CTkLabel(row3, text="(pywin32 missing)", font=ctk.CTkFont(size=10),
                          text_color="#ff453a").pack(side="left")

        row4 = ctk.CTkFrame(outer, fg_color="transparent")
        row4.pack(fill="x", padx=8, pady=(4, 6))
        self.helpers["btn"](row4, "▶  Start", lambda j=job: self.start_job(j), "#30d158").pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](row4, "⏹  Stop", lambda j=job: self.services["job_service"].stop_job(j), "#ff453a").pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](row4, "✕  Remove", lambda j=job: self.remove_job(j), "#ff9f0a").pack(side="left", padx=2, expand=True, fill="x")

    def start_job(self, job: HotkeyJob) -> None:
        self.read_job_vars(job)
        self.services["job_service"].start_job(job)

    def read_job_vars(self, job: HotkeyJob) -> None:
        vars_map = job.row_frame._vars
        try:
            job.key = vars_map["key"].get()
            job.min_ms = self.helpers["display_to_ms"](float(vars_map["min"].get()))
            job.max_ms = self.helpers["display_to_ms"](float(vars_map["max"].get()))
            job.min_mana = max(0, int(vars_map["min_mana"].get()))
            job.max_mana = max(job.min_mana, int(vars_map["max_mana"].get()))
            job.burst_enabled = vars_map["burst"].get()
            job.burst_chance = min(1.0, max(0.0, int(vars_map["b_chance"].get()) / 100.0))
            job.burst_cnt_min = max(0, int(vars_map["b_cmin"].get()))
            job.burst_cnt_max = max(job.burst_cnt_min, int(vars_map["b_cmax"].get()))
            job.burst_int_ms = self.helpers["display_to_ms"](float(vars_map["b_int"].get()))
            job.use_focus = vars_map["focus"].get()
            job.window_name = vars_map["win_name"].get()
            job.restore_focus = vars_map["restore"].get()
        except (ValueError, AttributeError):
            pass

    def root_poll_settings_now(self) -> None:
        for job in self.runtime.state.jobs:
            if hasattr(job, "row_frame") and job.row_frame:
                self.read_job_vars(job)

    def remove_job(self, job: HotkeyJob) -> None:
        self.services["job_service"].stop_job(job)
        if job in self.runtime.state.jobs:
            self.runtime.state.jobs.remove(job)
        if job.row_frame:
            job.row_frame.destroy()

    def poll_settings(self, state) -> None:
        state.afk_min_ms = self.helpers["get_ui_ms"]("afk_min_var", state.afk_min_ms)
        state.afk_max_ms = self.helpers["get_ui_ms"]("afk_max_var", state.afk_max_ms)
        state.rclick_min_ms = self.helpers["get_ui_ms"]("rclick_min_var", state.rclick_min_ms)
        state.rclick_max_ms = self.helpers["get_ui_ms"]("rclick_max_var", state.rclick_max_ms)
        if "rclick_mode_var" in self.ui_vars:
            state.rclick_mode = str(self.ui_vars["rclick_mode_var"].get()).strip().lower() or "timer"
        state.rclick_require_food = False
        if state.rclick_mode == "food":
            raw_food_minutes = self.ui_vars["rclick_food_min_var"].get() if "rclick_food_min_var" in self.ui_vars else state.rclick_food_min_minutes
            state.rclick_food_min_minutes = self.helpers["normalize_food_threshold_minutes"](raw_food_minutes, state.rclick_food_min_minutes)
            if "rclick_food_min_var" in self.ui_vars:
                self.ui_vars["rclick_food_min_var"].set(str(state.rclick_food_min_minutes))
        state.rclick_food_burst_count_min = max(1, self.helpers["get_ui_int"]("rclick_food_burst_count_min_var", state.rclick_food_burst_count_min))
        state.rclick_food_burst_count_max = max(state.rclick_food_burst_count_min, self.helpers["get_ui_int"]("rclick_food_burst_count_max_var", state.rclick_food_burst_count_max))
        state.rclick_food_burst_interval_ms = max(50, self.helpers["get_ui_ms"]("rclick_food_burst_interval_var", state.rclick_food_burst_interval_ms))
        state.rclick_click_delay_min_ms = max(100, self.helpers["get_ui_ms"]("rclick_click_delay_min_var", state.rclick_click_delay_min_ms))
        state.rclick_click_delay_max_ms = max(state.rclick_click_delay_min_ms, self.helpers["get_ui_ms"]("rclick_click_delay_max_var", state.rclick_click_delay_max_ms))
        state.rclick_post_click_settle_ms = max(100, self.helpers["get_ui_ms"]("rclick_post_settle_ms_var", state.rclick_post_click_settle_ms))
        state.rclick_jitter = max(0, self.helpers["get_ui_int"]("rclick_jitter_var", state.rclick_jitter))

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.pos_label:
            self.pos_label.configure(text=f"Pos: {state.rclick_pos[0]}, {state.rclick_pos[1]}")
        self._update_rclick_mode_controls()
        if self.jobs_frame:
            for child in list(self.jobs_frame.winfo_children()):
                child.destroy()
        for job in state.jobs:
            self._build_job_row(job)
