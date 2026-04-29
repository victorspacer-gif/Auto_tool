"""Rune tab UI for SystemMonitor."""

from __future__ import annotations

import tkinter as tk

from ...theme import BG, BLUE, BOLD, FG, GREEN, MONO, MUTED, ORANGE, PANEL, PURPLE, RED, SMALL, SMALL_B, TEAL


class RuneTab:
    """Owns the rune session tab UI and tab-local behavior."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.rune_hand_label: tk.Label | None = None
        self.rune_storage_label: tk.Label | None = None
        self.rune_blank_label: tk.Label | None = None
        self.cycle_label: tk.Label | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        spell_panel = tk.LabelFrame(left, text=" ✨  Rune Session Timing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        spell_panel.pack(fill="x", pady=(0, 8))
        self.helpers["register_module_indicator"](spell_panel, "rune", self.runtime.state.rune_active)
        unit = self.helpers["get_unit_label"]()

        rune_spell = tk.StringVar(value=self.runtime.state.rune_spell_key)
        rune_cycle = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_cycle_delay_ms)))
        rune_cycle_variation = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_cycle_delay_variation_ms)))
        rune_jitter = tk.StringVar(value=str(self.runtime.state.rune_jitter))
        rune_cast = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_cast_delay_ms)))
        rune_post_cast_settle = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_post_cast_settle_ms)))
        rune_blank_cycles = tk.StringVar(value=str(self.runtime.state.rune_available_blank_runes))
        rune_move_min = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_mouse_move_min_ms)))
        rune_move_max = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_mouse_move_max_ms)))
        rune_press_min = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_mouse_press_min_ms)))
        rune_press_max = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_mouse_press_max_ms)))
        rune_settle_min = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_mouse_settle_min_ms)))
        rune_settle_max = tk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_mouse_settle_max_ms)))
        rune_min_mana = tk.StringVar(value=str(self.runtime.state.rune_min_mana))
        rune_max_mana = tk.StringVar(value=str(self.runtime.state.rune_max_mana))

        self.ui_vars["rune_spell_key_var"] = rune_spell
        self.ui_vars["rune_cycle_delay_var"] = rune_cycle
        self.ui_vars["rune_cycle_variation_var"] = rune_cycle_variation
        self.ui_vars["rune_jitter_var"] = rune_jitter
        self.ui_vars["rune_cast_delay_var"] = rune_cast
        self.ui_vars["rune_post_cast_settle_var"] = rune_post_cast_settle
        self.ui_vars["rune_blank_cycles_var"] = rune_blank_cycles
        self.ui_vars["rune_move_min_var"] = rune_move_min
        self.ui_vars["rune_move_max_var"] = rune_move_max
        self.ui_vars["rune_press_min_var"] = rune_press_min
        self.ui_vars["rune_press_max_var"] = rune_press_max
        self.ui_vars["rune_settle_min_var"] = rune_settle_min
        self.ui_vars["rune_settle_max_var"] = rune_settle_max
        self.ui_vars["rune_min_mana_var"] = rune_min_mana
        self.ui_vars["rune_max_mana_var"] = rune_max_mana

        self.helpers["label_entry"](spell_panel, "Spell hotkey:", rune_spell, width=6)
        self.helpers["label_entry"](spell_panel, f"Cast settle delay ({unit}):", rune_cast, width=7)
        self.helpers["label_entry"](spell_panel, f"Post-cast settle ({unit}):", rune_post_cast_settle, width=8)
        self.helpers["label_entry"](spell_panel, f"Cycle delay base ({unit}):", rune_cycle, width=7)
        self.helpers["label_entry"](spell_panel, f"Cycle variation ({unit}):", rune_cycle_variation, width=7)
        self.helpers["label_entry"](spell_panel, "Position jitter (px ±):", rune_jitter, width=5)
        self.helpers["label_entry"](spell_panel, "Min mana to cast:", rune_min_mana, width=7)
        self.helpers["label_entry"](spell_panel, "Max mana (random range):", rune_max_mana, width=10)
        self.helpers["label_entry"](spell_panel, "avb blank runes:", rune_blank_cycles, width=7)

        self.cycle_label = tk.Label(spell_panel, text="≈ Cycle time: —", font=SMALL_B, fg=TEAL, bg=PANEL)
        self.cycle_label.pack(anchor="w", pady=(6, 0))

        rune_cycle.trace_add("write", lambda *_args: self._update_cycle_preview(rune_cycle, rune_cycle_variation, rune_post_cast_settle))
        rune_cycle_variation.trace_add("write", lambda *_args: self._update_cycle_preview(rune_cycle, rune_cycle_variation, rune_post_cast_settle))
        self._update_cycle_preview(rune_cycle, rune_cycle_variation, rune_post_cast_settle)

        positions_panel = tk.LabelFrame(left, text=" 🎯  Position Recording ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        positions_panel.pack(fill="both", expand=True, pady=(0, 8))
        self._build_position_row(positions_panel, "Record Hand", "Hand slot", self.record_rune_hand, "hand")
        self._build_position_row(positions_panel, "Record Storage", "Finished storage pos", self.record_rune_storage, "storage")
        self._build_position_row(positions_panel, "Record Blank", "Blank rune backpack pos", self.record_rune_blank, "blank")

        how_panel = tk.LabelFrame(right, text=" ℹ️  Cycle flow ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        how_panel.pack(fill="x", pady=(0, 8))
        for step in [
            "1.  Press spell hotkey → rune appears in hand",
            f"2.  Wait cast settle delay ({unit})",
            "3.  Acquire mouse lock",
            "4.  Drag rune: Hand → Finished storage",
            "5.  Drag blank: Blank stack → Hand slot",
            "6.  Release mouse lock",
            f"7.  Wait cycle delay ({unit})",
            "8.  Repeat",
        ]:
            tk.Label(how_panel, text=step, font=SMALL, fg=MUTED, bg=PANEL, justify="left", anchor="w").pack(fill="x")

        timing_panel = tk.LabelFrame(right, text=" 🖱️  Mouse Timing ", font=BOLD, fg=FG, bg=PANEL, bd=1, pady=8, padx=10)
        timing_panel.pack(fill="x", pady=(0, 8))
        self.helpers["label_entry"](timing_panel, f"Move min ({unit}):", rune_move_min, width=6)
        self.helpers["label_entry"](timing_panel, f"Move max ({unit}):", rune_move_max, width=6)
        self.helpers["label_entry"](timing_panel, f"Press min ({unit}):", rune_press_min, width=6)
        self.helpers["label_entry"](timing_panel, f"Press max ({unit}):", rune_press_max, width=6)
        self.helpers["label_entry"](timing_panel, f"Settle min ({unit}):", rune_settle_min, width=6)
        self.helpers["label_entry"](timing_panel, f"Settle max ({unit}):", rune_settle_max, width=6)

        buttons = tk.Frame(right, bg=BG)
        buttons.pack(fill="x", pady=(0, 8))
        self.helpers["btn"](buttons, "▶ Start Rune Session", self.services["rune_service"].start, GREEN).pack(fill="x", pady=2)
        self.helpers["btn"](buttons, "⏹ Stop Rune Session", self.services["rune_service"].stop, RED).pack(fill="x", pady=2)

    def _build_position_row(self, parent, title: str, label_text: str, command, slot: str) -> None:
        frame = tk.Frame(parent, bg=PANEL)
        frame.pack(fill="x", pady=4)
        label = tk.Label(frame, text=f"{label_text}: 0, 0", font=MONO, fg=TEAL, bg=PANEL, width=26, anchor="w")
        label.pack(side="left")
        if slot == "hand":
            self.rune_hand_label = label
        elif slot == "storage":
            self.rune_storage_label = label
        else:
            self.rune_blank_label = label
        self.helpers["btn"](frame, f"📍 {title}", command, BLUE).pack(side="left", padx=6)

    def _update_cycle_preview(self, rune_cycle, rune_cycle_variation, rune_post_cast_settle) -> None:
        if not self.cycle_label:
            return
        try:
            base_ms = self.helpers["display_to_ms"](float(rune_cycle.get()))
            variation_ms = self.helpers["display_to_ms"](float(rune_cycle_variation.get()))
            post_settle_ms = self.helpers["display_to_ms"](float(rune_post_cast_settle.get())) if rune_post_cast_settle.get() else 600
            min_seconds = max(0.0, (base_ms - variation_ms + post_settle_ms) / 1000.0)
            max_seconds = (base_ms + variation_ms + post_settle_ms) / 1000.0
            self.cycle_label.config(text=f"≈ {min_seconds:.1f}–{max_seconds:.1f} s between casts")
        except ValueError:
            self.cycle_label.config(text="≈ Cycle time: —")

    def _record_rune_position(self, attr_name: str, label: tk.Label | None, label_text: str) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            setattr(self.runtime.state, attr_name, pos)
            self.runtime.ui.log(f"✅ {label_text}: {pos}")
            self.runtime.ui.set_status(f"{label_text} captured", GREEN)
            if label:
                label.config(text=f"{label_text}: {pos[0]},{pos[1]}")

        self.services["position_capture"].capture(on_done, label_text)

    def record_rune_hand(self) -> None:
        self._record_rune_position("rune_hand_pos", self.rune_hand_label, "Hand slot")

    def record_rune_storage(self) -> None:
        self._record_rune_position("rune_storage_pos", self.rune_storage_label, "Finished storage pos")

    def record_rune_blank(self) -> None:
        self._record_rune_position("rune_blank_pos", self.rune_blank_label, "Blank rune backpack pos")

    def poll_settings(self, state) -> None:
        if "rune_spell_key_var" in self.ui_vars:
            state.rune_spell_key = str(self.ui_vars["rune_spell_key_var"].get()).lower().strip()
        state.rune_cycle_delay_ms = self.helpers["get_ui_ms"]("rune_cycle_delay_var", state.rune_cycle_delay_ms)
        state.rune_cycle_delay_variation_ms = max(0, self.helpers["get_ui_ms"]("rune_cycle_variation_var", state.rune_cycle_delay_variation_ms))
        state.rune_jitter = self.helpers["get_ui_int"]("rune_jitter_var", state.rune_jitter)
        state.rune_cast_delay_ms = self.helpers["get_ui_ms"]("rune_cast_delay_var", state.rune_cast_delay_ms)
        state.rune_post_cast_settle_ms = max(100, self.helpers["get_ui_ms"]("rune_post_cast_settle_var", state.rune_post_cast_settle_ms))
        state.rune_min_mana = max(0, self.helpers["get_ui_int"]("rune_min_mana_var", state.rune_min_mana))
        state.rune_max_mana = max(state.rune_min_mana, self.helpers["get_ui_int"]("rune_max_mana_var", state.rune_max_mana))
        state.rune_available_blank_runes = max(0, self.helpers["get_ui_int"]("rune_blank_cycles_var", state.rune_available_blank_runes))
        state.rune_mouse_move_min_ms = max(20, self.helpers["get_ui_ms"]("rune_move_min_var", state.rune_mouse_move_min_ms))
        state.rune_mouse_move_max_ms = max(state.rune_mouse_move_min_ms, self.helpers["get_ui_ms"]("rune_move_max_var", state.rune_mouse_move_max_ms))
        state.rune_mouse_press_min_ms = max(10, self.helpers["get_ui_ms"]("rune_press_min_var", state.rune_mouse_press_min_ms))
        state.rune_mouse_press_max_ms = max(state.rune_mouse_press_min_ms, self.helpers["get_ui_ms"]("rune_press_max_var", state.rune_mouse_press_max_ms))
        state.rune_mouse_settle_min_ms = max(10, self.helpers["get_ui_ms"]("rune_settle_min_var", state.rune_mouse_settle_min_ms))
        state.rune_mouse_settle_max_ms = max(state.rune_mouse_settle_min_ms, self.helpers["get_ui_ms"]("rune_settle_max_var", state.rune_mouse_settle_max_ms))

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.rune_hand_label:
            self.rune_hand_label.config(text=f"Hand slot: {state.rune_hand_pos[0]},{state.rune_hand_pos[1]}")
        if self.rune_storage_label:
            self.rune_storage_label.config(text=f"Finished storage pos: {state.rune_storage_pos[0]},{state.rune_storage_pos[1]}")
        if self.rune_blank_label:
            self.rune_blank_label.config(text=f"Blank rune backpack pos: {state.rune_blank_pos[0]},{state.rune_blank_pos[1]}")

