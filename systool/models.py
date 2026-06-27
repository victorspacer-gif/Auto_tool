"""Domain models used across the application."""

from __future__ import annotations

import dataclasses
import threading
from typing import Any

from . import config as app_config


def _group_property(group_name: str, attr_name: str):
    def getter(self):
        return getattr(getattr(self, group_name), attr_name)

    def setter(self, value):
        setattr(getattr(self, group_name), attr_name, value)

    return property(getter, setter)


@dataclasses.dataclass
class HotkeyJob:
    job_id: int
    key: str = "F1"
    min_ms: int = app_config.HOTKEY_JOB_MIN_MS_DEFAULT
    max_ms: int = app_config.HOTKEY_JOB_MAX_MS_DEFAULT
    min_mana: int = app_config.HOTKEY_JOB_MIN_MANA_DEFAULT
    max_mana: int = app_config.HOTKEY_JOB_MAX_MANA_DEFAULT
    burst_enabled: bool = False
    burst_chance: float = app_config.HOTKEY_JOB_BURST_CHANCE_DEFAULT
    burst_cnt_min: int = app_config.HOTKEY_JOB_BURST_COUNT_MIN_DEFAULT
    burst_cnt_max: int = app_config.HOTKEY_JOB_BURST_COUNT_MAX_DEFAULT
    burst_int_ms: int = app_config.HOTKEY_JOB_BURST_INTERVAL_MS_DEFAULT
    use_focus: bool = False
    window_name: str = ""
    restore_focus: bool = True
    running: bool = False
    stop_evt: threading.Event = dataclasses.field(default_factory=threading.Event)
    row_frame: Any = dataclasses.field(default=None, repr=False)


@dataclasses.dataclass
class AlarmState:
    active: bool = False
    mp3: str = ""
    threshold: float = app_config.ALARM_THRESHOLD_RATIO_DEFAULT
    cooldown: int = app_config.ALARM_COOLDOWN_SECONDS_DEFAULT
    region: tuple[int, int, int, int] | None = None
    battle_enabled: bool = False
    battle_threshold: float = app_config.BATTLE_CHANGE_THRESHOLD_RATIO_DEFAULT
    battle_region: tuple[int, int, int, int] | None = None
    auto_pause: bool = False
    hp_percent: int = 0
    hp_value: int = 0
    mp_value: int = 0
    cap_value: int = 0
    flash_window: bool = False
    system_sound: bool = True
    battle_logout_popup_timeout_sec: int = 0


@dataclasses.dataclass
class CharStatusState:
    active: bool = False
    region: tuple[int, int, int, int] | None = None
    hp_region: tuple[int, int, int, int] | None = None
    mana_region: tuple[int, int, int, int] | None = None
    cap_region: tuple[int, int, int, int] | None = None
    poll_ms: int = app_config.CHAR_STATUS_POLL_MS_DEFAULT
    samples: int = app_config.CHAR_STATUS_SAMPLES_DEFAULT
    sample_delay_ms: int = app_config.CHAR_STATUS_SAMPLE_DELAY_MS_DEFAULT
    tesseract_path: str = ""
    level: int | None = None
    hp: int | None = None
    mana: int | None = None
    cap: int | None = None
    food_seconds: int | None = None
    food_text: str = ""
    hp_peak: int = 0
    hp_regen_per_min: float = 0.0
    mana_regen_per_min: float = 0.0
    reads: int = 0
    failures: int = 0
    last_seen: float | None = None
    last_error: str = ""


@dataclasses.dataclass
class FishingState:
    active: bool = False
    rod_pos: tuple[int, int] = (0, 0)
    spots: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    cast_min_ms: int = app_config.FISH_CAST_MIN_MS_DEFAULT
    cast_max_ms: int = app_config.FISH_CAST_MAX_MS_DEFAULT
    wait_min_ms: int = app_config.FISH_WAIT_MIN_MS_DEFAULT
    wait_max_ms: int = app_config.FISH_WAIT_MAX_MS_DEFAULT
    rod_jitter: int = app_config.FISH_ROD_JITTER_DEFAULT
    spot_jitter: int = app_config.FISH_SPOT_JITTER_DEFAULT
    session_minutes: int = app_config.FISH_SESSION_MINUTES_DEFAULT
    session_remaining_secs: int = 0
    session_deadline: float | None = None
    min_cap: int = 10
    auto_restart_enabled: bool = False
    auto_restart_food_min_secs: int = app_config.FISH_AUTO_RESTART_FOOD_MIN_SECS_DEFAULT
    # Mouse speed multiplier for HumanMouse.move() duration calculation.
    # Higher values produce faster movement (duration is divided by this value).
    # Mirrors the same approach used in HealerState.mouse_speed.
    mouse_speed: float = app_config.FISH_MOUSE_SPEED_DEFAULT


