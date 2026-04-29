"""Healer tab UI for SystemMonitor."""

from __future__ import annotations

import tkinter as tk

from ...theme import BG, BLUE, BODY, BOLD, FG, GREEN, MONO, MUTED, PANEL, PURPLE, RED, SMALL, TEAL


class HealerTab:
    """Owns the healer tab UI and tab-local behavior."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.healer_char_label: tk.Label | None = None
        self.healer_rune_label: tk.Label | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        mode_panel = tk.LabelFrame(left, text=" ❤️  Healing Mode ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        mode_panel.pack(fill="x", pady=(0, 8))
        self.helpers["register_module_indicator"](mode_panel, "healer", self.runtime.state.healer_active)

        healer_mode = tk.StringVar(value=self.runtime.state.healer_mode)
        healer_spell_key = tk.StringVar(value=self.runtime.state.healer_spell_key)
        healer_use_percent = tk.BooleanVar(value=self.runtime.state.healer_use_percent)
        healer_hp_percent = tk.StringVar(value=str(self.runtime.state.healer_hp_percent))
        healer_hp_value = tk.StringVar(value=str(self.runtime.state.healer_hp_value))
        healer_min_mana = tk.StringVar(value=str(self.runtime.state.healer_min_mana))
        healer_max_mana = tk.StringVar(value=str(self.runtime.state.healer_max_mana))

        self.ui_vars["healer_mode_var"] = healer_mode
        self.ui_vars["healer_spell_key_var"] = healer_spell_key
        self.ui_vars["healer_use_percent_var"] = healer_use_percent
        self.ui_vars["healer_hp_percent_var"] = healer_hp_percent
        self.ui_vars["healer_hp_value_var"] = healer_hp_value
        self.ui_vars["healer_min_mana_var"] = healer_min_mana
        self.ui_vars["healer_max_mana_var"] = healer_max_mana

        mode_row = tk.Frame(mode_panel, bg=PANEL)
        mode_row.pack(fill="x", pady=2)
        tk.Label(mode_row, text="Heal with:", font=BOLD, fg=FG, bg=PANEL, width=22, anchor="w").pack(side="left")
        mode_menu = tk.OptionMenu(mode_row, healer_mode, "spell", "rune")
        mode_menu.config(font=BODY, bg=PANEL, fg=FG, activebackground=BLUE, bd=0, relief="flat", highlightthickness=0)
        mode_menu["menu"].config(bg=PANEL, fg=FG, activebackground=BLUE, activeforeground="white")
        mode_menu.pack(side="left", padx=4)

        self.helpers["label_entry"](mode_panel, "Spell hotkey:", healer_spell_key, width=6)
        tk.Checkbutton(mode_panel, text="Use HP percentage threshold", variable=healer_use_percent, font=BOLD, bg=PANEL, fg=FG, selectcolor=PANEL, activebackground=PANEL).pack(anchor="w", pady=(4, 2))
        self.helpers["label_entry"](mode_panel, "Heal below HP %:", healer_hp_percent, width=6)
        self.helpers["label_entry"](mode_panel, "Heal below HP value:", healer_hp_value, width=6)
        self.helpers["label_entry"](mode_panel, "Min mana to heal:", healer_min_mana, width=6)
        self.helpers["label_entry"](mode_panel, "Max mana (random range):", healer_max_mana, width=8)

        rune_panel = tk.LabelFrame(left, text=" 🧿  Rune Healing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        rune_panel.pack(fill="x", pady=(0, 8))
        self.healer_char_label = tk.Label(rune_panel, text="Character center: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.healer_char_label.pack(anchor="w", pady=(0, 4))
        self.healer_rune_label = tk.Label(rune_panel, text="Healing rune: 0, 0", font=MONO, fg=TEAL, bg=PANEL)
        self.healer_rune_label.pack(anchor="w", pady=(0, 4))

        healer_mouse_speed = tk.StringVar(value=str(self.runtime.state.healer_mouse_speed))
        healer_rune_delay = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.healer_rune_delay_ms)))
        self.ui_vars["healer_mouse_speed_var"] = healer_mouse_speed
        self.ui_vars["healer_rune_delay_var"] = healer_rune_delay

        row = tk.Frame(rune_panel, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        self.helpers["btn"](row, "🎯 Record Character", self.record_healer_character_pos, BLUE).pack(side="left", padx=(0, 4), expand=True, fill="x")
        self.helpers["btn"](row, "🎯 Record Rune", self.record_healer_rune_pos, PURPLE).pack(side="left", padx=4, expand=True, fill="x")
        self.helpers["label_entry"](rune_panel, "Mouse speed factor:", healer_mouse_speed, width=6)
        self.helpers["label_entry"](rune_panel, f"Rune delay ({self.helpers['get_unit_label']()}):", healer_rune_delay, width=6)

        buttons = tk.Frame(left, bg=BG)
        buttons.pack(fill="x", pady=(0, 8))
        self.helpers["btn"](buttons, "▶ Start Auto Healer", self.services["healer_service"].start, GREEN).pack(fill="x", pady=2)
        self.helpers["btn"](buttons, "⏹ Stop Auto Healer", self.services["healer_service"].stop, RED).pack(fill="x", pady=2)

        help_panel = tk.LabelFrame(right, text=" ℹ️  Flow ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        help_panel.pack(fill="both", expand=True, pady=(0, 8))
        for line in [
            "1. Character Status provides the live HP values.",
            "2. Spell mode presses a game hotkey like F1/F2 when healing is needed.",
            "3. Rune mode right-clicks the recorded rune and then left-clicks your recorded character center.",
            "4. Rune healing uses the shared mouse lock so it will not fight fishing or rune maker.",
        ]:
            tk.Label(help_panel, text=line, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x", pady=2)

    def _record_generic_position(self, attr_name: str, label: tk.Label | None, label_text: str, capture_label: str) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            setattr(self.runtime.state, attr_name, pos)
            self.runtime.ui.log(f"✅ {label_text}: {pos}")
            self.runtime.ui.set_status(f"{label_text} captured", GREEN)
            if label:
                label.config(text=f"{label_text}: {pos[0]}, {pos[1]}")

        self.services["position_capture"].capture(on_done, capture_label)

    def record_healer_character_pos(self) -> None:
        self._record_generic_position("healer_character_pos", self.healer_char_label, "Character center", "Character center")

    def record_healer_rune_pos(self) -> None:
        self._record_generic_position("healer_rune_pos", self.healer_rune_label, "Healing rune", "Healing rune")

    def poll_settings(self, state) -> None:
        if "healer_mode_var" in self.ui_vars:
            state.healer_mode = str(self.ui_vars["healer_mode_var"].get()).strip().lower() or "spell"
        if "healer_spell_key_var" in self.ui_vars:
            state.healer_spell_key = str(self.ui_vars["healer_spell_key_var"].get()).lower().strip()
        if "healer_use_percent_var" in self.ui_vars:
            state.healer_use_percent = bool(self.ui_vars["healer_use_percent_var"].get())
        state.healer_hp_percent = max(1, min(100, self.helpers["get_ui_int"]("healer_hp_percent_var", state.healer_hp_percent)))
        state.healer_hp_value = max(1, self.helpers["get_ui_int"]("healer_hp_value_var", state.healer_hp_value))
        state.healer_min_mana = max(0, self.helpers["get_ui_int"]("healer_min_mana_var", state.healer_min_mana))
        state.healer_max_mana = max(state.healer_min_mana, self.helpers["get_ui_int"]("healer_max_mana_var", state.healer_max_mana))
        try:
            state.healer_mouse_speed = max(0.2, min(3.0, float(self.ui_vars["healer_mouse_speed_var"].get())))
        except (KeyError, ValueError):
            pass
        state.healer_rune_delay_ms = max(50, self.helpers["get_ui_ms"]("healer_rune_delay_var", state.healer_rune_delay_ms))

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.healer_char_label:
            self.healer_char_label.config(text=f"Character center: {state.healer_character_pos[0]}, {state.healer_character_pos[1]}")
        if self.healer_rune_label:
            self.healer_rune_label.config(text=f"Healing rune: {state.healer_rune_pos[0]}, {state.healer_rune_pos[1]}")

