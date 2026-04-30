"""Configuration serialization and deserialization."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, fields, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import AppState

logger = logging.getLogger(__name__)


# Default user-facing numeric configuration values.
HOTKEY_JOB_MIN_MS_DEFAULT: int = 20_000
HOTKEY_JOB_MAX_MS_DEFAULT: int = 30_000
HOTKEY_JOB_MIN_MANA_DEFAULT: int = 20
HOTKEY_JOB_MAX_MANA_DEFAULT: int = 35
HOTKEY_JOB_BURST_CHANCE_DEFAULT: float = 0.20
HOTKEY_JOB_BURST_COUNT_MIN_DEFAULT: int = 2
HOTKEY_JOB_BURST_COUNT_MAX_DEFAULT: int = 4
HOTKEY_JOB_BURST_INTERVAL_MS_DEFAULT: int = 80

ALARM_THRESHOLD_RATIO_DEFAULT: float = 0.80
ALARM_COOLDOWN_SECONDS_DEFAULT: int = 10

CHAR_STATUS_POLL_MS_DEFAULT: int = 800
CHAR_STATUS_SAMPLES_DEFAULT: int = 3
CHAR_STATUS_SAMPLE_DELAY_MS_DEFAULT: int = 100

FISH_CAST_MIN_MS_DEFAULT: int = 500
FISH_CAST_MAX_MS_DEFAULT: int = 1000
FISH_WAIT_MIN_MS_DEFAULT: int = 500
FISH_WAIT_MAX_MS_DEFAULT: int = 1000
FISH_ROD_JITTER_DEFAULT: int = 5
FISH_SPOT_JITTER_DEFAULT: int = 15
FISH_SESSION_MINUTES_DEFAULT: int = 10
FISH_AUTO_RESTART_FOOD_MIN_SECS_DEFAULT: int = 300
FISH_MOUSE_SPEED_DEFAULT: float = 0.40

RUNE_CYCLE_DELAY_MS_DEFAULT: int = 70000
RUNE_CYCLE_DELAY_VARIATION_MS_DEFAULT: int = 2000
RUNE_JITTER_DEFAULT: int = 5
RUNE_CAST_DELAY_MS_DEFAULT: int = 1000
RUNE_POST_CAST_SETTLE_MS_DEFAULT: int = 2000
RUNE_MOUSE_MOVE_MIN_MS_DEFAULT: int = 180
RUNE_MOUSE_MOVE_MAX_MS_DEFAULT: int = 350
RUNE_MOUSE_PRESS_MIN_MS_DEFAULT: int = 60
RUNE_MOUSE_PRESS_MAX_MS_DEFAULT: int = 120
RUNE_MOUSE_SETTLE_MIN_MS_DEFAULT: int = 100
RUNE_MOUSE_SETTLE_MAX_MS_DEFAULT: int = 220

HEALER_HP_PERCENT_DEFAULT: int = 60
HEALER_HP_VALUE_DEFAULT: int = 120
HEALER_MOUSE_SPEED_DEFAULT: float = 0.40
HEALER_RUNE_DELAY_MS_DEFAULT: int = 250

APP_AFK_MIN_MS_DEFAULT: int = 70_000
APP_AFK_MAX_MS_DEFAULT: int = 88_000
APP_RCLICK_MIN_MS_DEFAULT: int = 160000
APP_RCLICK_MAX_MS_DEFAULT: int = 90000
APP_RCLICK_FOOD_MIN_MINUTES_DEFAULT: int = 10
APP_RCLICK_FOOD_BURST_COUNT_DEFAULT: int = 2
APP_RCLICK_FOOD_BURST_COUNT_MIN_DEFAULT: int = 2
APP_RCLICK_FOOD_BURST_COUNT_MAX_DEFAULT: int = 4
APP_RCLICK_FOOD_BURST_INTERVAL_MS_DEFAULT: int = 200
APP_RCLICK_CLICK_DELAY_MIN_MS_DEFAULT: int = 150
APP_RCLICK_CLICK_DELAY_MAX_MS_DEFAULT: int = 250
APP_RCLICK_POST_CLICK_SETTLE_MS_DEFAULT: int = 300
APP_LIGHT_FREEZE_INTERVAL_MS_DEFAULT: int = 1_000

# Validation and clamping bounds for persisted/user-provided values.
FOOD_TIMER_MIN_MINUTES_MIN: int = 1
FOOD_TIMER_MIN_MINUTES_MAX: int = 40
RCLICK_FOOD_BURST_COUNT_MIN: int = 1
RCLICK_FOOD_BURST_INTERVAL_MS_MIN: int = 50
RCLICK_CLICK_DELAY_MS_MIN: int = 100
RCLICK_POST_CLICK_SETTLE_MS_MIN: int = 100
PERCENT_VALUE_MIN: int = 0
PERCENT_VALUE_MAX: int = 100
CHAR_STATUS_POLL_MS_MIN: int = 250
FISH_SESSION_MINUTES_MIN: int = 1
FISH_SESSION_MINUTES_MAX: int = 40
FISH_AUTO_RESTART_FOOD_MIN_SECS_MIN: int = 30
FISH_AUTO_RESTART_FOOD_MIN_SECS_MAX: int = 600
NON_NEGATIVE_INT_MIN: int = 0
RUNE_MOUSE_MOVE_MS_MIN: int = 20
RUNE_MOUSE_PRESS_MS_MIN: int = 10
RUNE_MOUSE_SETTLE_MS_MIN: int = 10
HEALER_HP_MIN: int = 1
HEALER_MOUSE_SPEED_MIN: float = 0.2
HEALER_MOUSE_SPEED_MAX: float = 3.0
FISH_MOUSE_SPEED_MIN: float = 0.25
FISH_MOUSE_SPEED_MAX: float = 3.0
HEALER_RUNE_DELAY_MS_MIN: int = 50
BYTE_VALUE_MIN: int = 0
BYTE_VALUE_MAX: int = 255
LIGHT_FREEZE_INTERVAL_MS_MIN: int = 30

# Defaults used when reading legacy or incomplete saved job payloads.
JOB_JSON_MIN_MS_DEFAULT: int = 1_000
JOB_JSON_MAX_MS_DEFAULT: int = 3_000


# Fields that need special handling during serialization (non-dataclass types).
_JSON_SPECIAL = frozenset({
    "hotkey_bindings", "jobs", "fish_spots",
})


def _flatten(dataclass_obj: Any, prefix: str = "") -> dict[str, object]:
    """Flatten a dataclass into a dot-notation dict.

    Recursively flattens nested dataclasses and converts tuples/lists to lists
    for JSON compatibility.
    """
    result: dict[str, object] = {}
    if not is_dataclass(dataclass_obj):
        return result

    for f in fields(dataclass_obj):
        key = f"{prefix}.{f.name}" if prefix else f.name
        value = getattr(dataclass_obj, f.name)

        if is_dataclass(value):
            # Recursively flatten nested dataclasses
            nested = _flatten(value, key)
            result.update(nested)
        elif isinstance(value, tuple):
            result[key] = list(value)
        elif isinstance(value, (list,)):
            # Convert inner tuples/lists to lists for JSON compatibility
            result[key] = [
                list(item) if isinstance(item, (tuple, list)) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


class ConfigSerializer:

    @staticmethod
    def _to_json_compatible(value: Any) -> Any:
        """Convert a value to JSON-compatible form (tuples → lists, etc.)."""
        if isinstance(value, tuple):
            return list(value)
        elif isinstance(value, list):
            return [ConfigSerializer._to_json_compatible(item) for item in value]
        return value

    @staticmethod
    def to_dict(state: AppState) -> dict:
        """Serialize AppState → flat dict compatible with existing JSON.

        Uses dataclasses.asdict() + _flatten() for nested state objects,
        then merges special fields (hotkey_bindings, jobs, fish_spots).
        """
        result: dict[str, object] = {}

        # Flatten all nested dataclass groups using asdict-based approach.
        for group_name in ("alarm", "char_status", "fishing", "rune", "healer"):
            group_obj = getattr(state, group_name)
            if is_dataclass(group_obj):
                flat = _flatten(group_obj)
                # Flatten the dict keys to dot-notation (already done by _flatten).
                for k, v in flat.items():
                    result[f"{group_name}.{k}"] = ConfigSerializer._to_json_compatible(v)

        # Also flatten sandbox state.
        if is_dataclass(state.sandbox):
            flat = _flatten(state.sandbox)
            for k, v in flat.items():
                result[f"sandbox.{k}"] = ConfigSerializer._to_json_compatible(v)

        # Direct AppState attributes (non-dataclass).
        direct_attrs = [
            "afk_min_ms", "afk_max_ms",
            "rclick_min_ms", "rclick_max_ms",
            "rclick_mode", "rclick_require_food",
            "rclick_food_min_minutes", "rclick_food_burst_count",
            "rclick_food_burst_count_min", "rclick_food_burst_count_max",
            "rclick_food_burst_interval_ms",
            "rclick_click_delay_min_ms", "rclick_click_delay_max_ms",
            "rclick_post_click_settle_ms",
            "light_process_name", "light_direct_address_hex",
            "light_freeze_enabled", "light_freeze_color_value",
            "light_freeze_intensity_value", "light_freeze_interval_ms",
            "light_last_mode", "light_last_color_address_hex",
            "light_last_intensity_address_hex",
            "hp_pointer_address_hex", "hp_source", "hp_value",
            "mp_pointer_address_hex", "mp_source", "mp_value",
            "cap_pointer_address_hex", "cap_source", "cap_value",
        ]
        for attr in direct_attrs:
            result[attr] = ConfigSerializer._to_json_compatible(getattr(state, attr))

        # Split position tuples into x/y keys (deserializer expects separate fields).
        rclick_pos = getattr(state, "rclick_pos")
        if isinstance(rclick_pos, tuple):
            result["rclick_pos_x"] = rclick_pos[0]
            result["rclick_pos_y"] = rclick_pos[1]

        # Special fields that don't fit the dataclass flattening pattern.
        result["hotkey_bindings"] = dict(state.hotkey_bindings)
        result["jobs"] = [
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

        # Convert fish_spots list of tuples → list of lists for JSON.
        spots = getattr(state, "fish_spots")
        if isinstance(spots, (list, tuple)):
            result["fish_spots"] = [ConfigSerializer._to_json_compatible(s) for s in spots]

        return result

    @staticmethod
    def save_json(path: str, state: AppState) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(ConfigSerializer.to_dict(state), handle, indent=2)

    # ── Deserialization ─────────────────────────────────────────────

    @staticmethod
    def load_file(path: str) -> dict:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)

        # Separate scalar fields from complex types.
        cfg: dict[str, object] = {}
        for key, value in raw.items():
            if key not in _JSON_SPECIAL:
                cfg[key] = str(value)

        return {
            "cfg": cfg,
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
        from .models import HotkeyJob

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

        # ── AFK ───────────────────────────────────────────────────────
        state.afk_min_ms = get_int("afk_min_ms", state.afk_min_ms)
        state.afk_max_ms = get_int("afk_max_ms", state.afk_max_ms)

        # ── Right-click ───────────────────────────────────────────────
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
            max(FOOD_TIMER_MIN_MINUTES_MIN, round(legacy_food_secs / 60)),
        )
        state.rclick_food_min_minutes = max(FOOD_TIMER_MIN_MINUTES_MIN, min(FOOD_TIMER_MIN_MINUTES_MAX, food_minutes))

        state.rclick_food_burst_count = max(RCLICK_FOOD_BURST_COUNT_MIN, get_int("rclick_food_burst_count", state.rclick_food_burst_count))
        state.rclick_food_burst_count_min = max(RCLICK_FOOD_BURST_COUNT_MIN, get_int("rclick_food_burst_count_min", state.rclick_food_burst_count_min))
        state.rclick_food_burst_count_max = max(
            state.rclick_food_burst_count_min,
            get_int("rclick_food_burst_count_max", state.rclick_food_burst_count_max),
        )
        state.rclick_food_burst_interval_ms = max(RCLICK_FOOD_BURST_INTERVAL_MS_MIN, get_int("rclick_food_burst_interval_ms", state.rclick_food_burst_interval_ms))
        state.rclick_click_delay_min_ms = max(RCLICK_CLICK_DELAY_MS_MIN, get_int("rclick_click_delay_min_ms", state.rclick_click_delay_min_ms))
        state.rclick_click_delay_max_ms = max(
            state.rclick_click_delay_min_ms,
            get_int("rclick_click_delay_max_ms", state.rclick_click_delay_max_ms),
        )
        state.rclick_post_click_settle_ms = max(RCLICK_POST_CLICK_SETTLE_MS_MIN, get_int("rclick_post_click_settle_ms", state.rclick_post_click_settle_ms))

        # ── Alarm ─────────────────────────────────────────────────────
        state.alarm.mp3 = get_str("alarm_mp3", state.alarm.mp3)
        state.alarm.threshold = get_float("alarm_threshold", state.alarm.threshold)
        state.alarm.cooldown = get_int("alarm_cooldown", state.alarm.cooldown)
        state.alarm.auto_pause = get_bool("alarm_auto_pause", state.alarm.auto_pause)
        state.alarm.hp_percent = max(PERCENT_VALUE_MIN, min(PERCENT_VALUE_MAX, get_int("alarm_hp_percent", state.alarm.hp_percent)))
        state.alarm.hp_value = max(NON_NEGATIVE_INT_MIN, get_int("alarm_hp_value", state.alarm_hp_value))
        state.alarm.mp_value = max(NON_NEGATIVE_INT_MIN, get_int("alarm_mp_value", state.alarm_mp_value))
        state.alarm.cap_value = max(NON_NEGATIVE_INT_MIN, get_int("alarm_cap_value", state.alarm_cap_value))
        state.alarm.region = alarm_region

        # ── Char-status ───────────────────────────────────────────────
        state.char_status.region = char_status_region
        state.char_status.hp_region = char_status_hp_region
        state.char_status.mana_region = char_status_mana_region
        state.char_status.cap_region = char_status_cap_region
        state.char_status.poll_ms = max(CHAR_STATUS_POLL_MS_MIN, get_int("char_status_poll_ms", state.char_status.poll_ms))
        state.char_status.tesseract_path = get_str("char_status_tesseract_path", state.char_status.tesseract_path)

        # ── Fishing ───────────────────────────────────────────────────
        # All keys use dot-notation (e.g., "fishing.cast_min_ms") to match _flatten output.
        rod_pos_str = cfg.get("fishing.rod_pos", "[0, 0]")
        try:
            rod_list = json.loads(rod_pos_str) if isinstance(rod_pos_str, str) else list(rod_pos_str)
            state.fishing.rod_pos = (int(rod_list[0]), int(rod_list[1]))
        except (TypeError, ValueError):
            pass  # keep current value

        state.fishing.cast_min_ms = get_int("fishing.cast_min_ms", state.fishing.cast_min_ms)
        state.fishing.cast_max_ms = get_int("fishing.cast_max_ms", state.fishing.cast_max_ms)
        state.fishing.wait_min_ms = get_int("fishing.wait_min_ms", state.fishing.wait_min_ms)
        state.fishing.wait_max_ms = get_int("fishing.wait_max_ms", state.fishing.wait_max_ms)
        state.fishing.rod_jitter = get_int("fishing.rod_jitter", state.fishing.rod_jitter)
        state.fishing.spot_jitter = get_int("fishing.spot_jitter", state.fishing.spot_jitter)
        state.fishing.session_minutes = max(FISH_SESSION_MINUTES_MIN, min(FISH_SESSION_MINUTES_MAX, get_int("fishing.session_minutes", state.fishing.session_minutes)))
        state.fishing.min_cap = max(NON_NEGATIVE_INT_MIN, get_int("fishing.min_cap", state.fishing.min_cap))
        state.fishing.auto_restart_enabled = bool(get_bool("fishing.auto_restart_enabled", state.fishing.auto_restart_enabled))
        state.fishing.auto_restart_food_min_secs = max(FISH_AUTO_RESTART_FOOD_MIN_SECS_MIN, min(FISH_AUTO_RESTART_FOOD_MIN_SECS_MAX, get_int("fishing.auto_restart_food_min_secs", state.fishing.auto_restart_food_min_secs)))
        # Mouse speed multiplier — higher = faster movement (duration divided by this value).
        # Mirrors the same formula used in HealerState.mouse_speed.
        state.fishing.mouse_speed = max(FISH_MOUSE_SPEED_MIN, min(FISH_MOUSE_SPEED_MAX, get_float("fishing.mouse_speed", state.fishing.mouse_speed)))
        state.fish_spots = list(spots)

        # ── Rune ──────────────────────────────────────────────────────
        state.rune.spell_key = get_str("rune_spell_key", state.rune.spell_key)
        state.rune.cycle_delay_ms = get_int("rune_cycle_delay_ms", state.rune.cycle_delay_ms)
        state.rune.cycle_delay_variation_ms = max(NON_NEGATIVE_INT_MIN, get_int("rune_cycle_delay_variation_ms", state.rune.cycle_delay_variation_ms))
        state.rune.hand_pos = (
            get_int("rune_hand_x", state.rune.hand_pos[0]),
            get_int("rune_hand_y", state.rune.hand_pos[1]),
        )
        state.rune.storage_pos = (
            get_int("rune_storage_x", state.rune.storage_pos[0]),
            get_int("rune_storage_y", state.rune.storage_pos[1]),
        )
        state.rune.blank_pos = (
            get_int("rune_blank_x", state.rune.blank_pos[0]),
            get_int("rune_blank_y", state.rune.blank_pos[1]),
        )
        state.rune.jitter = get_int("rune_jitter", state.rune.jitter)
        state.rune.cast_delay_ms = get_int("rune_cast_delay_ms", state.rune.cast_delay_ms)
        state.rune.min_mana = max(NON_NEGATIVE_INT_MIN, get_int("rune_min_mana", state.rune.min_mana))
        state.rune.available_blank_runes = max(NON_NEGATIVE_INT_MIN, get_int("rune_available_blank_runes", state.rune_available_blank_runes))
        state.rune.mouse_move_min_ms = max(RUNE_MOUSE_MOVE_MS_MIN, get_int("rune_mouse_move_min_ms", state.rune.mouse_move_min_ms))
        state.rune.mouse_move_max_ms = max(state.rune.mouse_move_min_ms, get_int("rune_mouse_move_max_ms", state.rune.mouse_move_max_ms))
        state.rune.mouse_press_min_ms = max(RUNE_MOUSE_PRESS_MS_MIN, get_int("rune_mouse_press_min_ms", state.rune.mouse_press_min_ms))
        state.rune.mouse_press_max_ms = max(state.rune.mouse_press_min_ms, get_int("rune_mouse_press_max_ms", state.rune.mouse_press_max_ms))
        state.rune.mouse_settle_min_ms = max(RUNE_MOUSE_SETTLE_MS_MIN, get_int("rune_mouse_settle_min_ms", state.rune.mouse_settle_min_ms))
        state.rune.mouse_settle_max_ms = max(state.rune.mouse_settle_min_ms, get_int("rune_mouse_settle_max_ms", state.rune.mouse_settle_max_ms))

        # ── Healer ────────────────────────────────────────────────────
        state.healer.mode = get_str("healer_mode", state.healer.mode)
        state.healer.spell_key = get_str("healer_spell_key", state.healer.spell_key)
        state.healer.use_percent = get_bool("healer_use_percent", state.healer.use_percent)
        state.healer.hp_percent = max(HEALER_HP_MIN, min(PERCENT_VALUE_MAX, get_int("healer_hp_percent", state.healer.hp_percent)))
        state.healer.hp_value = max(HEALER_HP_MIN, get_int("healer_hp_value", state.healer_hp_value))
        state.healer.min_mana = max(NON_NEGATIVE_INT_MIN, get_int("healer_min_mana", state.healer.min_mana))
        state.healer.max_mana = max(state.healer.min_mana, get_int("healer_max_mana", state.healer_max_mana))
        state.healer.character_pos = (
            get_int("healer_character_x", state.healer.character_pos[0]),
            get_int("healer_character_y", state.healer.character_pos[1]),
        )
        state.healer.rune_pos = (
            get_int("healer_rune_x", state.healer.rune_pos[0]),
            get_int("healer_rune_y", state.healer.rune_pos[1]),
        )
        state.healer.mouse_speed = max(HEALER_MOUSE_SPEED_MIN, min(HEALER_MOUSE_SPEED_MAX, get_float("healer_mouse_speed", state.healer.mouse_speed)))
        state.healer.rune_delay_ms = max(HEALER_RUNE_DELAY_MS_MIN, get_int("healer_rune_delay_ms", state.healer.rune_delay_ms))

        # ── Light ─────────────────────────────────────────────────────
        state.light_process_name = get_str("light_process_name", state.light_process_name)
        state.light_direct_address_hex = get_str("light_direct_address_hex", state.light_direct_address_hex)
        state.sandbox.backend = get_str("sandbox_backend", state.sandbox.backend)
        state.sandbox.box_name = get_str("sandbox_box_name", state.sandbox.box_name)
        state.sandbox.exe_path = get_str("sandbox_exe_path", state.sandbox.exe_path)
        state.sandbox.args = get_str("sandbox_args", state.sandbox.args)
        state.sandbox.drop_admin = get_bool("sandbox_drop_admin", state.sandbox.drop_admin)
        state.sandbox.spoof_env = get_bool("sandbox_spoof_env", state.sandbox.spoof_env)
        state.light_freeze_enabled = get_bool("light_freeze_enabled", state.light_freeze_enabled)
        state.light_freeze_color_value = max(BYTE_VALUE_MIN, min(BYTE_VALUE_MAX, get_int("light_freeze_color_value", state.light_freeze_color_value)))
        state.light_freeze_intensity_value = max(BYTE_VALUE_MIN, min(BYTE_VALUE_MAX, get_int("light_freeze_intensity_value", state.light_freeze_intensity_value)))
        state.light_freeze_interval_ms = max(LIGHT_FREEZE_INTERVAL_MS_MIN, get_int("light_freeze_interval_ms", state.light_freeze_interval_ms))
        state.light_last_mode = get_str("light_last_mode", state.light_last_mode)
        state.light_last_color_address_hex = get_str("light_last_color_address_hex", state.light_last_color_address_hex)
        state.light_last_intensity_address_hex = get_str("light_last_intensity_address_hex", state.light_last_intensity_address_hex)

        raw_original_color = cfg.get("light_original_color_value")
        raw_original_intensity = cfg.get("light_original_intensity_value")
        state.light_original_color_value = None if raw_original_color in (None, "", "None") else max(BYTE_VALUE_MIN, min(BYTE_VALUE_MAX, get_int("light_original_color_value", 0)))
        state.light_original_intensity_value = None if raw_original_intensity in (None, "", "None") else max(BYTE_VALUE_MIN, min(BYTE_VALUE_MAX, get_int("light_original_intensity_value", 0)))

        # ── Hotkeys & jobs ────────────────────────────────────────────
        for action, binding in hotkeys.items():
            if action in state.hotkey_bindings:
                state.hotkey_bindings[action] = binding

        state.jobs = []
        state.job_counter = 0
        for job_data in jobs:
            job = HotkeyJob(
                job_id=int(float(job_data.get("job_id", 0) or 0)) or len(state.jobs) + 1,
                key=job_data.get("key", "F1"),
                min_ms=int(float(job_data.get("min_ms", JOB_JSON_MIN_MS_DEFAULT))),
                max_ms=int(float(job_data.get("max_ms", JOB_JSON_MAX_MS_DEFAULT))),
                min_mana=int(float(job_data.get("min_mana", HOTKEY_JOB_MIN_MANA_DEFAULT) or 0)),
                burst_enabled=str(job_data.get("burst", "false")).lower() == "true",
                burst_chance=float(job_data.get("burst_chance", HOTKEY_JOB_BURST_CHANCE_DEFAULT)),
                burst_cnt_min=int(job_data.get("burst_cnt_min", HOTKEY_JOB_BURST_COUNT_MIN_DEFAULT)),
                burst_cnt_max=int(job_data.get("burst_cnt_max", HOTKEY_JOB_BURST_COUNT_MAX_DEFAULT)),
                burst_int_ms=int(job_data.get("burst_int_ms", HOTKEY_JOB_BURST_INTERVAL_MS_DEFAULT)),
                use_focus=str(job_data.get("use_focus", "false")).lower() == "true",
                window_name=job_data.get("window_name", ""),
                restore_focus=str(job_data.get("restore_focus", "true")).lower() == "true",
            )
            state.jobs.append(job)
            state.job_counter = max(state.job_counter, job.job_id)
