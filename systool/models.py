"""Domain models used across the application."""

from __future__ import annotations

import dataclasses
import threading
from typing import Any


@dataclasses.dataclass
class HotkeyJob:
    job_id: int
    key: str = "F1"
    min_ms: int = 1_000
    max_ms: int = 3_000
    burst_enabled: bool = False
    burst_chance: float = 0.20
    burst_cnt_min: int = 3
    burst_cnt_max: int = 8
    burst_int_ms: int = 80
    use_focus: bool = False
    window_name: str = ""
    restore_focus: bool = True
    running: bool = False
    stop_evt: threading.Event = dataclasses.field(default_factory=threading.Event)
    row_frame: Any = dataclasses.field(default=None, repr=False)


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
            "fish_stop": "Stop Fishing Session",
            "rune_stop": "Stop Rune Session",
            "record_pos": "Record Position",
            "stop_all": "Stop All Activities",
        }
    )
    rebind_active: bool = False
    rebind_target: str | None = None

    afk_active: bool = False
    afk_min_ms: int = 30_000
    afk_max_ms: int = 60_000

    rclick_active: bool = False
    rclick_pos: tuple[int, int] = (0, 0)
    rclick_min_ms: int = 5_000
    rclick_max_ms: int = 15_000

    alarm_active: bool = False
    alarm_mp3: str = ""
    alarm_threshold: float = 0.90
    alarm_cooldown: int = 10
    alarm_region: tuple[int, int, int, int] | None = None
    alarm_auto_pause: bool = False

    fish_active: bool = False
    fish_rod_pos: tuple[int, int] = (0, 0)
    fish_spots: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    fish_cast_min_ms: int = 1_500
    fish_cast_max_ms: int = 4_000
    fish_wait_min_ms: int = 8_000
    fish_wait_max_ms: int = 18_000
    fish_rod_jitter: int = 5
    fish_spot_jitter: int = 22
    fish_session_minutes: int = 10
    fish_session_remaining_secs: int = 0
    fish_session_deadline: float | None = None

    rune_active: bool = False
    rune_spell_key: str = "f1"
    rune_cycle_delay_ms: int = 5_000
    rune_hand_pos: tuple[int, int] = (0, 0)
    rune_storage_pos: tuple[int, int] = (0, 0)
    rune_blank_pos: tuple[int, int] = (0, 0)
    rune_jitter: int = 6
    rune_cast_delay_ms: int = 900

    stats: dict[str, int] = dataclasses.field(
        default_factory=lambda: {
            "hotkeys": 0,
            "bursts": 0,
            "afk_moves": 0,
            "right_clicks": 0,
            "alarms": 0,
            "fish_casts": 0,
            "runes_made": 0,
        }
    )
    jobs: list[HotkeyJob] = dataclasses.field(default_factory=list)
    job_counter: int = 0
