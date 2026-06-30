"""Luxe (CTk) healer tab — ported from tkinter HealerTab."""

from __future__ import annotations

import customtkinter as ctk

from ...config import (
    HEALER_HP_MIN,
    HEALER_MOUSE_SPEED_MAX,
    HEALER_MOUSE_SPEED_MIN,
    HEALER_RUNE_DELAY_MS_MIN,
    NON_NEGATIVE_INT_MIN,
    PERCENT_VALUE_MAX,
)


class HealerTab:
    """Owns the healer tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.healer_char_label: ctk.CTkLabel | None = None
        self.healer_rune_label: ctk.CTkLabel | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        # ── Healing Mode ──
        mode_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        mode_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(mode_panel, text="❤️  Healing Mode",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.helpers["register_module_indicator"](mode_panel, "healer", self.runtime.state.healer_active)

        healer_mode = ctk.StringVar(value=self.runtime.state.healer_mode)
        healer_spell_key = ctk.StringVar(value=self.runtime.state.healer_spell_key)
        healer_use_percent = ctk.BooleanVar(value=self.runtime.state.healer_use_percent)
        healer_hp_percent = ctk.StringVar(value=str(self.runtime.state.healer_hp_percent))
        healer_hp_value = ctk.StringVar(value=str(self.runtime.state.healer_hp_value))
        healer_min_mana = ctk.StringVar(value=str(self.runtime.state.healer_min_mana))
        healer_max_mana = ctk.StringVar(value=str(self.runtime.state.healer_max_mana))

        self.ui_vars["healer_mode_var"] = healer_mode
        self.ui_vars["healer_spell_key_var"] = healer_spell_key
        self.ui_vars["healer_use_percent_var"] = healer_use_percent
        self.ui_vars["healer_hp_percent_var"] = healer_hp_percent
        self.ui_vars["healer_hp_value_var"] = healer_hp_value
        self.ui_vars["healer_min_mana_var"] = healer_min_mana
        self.ui_vars["healer_max_mana_var"] = healer_max_mana

        mode_row = ctk.CTkFrame(mode_panel, fg_color="transparent")
        mode_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(mode_row, text="Heal with:", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", width=150, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(mode_row, values=["spell", "rune"], variable=healer_mode,
                           fg_color="#1a1a1a", button_color="#0a84ff",
                           dropdown_fg_color="#252525", dropdown_text_color="#e8e8e8",
                           dropdown_hover_color="#0a84ff").pack(side="left", padx=4)

        self.helpers["label_entry"](mode_panel, "Spell hotkey:", healer_spell_key, width=80)
        ctk.CTkCheckBox(mode_panel, text="Use HP percentage threshold", variable=healer_use_percent,
                         fg_color="#0a84ff", text_color="#e8e8e8",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.helpers["label_entry"](mode_panel, "Heal below HP %:", healer_hp_percent, width=80)
        self.helpers["label_entry"](mode_panel, "Heal below HP value:", healer_hp_value, width=80)
        self.helpers["label_entry"](mode_panel, "Min mana to heal:", healer_min_mana, width=80)
        self.helpers["label_entry"](mode_panel, "Max mana (random range):", healer_max_mana, width=110)

        # ── Rune Healing ──
        rune_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        rune_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(rune_panel, text="🧿  Rune Healing",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.healer_char_label = ctk.CTkLabel(rune_panel, text="Character center: 0, 0",
                                               font=ctk.CTkFont(size=10, family="Consolas"),
                                               text_color="#5ac8fa", anchor="w")
        self.healer_char_label.pack(padx=10, pady=(0, 4))
        self.healer_rune_label = ctk.CTkLabel(rune_panel, text="Healing rune: 0, 0",
                                               font=ctk.CTkFont(size=10, family="Consolas"),
                                               text_color="#5ac8fa", anchor="w")
        self.healer_rune_label.pack(padx=10, pady=(0, 4))

        healer_mouse_speed = ctk.StringVar(value=str(self.runtime.state.healer_mouse_speed))
        healer_rune_delay = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.healer_rune_delay_ms)))
        self.ui_vars["healer_mouse_speed_var"] = healer_mouse_speed
        self.ui_vars["healer_rune_delay_var"] = healer_rune_delay

        row = ctk.CTkFrame(rune_panel, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 6))
        self.helpers["btn"](row, "🎯  Record Character", self.record_healer_character_pos, "#0a84ff").pack(side="left", padx=(0, 4), expand=True, fill="x")
        self.helpers["btn"](row, "🎯  Record Rune", self.record_healer_rune_pos, "#bf5af2").pack(side="left", padx=4, expand=True, fill="x")
        self.helpers["label_entry"](rune_panel, "Mouse speed factor:", healer_mouse_speed, width=80)
        self.helpers["label_entry"](rune_panel, f"Rune delay ({self.helpers['get_unit_label']()}):", healer_rune_delay, width=80)

        buttons = ctk.CTkFrame(left, fg_color="transparent")
        buttons.pack(fill="x", pady=(0, 8))
        self.helpers["btn"](buttons, "▶  Start Auto Healer", self.services["healer_service"].start, "#30d158").pack(fill="x", pady=2)
        self.helpers["btn"](buttons, "⏹  Stop Auto Healer", self.services["healer_service"].stop, "#ff453a").pack(fill="x", pady=2)

        # ── Flow Help ──
        help_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        help_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(help_panel, text="ℹ️  Flow",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        for line in [
            "1. Character Status provides the live HP values.",
            "2. Spell mode presses a game hotkey like F1/F2 when healing is needed.",
            "3. Rune mode right-clicks the recorded rune and then left-clicks your recorded character center.",
            "4. Rune healing uses the shared mouse lock so it will not fight fishing or rune maker.",
        ]:
            ctk.CTkLabel(help_panel, text=line, font=ctk.CTkFont(size=10),
                          text_color="#777777", justify="left", anchor="w").pack(padx=10, fill="x", pady=2)

    def _record_generic_position(self, attr_name: str, label, label_text: str, capture_label: str) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            setattr(self.runtime.state, attr_name, pos)
            self.runtime.ui.log(f"✅ {label_text}: {pos}")
            self.runtime.ui.set_status(f"{label_text} captured", "#30d158")
            if label:
                label.configure(text=f"{label_text}: {pos[0]}, {pos[1]}")

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
        state.healer_hp_percent = max(HEALER_HP_MIN, min(PERCENT_VALUE_MAX, self.helpers["get_ui_int"]("healer_hp_percent_var", state.healer_hp_percent)))
        state.healer_hp_value = max(HEALER_HP_MIN, self.helpers["get_ui_int"]("healer_hp_value_var", state.healer_hp_value))
        state.healer_min_mana = max(NON_NEGATIVE_INT_MIN, self.helpers["get_ui_int"]("healer_min_mana_var", state.healer_min_mana))
        state.healer_max_mana = max(state.healer_min_mana, self.helpers["get_ui_int"]("healer_max_mana_var", state.healer_max_mana))
        try:
            state.healer_mouse_speed = max(HEALER_MOUSE_SPEED_MIN, min(HEALER_MOUSE_SPEED_MAX, float(self.ui_vars["healer_mouse_speed_var"].get())))
        except (KeyError, ValueError):
            pass
        state.healer_rune_delay_ms = max(HEALER_RUNE_DELAY_MS_MIN, self.helpers["get_ui_ms"]("healer_rune_delay_var", state.healer_rune_delay_ms))

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.healer_char_label:
            self.healer_char_label.configure(text=f"Character center: {state.healer_character_pos[0]}, {state.healer_character_pos[1]}")
        if self.healer_rune_label:
            self.healer_rune_label.configure(text=f"Healing rune: {state.healer_rune_pos[0]}, {state.healer_rune_pos[1]}")
