"""Configuration serialization and deserialization."""

from __future__ import annotations

import json

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
            "rclick_food_min_minutes": state.rclick_food_min_minutes,
            "rclick_food_burst_count": state.rclick_food_burst_count,
            "rclick_food_burst_count_min": state.rclick_food_burst_count_min,
            "rclick_food_burst_count_max": state.rclick_food_burst_count_max,
            "rclick_food_burst_interval_ms": state.rclick_food_burst_interval_ms,
            "rclick_click_delay_min_ms": state.rclick_click_delay_min_ms,
            "rclick_click_delay_max_ms": state.rclick_click_delay_max_ms,
            "rclick_post_click_settle_ms": state.rclick_post_click_settle_ms,
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
            "fish_auto_restart_enabled": state.fish_auto_restart_enabled,
            "fish_auto_restart_food_min_secs": state.fish_auto_restart_food_min_secs,
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
    def load_file(path: str) -> dict:
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
        legacy_food_secs = get_int("rclick_food_min_secs", state.rclick_food_min_minutes * 60)
        food_minutes = get_int(
            "rclick_food_min_minutes",
            max(1, round(legacy_food_secs / 60)),
        )
        state.rclick_food_min_minutes = max(1, min(40, food_minutes))
        state.rclick_food_burst_count = max(1, get_int("rclick_food_burst_count", state.rclick_food_burst_count))
        state.rclick_food_burst_count_min = max(1, get_int("rclick_food_burst_count_min", state.rclick_food_burst_count_min))
        state.rclick_food_burst_count_max = max(
            state.rclick_food_burst_count_min,
            get_int("rclick_food_burst_count_max", state.rclick_food_burst_count_max),
        )
        state.rclick_food_burst_interval_ms = max(50, get_int("rclick_food_burst_interval_ms", state.rclick_food_burst_interval_ms))
        state.rclick_click_delay_min_ms = max(100, get_int("rclick_click_delay_min_ms", state.rclick_click_delay_min_ms))
        state.rclick_click_delay_max_ms = max(
            state.rclick_click_delay_min_ms,
            get_int("rclick_click_delay_max_ms", state.rclick_click_delay_max_ms),
        )
        state.rclick_post_click_settle_ms = max(100, get_int("rclick_post_click_settle_ms", state.rclick_post_click_settle_ms))
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
        state.fish_auto_restart_enabled = bool(get_bool("fish_auto_restart_enabled", state.fish_auto_restart_enabled))
        state.fish_auto_restart_food_min_secs = max(30, min(600, get_int("fish_auto_restart_food_min_secs", state.fish_auto_restart_food_min_secs)))
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
