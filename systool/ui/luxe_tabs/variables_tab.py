"""Luxe (CTk) variables tab — ported from tkinter VariablesTab."""

from __future__ import annotations

import logging
import time
import customtkinter as ctk

logger = logging.getLogger(__name__)


class VariablesTab:
    """Owns the variables tab UI for the Luxe interface."""

    def __init__(self, parent, runtime, services, helpers, ui_vars):
        self.parent = parent
        self.runtime = runtime
        self.services = services
        self.helpers = helpers
        self.ui_vars = ui_vars

        self.var_level_label: ctk.CTkLabel | None = None
        self.var_hp_label: ctk.CTkLabel | None = None
        self.var_cap_label: ctk.CTkLabel | None = None
        self.var_mp_label: ctk.CTkLabel | None = None
        self.var_food_label: ctk.CTkLabel | None = None
        self.var_hp_source_label: ctk.CTkLabel | None = None
        self.var_mp_source_label: ctk.CTkLabel | None = None
        self.var_cap_source_label: ctk.CTkLabel | None = None
        self.var_food_source_label: ctk.CTkLabel | None = None
        self.var_hp_addr_label: ctk.CTkLabel | None = None
        self.var_mp_addr_label: ctk.CTkLabel | None = None
        self.var_cap_addr_label: ctk.CTkLabel | None = None
        self.var_food_addr_label: ctk.CTkLabel | None = None
        self.var_regen_label: ctk.CTkLabel | None = None
        self.var_read_stats_label: ctk.CTkLabel | None = None
        self.var_last_update_label: ctk.CTkLabel | None = None

        self._build()

    def _build(self) -> None:
        content_frame = self.helpers["create_scrollable_content"](self.parent)
        left, right = self.helpers["create_responsive_columns"](content_frame)

        # ── Live Variables ──
        vars_panel = ctk.CTkFrame(left, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        vars_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(vars_panel, text="Live Variables",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 4))
        self.var_level_label = ctk.CTkLabel(vars_panel, text="Level: —",
                                             font=ctk.CTkFont(size=14, weight="bold"),
                                             text_color="#5ac8fa", anchor="w")
        self.var_level_label.pack(padx=10, fill="x", pady=2)
        self.var_hp_label = ctk.CTkLabel(vars_panel, text="HP: —",
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          text_color="#ff453a", anchor="w")
        self.var_hp_label.pack(padx=10, fill="x", pady=2)
        self.var_cap_label = ctk.CTkLabel(vars_panel, text="Cap: —",
                                           font=ctk.CTkFont(size=14, weight="bold"),
                                           text_color="#5ac8fa", anchor="w")
        self.var_cap_label.pack(padx=10, fill="x", pady=2)
        self.var_mp_label = ctk.CTkLabel(vars_panel, text="MP: —",
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          text_color="#0a84ff", anchor="w")
        self.var_mp_label.pack(padx=10, fill="x", pady=2)
        self.var_food_label = ctk.CTkLabel(vars_panel, text="Food: —",
                                            font=ctk.CTkFont(size=14, weight="bold"),
                                            text_color="#30d158", anchor="w")
        self.var_food_label.pack(padx=10, fill="x", pady=2)

        # ── Source Metadata ──
        meta_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        meta_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(meta_panel, text="Source Metadata",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 4))
        self.var_hp_source_label = ctk.CTkLabel(meta_panel, text="HP source: —",
                                                 font=ctk.CTkFont(size=10, family="Consolas"),
                                                 text_color="#777777", anchor="w")
        self.var_hp_source_label.pack(padx=10, fill="x", pady=2)
        self.var_mp_source_label = ctk.CTkLabel(meta_panel, text="MP source: —",
                                                 font=ctk.CTkFont(size=10, family="Consolas"),
                                                 text_color="#777777", anchor="w")
        self.var_mp_source_label.pack(padx=10, fill="x", pady=2)
        self.var_cap_source_label = ctk.CTkLabel(meta_panel, text="Cap source: —",
                                                  font=ctk.CTkFont(size=10, family="Consolas"),
                                                  text_color="#777777", anchor="w")
        self.var_cap_source_label.pack(padx=10, fill="x", pady=2)
        self.var_food_source_label = ctk.CTkLabel(meta_panel, text="Food source: —",
                                                   font=ctk.CTkFont(size=10, family="Consolas"),
                                                   text_color="#777777", anchor="w")
        self.var_food_source_label.pack(padx=10, fill="x", pady=2)

        addr_frame = ctk.CTkFrame(meta_panel, fg_color="transparent")
        addr_frame.pack(fill="x", padx=10, pady=(4, 0))
        self.var_hp_addr_label = ctk.CTkLabel(addr_frame, text="HP address: —",
                                               font=ctk.CTkFont(size=10, family="Consolas"),
                                               text_color="#777777", anchor="w")
        self.var_hp_addr_label.pack(fill="x", pady=1)
        self.var_mp_addr_label = ctk.CTkLabel(addr_frame, text="MP address: —",
                                               font=ctk.CTkFont(size=10, family="Consolas"),
                                               text_color="#777777", anchor="w")
        self.var_mp_addr_label.pack(fill="x", pady=1)
        self.var_cap_addr_label = ctk.CTkLabel(addr_frame, text="Cap address: —",
                                                font=ctk.CTkFont(size=10, family="Consolas"),
                                                text_color="#777777", anchor="w")
        self.var_cap_addr_label.pack(fill="x", pady=1)
        self.var_food_addr_label = ctk.CTkLabel(addr_frame, text="Food address: —",
                                                 font=ctk.CTkFont(size=10, family="Consolas"),
                                                 text_color="#777777", anchor="w")
        self.var_food_addr_label.pack(fill="x", pady=1)

        # ── Read Statistics ──
        stats_panel = ctk.CTkFrame(right, fg_color="transparent", border_width=1, border_color="#3a3a3a")
        stats_panel.pack(fill="both", expand=True, pady=(0, 8))
        ctk.CTkLabel(stats_panel, text="Read Statistics",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="#e8e8e8", anchor="w").pack(padx=10, pady=(8, 4))
        self.var_regen_label = ctk.CTkLabel(stats_panel, text="Regen: HP 0.0/min | Mana 0.0/min",
                                             font=ctk.CTkFont(size=10, family="Consolas"),
                                             text_color="#777777", anchor="w")
        self.var_regen_label.pack(padx=10, fill="x", pady=2)
        self.var_read_stats_label = ctk.CTkLabel(stats_panel, text="Reads: — | Misses: —",
                                                  font=ctk.CTkFont(size=10, family="Consolas"),
                                                  text_color="#777777", anchor="w")
        self.var_read_stats_label.pack(padx=10, fill="x", pady=2)
        self.var_last_update_label = ctk.CTkLabel(stats_panel, text="Last update: —",
                                                   font=ctk.CTkFont(size=10, family="Consolas"),
                                                   text_color="#777777", anchor="w")
        self.var_last_update_label.pack(padx=10, fill="x", pady=(10, 2))

    def refresh_display(self) -> None:
        state = self.runtime.state
        if self.services["hp_service"] is not None and hasattr(self.services["hp_service"], "_read_all_stats"):
            try:
                self.services["hp_service"]._read_all_stats()
            except Exception:
                logger.debug("Batch stats read failed")
        else:
            for service_name, method_name, log_name in [
                ("hp_service", "get_hp", "HP"),
                ("mp_service", "get_mp", "MP"),
                ("cap_service", "get_cap", "Cap"),
                ("food_service", "get_food", "Food"),
            ]:
                service = self.services.get(service_name)
                if service is None:
                    continue
                try:
                    getattr(service, method_name)()
                except Exception:
                    logger.debug("%s read failed", log_name)

        if self.var_level_label:
            self.var_level_label.configure(text=f"Level: {state.char_status_level if state.char_status_level is not None else '—'}")
        if self.var_hp_label:
            hp_display = state.hp_value if state.hp_value is not None else state.char_status_hp
            self.helpers["set_stat_label"](self.var_hp_label, hp_display, state.hp_source if state.hp_value is not None else None)
        if self.var_cap_label:
            cap_display = state.cap_value if state.cap_value is not None else state.char_status_cap
            self.helpers["set_stat_label"](self.var_cap_label, cap_display, state.cap_source if state.cap_value is not None else None)
        if self.var_mp_label:
            mp_display = state.mp_value if state.mp_value is not None else state.char_status_mana
            self.helpers["set_stat_label"](self.var_mp_label, mp_display, state.mp_source if state.mp_value is not None else None)
        if self.var_food_label:
            food_display = state.food_value if state.food_value is not None else state.char_status_food_seconds
            src = "pointer" if state.food_value is not None else ("ocr" if state.char_status_food_seconds is not None else "none")
            self.helpers["set_stat_label"](self.var_food_label, food_display, src)

        if self.var_hp_source_label:
            src = state.hp_source if state.hp_value is not None else ("ocr" if state.char_status_hp is not None else "none")
            self.var_hp_source_label.configure(text=f"HP source: {src}")
        if self.var_mp_source_label:
            src = state.mp_source if state.mp_value is not None else ("ocr" if state.char_status_mana is not None else "none")
            self.var_mp_source_label.configure(text=f"MP source: {src}")
        if self.var_cap_source_label:
            src = state.cap_source if state.cap_value is not None else ("ocr" if state.char_status_cap is not None else "none")
            self.var_cap_source_label.configure(text=f"Cap source: {src}")
        if self.var_food_source_label:
            src = state.food_source if state.food_value is not None else ("ocr" if state.char_status_food_seconds is not None else "none")
            self.var_food_source_label.configure(text=f"Food source: {src}")

        if self.var_hp_addr_label:
            self.var_hp_addr_label.configure(text=f"HP address: {state.hp_pointer_address_hex or '—'}")
        if self.var_mp_addr_label:
            self.var_mp_addr_label.configure(text=f"MP address: {state.mp_pointer_address_hex or '—'}")
        if self.var_cap_addr_label:
            self.var_cap_addr_label.configure(text=f"Cap address: {state.cap_pointer_address_hex or '—'}")
        if self.var_food_addr_label:
            self.var_food_addr_label.configure(text=f"Food address: {state.food_pointer_address_hex or '—'}")

        if self.var_regen_label:
            hp_regen = state.char_status_hp_regen_per_min if hasattr(state, "char_status_hp_regen_per_min") else 0.0
            mp_regen = state.char_status_mana_regen_per_min if hasattr(state, "char_status_mana_regen_per_min") else 0.0
            self.var_regen_label.configure(text=f"Regen: HP {hp_regen:.1f}/min | Mana {mp_regen:.1f}/min")
        if self.var_read_stats_label:
            reads = state.char_status_reads if hasattr(state, "char_status_reads") else 0
            misses = state.char_status_failures if hasattr(state, "char_status_failures") else 0
            self.var_read_stats_label.configure(text=f"Reads: {reads} | Misses: {misses}")
        if self.var_last_update_label:
            if state.char_status_last_seen:
                seen = time.strftime("%H:%M:%S", time.localtime(state.char_status_last_seen))
                peak_text = f"  |  HP max: {state.char_status_hp_peak}" if hasattr(state, "char_status_hp_peak") and state.char_status_hp_peak else ""
                reads = state.char_status_reads if hasattr(state, "char_status_reads") else 0
                self.var_last_update_label.configure(text=f"Last update: {seen}  |  Reads: {reads}{peak_text}")
            else:
                self.var_last_update_label.configure(text="Last update: —")
