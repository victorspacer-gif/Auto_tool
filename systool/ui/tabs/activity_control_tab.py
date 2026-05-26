"""Activity control tab UI for SystemMonitor."""

from __future__ import annotations

import logging
import tkinter as tk

from ...models import HotkeyJob
from ...runtime import HAS_WIN32
from ...theme import BG, BLUE, BODY, BOLD, FG, GREEN, MONO, MUTED, ORANGE, PANEL, RED, SMALL, SMALL_B, TEAL

logger = logging.getLogger(__name__)


class ActivityControlTab:
    """Owns the activity control tab UI and tab-local behavior."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.jobs_frame: tk.Frame | None = None
        self.pos_label: tk.Label | None = None
        self.rclick_food_mode_container: tk.Frame | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame, threshold=1360)

        jobs_frame = tk.LabelFrame(left, text=" Hotkey Tasks - independent threads ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=6, padx=8)
        jobs_frame.pack(fill="both", expand=True)
        top = tk.Frame(jobs_frame, bg=PANEL)
        top.pack(fill="x", pady=(0, 6))
        self.helpers["btn"](top, "+ Add Job", self.add_job, BLUE).pack(side="left", padx=2)
        tk.Label(top, text="Enable 'Focus window' to direct keys to a selected app window", font=SMALL, fg=MUTED, bg=PANEL).pack(side="left", padx=10)
        canvas = tk.Canvas(jobs_frame, bg=PANEL, highlightthickness=0)
        scrollbar = tk.Scrollbar(jobs_frame, orient="vertical", command=canvas.yview)
        self.jobs_frame = tk.Frame(canvas, bg=PANEL)
        self.jobs_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.jobs_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.helpers["register_mousewheel_target"](jobs_frame, canvas)
        self.helpers["register_mousewheel_target"](canvas, canvas)
        self.helpers["register_mousewheel_target"](self.jobs_frame, canvas)

        self._build_afk_panel(right)
        self._build_right_click_panel(right)

    def _build_afk_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(parent, text=" Activity Monitor ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        panel.pack(fill="x", pady=(0, 8))
        self.helpers["register_module_indicator"](panel, "afk", self.runtime.state.afk_active)
        afk_min = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.afk_min_ms)))
        afk_max = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.afk_max_ms)))
        self.ui_vars["afk_min_var"] = afk_min
        self.ui_vars["afk_max_var"] = afk_max
        afk_min.trace_add("write", self._update_afk_min)
        afk_max.trace_add("write", self._update_afk_max)
        unit = self.helpers["get_unit_label"]()
        self.helpers["label_entry"](panel, f"Timer Min ({unit}):", afk_min)
        self.helpers["label_entry"](panel, f"Timer Max ({unit}):", afk_max)
        tk.Label(panel, text="Ctrl held down -> arrow press -> Ctrl released", font=SMALL, fg=MUTED, bg=PANEL).pack(anchor="w")
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 0))
        self.helpers["btn"](buttons, "Start", self.services["afk_service"].start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self.helpers["btn"](buttons, "Stop", self.services["afk_service"].stop, RED).pack(side="left", expand=True, fill="x", padx=2)

    def _build_right_click_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(parent, text=" Right-Click Monitor ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        panel.pack(fill="x", pady=(0, 8))
        self.helpers["register_module_indicator"](panel, "rclick", self.runtime.state.rclick_active)
        self.pos_label = tk.Label(panel, text="Pos: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.pos_label.pack(anchor="w", pady=(0, 4))
        self.helpers["btn"](panel, "Record Position", self.record_rclick_pos, BLUE).pack(fill="x", pady=(0, 6))

        unit = self.helpers["get_unit_label"]()
        rclick_jitter = tk.StringVar(value=str(self.runtime.state.rclick_jitter))
        self.ui_vars["rclick_jitter_var"] = rclick_jitter
        row1 = tk.Frame(panel, bg=PANEL)
        row1.pack(fill="x", pady=2)
        self.helpers["label_entry"](row1, "Click jitter (px +/-):", rclick_jitter, width=5).pack(side="left")

        min_var = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_min_ms)))
        max_var = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_max_ms)))
        self.ui_vars["rclick_min_var"] = min_var
        self.ui_vars["rclick_max_var"] = max_var
        min_var.trace_add("write", self._update_rclick_min)
        max_var.trace_add("write", self._update_rclick_max)
        row2 = tk.Frame(panel, bg=PANEL)
        row2.pack(fill="x", pady=2)
        self.helpers["label_entry"](row2, f"Timer Min ({unit}):", min_var).pack(side="left")
        self.helpers["label_entry"](row2, f"Timer Max ({unit}):", max_var).pack(side="left", padx=(8, 0))

        rclick_food_burst_count_min = tk.StringVar(value=str(self.runtime.state.rclick_food_burst_count_min))
        rclick_food_burst_count_max = tk.StringVar(value=str(self.runtime.state.rclick_food_burst_count_max))
        self.ui_vars["rclick_food_burst_count_min_var"] = rclick_food_burst_count_min
        self.ui_vars["rclick_food_burst_count_max_var"] = rclick_food_burst_count_max
        row3 = tk.Frame(panel, bg=PANEL)
        row3.pack(fill="x", pady=2)
        self.helpers["label_entry"](row3, "Burst clicks min:", rclick_food_burst_count_min, width=6).pack(side="left")
        self.helpers["label_entry"](row3, "Burst clicks max:", rclick_food_burst_count_max, width=6).pack(side="left", padx=(8, 0))

        rclick_food_burst_interval = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_food_burst_interval_ms)))
        click_delay_min = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_click_delay_min_ms)))
        self.ui_vars["rclick_food_burst_interval_var"] = rclick_food_burst_interval
        self.ui_vars["rclick_click_delay_min_var"] = click_delay_min
        row4 = tk.Frame(panel, bg=PANEL)
        row4.pack(fill="x", pady=2)
        self.helpers["label_entry"](row4, f"Burst interval ({unit}):", rclick_food_burst_interval, width=6).pack(side="left")
        self.helpers["label_entry"](row4, f"Click delay min ({unit}):", click_delay_min, width=6).pack(side="left", padx=(8, 0))

        click_delay_max = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_click_delay_max_ms)))
        post_settle = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rclick_post_click_settle_ms)))
        self.ui_vars["rclick_click_delay_max_var"] = click_delay_max
        self.ui_vars["rclick_post_settle_ms_var"] = post_settle
        row5 = tk.Frame(panel, bg=PANEL)
        row5.pack(fill="x", pady=2)
        self.helpers["label_entry"](row5, f"Click delay max ({unit}):", click_delay_max, width=6).pack(side="left")
        self.helpers["label_entry"](row5, f"Post-click settle ({unit}):", post_settle, width=6).pack(side="left", padx=(8, 0))

        rclick_mode = tk.StringVar(value=self.runtime.state.rclick_mode)
        rclick_food_min = tk.StringVar(value=str(self.runtime.state.rclick_food_min_minutes))
        self.ui_vars["rclick_mode_var"] = rclick_mode
        self.ui_vars["rclick_food_min_var"] = rclick_food_min
        mode_row = tk.Frame(panel, bg=PANEL)
        mode_row.pack(fill="x", pady=2)
        tk.Label(mode_row, text="Mode:", font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        mode_menu = tk.OptionMenu(mode_row, rclick_mode, "timer", "food")
        mode_menu.config(font=BODY, bg=PANEL, fg=FG, activebackground=BLUE, bd=0, relief="flat", highlightthickness=0)
        mode_menu["menu"].config(bg=PANEL, fg=FG, activebackground=BLUE, activeforeground="white")
        mode_menu.pack(side="left", padx=4)

        self.rclick_food_mode_container = tk.Frame(panel, bg=PANEL)
        self.rclick_food_mode_container.pack(fill="x")
        self.helpers["label_entry"](self.rclick_food_mode_container, "Min food timer (minutes):", rclick_food_min, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Burst interval ({unit}):", rclick_food_burst_interval, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Click delay min ({unit}):", click_delay_min, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Click delay max ({unit}):", click_delay_max, width=6)
        self.helpers["label_entry"](self.rclick_food_mode_container, f"Post-click settle ({unit}):", post_settle, width=6)

        rclick_mode.trace_add("write", self._update_rclick_mode_controls)
        self._update_rclick_mode_controls()

        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", pady=(6, 0))
        self.helpers["btn"](buttons, "Start", self.services["rclick_service"].start, GREEN).pack(side="left", expand=True, fill="x", padx=2)
        self.helpers["btn"](buttons, "Stop", self.services["rclick_service"].stop, RED).pack(side="left", expand=True, fill="x", padx=2)

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
        show_food_controls = mode == "food"
        if self.rclick_food_mode_container is None:
            return
        if show_food_controls and not self.rclick_food_mode_container.winfo_manager():
            self.rclick_food_mode_container.pack(fill="x")
        elif not show_food_controls and self.rclick_food_mode_container.winfo_manager():
            self.rclick_food_mode_container.pack_forget()

    def record_rclick_pos(self) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            self.runtime.state.rclick_pos = pos
            self.runtime.ui.log(f"Right-click pos: {pos}")
            self.runtime.ui.set_status(f"Pos: {pos}", GREEN)
            if self.pos_label:
                self.pos_label.config(text=f"Pos: {pos[0]}, {pos[1]}")

        self.services["position_capture"].capture(on_done, "right-click target")

    def add_job(self) -> None:
        self.runtime.state.job_counter += 1
        job = HotkeyJob(job_id=self.runtime.state.job_counter)
        self.runtime.state.jobs.append(job)
        self._build_job_row(job)

    def _build_job_row(self, job: HotkeyJob) -> None:
        if self.jobs_frame is None:
            return
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

        unit = self.helpers["get_unit_label"]()
        for label, name, default in [
            (f"Min ({unit}):", "min", str(self.helpers["ms_to_display"](job.min_ms))),
            (f"Max ({unit}):", "max", str(self.helpers["ms_to_display"](job.max_ms))),
        ]:
            tk.Label(row1, text=label, font=BOLD, fg=FG, bg=PANEL).pack(side="left", padx=(8, 0))
            value = tk.StringVar(value=default)
            self.helpers["entry"](row1, value, 6).pack(side="left", padx=4)
            outer._vars[name] = value

        tk.Label(row1, text="Min mana:", font=BOLD, fg=FG, bg=PANEL).pack(side="left", padx=(8, 0))
        min_mana_var = tk.StringVar(value=str(job.min_mana))
        self.helpers["entry"](row1, min_mana_var, 6).pack(side="left", padx=4)
        outer._vars["min_mana"] = min_mana_var
        tk.Label(row1, text="Max mana:", font=BOLD, fg=FG, bg=PANEL).pack(side="left", padx=(8, 0))
        max_mana_var = tk.StringVar(value=str(job.max_mana))
        self.helpers["entry"](row1, max_mana_var, 6).pack(side="left", padx=4)
        outer._vars["max_mana"] = max_mana_var
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
            (f"Int ({unit}):", "b_int", str(self.helpers["ms_to_display"](job.burst_int_ms))),
        ]:
            tk.Label(row2, text=label, font=SMALL, fg=MUTED, bg=PANEL).pack(side="left", padx=(8, 0))
            value = tk.StringVar(value=default)
            self.helpers["entry"](row2, value, 4).pack(side="left", padx=2)
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
        self.helpers["btn"](row4, "Start", lambda j=job: self.start_job(j), GREEN).pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](row4, "Stop", lambda j=job: self.services["job_service"].stop_job(j), RED).pack(side="left", padx=2, expand=True, fill="x")
        self.helpers["btn"](row4, "Remove", lambda j=job: self.remove_job(j), ORANGE).pack(side="left", padx=2, expand=True, fill="x")

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
        except (ValueError, tk.TclError):
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
            self.pos_label.config(text=f"Pos: {state.rclick_pos[0]}, {state.rclick_pos[1]}")
        self._update_rclick_mode_controls()
        if self.jobs_frame:
            for child in list(self.jobs_frame.winfo_children()):
                child.destroy()
        for job in state.jobs:
            self._build_job_row(job)
