"""Tests for domain models: AppState and HotkeyJob."""

import threading

from systool.models import AppState, HotkeyJob


class TestHotkeyJobDefaults:
    """Verify HotkeyJob dataclass defaults match the codebase expectations."""

    def test_default_key(self):
        job = HotkeyJob(job_id=1)
        assert job.key == "F1"

    def test_default_ms_range(self):
        job = HotkeyJob(job_id=1)
        assert job.min_ms == 20_000
        assert job.max_ms == 30_000

    def test_default_mana(self):
        from systool.config import HOTKEY_JOB_MIN_MANA_DEFAULT
        job = HotkeyJob(job_id=1)
        assert job.min_mana == HOTKEY_JOB_MIN_MANA_DEFAULT

    def test_burst_defaults(self):
        job = HotkeyJob(job_id=1)
        assert job.burst_enabled is False
        assert job.burst_chance == 0.20
        assert job.burst_cnt_min == 2
        assert job.burst_cnt_max == 4
        assert job.burst_int_ms == 80

    def test_focus_defaults(self):
        job = HotkeyJob(job_id=1)
        assert job.use_focus is False
        assert job.window_name == ""
        assert job.restore_focus is True

    def test_stop_event_created(self):
        job = HotkeyJob(job_id=1)
        assert isinstance(job.stop_evt, threading.Event)

    def test_custom_values(self):
        job = HotkeyJob(
            job_id=42,
            key="F9",
            min_ms=500,
            max_ms=2000,
            burst_enabled=True,
            use_focus=True,
            window_name="MapleStory",
        )
        assert job.job_id == 42
        assert job.key == "F9"
        assert job.min_ms == 500
        assert job.max_ms == 2000
        assert job.burst_enabled is True
        assert job.use_focus is True
        assert job.window_name == "MapleStory"


class TestAppStateDefaults:
    """Verify AppState dataclass defaults."""

    def test_hotkey_bindings_defaults(self):
        state = AppState()
        expected = {
            "pause": "f5",
            "alarm": "f6",
            "rclick": "f7",
            "afk": "f8",
            "fish_stop": "f9",
            "rune_stop": "f10",
            "record_pos": "f12",
            "stop_all": "home",
        }
        assert state.hotkey_bindings == expected

    def test_hotkey_labels_defaults(self):
        state = AppState()
        expected = {
            "pause": "Pause / Resume",
            "alarm": "Toggle Screen Watch",
            "rclick": "Toggle Right-Click Monitor",
            "afk": "Toggle Activity Monitor",
            "fish_stop": "Toggle Fishing Session",
            "rune_stop": "Toggle Rune Session",
            "record_pos": "Record Position",
            "stop_all": "Stop All Activities",
        }
        assert state.hotkey_labels == expected

    def test_afk_defaults(self):
        state = AppState()
        assert state.afk_min_ms == 70_000
        assert state.afk_max_ms == 88_000

    def test_rclick_defaults(self):
        state = AppState()
        assert state.rclick_pos == (0, 0)
        assert state.rclick_mode == "timer"
        assert state.rclick_food_min_minutes == 10

    def test_alarm_defaults(self):
        state = AppState()
        assert state.alarm_threshold == 0.80
        assert state.alarm_cooldown == 10
        assert state.alarm_flash_window is False
        assert state.alarm_system_sound is True

    def test_char_status_defaults(self):
        state = AppState()
        assert state.char_status_poll_ms == 800
        assert state.char_status_samples == 3
        assert state.char_status_hp_peak == 0
        assert state.char_status_hp_regen_per_min == 0.0
        assert state.char_status_mana_regen_per_min == 0.0

    def test_fish_defaults(self):
        state = AppState()
        assert state.fish_rod_pos == (0, 0)
        assert state.fish_session_minutes == 10
        assert state.fish_min_cap == 10
        # Mouse speed multiplier defaults to 1.0 (neutral — no speed change).
        from systool.config import FISH_MOUSE_SPEED_DEFAULT
        assert state.fishing.mouse_speed == FISH_MOUSE_SPEED_DEFAULT

    def test_rune_defaults(self):
        from systool.config import RUNE_CYCLE_DELAY_MS_DEFAULT
        state = AppState()
        assert state.rune_spell_key == "f1"
        assert state.rune_cycle_delay_ms == RUNE_CYCLE_DELAY_MS_DEFAULT
        assert state.rune_hand_pos == (0, 0)

    def test_healer_defaults(self):
        state = AppState()
        assert state.healer_mode == "spell"
        assert state.healer_hp_percent == 60
        assert state.healer_use_percent is True

    def test_light_defaults(self):
        state = AppState()
        assert state.light_process_name == "miracle_gl.exe"
        assert state.light_direct_address_hex == ""
        assert state.light_freeze_enabled is False
        assert state.light_freeze_color_value == 0
        assert state.light_freeze_intensity_value == 0
        assert state.light_freeze_interval_ms == 1_000

    def test_stats_defaults(self):
        state = AppState()
        expected = {
            "hotkeys": 0,
            "bursts": 0,
            "afk_moves": 0,
            "right_clicks": 0,
            "alarms": 0,
            "fish_casts": 0,
            "runes_made": 0,
            "heals": 0,
        }
        assert state.stats == expected

    def test_jobs_empty_list(self):
        state = AppState()
        assert state.jobs == []
        assert state.job_counter == 0


class TestAppStateMutations:
    """Test that AppState fields can be mutated correctly."""

    def test_update_rclick_pos(self):
        state = AppState()
        state.rclick_pos = (100, 200)
        assert state.rclick_pos == (100, 200)

    def test_add_job(self):
        """Appending a job directly doesn't auto-increment the counter.
        
        The caller (app.py) increments job_counter before creating jobs:
            self.runtime.state.job_counter += 1
            job = HotkeyJob(job_id=self.runtime.state.job_counter)
        """
        state = AppState()
        job = HotkeyJob(job_id=1, key="F3")
        state.jobs.append(job)
        assert len(state.jobs) == 1
        # Counter is not auto-incremented by the dataclass itself
        assert state.job_counter == 0

    def test_add_job_with_increment_pattern(self):
        """Test the pattern used in app.py for adding jobs."""
        state = AppState()
        state.job_counter += 1
        job = HotkeyJob(job_id=state.job_counter, key="F3")
        state.jobs.append(job)
        assert len(state.jobs) == 1
        assert state.job_counter >= 1

    def test_update_char_status_values(self):
        state = AppState()
        state.char_status_hp = 850
        state.char_status_mana = 420
        state.char_status_level = 99
        assert state.char_status_hp == 850
        assert state.char_status_mana == 420
        assert state.char_status_level == 99

    def test_toggle_active_flags(self):
        state = AppState()
        state.afk_active = True
        state.alarm_active = False
        assert state.afk_active is True
        assert state.alarm_active is False