@dataclasses.dataclass
class RuneState:
    active: bool = False
    spell_key: str = "f1"
    cycle_delay_ms: int = app_config.RUNE_CYCLE_DELAY_MS_DEFAULT
    cycle_delay_variation_ms: int = app_config.RUNE_CYCLE_DELAY_VARIATION_MS_DEFAULT
    hand_pos: tuple[int, int] = (0, 0)
    storage_pos: tuple[int, int] = (0, 0)
    blank_pos: tuple[int, int] = (0, 0)
    jitter: int = app_config.RUNE_JITTER_DEFAULT
    cast_delay_ms: int = app_config.RUNE_CAST_DELAY_MS_DEFAULT
    post_cast_settle_ms: int = app_config.RUNE_POST_CAST_SETTLE_MS_DEFAULT
    min_mana: int = 60
    max_mana: int = 80
    available_blank_runes: int = 0
    mouse_move_min_ms: int = app_config.RUNE_MOUSE_MOVE_MIN_MS_DEFAULT
    mouse_move_max_ms: int = app_config.RUNE_MOUSE_MOVE_MAX_MS_DEFAULT
    mouse_press_min_ms: int = app_config.RUNE_MOUSE_PRESS_MIN_MS_DEFAULT
    mouse_press_max_ms: int = app_config.RUNE_MOUSE_PRESS_MAX_MS_DEFAULT
    mouse_settle_min_ms: int = app_config.RUNE_MOUSE_SETTLE_MIN_MS_DEFAULT
    mouse_settle_max_ms: int = app_config.RUNE_MOUSE_SETTLE_MAX_MS_DEFAULT


@dataclasses.dataclass
class HealerState:
    active: bool = False
    mode: str = "spell"
    spell_key: str = "f1"
    use_percent: bool = True
    hp_percent: int = app_config.HEALER_HP_PERCENT_DEFAULT
    hp_value: int = app_config.HEALER_HP_VALUE_DEFAULT
    min_mana: int = 20
    max_mana: int = 0
    character_pos: tuple[int, int] = (0, 0)
    rune_pos: tuple[int, int] = (0, 0)
    mouse_speed: float = app_config.HEALER_MOUSE_SPEED_DEFAULT
    rune_delay_ms: int = app_config.HEALER_RUNE_DELAY_MS_DEFAULT


@dataclasses.dataclass
class SandboxState:
    backend: str = "jobobj"
    box_name: str = "LauncherBox"
    exe_path: str = ""
    args: str = ""
    drop_admin: bool = False
    spoof_env: bool = True


@dataclasses.dataclass
class CaveBotState:
    """State for the CaveBot automation module."""
    active: bool = False
    script_name: str = ""
    stand_seconds: int = 1
    walking_enabled: bool = True
    walk_for_debug: bool = False
    attack_players: bool = False
    force_attack: bool = False
    follow_mode: bool = True
    monsters_to_attack: list[str] = dataclasses.field(default_factory=list)
    priority_one: int = 1
    priority_two: int = 2
    priority_three: int = 3
    priority_four: int = 4
    player_seen: bool = False
    attacking_you: bool = False
    cant_attack_suspend: bool = False
    suspend_after: int = 5
    monsters_range: int = 3
    attack_mode: str = "normal"
    cap_below_than: int = 0
    drop_items: bool = False
    load_auto_seller: bool = False
    load_auto_banker: bool = False
    looting_enabled: bool = True
    skill_key: str = "f1"  # Key to use for targeting monster
    # Region for map minimap click area
    map_region: tuple[int, int, int, int] | None = None
    # SQM click positions for looting (9 around character)
    sqm_positions: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    battle_list_x: int = 0  # X position of battle list for clicking


