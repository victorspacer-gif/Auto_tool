"""Luxe (CTk) rune session tab — ported from tkinter RuneTab."""

from __future__ import annotations

import customtkinter as ctk

from ...config import NON_NEGATIVE_INT_MIN


class RuneTab:
    """Owns the rune session tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.rune_hand_label: ctk.CTkLabel | None = None
        self.rune_storage_label: ctk.CTkLabel | None = None
        self.rune_blank_label: ctk.CTkLabel | None = None
        self.cycle_label: ctk.CTkLabel | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        # ── Rune Session Timing ──
        spell_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        spell_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(spell_panel, text="Rune Session Timing",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self.helpers["register_module_indicator"](spell_panel, "rune", self.runtime.state.rune_active)
        unit = self.helpers["get_unit_label"]()

        rune_spell = ctk.StringVar(value=self.runtime.state.rune_spell_key)
        rune_cycle = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_cycle_delay_ms)))
        rune_cycle_variation = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_cycle_delay_variation_ms)))
        rune_jitter = ctk.StringVar(value=str(self.runtime.state.rune_jitter))
        rune_cast = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_cast_delay_ms)))
        rune_post_cast_settle = ctk.StringVar(value=str(self.helpers["ms_to_display"](self.runtime.state.rune_post_cast_settle_ms)))
        rune_blank_cycles = ctk.StringVar(value=str(self.runtime.state.rune_available_blank_runes))
        rune_min_mana = ctk.StringVar(value=str(self.runtime.state.rune_min_mana))
        rune_max_mana = ctk.StringVar(value=str(self.runtime.state.rune_max_mana))

        self.ui_vars["rune_spell_key_var"] = rune_spell
        self.ui_vars["rune_cycle_delay_var"] = rune_cycle
        self.ui_vars["rune_cycle_variation_var"] = rune_cycle_variation
        self.ui_vars["rune_jitter_var"] = rune_jitter
        self.ui_vars["rune_cast_delay_var"] = rune_cast
        self.ui_vars["rune_post_cast_settle_var"] = rune_post_cast_settle
        self.ui_vars["rune_blank_cycles_var"] = rune_blank_cycles
        self.ui_vars["rune_min_mana_var"] = rune_min_mana
        self.ui_vars["rune_max_mana_var"] = rune_max_mana

        self.helpers["label_entry"](spell_panel, "Spell hotkey:", rune_spell, width=80)
        self.helpers["label_entry"](spell_panel, f"Cast settle delay ({unit}):", rune_cast, width=80)
        self.helpers["label_entry"](spell_panel, f"Post-cast settle ({unit}):", rune_post_cast_settle, width=80)
        self.helpers["label_entry"](spell_panel, f"Cycle delay base ({unit}):", rune_cycle, width=80)
        self.helpers["label_entry"](spell_panel, f"Cycle variation ({unit}):", rune_cycle_variation, width=80)
        self.helpers["label_entry"](spell_panel, "Position jitter (px ±):", rune_jitter, width=75)
        self.helpers["label_entry"](spell_panel, "Min mana to cast:", rune_min_mana, width=80)
        self.helpers["label_entry"](spell_panel, "Max mana (random range):", rune_max_mana, width=110)
        self.helpers["label_entry"](spell_panel, "avb blank runes:", rune_blank_cycles, width=80)

        self.cycle_label = ctk.CTkLabel(spell_panel, text="Approx cycle time: -",
                                         font=ctk.CTkFont(size=10, weight="bold"),
                                         text_color="#5ac8fa", anchor="w")
        self.cycle_label.pack(padx=10, pady=(6, 4))

        rune_cycle.trace_add("write", lambda *_args: self._update_cycle_preview(rune_cycle, rune_cycle_variation, rune_post_cast_settle))
        rune_cycle_variation.trace_add("write", lambda *_args: self._update_cycle_preview(rune_cycle, rune_cycle_variation, rune_post_cast_settle))
        self._update_cycle_preview(rune_cycle, rune_cycle_variation, rune_post_cast_settle)

        # ── Position Recording ──
        positions_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        positions_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(positions_panel, text="Position Recording",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        self._build_position_row(positions_panel, "Record Hand", "Hand slot", self.record_rune_hand, "hand")
        self._build_position_row(positions_panel, "Record Storage", "Finished storage pos", self.record_rune_storage, "storage")
        self._build_position_row(positions_panel, "Record Blank", "Blank rune backpack pos", self.record_rune_blank, "blank")

        # ── Cycle Flow ──
        how_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        how_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(how_panel, text="Cycle Flow",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        for step in [
            "1. Press spell hotkey → rune appears in hand",
            f"2. Wait cast settle delay ({unit})",
            "3. Acquire mouse lock",
            "4. Drag rune: Hand → Finished storage",
            "5. Drag blank: Blank stack → Hand slot",
            "6. Release mouse lock",
            f"7. Wait cycle delay ({unit})",
            "8. Repeat",
        ]:
            ctk.CTkLabel(how_panel, text=step, font=ctk.CTkFont(size=10),
                          text_color="#777777", justify="left", anchor="w").pack(padx=10, fill="x", pady=2)

        # ── Mouse Timing ──
        timing_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        timing_panel.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(timing_panel, text="Mouse Timing",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 2))
        ctk.CTkLabel(
            timing_panel,
            text="Rune drags now use the shared default HumanMouse timing.\n"
                 "The per-rune move/press/settle tuning section was removed so\n"
                 "this session follows the same standard mouse behavior as the\n"
                 "rest of the app.",
            font=ctk.CTkFont(size=10),
            text_color="#777777",
            justify="left",
            anchor="w",
        ).pack(padx=10, fill="x", pady=(2, 8))

        buttons = ctk.CTkFrame(right, fg_color="transparent")
        buttons.pack(fill="x", pady=(0, 8))
        self.helpers["btn"](buttons, "▶  Start Rune Session", self.services["rune_service"].start, "#30d158").pack(fill="x", pady=2)
        self.helpers["btn"](buttons, "⏹  Stop Rune Session", self.services["rune_service"].stop, "#ff453a").pack(fill="x", pady=2)

    def _build_position_row(self, parent, title: str, label_text: str, command, slot: str) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=4)
        label = ctk.CTkLabel(frame, text=f"{label_text}: 0, 0",
                              font=ctk.CTkFont(size=10, family="Consolas"),
                              text_color="#5ac8fa", anchor="w", width=220)
        label.pack(side="left")
        if slot == "hand":
            self.rune_hand_label = label
        elif slot == "storage":
            self.rune_storage_label = label
        else:
            self.rune_blank_label = label
        self.helpers["btn"](frame, title, command, "#0a84ff").pack(side="left", padx=6)

    def _update_cycle_preview(self, rune_cycle, rune_cycle_variation, rune_post_cast_settle) -> None:
        if not self.cycle_label:
            return
        try:
            base_ms = self.helpers["display_to_ms"](float(rune_cycle.get()))
            variation_ms = self.helpers["display_to_ms"](float(rune_cycle_variation.get()))
            post_settle_ms = self.helpers["display_to_ms"](float(rune_post_cast_settle.get())) if rune_post_cast_settle.get() else 600
            min_seconds = max(0.0, (base_ms - variation_ms + post_settle_ms) / 1000.0)
            max_seconds = (base_ms + variation_ms + post_settle_ms) / 1000.0
            self.cycle_label.configure(text=f"Approx {min_seconds:.1f}-{max_seconds:.1f} s between casts")
        except ValueError:
            self.cycle_label.configure(text="Approx cycle time: -")

    def _record_rune_position(self, attr_name: str, label, label_text: str) -> None:
        def on_done(pos: tuple[int, int]) -> None:
            setattr(self.runtime.state, attr_name, pos)
            self.runtime.ui.log(f"{label_text}: {pos}")
            self.runtime.ui.set_status(f"{label_text} captured", "#30d158")
            if label:
                label.configure(text=f"{label_text}: {pos[0]},{pos[1]}")

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
        state.rune_cycle_delay_variation_ms = max(NON_NEGATIVE_INT_MIN, self.helpers["get_ui_ms"]("rune_cycle_variation_var", state.rune_cycle_delay_variation_ms))
        state.rune_jitter = self.helpers["get_ui_int"]("rune_jitter_var", state.rune_jitter)
        state.rune_cast_delay_ms = self.helpers["get_ui_ms"]("rune_cast_delay_var", state.rune_cast_delay_ms)
        state.rune_post_cast_settle_ms = max(100, self.helpers["get_ui_ms"]("rune_post_cast_settle_var", state.rune_post_cast_settle_ms))
        state.rune_min_mana = max(NON_NEGATIVE_INT_MIN, self.helpers["get_ui_int"]("rune_min_mana_var", state.rune_min_mana))
        state.rune_max_mana = max(state.rune_min_mana, self.helpers["get_ui_int"]("rune_max_mana_var", state.rune_max_mana))
        state.rune_available_blank_runes = max(NON_NEGATIVE_INT_MIN, self.helpers["get_ui_int"]("rune_blank_cycles_var", state.rune_available_blank_runes))

    def refresh_from_state(self) -> None:
        state = self.runtime.state
        if self.rune_hand_label:
            self.rune_hand_label.configure(text=f"Hand slot: {state.rune_hand_pos[0]},{state.rune_hand_pos[1]}")
        if self.rune_storage_label:
            self.rune_storage_label.configure(text=f"Finished storage pos: {state.rune_storage_pos[0]},{state.rune_storage_pos[1]}")
        if self.rune_blank_label:
            self.rune_blank_label.configure(text=f"Blank rune backpack pos: {state.rune_blank_pos[0]},{state.rune_blank_pos[1]}")
