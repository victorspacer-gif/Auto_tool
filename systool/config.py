"""Configuration serialization and deserialization."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import AppState, HotkeyJob


class ConfigSerializer:
    @staticmethod
    def to_dict(state: AppState) -> dict:
        jobs_data = [
            {
                "job_id": job.job_id,
                "key": job.key,
                "min_ms": job.min_ms,
                "max_ms": job.max_ms,
                "min_mana": job.min_mana,
                "burst": job.burst_enabled,
                "burst_chance": job.burst_chance,
                "burst_cnt_min": job.burst_cnt_min,
                "burst_cnt_max": job.burst_cnt_max,
                "burst_int_ms": job.burst_int_ms,
                "use_focus": job.use_focus,
                "window_name": job.window_name,
                "restore_focus": job.restore_focus,
            }
            for job in state.jobs
        ]
        return {
            "time_unit": state.time_unit,
            "jobs": jobs_data,
            "hotkey_bindings": dict(state.hotkey_bindings),
            "afk_min_ms": state.afk_min_ms,
            "afk_max_ms": state.afk_max_ms,
            "rclick_pos_x": state.rclick_pos[0],
            "rclick_pos_y": state.rclick_pos[1],
            "rclick_min_ms": state.rclick_min_ms,
            "rclick_max_ms": state.rclick_max_ms,
            "rclick_mode": state.rclick_mode,
            "rclick_require_food": state.rclick_require_food,
            "rclick_food_min_secs": state.rclick_food_min_secs,
            "rclick_food_burst_count": state.rclick_food_burst_count,
            "rclick_food_burst_interval_ms": state.rclick_food_burst_interval_ms,
            "alarm_mp3": state.alarm_mp3,
            "alarm_threshold": state.alarm_threshold,
            "alarm_cooldown": state.alarm_cooldown,
            "alarm_auto_pause": state.alarm_auto_pause,
            "alarm_hp_percent": state.alarm_hp_percent,
            "alarm_hp_value": state.alarm_hp_value,
            "alarm_mp_value": state.alarm_mp_value,
            "alarm_cap_value": state.alarm_cap_value,
            "alarm_region": list(state.alarm_region) if state.alarm_region else None,
            "char_status_region": list(state.char_status_region) if state.char_status_region else None,
            "char_status_hp_region": list(state.char_status_hp_region) if state.char_status_hp_region else None,
            "char_status_mana_region": list(state.char_status_mana_region) if state.char_status_mana_region else None,
            "char_status_cap_region": list(state.char_status_cap_region) if state.char_status_cap_region else None,
            "char_status_poll_ms": state.char_status_poll_ms,
            "char_status_tesseract_path": state.char_status_tesseract_path,
            "fish_rod_x": state.fish_rod_pos[0],
            "fish_rod_y": state.fish_rod_pos[1],
            "fish_spots": [[x, y] for x, y in state.fish_spots],
            "fish_cast_min_ms": state.fish_cast_min_ms,
            "fish_cast_max_ms": state.fish_cast_max_ms,
            "fish_wait_min_ms": state.fish_wait_min_ms,
            "fish_wait_max_ms": state.fish_wait_max_ms,
            "fish_rod_jitter": state.fish_rod_jitter,
            "fish_spot_jitter": state.fish_spot_jitter,
            "fish_session_minutes": state.fish_session_minutes,
            "fish_min_cap": state.fish_min_cap,
            "rune_spell_key": state.rune_spell_key,
            "rune_cycle_delay_ms": state.rune_cycle_delay_ms,
            "rune_cycle_delay_variation_ms": state.rune_cycle_delay_variation_ms,
            "rune_hand_x": state.rune_hand_pos[0],
            "rune_hand_y": state.rune_hand_pos[1],
            "rune_storage_x": state.rune_storage_pos[0],
            "rune_storage_y": state.rune_storage_pos[1],
            "rune_blank_x": state.rune_blank_pos[0],
            "rune_blank_y": state.rune_blank_pos[1],
            "rune_jitter": state.rune_jitter,
            "rune_cast_delay_ms": state.rune_cast_delay_ms,
            "rune_min_mana": state.rune_min_mana,
            "rune_available_blank_runes": state.rune_available_blank_runes,
            "rune_mouse_move_min_ms": state.rune_mouse_move_min_ms,
            "rune_mouse_move_max_ms": state.rune_mouse_move_max_ms,
            "rune_mouse_press_min_ms": state.rune_mouse_press_min_ms,
            "rune_mouse_press_max_ms": state.rune_mouse_press_max_ms,
            "rune_mouse_settle_min_ms": state.rune_mouse_settle_min_ms,
            "rune_mouse_settle_max_ms": state.rune_mouse_settle_max_ms,
            "healer_mode": state.healer_mode,
            "healer_spell_key": state.healer_spell_key,
            "healer_use_percent": state.healer_use_percent,
            "healer_hp_percent": state.healer_hp_percent,
            "healer_hp_value": state.healer_hp_value,
            "healer_min_mana": state.healer_min_mana,
            "healer_max_mana": state.healer_max_mana,
            "healer_character_x": state.healer_character_pos[0],
            "healer_character_y": state.healer_character_pos[1],
            "healer_rune_x": state.healer_rune_pos[0],
            "healer_rune_y": state.healer_rune_pos[1],
            "healer_mouse_speed": state.healer_mouse_speed,
            "healer_rune_delay_ms": state.healer_rune_delay_ms,
            "light_process_name": state.light_process_name,
            "light_direct_address_hex": state.light_direct_address_hex,
            "light_freeze_enabled": state.light_freeze_enabled,
            "light_freeze_color_value": state.light_freeze_color_value,
            "light_freeze_intensity_value": state.light_freeze_intensity_value,
            "light_freeze_interval_ms": state.light_freeze_interval_ms,
            "light_last_mode": state.light_last_mode,
            "light_last_color_address_hex": state.light_last_color_address_hex,
            "light_last_intensity_address_hex": state.light_last_intensity_address_hex,
            "light_original_color_value": state.light_original_color_value,
            "light_original_intensity_value": state.light_original_intensity_value,
            # Verbose logging toggles
            "afk_verbose": state.afk_verbose,
            "rclick_verbose": state.rclick_verbose,
            "alarm_verbose": state.alarm_verbose,
            "char_status_verbose": state.char_status_verbose,
            "fish_verbose": state.fish_verbose,
            "rune_verbose": state.rune_verbose,
            "healer_verbose": state.healer_verbose,
            "light_verbose": state.light_verbose,
            "sandbox_backend": state.sandbox_backend,
            "sandbox_box_name": state.sandbox_box_name,
            "sandbox_exe_path": state.sandbox_exe_path,
            "sandbox_args": state.sandbox_args,
            "sandbox_drop_admin": state.sandbox_drop_admin,
            "sandbox_spoof_env": state.sandbox_spoof_env,
        }

    @staticmethod
    def save_json(path: str, state: AppState) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(ConfigSerializer.to_dict(state), handle, indent=2)

    @staticmethod
    def save_xml(path: str, state: AppState) -> None:
        config = ConfigSerializer.to_dict(state)
        root = ET.Element("SystemMonitorConfig")
        jobs_el = ET.SubElement(root, "jobs")
        for job_data in config.pop("jobs", []):
            job_el = ET.SubElement(jobs_el, "job")
            for key, value in job_data.items():
                child = ET.SubElement(job_el, key)
                child.text = str(value)
        hotkeys_el = ET.SubElement(root, "hotkey_bindings")
        for key, value in config.pop("hotkey_bindings", {}).items():
            child = ET.SubElement(hotkeys_el, key)
            child.text = str(value)
        spots_el = ET.SubElement(root, "fish_spots")
        for x, y in config.pop("fish_spots", []):
            spot = ET.SubElement(spots_el, "spot")
            spot.text = f"{x},{y}"
        def _region_text(val):
            return ",".join(map(str, val)) if val else ""

        region = config.pop("alarm_region", None)
        region_el = ET.SubElement(root, "alarm_region")
        region_el.text = _region_text(region)
        csr = config.pop("char_status_region", None)
        csr_el = ET.SubElement(root, "char_status_region")
        csr_el.text = _region_text(csr)
        chr_el = config.pop("char_status_hp_region", None)
        char_hp_el = ET.SubElement(root, "char_status_hp_region")
        char_hp_el.text = _region_text(chr_el)
        cmr_el = config.pop("char_status_mana_region", None)
        char_mana_el = ET.SubElement(root, "char_status_mana_region")
        char_mana_el.text = _region_text(cmr_el)
        ccr_el = config.pop("char_status_cap_region", None)
        char_cap_el = ET.SubElement(root, "char_status_cap_region")
        char_cap_el.text = _region_text(ccr_el)
        for key, value in config.items():
            child = ET.SubElement(root, key)
            child.text = str(value)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def load_file(path: str) -> dict:
        if path.endswith(".xml"):
            return ConfigSerializer._load_xml(path)
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        return {
            "cfg": {key: str(value) for key, value in raw.items() if key not in {"jobs", "fish_spots", "alarm_region", "char_status_region", "char_status_hp_region", "char_status_mana_region", "char_status_cap_region", "hotkey_bindings"}},
            "jobs": raw.get("jobs", []),
            "spots": [tuple(item) for item in raw.get("fish_spots", [])],
            "alarm_region": tuple(raw["alarm_region"]) if raw.get("alarm_region") else None,
            "char_status_region": tuple(raw["char_status_region"]) if raw.get("char_status_region") else None,
            "char_status_hp_region": tuple(raw["char_status_hp_region"]) if raw.get("char_status_hp_region") else None,
            "char_status_mana_region": tuple(raw["char_status_mana_region"]) if raw.get("char_status_mana_region") else None,
            "char_status_cap_region": tuple(raw["char_status_cap_region"]) if raw.get("char_status_cap_region") else None,
            "hotkeys": raw.get("hotkey_bindings", {}),
        }

    @staticmethod
    def _load_xml(path: str) -> dict:
        root = ET.parse(path).getroot()
        cfg: dict[str, str] = {}
        jobs: list[dict] = []
        spots: list[tuple[int, int]] = []
        alarm_region = None
        char_status_region = None
        char_status_hp_region = None
        char_status_mana_region = None
        char_status_cap_region = None
        hotkeys: dict[str, str] = {}
        for child in root:
            if child.tag == "jobs":
                for job_el in child:
                    jobs.append({field.tag: field.text for field in job_el})
            elif child.tag == "fish_spots":
                for spot in child:
                    if spot.text:
                        x_val, y_val = spot.text.split(",")
                        spots.append((int(x_val), int(y_val)))
            elif child.tag == "alarm_region" and child.text:
                parts = child.text.split(",")
                if len(parts) == 4:
                    alarm_region = tuple(int(part) for part in parts)
            elif child.tag == "char_status_region" and child.text:
                parts = child.text.split(",")
                if len(parts) == 4:
                    char_status_region = tuple(int(part) for part in parts)
            elif child.tag == "char_status_hp_region" and child.text:
                parts = child.text.split(",")
                if len(parts) == 4:
                    char_status_hp_region = tuple(int(part) for part in parts)
            elif child.tag == "char_status_mana_region" and child.text:
                parts = child.text.split(",")
                if len(parts) == 4:
                    char_status_mana_region = tuple(int(part) for part in parts)
            elif child.tag == "char_status_cap_region" and child.text:
                parts = child.text.split(",")
                if len(parts) == 4:
                    char_status_cap_region = tuple(int(part) for part in parts)
            elif child.tag == "hotkey_bindings":
                hotkeys = {field.tag: field.text or "" for field in child}
            else:
                cfg[child.tag] = child.text or ""
        return {
            "cfg": cfg,
            "jobs": jobs,
            "spots": spots,
            "alarm_region": alarm_region,
            "char_status_region": char_status_region,
            "char_status_hp_region": char_status_hp_region,
            "char_status_mana_region": char_status_mana_region,
            "char_status_cap_region": char_status_cap_region,
            "hotkeys": hotkeys,
        }

    @staticmethod
    def apply_loaded(state: AppState, payload: dict) -> None:
        cfg = payload["cfg"]
        jobs = payload["jobs"]
        spots = payload["spots"]
        alarm_region = payload["alarm_region"]
        char_status_region = payload.get("char_status_region")
        char_status_hp_region = payload.get("char_status_hp_region")
        char_status_mana_region = payload.get("char_status_mana_region")
        char_status_cap_region = payload.get("char_status_cap_region")
        hotkeys = payload["hotkeys"]

        def get_int(name: str, default: int) -> int:
            try:
                return int(float(cfg.get(name, default)))
            except (TypeError, ValueError):
                return default

        def get_float(name: str, default: float) -> float:
            try:
                return float(cfg.get(name, default))
            except (TypeError, ValueError):
                return default

        def get_str(name: str, default: str) -> str:
            return str(cfg.get(name, default))

        def get_bool(name: str, default: bool) -> bool:
            return str(cfg.get(name, str(default))).lower() == "true"

        state.time_unit = get_str("time_unit", state.time_unit)
        state.afk_min_ms = get_int("afk_min_ms", state.afk_min_ms)
        state.afk_max_ms = get_int("afk_max_ms", state.afk_max_ms)
        state.rclick_pos = (
            get_int("rclick_pos_x", state.rclick_pos[0]),
            get_int("rclick_pos_y", state.rclick_pos[1]),
        )
        state.rclick_min_ms = get_int("rclick_min_ms", state.rclick_min_ms)
        state.rclick_max_ms = get_int("rclick_max_ms", state.rclick_max_ms)
        state.rclick_mode = get_str("rclick_mode", state.rclick_mode)
        state.rclick_require_food = get_bool("rclick_require_food", state.rclick_require_food)
        state.rclick_food_min_secs = max(0, get_int("rclick_food_min_secs", state.rclick_food_min_secs))
        state.rclick_food_burst_count = max(1, get_int("rclick_food_burst_count", state.rclick_food_burst_count))
        state.rclick_food_burst_interval_ms = max(50, get_int("rclick_food_burst_interval_ms", state.rclick_food_burst_interval_ms))
        state.alarm_mp3 = get_str("alarm_mp3", state.alarm_mp3)
        state.alarm_threshold = get_float("alarm_threshold", state.alarm_threshold)
        state.alarm_cooldown = get_int("alarm_cooldown", state.alarm_cooldown)
        state.alarm_auto_pause = get_bool("alarm_auto_pause", state.alarm_auto_pause)
        state.alarm_hp_percent = max(0, min(100, get_int("alarm_hp_percent", state.alarm_hp_percent)))
        state.alarm_hp_value = max(0, get_int("alarm_hp_value", state.alarm_hp_value))
        state.alarm_mp_value = max(0, get_int("alarm_mp_value", state.alarm_mp_value))
        state.alarm_cap_value = max(0, get_int("alarm_cap_value", state.alarm_cap_value))
        state.alarm_region = alarm_region
        state.char_status_region = char_status_region
        state.char_status_hp_region = char_status_hp_region
        state.char_status_mana_region = char_status_mana_region
        state.char_status_cap_region = char_status_cap_region
        state.char_status_poll_ms = max(250, get_int("char_status_poll_ms", state.char_status_poll_ms))
        state.char_status_tesseract_path = get_str("char_status_tesseract_path", state.char_status_tesseract_path)
        state.fish_rod_pos = (
            get_int("fish_rod_x", state.fish_rod_pos[0]),
            get_int("fish_rod_y", state.fish_rod_pos[1]),
        )
        state.fish_cast_min_ms = get_int("fish_cast_min_ms", state.fish_cast_min_ms)
        state.fish_cast_max_ms = get_int("fish_cast_max_ms", state.fish_cast_max_ms)
        state.fish_wait_min_ms = get_int("fish_wait_min_ms", state.fish_wait_min_ms)
        state.fish_wait_max_ms = get_int("fish_wait_max_ms", state.fish_wait_max_ms)
        state.fish_rod_jitter = get_int("fish_rod_jitter", state.fish_rod_jitter)
        state.fish_spot_jitter = get_int("fish_spot_jitter", state.fish_spot_jitter)
        state.fish_session_minutes = max(1, min(40, get_int("fish_session_minutes", state.fish_session_minutes)))
        state.fish_min_cap = max(0, get_int("fish_min_cap", state.fish_min_cap))
        state.fish_spots = list(spots)
        state.rune_spell_key = get_str("rune_spell_key", state.rune_spell_key)
        state.rune_cycle_delay_ms = get_int("rune_cycle_delay_ms", state.rune_cycle_delay_ms)
        state.rune_cycle_delay_variation_ms = max(
            0,
            get_int("rune_cycle_delay_variation_ms", state.rune_cycle_delay_variation_ms),
        )
        state.rune_hand_pos = (
            get_int("rune_hand_x", state.rune_hand_pos[0]),
            get_int("rune_hand_y", state.rune_hand_pos[1]),
        )
        state.rune_storage_pos = (
            get_int("rune_storage_x", state.rune_storage_pos[0]),
            get_int("rune_storage_y", state.rune_storage_pos[1]),
        )
        state.rune_blank_pos = (
            get_int("rune_blank_x", state.rune_blank_pos[0]),
            get_int("rune_blank_y", state.rune_blank_pos[1]),
        )
        state.rune_jitter = get_int("rune_jitter", state.rune_jitter)
        state.rune_cast_delay_ms = get_int("rune_cast_delay_ms", state.rune_cast_delay_ms)
        state.rune_min_mana = max(0, get_int("rune_min_mana", state.rune_min_mana))
        state.rune_available_blank_runes = max(
            0,
            get_int("rune_available_blank_runes", state.rune_available_blank_runes),
        )
        state.rune_mouse_move_min_ms = max(20, get_int("rune_mouse_move_min_ms", state.rune_mouse_move_min_ms))
        state.rune_mouse_move_max_ms = max(
            state.rune_mouse_move_min_ms,
            get_int("rune_mouse_move_max_ms", state.rune_mouse_move_max_ms),
        )
        state.rune_mouse_press_min_ms = max(10, get_int("rune_mouse_press_min_ms", state.rune_mouse_press_min_ms))
        state.rune_mouse_press_max_ms = max(
            state.rune_mouse_press_min_ms,
            get_int("rune_mouse_press_max_ms", state.rune_mouse_press_max_ms),
        )
        state.rune_mouse_settle_min_ms = max(
            10,
            get_int("rune_mouse_settle_min_ms", state.rune_mouse_settle_min_ms),
        )
        state.rune_mouse_settle_max_ms = max(
            state.rune_mouse_settle_min_ms,
            get_int("rune_mouse_settle_max_ms", state.rune_mouse_settle_max_ms),
        )
        state.healer_mode = get_str("healer_mode", state.healer_mode)
        state.healer_spell_key = get_str("healer_spell_key", state.healer_spell_key)
        state.healer_use_percent = get_bool("healer_use_percent", state.healer_use_percent)
        state.healer_hp_percent = max(1, min(100, get_int("healer_hp_percent", state.healer_hp_percent)))
        state.healer_hp_value = max(1, get_int("healer_hp_value", state.healer_hp_value))
        state.healer_min_mana = max(0, get_int("healer_min_mana", state.healer_min_mana))
        state.healer_max_mana = max(state.healer_min_mana, get_int("healer_max_mana", state.healer_max_mana))
        state.healer_character_pos = (
            get_int("healer_character_x", state.healer_character_pos[0]),
            get_int("healer_character_y", state.healer_character_pos[1]),
        )
        state.healer_rune_pos = (
            get_int("healer_rune_x", state.healer_rune_pos[0]),
            get_int("healer_rune_y", state.healer_rune_pos[1]),
        )
        state.healer_mouse_speed = max(0.2, min(3.0, get_float("healer_mouse_speed", state.healer_mouse_speed)))
        state.healer_rune_delay_ms = max(50, get_int("healer_rune_delay_ms", state.healer_rune_delay_ms))
        state.light_process_name = get_str("light_process_name", state.light_process_name)
        state.light_direct_address_hex = get_str("light_direct_address_hex", state.light_direct_address_hex)
        state.sandbox_backend = get_str("sandbox_backend", state.sandbox_backend)
        state.sandbox_box_name = get_str("sandbox_box_name", state.sandbox_box_name)
        state.sandbox_exe_path = get_str("sandbox_exe_path", state.sandbox_exe_path)
        state.sandbox_args = get_str("sandbox_args", state.sandbox_args)
        state.sandbox_drop_admin = get_bool("sandbox_drop_admin", state.sandbox_drop_admin)
        state.sandbox_spoof_env = get_bool("sandbox_spoof_env", state.sandbox_spoof_env)
        state.light_freeze_enabled = get_bool("light_freeze_enabled", state.light_freeze_enabled)
        state.light_freeze_color_value = max(0, min(255, get_int("light_freeze_color_value", state.light_freeze_color_value)))
        state.light_freeze_intensity_value = max(0, min(255, get_int("light_freeze_intensity_value", state.light_freeze_intensity_value)))
        state.light_freeze_interval_ms = max(30, get_int("light_freeze_interval_ms", state.light_freeze_interval_ms))
        state.light_last_mode = get_str("light_last_mode", state.light_last_mode)
        state.light_last_color_address_hex = get_str("light_last_color_address_hex", state.light_last_color_address_hex)
        state.light_last_intensity_address_hex = get_str("light_last_intensity_address_hex", state.light_last_intensity_address_hex)
        raw_original_color = cfg.get("light_original_color_value")
        raw_original_intensity = cfg.get("light_original_intensity_value")
        state.light_original_color_value = None if raw_original_color in (None, "", "None") else max(0, min(255, get_int("light_original_color_value", 0)))
        state.light_original_intensity_value = None if raw_original_intensity in (None, "", "None") else max(0, min(255, get_int("light_original_intensity_value", 0)))

        # Verbose logging toggles
        state.afk_verbose = get_bool("afk_verbose", False)
        state.rclick_verbose = get_bool("rclick_verbose", False)
        state.alarm_verbose = get_bool("alarm_verbose", False)
        state.char_status_verbose = get_bool("char_status_verbose", False)
        state.fish_verbose = get_bool("fish_verbose", False)
        state.rune_verbose = get_bool("rune_verbose", False)
        state.healer_verbose = get_bool("healer_verbose", False)
        state.light_verbose = get_bool("light_verbose", False)

        for action, binding in hotkeys.items():
            if action in state.hotkey_bindings:
                state.hotkey_bindings[action] = binding

        state.jobs = []
        state.job_counter = 0
        for job_data in jobs:
            job = HotkeyJob(
                job_id=int(float(job_data.get("job_id", 0) or 0)) or len(state.jobs) + 1,
                key=job_data.get("key", "F1"),
                min_ms=int(float(job_data.get("min_ms", 1000))),
                max_ms=int(float(job_data.get("max_ms", 3000))),
                min_mana=int(float(job_data.get("min_mana", 0) or 0)),
                burst_enabled=str(job_data.get("burst", "false")).lower() == "true",
                burst_chance=float(job_data.get("burst_chance", 0.2)),
                burst_cnt_min=int(job_data.get("burst_cnt_min", 3)),
                burst_cnt_max=int(job_data.get("burst_cnt_max", 8)),
                burst_int_ms=int(job_data.get("burst_int_ms", 80)),
                use_focus=str(job_data.get("use_focus", "false")).lower() == "true",
                window_name=job_data.get("window_name", ""),
                restore_focus=str(job_data.get("restore_focus", "true")).lower() == "true",
            )
            state.jobs.append(job)
            state.job_counter = max(state.job_counter, job.job_id)