@dataclasses.dataclass
class AppState:
    hotkey_bindings: dict[str, str] = dataclasses.field(
        default_factory=lambda: {
            "pause": "f5",
            "alarm": "f6",
            "rclick": "f7",
            "afk": "f8",
            "fish_stop": "f9",
            "rune_stop": "f10",
            "record_pos": "f12",
            "stop_all": "home",
        }
    )
    hotkey_labels: dict[str, str] = dataclasses.field(
        default_factory=lambda: {
            "pause": "Pause / Resume",
            "alarm": "Toggle Screen Watch",
            "rclick": "Toggle Right-Click Monitor",
            "afk": "Toggle Activity Monitor",
            "fish_stop": "Toggle Fishing Session",
            "rune_stop": "Toggle Rune Session",
            "record_pos": "Record Position",
            "stop_all": "Stop All Activities",
        }
    )
    rebind_active: bool = False
    rebind_target: str | None = None

    afk_active: bool = False
    afk_min_ms: int = app_config.APP_AFK_MIN_MS_DEFAULT
    afk_max_ms: int = app_config.APP_AFK_MAX_MS_DEFAULT

    rclick_active: bool = False
    rclick_pos: tuple[int, int] = (0, 0)
    rclick_min_ms: int = app_config.APP_RCLICK_MIN_MS_DEFAULT
    rclick_max_ms: int = app_config.APP_RCLICK_MAX_MS_DEFAULT
    rclick_mode: str = "timer"
    rclick_require_food: bool = False
    rclick_food_min_minutes: int = app_config.APP_RCLICK_FOOD_MIN_MINUTES_DEFAULT
    rclick_food_burst_count: int = app_config.APP_RCLICK_FOOD_BURST_COUNT_DEFAULT
    rclick_food_burst_count_min: int = app_config.APP_RCLICK_FOOD_BURST_COUNT_MIN_DEFAULT
    rclick_food_burst_count_max: int = app_config.APP_RCLICK_FOOD_BURST_COUNT_MAX_DEFAULT
    rclick_food_burst_interval_ms: int = app_config.APP_RCLICK_FOOD_BURST_INTERVAL_MS_DEFAULT
    rclick_click_delay_min_ms: int = app_config.APP_RCLICK_CLICK_DELAY_MIN_MS_DEFAULT
    rclick_click_delay_max_ms: int = app_config.APP_RCLICK_CLICK_DELAY_MAX_MS_DEFAULT
    rclick_post_click_settle_ms: int = app_config.APP_RCLICK_POST_CLICK_SETTLE_MS_DEFAULT
    rclick_jitter: int = app_config.RCLICK_JITTER_DEFAULT

    alarm: AlarmState = dataclasses.field(default_factory=AlarmState)
    char_status: CharStatusState = dataclasses.field(default_factory=CharStatusState)
    fishing: FishingState = dataclasses.field(default_factory=FishingState)
    rune: RuneState = dataclasses.field(default_factory=RuneState)
    healer: HealerState = dataclasses.field(default_factory=HealerState)
    sandbox: SandboxState = dataclasses.field(default_factory=SandboxState)
    cavebot: CaveBotState = dataclasses.field(default_factory=CaveBotState)

    light_process_name: str = "miracle_gl.exe"
    light_memory_backend: str = "pymem"
    attached_window_title: str = ""
    character_name: str = ""
    character_name_normalized: str = ""
    light_direct_address_hex: str = ""
    light_freeze_enabled: bool = False
    light_freeze_color_value: int = 0
    light_freeze_intensity_value: int = 0
    light_custom_color_value: int = 215
    light_custom_intensity_value: int = 8
    light_freeze_interval_ms: int = app_config.APP_LIGHT_FREEZE_INTERVAL_MS_DEFAULT
    light_last_mode: str = ""
    light_last_color_address_hex: str = ""
    light_last_intensity_address_hex: str = ""
    light_original_color_value: int | None = None
    light_original_intensity_value: int | None = None

    hp_pointer_address_hex: str = ""
    hp_source: str = "ocr"
    hp_value: int | None = None

    mp_pointer_address_hex: str = ""
    mp_source: str = "none"
    mp_value: int | None = None

    cap_pointer_address_hex: str = ""
    cap_source: str = "none"
    cap_value: int | None = None

    food_pointer_address_hex: str = ""
    food_source: str = "ocr"
    food_value: int | None = None

    _prev_ocr_hp: int | None = None
    _prev_ocr_mp: int | None = None
    _prev_ocr_cap: int | None = None
    _hp_pointer_invalid: bool = False
    _mp_pointer_invalid: bool = False
    _cap_pointer_invalid: bool = False
    _mp_resolved_addr: int | None = None
    _cap_resolved_addr: int | None = None

    stats: dict[str, int] = dataclasses.field(
        default_factory=lambda: {
            "hotkeys": 0,
            "bursts": 0,
            "afk_moves": 0,
            "right_clicks": 0,
            "alarms": 0,
            "fish_casts": 0,
            "runes_made": 0,
            "heals": 0,
        }
    )
    jobs: list[HotkeyJob] = dataclasses.field(default_factory=list)
    job_counter: int = 0

    alarm_active = _group_property("alarm", "active")
    alarm_mp3 = _group_property("alarm", "mp3")
    alarm_threshold = _group_property("alarm", "threshold")
    alarm_cooldown = _group_property("alarm", "cooldown")
    alarm_region = _group_property("alarm", "region")
    alarm_battle_enabled = _group_property("alarm", "battle_enabled")
    alarm_battle_threshold = _group_property("alarm", "battle_threshold")
    alarm_battle_region = _group_property("alarm", "battle_region")
    alarm_auto_pause = _group_property("alarm", "auto_pause")
    alarm_hp_percent = _group_property("alarm", "hp_percent")
    alarm_hp_value = _group_property("alarm", "hp_value")
    alarm_mp_value = _group_property("alarm", "mp_value")
    alarm_cap_value = _group_property("alarm", "cap_value")
    alarm_flash_window = _group_property("alarm", "flash_window")
    alarm_system_sound = _group_property("alarm", "system_sound")

    char_status_active = _group_property("char_status", "active")
    char_status_region = _group_property("char_status", "region")
    char_status_hp_region = _group_property("char_status", "hp_region")
    char_status_mana_region = _group_property("char_status", "mana_region")
    char_status_cap_region = _group_property("char_status", "cap_region")
    char_status_poll_ms = _group_property("char_status", "poll_ms")
    char_status_samples = _group_property("char_status", "samples")
    char_status_sample_delay_ms = _group_property("char_status", "sample_delay_ms")
    char_status_tesseract_path = _group_property("char_status", "tesseract_path")
    char_status_level = _group_property("char_status", "level")
    char_status_hp = _group_property("char_status", "hp")
    char_status_mana = _group_property("char_status", "mana")
    char_status_cap = _group_property("char_status", "cap")
    char_status_food_seconds = _group_property("char_status", "food_seconds")
    char_status_food_text = _group_property("char_status", "food_text")
    char_status_hp_peak = _group_property("char_status", "hp_peak")
    char_status_hp_regen_per_min = _group_property("char_status", "hp_regen_per_min")
    char_status_mana_regen_per_min = _group_property("char_status", "mana_regen_per_min")
    char_status_reads = _group_property("char_status", "reads")
    char_status_failures = _group_property("char_status", "failures")
    char_status_last_seen = _group_property("char_status", "last_seen")
    char_status_last_error = _group_property("char_status", "last_error")

    fish_active = _group_property("fishing", "active")
    fish_rod_pos = _group_property("fishing", "rod_pos")
    fish_spots = _group_property("fishing", "spots")
    fish_cast_min_ms = _group_property("fishing", "cast_min_ms")
    fish_cast_max_ms = _group_property("fishing", "cast_max_ms")
    fish_wait_min_ms = _group_property("fishing", "wait_min_ms")
    fish_wait_max_ms = _group_property("fishing", "wait_max_ms")
    fish_rod_jitter = _group_property("fishing", "rod_jitter")
    fish_spot_jitter = _group_property("fishing", "spot_jitter")
    fish_session_minutes = _group_property("fishing", "session_minutes")
    fish_session_remaining_secs = _group_property("fishing", "session_remaining_secs")
    fish_session_deadline = _group_property("fishing", "session_deadline")
    fish_min_cap = _group_property("fishing", "min_cap")
    fish_auto_restart_enabled = _group_property("fishing", "auto_restart_enabled")
    fish_auto_restart_food_min_secs = _group_property("fishing", "auto_restart_food_min_secs")
    fish_mouse_speed = _group_property("fishing", "mouse_speed")

    rune_active = _group_property("rune", "active")
    rune_spell_key = _group_property("rune", "spell_key")
    rune_cycle_delay_ms = _group_property("rune", "cycle_delay_ms")
    rune_cycle_delay_variation_ms = _group_property("rune", "cycle_delay_variation_ms")
    rune_hand_pos = _group_property("rune", "hand_pos")
    rune_storage_pos = _group_property("rune", "storage_pos")
    rune_blank_pos = _group_property("rune", "blank_pos")
    rune_jitter = _group_property("rune", "jitter")
    rune_cast_delay_ms = _group_property("rune", "cast_delay_ms")
    rune_post_cast_settle_ms = _group_property("rune", "post_cast_settle_ms")
    rune_min_mana = _group_property("rune", "min_mana")
    rune_max_mana = _group_property("rune", "max_mana")
    rune_available_blank_runes = _group_property("rune", "available_blank_runes")
    rune_mouse_move_min_ms = _group_property("rune", "mouse_move_min_ms")
    rune_mouse_move_max_ms = _group_property("rune", "mouse_move_max_ms")
    rune_mouse_press_min_ms = _group_property("rune", "mouse_press_min_ms")
    rune_mouse_press_max_ms = _group_property("rune", "mouse_press_max_ms")
    rune_mouse_settle_min_ms = _group_property("rune", "mouse_settle_min_ms")
    rune_mouse_settle_max_ms = _group_property("rune", "mouse_settle_max_ms")

    healer_active = _group_property("healer", "active")
    healer_mode = _group_property("healer", "mode")
    healer_spell_key = _group_property("healer", "spell_key")
    healer_use_percent = _group_property("healer", "use_percent")
    healer_hp_percent = _group_property("healer", "hp_percent")
    healer_hp_value = _group_property("healer", "hp_value")
    healer_min_mana = _group_property("healer", "min_mana")
    healer_max_mana = _group_property("healer", "max_mana")
    healer_character_pos = _group_property("healer", "character_pos")
    healer_rune_pos = _group_property("healer", "rune_pos")
    healer_mouse_speed = _group_property("healer", "mouse_speed")
    healer_rune_delay_ms = _group_property("healer", "rune_delay_ms")

    cavebot_active = _group_property("cavebot", "active")
    cavebot_script_name = _group_property("cavebot", "script_name")
    cavebot_stand_seconds = _group_property("cavebot", "stand_seconds")
    cavebot_walking_enabled = _group_property("cavebot", "walking_enabled")
    cavebot_walk_for_debug = _group_property("cavebot", "walk_for_debug")
    cavebot_attack_players = _group_property("cavebot", "attack_players")
    cavebot_force_attack = _group_property("cavebot", "force_attack")
    cavebot_follow_mode = _group_property("cavebot", "follow_mode")
    cavebot_monsters_to_attack = _group_property("cavebot", "monsters_to_attack")
    cavebot_player_seen = _group_property("cavebot", "player_seen")
    cavebot_attacking_you = _group_property("cavebot", "attacking_you")
    cavebot_cant_attack_suspend = _group_property("cavebot", "cant_attack_suspend")
    cavebot_suspend_after = _group_property("cavebot", "suspend_after")
    cavebot_monsters_range = _group_property("cavebot", "monsters_range")
    cavebot_attack_mode = _group_property("cavebot", "attack_mode")
    cavebot_cap_below_than = _group_property("cavebot", "cap_below_than")
    cavebot_drop_items = _group_property("cavebot", "drop_items")
    cavebot_load_auto_seller = _group_property("cavebot", "load_auto_seller")
    cavebot_load_auto_banker = _group_property("cavebot", "load_auto_banker")
    cavebot_looting_enabled = _group_property("cavebot", "looting_enabled")
    cavebot_skill_key = _group_property("cavebot", "skill_key")
    cavebot_map_region = _group_property("cavebot", "map_region")
    cavebot_sqm_positions = _group_property("cavebot", "sqm_positions")
    cavebot_battle_list_x = _group_property("cavebot", "battle_list_x")
