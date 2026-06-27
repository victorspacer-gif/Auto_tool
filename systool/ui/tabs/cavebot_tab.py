"""CaveBot tab UI for SystemMonitor — script management, monster config, controls.

Adapted from TibiaAuto12 CaveBot module pattern.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, scrolledtext

logger = logging.getLogger(__name__)

from ...services.cavebot import CaveBotService
from ...theme import BG, BLUE, BOLD, FG, GREEN, MONO, MUTED, ORANGE, PANEL, RED, SMALL, SMALL_B, TEAL, PURPLE


class CaveBotTab:
    """Owns the CaveBot tab UI and tab-local behaviour."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars
        self.cavebot_service: CaveBotService = services["cavebot_service"]

        self._script_listbox: tk.Listbox | None = None
        self._wp_listbox: tk.Listbox | None = None
        self._script_var = tk.StringVar(value=runtime.state.cavebot.script_name)
        self._stand_var = tk.StringVar(value=str(runtime.state.cavebot.stand_seconds))
        self._monster_entries: list[tuple[tk.BooleanVar, tk.StringVar, tk.StringVar]] = []

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        # ── Left column: Script management + Waypoints ────────────
        script_panel = tk.LabelFrame(left, text=" 📜  Script Manager ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        script_panel.pack(fill="x", pady=(0, 8))
        self.helpers["register_module_indicator"](script_panel, "cavebot", self.runtime.state.cavebot.active)

        name_row = tk.Frame(script_panel, bg=PANEL)
        name_row.pack(fill="x", pady=(0, 4))
        tk.Label(name_row, text="Script:", font=BOLD, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        script_entry = tk.Entry(name_row, textvariable=self._script_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=20)
        script_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_row = tk.Frame(script_panel, bg=PANEL)
        btn_row.pack(fill="x", pady=(0, 4))
        self.helpers["btn"](btn_row, "🔄 Refresh List", self._refresh_script_list, BLUE).pack(side="left", padx=2)
        self.helpers["btn"](btn_row, "➕ New Script", self._new_script, GREEN).pack(side="left", padx=2)
        self.helpers["btn"](btn_row, "🗑 Delete Script", self._delete_script, RED).pack(side="left", padx=2)

        list_frame = tk.Frame(script_panel, bg=PANEL, height=100)
        list_frame.pack(fill="x", pady=(0, 4))
        self._script_listbox = tk.Listbox(list_frame, bg=BG, fg=FG, font=MONO, selectbackground=BLUE,
                                          selectforeground="white", relief="flat", bd=2, height=5)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self._script_listbox.yview)
        self._script_listbox.configure(yscrollcommand=scrollbar.set)
        self._script_listbox.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._script_listbox.bind("<<ListboxSelect>>", self._on_script_select)
        self._refresh_script_list()

        # ── Control Buttons ───────────────────────────────────────
        control_panel = tk.LabelFrame(left, text=" 🎮  Controls ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        control_panel.pack(fill="x", pady=(0, 8))

        ctrl_row = tk.Frame(control_panel, bg=PANEL)
        ctrl_row.pack(fill="x", pady=(0, 4))
        self._start_btn = self.helpers["btn"](ctrl_row, "▶ Start CaveBot", self._toggle_cavebot, GREEN)
        self._start_btn.pack(side="left", padx=2)
        self.helpers["btn"](ctrl_row, "⏹ Stop", self._stop_cavebot, RED).pack(side="left", padx=2)

        settings_row = tk.Frame(control_panel, bg=PANEL)
        settings_row.pack(fill="x", pady=(0, 4))
        tk.Label(settings_row, text="Stand (s):", font=SMALL, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        stand_entry = tk.Entry(settings_row, textvariable=self._stand_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=4)
        stand_entry.pack(side="left", padx=(0, 8))

        self._walk_var = tk.BooleanVar(value=self.runtime.state.cavebot.walking_enabled)
        walk_cb = tk.Checkbutton(settings_row, text="Walk", variable=self._walk_var, bg=PANEL, fg=FG,
                                 selectcolor=BG, font=SMALL, command=self._sync_walk)
        walk_cb.pack(side="left", padx=2)

        self._loot_var = tk.BooleanVar(value=self.runtime.state.cavebot.looting_enabled)
        loot_cb = tk.Checkbutton(settings_row, text="Loot", variable=self._loot_var, bg=PANEL, fg=FG,
                                 selectcolor=BG, font=SMALL)
        loot_cb.pack(side="left", padx=2)

        self._debug_var = tk.BooleanVar(value=self.runtime.state.cavebot.walk_for_debug)
        debug_cb = tk.Checkbutton(settings_row, text="Debug Walk", variable=self._debug_var, bg=PANEL, fg=FG,
                                  selectcolor=BG, font=SMALL)
        debug_cb.pack(side="left", padx=2)

        self._follow_var = tk.BooleanVar(value=self.runtime.state.cavebot.follow_mode)
        follow_cb = tk.Checkbutton(settings_row, text="Follow", variable=self._follow_var, bg=PANEL, fg=FG,
                                   selectcolor=BG, font=SMALL)
        follow_cb.pack(side="left", padx=2)

        # ── Monster Targeting ─────────────────────────────────────
        monster_panel = tk.LabelFrame(left, text=" 👾  Monster Targeting ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        monster_panel.pack(fill="x", pady=(0, 8))

        current_monsters = self.runtime.state.cavebot.monsters_to_attack or ["", "", "", ""]
        # Ensure at least 4 slots
        while len(current_monsters) < 4:
            current_monsters.append("")
        self._monster_entries = []
        for i in range(4):
            row = tk.Frame(monster_panel, bg=PANEL)
            row.pack(fill="x", pady=2)
            enabled_var = tk.BooleanVar(value=bool(current_monsters[i]))
            cb = tk.Checkbutton(row, variable=enabled_var, bg=PANEL, fg=FG, selectcolor=BG, font=SMALL)
            cb.pack(side="left", padx=(0, 2))
            tk.Label(row, text=f"Monster {i+1}:", font=SMALL_B, bg=PANEL, fg=FG).pack(side="left", padx=(0, 2))
            name_var = tk.StringVar(value=current_monsters[i])
            entry = tk.Entry(row, textvariable=name_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=15)
            entry.pack(side="left", padx=(0, 4))
            # Skill key per monster row (for individual targeting)
            skill_var = tk.StringVar(value="f1")
            tk.Label(row, text="Key:", font=SMALL, bg=PANEL, fg=MUTED).pack(side="left", padx=(0, 2))
            sk_entry = tk.Entry(row, textvariable=skill_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=4)
            sk_entry.pack(side="left")
            self._monster_entries.append((enabled_var, name_var, skill_var))

        # ── SQM Loot Positions ────────────────────────────────────
        sqm_panel = tk.LabelFrame(left, text=" 🗺️  Loot SQM Positions ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        sqm_panel.pack(fill="x", pady=(0, 8))
        self._sqm_listbox = tk.Listbox(sqm_panel, bg=BG, fg=FG, font=MONO, selectbackground=BLUE,
                                       selectforeground="white", relief="flat", bd=2, height=4)
        self._sqm_listbox.pack(fill="x", padx=4, pady=4)
        sqm_btn_row = tk.Frame(sqm_panel, bg=PANEL)
        sqm_btn_row.pack(fill="x")
        self.helpers["btn"](sqm_btn_row, "➕ Add Current Pos", self._add_sqm_pos, BLUE).pack(side="left", padx=2)
        self.helpers["btn"](sqm_btn_row, "✕ Remove Selected", self._remove_sqm_pos, ORANGE).pack(side="left", padx=2)
        self.helpers["btn"](sqm_btn_row, "🗑 Clear All", self._clear_sqm_pos, RED).pack(side="left", padx=2)
        self._refresh_sqm_list()

        # ── Battle List X ──────────────────────────────────────────
        battle_panel = tk.LabelFrame(left, text=" ⚔️  Battle List Config ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        battle_panel.pack(fill="x", pady=(0, 8))
        self._battle_x_var = tk.StringVar(value=str(self.runtime.state.cavebot.battle_list_x))
        battle_row = tk.Frame(battle_panel, bg=PANEL)
        battle_row.pack(fill="x", pady=2)
        tk.Label(battle_row, text="Battle List X:", font=BOLD, bg=PANEL, fg=FG).pack(side="left", padx=(0, 4))
        tk.Entry(battle_row, textvariable=self._battle_x_var, font=MONO, bg=BG, fg=FG, relief="flat", bd=2, width=8).pack(side="left")
        self.helpers["btn"](battle_row, "🎯 Record X", self._record_battle_x, PURPLE).pack(side="left", padx=(8, 0))

    # ── Script management ──────────────────────────────────────────

    def _refresh_script_list(self) -> None:
        if not self._script_listbox:
            return
        self._script_listbox.delete(0, tk.END)
        scripts = CaveBotService.list_scripts()
        for s in scripts:
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
            # Prompt for name
            from tkinter.simpledialog import askstring
            name = askstring("New Script", "Enter script name:", parent=self.parent)
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
        if messagebox.askyesno("Delete Script", f"Delete script '{name}'?", parent=self.parent):
            CaveBotService.delete_script(name)
            self._script_var.set("")
            self.runtime.state.cavebot.script_name = ""
            self._refresh_script_list()
            self.runtime.ui.log(f"🗑 Script '{name}' deleted")

    # ── Controls ───────────────────────────────────────────────────

    def _toggle_cavebot(self) -> None:
        # Sync UI state to runtime before starting
        self._sync_ui_to_state()
        service = self.cavebot_service
        if self.runtime.state.cavebot.active:
            service.stop()
        else:
            service.start()

    def _stop_cavebot(self) -> None:
        self.cavebot_service.stop()

    def _sync_walk(self) -> None:
        self.runtime.state.cavebot.walking_enabled = self._walk_var.get()

    def _sync_ui_to_state(self) -> None:
        state = self.runtime.state.cavebot
        state.script_name = self._script_var.get().strip()
        try:
            state.stand_seconds = max(0, int(self._stand_var.get()))
        except (ValueError, TypeError):
            state.stand_seconds = 1
        state.walking_enabled = self._walk_var.get()
        state.looting_enabled = self._loot_var.get()
        state.walk_for_debug = self._debug_var.get()
        state.follow_mode = self._follow_var.get()

        # Sync monster list
        monsters = []
        for enabled_var, name_var, skill_var in self._monster_entries:
            if enabled_var.get() and name_var.get().strip():
                monsters.append(name_var.get().strip())
        state.monsters_to_attack = monsters

        # Sync skill key from first monster's key
        if self._monster_entries and self._monster_entries[0][1].get().strip():
            state.skill_key = self._monster_entries[0][2].get().strip()

        # Sync battle list X
        try:
            state.battle_list_x = int(self._battle_x_var.get())
        except (ValueError, TypeError):
            pass

    # ── SQM Loot positions ─────────────────────────────────────────

    def _add_sqm_pos(self) -> None:
        """Record current mouse position as an SQM loot spot."""
        pos_service = self.services.get("position_capture")
        if pos_service:
            pos_service.capture(
                on_done=lambda pos: self._on_sqm_captured(pos),
                label="SQM loot position",
            )

    def _on_sqm_captured(self, pos: tuple[int, int]) -> None:
        state = self.runtime.state.cavebot
        if pos not in state.sqm_positions:
            state.sqm_positions.append(pos)
            self._refresh_sqm_list()
            self.runtime.ui.log(f"📍 SQM position added: {pos}")

    def _remove_sqm_pos(self) -> None:
        if not self._sqm_listbox:
            return
        selection = self._sqm_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        state = self.runtime.state.cavebot
        if 0 <= idx < len(state.sqm_positions):
            removed = state.sqm_positions.pop(idx)
            self._refresh_sqm_list()
            self.runtime.ui.log(f"✕ Removed SQM: {removed}")

    def _clear_sqm_pos(self) -> None:
        self.runtime.state.cavebot.sqm_positions.clear()
        self._refresh_sqm_list()
        self.runtime.ui.log("🗑 Cleared all SQM positions")

    def _refresh_sqm_list(self) -> None:
        if not self._sqm_listbox:
            return
        self._sqm_listbox.delete(0, tk.END)
        for pos in self.runtime.state.cavebot.sqm_positions:
            self._sqm_listbox.insert(tk.END, f"{pos[0]}, {pos[1]}")

    # ── Battle list X ──────────────────────────────────────────────

    def _record_battle_x(self) -> None:
        """Record the X coordinate of the battle list via mouse click."""
        pos_service = self.services.get("position_capture")
        if pos_service:
            pos_service.capture(
                on_done=lambda pos: self._on_battle_x_captured(pos),
                label="Battle list X position",
            )

    def _on_battle_x_captured(self, pos: tuple[int, int]) -> None:
        x = pos[0]
        self._battle_x_var.set(str(x))
        self.runtime.state.cavebot.battle_list_x = x
        self.runtime.ui.log(f"⚔️ Battle list X set to {x}")
