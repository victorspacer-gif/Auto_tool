"""CaveBot tab UI — waypoint editor, chase target, auto looter controls.

Adapted from the TibiaAuto12 CaveBot module pattern with full waypoint
management (add/remove/load/reset), monster targeting configuration, and
companion module controls.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, simpledialog

logger = logging.getLogger(__name__)

from ...services.cavebot import CaveBotService
from ...services.chase_target import ChaseTargetService
from ...services.auto_looter import AutoLooterService
from ...theme import BG, BLUE, BOLD, FG, GREEN, MONO, MUTED, ORANGE, PANEL, RED, SMALL, SMALL_B, TEAL, PURPLE


# Waypoint mark names (matching TibiaAuto12)
MARK_NAMES = [
    "CheckMark", "QuestionMark", "ExclimationMark", "Star", "Cross",
    "Church", "Mouth", "Shovel", "Sword", "Flag",
    "Lock", "Bag", "Skull", "Money", "ArrowUp",
    "ArrowDown", "ArrowRight", "ArrowLeft", "Above", "Bellow",
]

WAYPOINT_TYPES = {1: "Walk", 2: "Rope", 3: "Shovel"}


class CaveBotTab:
    """Owns the CaveBot tab UI with all sub-module controls."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars
        self.cavebot_service: CaveBotService = services.get("cavebot_service")
        self.chase_target_service: ChaseTargetService | None = services.get("chase_target_service")
        self.auto_looter_service: AutoLooterService | None = services.get("auto_looter_service")

        # UI state vars
        self._script_var = tk.StringVar(value=runtime.state.cavebot.script_name)
        self._stand_var = tk.StringVar(value=str(runtime.state.cavebot.stand_seconds))
        self._mark_var = tk.IntVar(value=1)
        self._wp_type_var = tk.IntVar(value=1)
        self._walk_var = tk.BooleanVar(value=runtime.state.cavebot.walking_enabled)
        self._loot_var = tk.BooleanVar(value=runtime.state.cavebot.looting_enabled)
        self._debug_var = tk.BooleanVar(value=runtime.state.cavebot.walk_for_debug)
        self._follow_var = tk.BooleanVar(value=runtime.state.cavebot.follow_mode)

        # Script waypoint display widgets
        self._script_listbox: tk.Listbox | None = None
        self._wp_listbox: tk.Listbox | None = None
        self._prev_wp_label: tk.Label | None = None
        self._curr_wp_label: tk.Label | None = None
        self._next_wp_label: tk.Label | None = None
        self._prev_type_label: tk.Label | None = None
        self._curr_type_label: tk.Label | None = None
        self._next_type_label: tk.Label | None = None

        # SQM list
        self._sqm_listbox: tk.Listbox | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        # ═══════════════════════════════════════════════════════════
        # LEFT COLUMN — Script Manager + Waypoint Editor + Controls
        # ═══════════════════════════════════════════════════════════

        # ── Script Manager ────────────────────────────────────────
        script_panel = tk.LabelFrame(
            left, text=" 📜  Script Manager ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10
        )
        script_panel.pack(fill="x", pady=(0, 6))
        self.helpers["register_module_indicator"](script_panel, "cavebot", self.runtime.state.cavebot.active)

        name_row = tk.Frame(script_panel, bg=PANEL)
        name_row.pack(fill="x", pady=(0, 4))
        tk.Label(name_row, text="Script:", font=BOLD, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        script_entry = tk.Entry(
            name_row, textvariable=self._script_var, font=MONO, bg=BG, fg=FG,
            relief="flat", bd=2, width=18
        )
        script_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_row = tk.Frame(script_panel, bg=PANEL)
        btn_row.pack(fill="x", pady=(0, 4))
        self.helpers["btn"](btn_row, "🔄 List", self._refresh_script_list, BLUE).pack(side="left", padx=1)
        self.helpers["btn"](btn_row, "➕ New", self._new_script, GREEN).pack(side="left", padx=1)
        self.helpers["btn"](btn_row, "🗑 Delete", self._delete_script, RED).pack(side="left", padx=1)
        self.helpers["btn"](btn_row, "📂 Load", self._load_script_to_ui, PURPLE).pack(side="left", padx=1)

        list_frame = tk.Frame(script_panel, bg=PANEL, height=80)
        list_frame.pack(fill="x")
        self._script_listbox = tk.Listbox(
            list_frame, bg=BG, fg=FG, font=MONO, selectbackground=BLUE,
            selectforeground="white", relief="flat", bd=2, height=4
        )
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self._script_listbox.yview)
        self._script_listbox.configure(yscrollcommand=scrollbar.set)
        self._script_listbox.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._script_listbox.bind("<<ListboxSelect>>", self._on_script_select)
        self._refresh_script_list()

        # ── Waypoint Editor ───────────────────────────────────────
        wp_panel = tk.LabelFrame(
            left, text=" 🗺️  Waypoint Editor ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10
        )
        wp_panel.pack(fill="x", pady=(0, 6))

        # Mark selector row
        mark_row = tk.Frame(wp_panel, bg=PANEL)
        mark_row.pack(fill="x", pady=(0, 4))
        tk.Label(mark_row, text="Mark:", font=BOLD, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        mark_dropdown = tk.OptionMenu(mark_row, self._mark_var, *range(1, len(MARK_NAMES) + 1))
        mark_dropdown.configure(bg=BG, fg=FG, font=MONO, relief="flat", bd=1, highlightthickness=0)
        mark_dropdown.pack(side="left", padx=(0, 8))

        tk.Label(mark_row, text="Type:", font=BOLD, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        type_dropdown = tk.OptionMenu(mark_row, self._wp_type_var, *[1, 2, 3])
        type_dropdown.configure(bg=BG, fg=FG, font=MONO, relief="flat", bd=1, highlightthickness=0)
        type_dropdown.pack(side="left", padx=(0, 8))

        tk.Label(mark_row, text=f" = {MARK_NAMES[0]} / Walk", font=SMALL, bg=PANEL, fg=MUTED).pack(side="left")

        # Previous / Current / Next waypoint display
        nav_frame = tk.Frame(wp_panel, bg=PANEL)
        nav_frame.pack(fill="x", pady=(0, 4))
        for col, label_text in [("Prev", 0), ("Curr", 1), ("Next", 2)]:
            col_frame = tk.Frame(nav_frame, bg=PANEL)
            col_frame.pack(side="left", fill="x", expand=True, padx=2)
            tk.Label(col_frame, text=label_text, font=SMALL_B, bg=PANEL, fg=TEAL).pack()
            lbl = tk.Label(col_frame, text="—", font=MONO, bg=PANEL, fg=FG)
            lbl.pack()
            tlbl = tk.Label(col_frame, text="", font=SMALL, bg=PANEL, fg=MUTED)
            tlbl.pack()
            if label_text == "Prev":
                self._prev_wp_label = lbl
                self._prev_type_label = tlbl
            elif label_text == "Curr":
                self._curr_wp_label = lbl
                self._curr_type_label = tlbl
            else:
                self._next_wp_label = lbl
                self._next_type_label = tlbl

        # Actions
        wp_btn_row = tk.Frame(wp_panel, bg=PANEL)
        wp_btn_row.pack(fill="x", pady=(0, 4))
        self.helpers["btn"](wp_btn_row, "➕ Add WP", self._add_waypoint, GREEN).pack(side="left", padx=1)
        self.helpers["btn"](wp_btn_row, "✕ Remove WP", self._remove_waypoint, ORANGE).pack(side="left", padx=1)
        self.helpers["btn"](wp_btn_row, "⟳ Reset Marks", self._reset_waypoints, BLUE).pack(side="left", padx=1)
        self.helpers["btn"](wp_btn_row, "<< Prev", self._prev_waypoint, PURPLE).pack(side="left", padx=1)
        self.helpers["btn"](wp_btn_row, "Next >>", self._next_waypoint, PURPLE).pack(side="left", padx=1)

        # ── Waypoint list ─────────────────────────────────────────
        wp_list_frame = tk.Frame(wp_panel, bg=PANEL, height=80)
        wp_list_frame.pack(fill="x")
        self._wp_listbox = tk.Listbox(
            wp_list_frame, bg=BG, fg=FG, font=MONO, selectbackground=BLUE,
            selectforeground="white", relief="flat", bd=2, height=4
        )
        wp_scroll = tk.Scrollbar(wp_list_frame, orient="vertical", command=self._wp_listbox.yview)
        self._wp_listbox.configure(yscrollcommand=wp_scroll.set)
        self._wp_listbox.pack(side="left", fill="x", expand=True)
        wp_scroll.pack(side="right", fill="y")

        # ── CaveBot Controls ──────────────────────────────────────
        ctrl_panel = tk.LabelFrame(
            left, text=" 🎮  CaveBot Controls ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10
        )
        ctrl_panel.pack(fill="x", pady=(0, 6))

        ctrl_row = tk.Frame(ctrl_panel, bg=PANEL)
        ctrl_row.pack(fill="x", pady=(0, 4))
        self.helpers["btn"](ctrl_row, "▶ Start CaveBot", self._start_cavebot, GREEN).pack(side="left", padx=2)
        self.helpers["btn"](ctrl_row, "⏹ Stop CaveBot", self._stop_cavebot, RED).pack(side="left", padx=2)

        opts_row = tk.Frame(ctrl_panel, bg=PANEL)
        opts_row.pack(fill="x", pady=(0, 4))
        tk.Label(opts_row, text="Stand (s):", font=SMALL, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        tk.Entry(opts_row, textvariable=self._stand_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=4).pack(side="left", padx=(0, 8))
        for var, text in [(self._walk_var, "Walk"), (self._loot_var, "Loot"),
                          (self._debug_var, "Debug"), (self._follow_var, "Follow")]:
            cb = tk.Checkbutton(opts_row, text=text, variable=var, bg=PANEL, fg=FG,
                                selectcolor=BG, font=SMALL, command=self._sync_controls)
            cb.pack(side="left", padx=2)

        # ═══════════════════════════════════════════════════════════
        # RIGHT COLUMN — Chase Target + Auto Looter
        # ═══════════════════════════════════════════════════════════

        # ── Chase Target ──────────────────────────────────────────
        chase_panel = tk.LabelFrame(
            right, text=" 🎯  Chase Target ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10
        )
        chase_panel.pack(fill="x", pady=(0, 6))
        self.helpers["register_module_indicator"](chase_panel, "chase_target", self.runtime.state.chase_target.active)

        chase_btn_row = tk.Frame(chase_panel, bg=PANEL)
        chase_btn_row.pack(fill="x", pady=(0, 4))
        self.helpers["btn"](chase_btn_row, "▶ Start Chase", self._start_chase_target, GREEN).pack(side="left", padx=1)
        self.helpers["btn"](chase_btn_row, "⏹ Stop Chase", self._stop_chase_target, RED).pack(side="left", padx=1)

        # Monster config
        chase_state = self.runtime.state.chase_target
        monster_names = chase_state.monster_names or ["", "", "", ""]
        while len(monster_names) < 4:
            monster_names.append("")
        self._chase_monster_entries: list[tk.Entry] = []
        for i in range(4):
            row = tk.Frame(chase_panel, bg=PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"M{i+1}:", font=SMALL_B, bg=PANEL, fg=FG).pack(side="left", padx=(0, 2))
            var = tk.StringVar(value=monster_names[i])
            entry = tk.Entry(row, textvariable=var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=14)
            entry.pack(side="left", padx=(0, 4))
            self._chase_monster_entries.append(entry)

        # Attack key + scan interval
        chase_opts = tk.Frame(chase_panel, bg=PANEL)
        chase_opts.pack(fill="x", pady=(0, 4))
        self._chase_key_var = tk.StringVar(value=chase_state.attack_key)
        tk.Label(chase_opts, text="Key:", font=SMALL, bg=PANEL, fg=FG).pack(side="left", padx=(0, 2))
        tk.Entry(chase_opts, textvariable=self._chase_key_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=5).pack(side="left", padx=(0, 8))
        tk.Label(chase_opts, text="Interval (ms):", font=SMALL, bg=PANEL, fg=FG).pack(side="left", padx=(0, 2))
        self._chase_interval_var = tk.StringVar(value=str(chase_state.scan_interval_ms))
        tk.Entry(chase_opts, textvariable=self._chase_interval_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=5).pack(side="left")

        # Mode toggles
        chase_toggles = tk.Frame(chase_panel, bg=PANEL)
        chase_toggles.pack(fill="x", pady=(0, 4))
        self._chase_follow_var = tk.BooleanVar(value=chase_state.follow_mode)
        cb = tk.Checkbutton(chase_toggles, text="Follow", variable=self._chase_follow_var, bg=PANEL, fg=FG,
                            selectcolor=BG, font=SMALL)
        cb.pack(side="left", padx=2)

        # Battle list X for chase
        chase_battle = tk.Frame(chase_panel, bg=PANEL)
        chase_battle.pack(fill="x", pady=(0, 4))
        self._chase_battle_x_var = tk.StringVar(value=str(chase_state.battle_list_x))
        tk.Label(chase_battle, text="Battle X:", font=SMALL_B, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        tk.Entry(chase_battle, textvariable=self._chase_battle_x_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=6).pack(side="left", padx=(0, 4))
        self.helpers["btn"](chase_battle, "🎯 Record X", self._record_battle_list_x, PURPLE).pack(side="left", padx=2)

        # ── Auto Looter ───────────────────────────────────────────
        looter_panel = tk.LabelFrame(
            right, text=" 💰  Auto Looter ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10
        )
        looter_panel.pack(fill="x", pady=(0, 6))
        self.helpers["register_module_indicator"](looter_panel, "auto_looter", self.runtime.state.auto_looter.active)

        looter_btn_row = tk.Frame(looter_panel, bg=PANEL)
        looter_btn_row.pack(fill="x", pady=(0, 4))
        self.helpers["btn"](looter_btn_row, "▶ Start Looter", self._start_looter, GREEN).pack(side="left", padx=1)
        self.helpers["btn"](looter_btn_row, "⏹ Stop Looter", self._stop_looter, RED).pack(side="left", padx=1)
        self.helpers["btn"](looter_btn_row, "🔁 Loot Once", self._loot_once, BLUE).pack(side="left", padx=1)

        # SQM positions
        sqm_label = tk.Frame(looter_panel, bg=PANEL)
        sqm_label.pack(fill="x", pady=(0, 2))
        tk.Label(sqm_label, text="SQM Positions:", font=BOLD, bg=PANEL, fg=FG).pack(side="left")

        sqm_list_frame = tk.Frame(looter_panel, bg=PANEL, height=70)
        sqm_list_frame.pack(fill="x")
        self._looter_sqm_listbox = tk.Listbox(
            sqm_list_frame, bg=BG, fg=FG, font=MONO, selectbackground=BLUE,
            selectforeground="white", relief="flat", bd=2, height=3
        )
        sqm_scroll = tk.Scrollbar(sqm_list_frame, orient="vertical", command=self._looter_sqm_listbox.yview)
        self._looter_sqm_listbox.configure(yscrollcommand=sqm_scroll.set)
        self._looter_sqm_listbox.pack(side="left", fill="x", expand=True)
        sqm_scroll.pack(side="right", fill="y")

        sqm_btn_row = tk.Frame(looter_panel, bg=PANEL)
        sqm_btn_row.pack(fill="x", pady=(0, 4))
        self.helpers["btn"](sqm_btn_row, "➕ Add Pos", self._add_looter_sqm, BLUE).pack(side="left", padx=1)
        self.helpers["btn"](sqm_btn_row, "✕ Remove", self._remove_looter_sqm, ORANGE).pack(side="left", padx=1)
        self.helpers["btn"](sqm_btn_row, "🗑 Clear", self._clear_looter_sqm, RED).pack(side="left", padx=1)
        self.helpers["btn"](sqm_btn_row, "⬇ Copy from CaveBot", self._copy_sqm_from_cavebot, PURPLE).pack(side="left", padx=1)

        looter_opts = tk.Frame(looter_panel, bg=PANEL)
        looter_opts.pack(fill="x")
        self._looter_min_delay_var = tk.StringVar(value=str(self.runtime.state.auto_looter.loot_delay_min_ms))
        self._looter_max_delay_var = tk.StringVar(value=str(self.runtime.state.auto_looter.loot_delay_max_ms))
        tk.Label(looter_opts, text="Delay:", font=SMALL, bg=PANEL, fg=FG).pack(side="left", padx=(0, 2))
        tk.Entry(looter_opts, textvariable=self._looter_min_delay_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=4).pack(side="left", padx=(0, 2))
        tk.Label(looter_opts, text="–", font=SMALL, bg=PANEL, fg=FG).pack(side="left", padx=(0, 2))
        tk.Entry(looter_opts, textvariable=self._looter_max_delay_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=4).pack(side="left", padx=(0, 2))

        # Initial refresh of lists
        self._refresh_sqm_list("cavebot")
        self._refresh_sqm_list("looter")

    # ═══════════════════════════════════════════════════════════════
    # Script Management
    # ═══════════════════════════════════════════════════════════════

    def _refresh_script_list(self) -> None:
        if not self._script_listbox:
            return
        self._script_listbox.delete(0, tk.END)
        for s in CaveBotService.list_scripts():
            self._script_listbox.insert(tk.END, s)

    def _on_script_select(self, _event=None) -> None:
        selection = self._script_listbox.curselection()
        if not selection:
            return
        name = self._script_listbox.get(selection[0])
        self._script_var.set(name)
        self.runtime.state.cavebot.script_name = name

    def _new_script(self) -> None:
        name = self._script_var.get().strip()
        if not name:
            name = simpledialog.askstring("New Script", "Enter script name:", parent=self.parent)
            if not name:
                return
            name = name.strip()
            self._script_var.set(name)
        CaveBotService.create_default_script(name)
        self.runtime.state.cavebot.script_name = name
        self._refresh_script_list()
        self.runtime.ui.log(f"📜 Script '{name}' created")

    def _delete_script(self) -> None:
        name = self._script_var.get().strip()
        if not name:
            return
        if messagebox.askyesno("Delete", f"Delete script '{name}'?", parent=self.parent):
            CaveBotService.delete_script(name)
            self._script_var.set("")
            self.runtime.state.cavebot.script_name = ""
            self._refresh_script_list()
            self._clear_waypoint_display()
            self.runtime.ui.log(f"🗑 Script '{name}' deleted")

    def _load_script_to_ui(self) -> None:
        """Load the selected script and populate the waypoint display."""
        name = self._script_var.get().strip()
        if not name:
            return
        data = CaveBotService.load_script(name)
        if not data:
            self.runtime.ui.log(f"⚠️ Script '{name}' is empty or not found")
            return
        self._refresh_waypoint_list(data)
        self._refresh_nav_display(data)
        self.runtime.state.cavebot.script_name = name
        self.runtime.ui.log(f"📂 Loaded script '{name}' ({len(data)} waypoints)")

    # ═══════════════════════════════════════════════════════════════
    # Waypoint Editing
    # ═══════════════════════════════════════════════════════════════

    def _add_waypoint(self) -> None:
        """Add a new waypoint at the current position."""
        name = self._script_var.get().strip()
        if not name:
            self.runtime.ui.log("⚠️  Select/create a script first")
            return

        mark_idx = self._mark_var.get()
        mark_name = MARK_NAMES[mark_idx - 1] if 1 <= mark_idx <= len(MARK_NAMES) else ""
        wp_type = self._wp_type_var.get()

        # Record current mouse position for the waypoint coordinate
        pos_service = self.services.get("position_capture")
        if pos_service:
            pos_service.capture(
                on_done=lambda pos: self._add_waypoint_at_pos(name, mark_name, wp_type, pos),
                label=f"Waypoint: {mark_name}",
            )
        else:
            # Without position capture, just add the mark without coordinates
            self._add_waypoint_at_pos(name, mark_name, wp_type, None)

    def _add_waypoint_at_pos(self, script_name: str, mark_name: str, wp_type: int, pos: tuple | None) -> None:
        data = CaveBotService.load_script(script_name)
        if not data or data[0].get("status") == "NotConfigured":
            # Replace the placeholder
            data = [{"mark": mark_name, "x": pos[0] if pos else 0, "y": pos[1] if pos else 0,
                     "type": wp_type, "status": True}]

            # Find current active waypoint and insert after it
            active_idx = None
            for i, wp in enumerate(data):
                if wp.get("status") is True:
                    active_idx = i
                    break

            if active_idx is not None:
                # Insert after active
                new_wp = {"mark": mark_name, "x": pos[0] if pos else 0, "y": pos[1] if pos else 0,
                          "type": wp_type, "status": False}
                data.insert(active_idx + 1, new_wp)
                # Move active flag to new waypoint
                data[active_idx]["status"] = False
                data[active_idx + 1]["status"] = True

        CaveBotService.save_script(script_name, data)
        self._refresh_waypoint_list(data)
        self._refresh_nav_display(data)
        pos_str = f"({pos[0]},{pos[1]})" if pos else "cursor"
        self.runtime.ui.log(f"➕ Added waypoint {mark_name} at {pos_str}")

    def _remove_waypoint(self) -> None:
        name = self._script_var.get().strip()
        if not name:
            return
        data = CaveBotService.load_script(name)
        if not data:
            return

        # Find the active waypoint
        active_idx = None
        for i, wp in enumerate(data):
            if wp.get("status") is True:
                active_idx = i
                break

        if active_idx is None:
            return

        del data[active_idx]
        if data:
            # Set next waypoint or first as active
            next_idx = min(active_idx, len(data) - 1)
            data[next_idx]["status"] = True
        else:
            # Script is now empty — insert placeholder
            data = [{"mark": "", "x": 0, "y": 0, "type": 1, "status": "NotConfigured"}]

        CaveBotService.save_script(name, data)
        self._refresh_waypoint_list(data)
        self._refresh_nav_display(data)
        self.runtime.ui.log("✕ Removed current waypoint")

    def _reset_waypoints(self) -> None:
        name = self._script_var.get().strip()
        if not name:
            return
        data = CaveBotService.load_script(name)
        if not data:
            return
        for wp in data:
            wp["status"] = False
        if data:
            data[0]["status"] = True
        CaveBotService.save_script(name, data)
        self._refresh_waypoint_list(data)
        self._refresh_nav_display(data)
        self.runtime.ui.log("⟳ Waypoints reset to first")

    def _prev_waypoint(self) -> None:
        self._move_waypoint(-1)

    def _next_waypoint(self) -> None:
        self._move_waypoint(1)

    def _move_waypoint(self, direction: int) -> None:
        name = self._script_var.get().strip()
        if not name:
            return
        data = CaveBotService.load_script(name)
        if not data:
            return
        active_idx = None
        for i, wp in enumerate(data):
            if wp.get("status") is True:
                active_idx = i
                break
        if active_idx is None:
            return
        data[active_idx]["status"] = False
        new_idx = (active_idx + direction) % len(data)
        data[new_idx]["status"] = True
        CaveBotService.save_script(name, data)
        self._refresh_waypoint_list(data)
        self._refresh_nav_display(data)

    # ═══════════════════════════════════════════════════════════════
    # Display Helpers
    # ═══════════════════════════════════════════════════════════════

    def _refresh_waypoint_list(self, data: list[dict]) -> None:
        if not self._wp_listbox:
            return
        self._wp_listbox.delete(0, tk.END)
        for i, wp in enumerate(data):
            mark = wp.get("mark", "?")
            wp_type = WAYPOINT_TYPES.get(wp.get("type", 1), "?")
            status = "●" if wp.get("status") is True else "○"
            coords = f"({wp.get('x', 0)},{wp.get('y', 0)})" if wp.get("x") else ""
            self._wp_listbox.insert(tk.END, f"{status} {i+1}: {mark} {coords} ({wp_type})")

    def _refresh_nav_display(self, data: list[dict]) -> None:
        if not data:
            self._clear_waypoint_display()
            return
        active_idx = None
        for i, wp in enumerate(data):
            if wp.get("status") is True:
                active_idx = i
                break
        if active_idx is None:
            return

        prev_idx = (active_idx - 1) % len(data)
        next_idx = (active_idx + 1) % len(data)

        for lbl, tlbl, idx in [(self._prev_wp_label, self._prev_type_label, prev_idx),
                                (self._curr_wp_label, self._curr_type_label, active_idx),
                                (self._next_wp_label, self._next_type_label, next_idx)]:
            if lbl:
                wp = data[idx]
                mark = wp.get("mark", "?")
                coords = f"({wp.get('x',0)},{wp.get('y',0)})" if wp.get("x") else ""
                lbl.config(text=f"{mark} {coords}")
            if tlbl:
                tlbl.config(text=WAYPOINT_TYPES.get(data[idx].get("type", 1), "?"))

    def _clear_waypoint_display(self) -> None:
        for lbl in [self._prev_wp_label, self._curr_wp_label, self._next_wp_label]:
            if lbl:
                lbl.config(text="—")
        for tlbl in [self._prev_type_label, self._curr_type_label, self._next_type_label]:
            if tlbl:
                tlbl.config(text="")

    # ═══════════════════════════════════════════════════════════════
    # CaveBot Controls
    # ═══════════════════════════════════════════════════════════════

    def _sync_controls(self) -> None:
        state = self.runtime.state.cavebot
        state.walking_enabled = self._walk_var.get()
        state.looting_enabled = self._loot_var.get()
        state.walk_for_debug = self._debug_var.get()
        state.follow_mode = self._follow_var.get()

    def _start_cavebot(self) -> None:
        # Sync UI to state
        state = self.runtime.state.cavebot
        state.script_name = self._script_var.get().strip()
        try:
            state.stand_seconds = max(0, int(self._stand_var.get()))
        except (ValueError, TypeError):
            state.stand_seconds = 1
        self._sync_controls()
        self.cavebot_service.start()

    def _stop_cavebot(self) -> None:
        self.cavebot_service.stop()

    # ═══════════════════════════════════════════════════════════════
    # Chase Target Controls
    # ═══════════════════════════════════════════════════════════════

    def _start_chase_target(self) -> None:
        chase = self.runtime.state.chase_target
        # Sync monster names from UI
        names = []
        for entry in self._chase_monster_entries:
            name = entry.get().strip()
            if name:
                names.append(name)
        chase.monster_names = names
        chase.attack_key = self._chase_key_var.get().strip()
        try:
            chase.scan_interval_ms = max(50, int(self._chase_interval_var.get()))
        except (ValueError, TypeError):
            chase.scan_interval_ms = 300
        chase.follow_mode = self._chase_follow_var.get()
        try:
            chase.battle_list_x = int(self._chase_battle_x_var.get())
        except (ValueError, TypeError):
            pass
        if self.chase_target_service:
            self.chase_target_service.start()

    def _stop_chase_target(self) -> None:
        if self.chase_target_service:
            self.chase_target_service.stop()

    def _record_battle_list_x(self) -> None:
        pos_service = self.services.get("position_capture")
        if pos_service:
            pos_service.capture(
                on_done=lambda pos: self._on_battle_x_captured(pos),
                label="Battle list X",
            )

    def _on_battle_x_captured(self, pos: tuple[int, int]) -> None:
        x = pos[0]
        self._chase_battle_x_var.set(str(x))
        self.runtime.state.chase_target.battle_list_x = x
        self.runtime.state.cavebot.battle_list_x = x
        self.runtime.ui.log(f"⚔️ Battle list X set to {x}")

    # ═══════════════════════════════════════════════════════════════
    # Auto Looter Controls
    # ═══════════════════════════════════════════════════════════════

    def _start_looter(self) -> None:
        looter = self.runtime.state.auto_looter
        try:
            looter.loot_delay_min_ms = max(50, int(self._looter_min_delay_var.get()))
            looter.loot_delay_max_ms = max(looter.loot_delay_min_ms, int(self._looter_max_delay_var.get()))
        except (ValueError, TypeError):
            pass
        if self.auto_looter_service:
            self.auto_looter_service.start()

    def _stop_looter(self) -> None:
        if self.auto_looter_service:
            self.auto_looter_service.stop()

    def _loot_once(self) -> None:
        if self.auto_looter_service:
            self.auto_looter_service.loot_once()

    def _add_looter_sqm(self) -> None:
        pos_service = self.services.get("position_capture")
        if pos_service:
            pos_service.capture(
                on_done=lambda pos: self._on_looter_sqm_added(pos),
                label="Looter SQM position",
            )

    def _on_looter_sqm_added(self, pos: tuple[int, int]) -> None:
        state = self.runtime.state.auto_looter
        if pos not in state.sqm_positions:
            state.sqm_positions.append(pos)
            self._refresh_sqm_list("looter")
            self.runtime.ui.log(f"📍 Looter SQM added: {pos}")

    def _remove_looter_sqm(self) -> None:
        if not self._looter_sqm_listbox:
            return
        sel = self._looter_sqm_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        state = self.runtime.state.auto_looter
        if 0 <= idx < len(state.sqm_positions):
            removed = state.sqm_positions.pop(idx)
            self._refresh_sqm_list("looter")
            self.runtime.ui.log(f"✕ Removed looter SQM: {removed}")

    def _clear_looter_sqm(self) -> None:
        self.runtime.state.auto_looter.sqm_positions.clear()
        self._refresh_sqm_list("looter")
        self.runtime.ui.log("🗑 Cleared all looter SQM positions")

    def _copy_sqm_from_cavebot(self) -> None:
        """Copy SQM positions from CaveBot to AutoLooter."""
        cavebot_sqms = list(self.runtime.state.cavebot.sqm_positions)
        looter_state = self.runtime.state.auto_looter
        for sqm in cavebot_sqms:
            if sqm not in looter_state.sqm_positions:
                looter_state.sqm_positions.append(sqm)
        self._refresh_sqm_list("looter")
        self.runtime.ui.log(f"⬇ Copied {len(cavebot_sqms)} SQM(s) to looter")

    def _refresh_sqm_list(self, source: str) -> None:
        if source == "looter" and self._looter_sqm_listbox:
            self._looter_sqm_listbox.delete(0, tk.END)
            for pos in self.runtime.state.auto_looter.sqm_positions:
                self._looter_sqm_listbox.insert(tk.END, f"{pos[0]}, {pos[1]}")
