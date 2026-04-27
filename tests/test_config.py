"""Tests for configuration serialization: JSON and XML save/load round-trips."""

import json
import os
import tempfile
from pathlib import Path

from systool.config import ConfigSerializer
from systool.models import AppState, HotkeyJob


class TestConfigToDict:
    """Verify to_dict produces valid serializable output."""

    def test_to_dict_returns_dict(self):
        state = AppState()
        result = ConfigSerializer.to_dict(state)
        assert isinstance(result, dict)

    def test_to_dict_has_jobs_key(self):
        state = AppState()
        result = ConfigSerializer.to_dict(state)
        assert "jobs" in result
        assert isinstance(result["jobs"], list)

    def test_to_dict_has_hotkey_bindings(self):
        state = AppState()
        result = ConfigSerializer.to_dict(state)
        assert "hotkey_bindings" in result
        assert isinstance(result["hotkey_bindings"], dict)

    def test_to_dict_with_jobs(self):
        state = AppState()
        job = HotkeyJob(job_id=1, key="F3", min_ms=500, max_ms=2000, burst_enabled=True)
        state.jobs.append(job)
        result = ConfigSerializer.to_dict(state)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["key"] == "F3"
        assert result["jobs"][0]["burst"] is True

    def test_to_dict_json_serializable(self):
        """to_dict output must be JSON-serializable."""
        state = AppState()
        job = HotkeyJob(job_id=1, key="F5")
        state.jobs.append(job)
        result = ConfigSerializer.to_dict(state)
        # Should not raise
        json.dumps(result)


class TestJSONRoundTrip:
    """Test JSON save and load round-trips."""

    def test_json_save_creates_file(self):
        state = AppState()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ConfigSerializer.save_json(path, state)
            assert os.path.exists(path)
        finally:
            os.unlink(path)

    def test_json_load_returns_dict(self):
        state = AppState()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ConfigSerializer.save_json(path, state)
            result = ConfigSerializer.load_file(path)
            assert isinstance(result, dict)
            assert "cfg" in result
            assert "jobs" in result
            assert "spots" in result
            assert "hotkeys" in result
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_afk_times(self):
        """Round-trip should preserve afk_min_ms and afk_max_ms."""
        state = AppState()
        state.afk_min_ms = 45000
        state.afk_max_ms = 90000

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.afk_min_ms == 45000
            assert new_state.afk_max_ms == 90000
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_rclick_pos(self):
        state = AppState()
        state.rclick_pos = (150, 320)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.rclick_pos == (150, 320)
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_jobs(self):
        state = AppState()
        job = HotkeyJob(job_id=1, key="F9", min_ms=200, max_ms=800, burst_enabled=True)
        state.jobs.append(job)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert len(new_state.jobs) == 1
            assert new_state.jobs[0].key == "F9"
            assert new_state.jobs[0].min_ms == 200
            assert new_state.jobs[0].max_ms == 800
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_hotkey_bindings(self):
        state = AppState()
        state.hotkey_bindings["pause"] = "ctrl+p"
        state.hotkey_bindings["stop_all"] = "esc"

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.hotkey_bindings["pause"] == "ctrl+p"
            assert new_state.hotkey_bindings["stop_all"] == "esc"
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_fish_spots(self):
        state = AppState()
        state.fish_spots = [(100, 200), (300, 400)]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.fish_spots == [(100, 200), (300, 400)]
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_alarm_region(self):
        state = AppState()
        state.alarm_region = (10, 20, 500, 500)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.alarm_region == (10, 20, 500, 500)
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_char_status_regions(self):
        state = AppState()
        state.char_status_region = (0, 0, 800, 600)
        state.char_status_hp_region = (100, 200, 300, 50)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.char_status_region == (0, 0, 800, 600)
            assert new_state.char_status_hp_region == (100, 200, 300, 50)
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_rune_positions(self):
        state = AppState()
        state.rune_hand_pos = (100, 200)
        state.rune_storage_pos = (300, 400)
        state.rune_blank_pos = (500, 600)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.rune_hand_pos == (100, 200)
            assert new_state.rune_storage_pos == (300, 400)
            assert new_state.rune_blank_pos == (500, 600)
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_healer_settings(self):
        state = AppState()
        state.healer_mode = "rune"
        state.healer_hp_percent = 45
        state.healer_mouse_speed = 1.5

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.healer_mode == "rune"
            assert new_state.healer_hp_percent == 45
            assert new_state.healer_mouse_speed == 1.5
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_healer_mana_thresholds(self):
        """Verify healer_min_mana and healer_max_mana survive JSON save/load."""
        state = AppState()
        state.healer_mode = "rune"
        state.healer_hp_percent = 45
        state.healer_mouse_speed = 1.5
        state.healer_min_mana = 30
        state.healer_max_mana = 35

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.healer_mode == "rune"
            assert new_state.healer_hp_percent == 45
            assert new_state.healer_mouse_speed == 1.5
            assert new_state.healer_min_mana == 30
            assert new_state.healer_max_mana == 35
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_healer_mana_clamped(self):
        """Verify healer_max_mana is clamped to >= min_mana on load."""
        state = AppState()
        state.healer_min_mana = 50
        state.healer_max_mana = 30  # invalid: max < min

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            # apply_loaded should clamp max to min when max < min
            assert new_state.healer_max_mana == 50
        finally:
            os.unlink(path)

    def test_json_round_trip_preserves_light_settings(self):
        state = AppState()
        state.light_process_name = "test.exe"
        state.light_direct_address_hex = "ABCDEF"
        state.light_freeze_enabled = True

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.light_process_name == "test.exe"
            assert new_state.light_direct_address_hex == "ABCDEF"
            assert new_state.light_freeze_enabled is True
        finally:
            os.unlink(path)


class TestXMLRoundTrip:
    """Test XML save and load round-trips."""

    def test_xml_save_creates_file(self):
        state = AppState()
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name
        try:
            ConfigSerializer.save_xml(path, state)
            assert os.path.exists(path)
        finally:
            os.unlink(path)

    def test_xml_load_returns_dict(self):
        state = AppState()
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name
        try:
            ConfigSerializer.save_xml(path, state)
            result = ConfigSerializer.load_file(path)
            assert isinstance(result, dict)
            assert "cfg" in result
            assert "jobs" in result
            assert "hotkeys" in result
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_afk_times(self):
        state = AppState()
        state.afk_min_ms = 45000
        state.afk_max_ms = 90000

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.afk_min_ms == 45000
            assert new_state.afk_max_ms == 90000
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_rclick_pos(self):
        state = AppState()
        state.rclick_pos = (150, 320)

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.rclick_pos == (150, 320)
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_jobs(self):
        state = AppState()
        job = HotkeyJob(job_id=1, key="F9", min_ms=200, max_ms=800)
        state.jobs.append(job)

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert len(new_state.jobs) == 1
            assert new_state.jobs[0].key == "F9"
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_fish_spots(self):
        state = AppState()
        state.fish_spots = [(100, 200), (300, 400)]

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.fish_spots == [(100, 200), (300, 400)]
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_alarm_region(self):
        state = AppState()
        state.alarm_region = (10, 20, 500, 500)

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.alarm_region == (10, 20, 500, 500)
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_char_status_regions(self):
        state = AppState()
        state.char_status_region = (0, 0, 800, 600)
        state.char_status_hp_region = (100, 200, 300, 50)

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.char_status_region == (0, 0, 800, 600)
            assert new_state.char_status_hp_region == (100, 200, 300, 50)
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_healer_settings(self):
        state = AppState()
        state.healer_mode = "rune"
        state.healer_hp_percent = 45
        state.healer_mouse_speed = 1.5

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.healer_mode == "rune"
            assert new_state.healer_hp_percent == 45
            assert new_state.healer_mouse_speed == 1.5
        finally:
            os.unlink(path)

    def test_xml_round_trip_preserves_healer_mana_thresholds(self):
        """Verify healer_min_mana and healer_max_mana survive XML save/load."""
        state = AppState()
        state.healer_mode = "rune"
        state.healer_hp_percent = 45
        state.healer_mouse_speed = 1.5
        state.healer_min_mana = 30
        state.healer_max_mana = 35

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            ConfigSerializer.save_xml(path, state)
            payload = ConfigSerializer.load_file(path)
            new_state = AppState()
            ConfigSerializer.apply_loaded(new_state, payload)
            assert new_state.healer_mode == "rune"
            assert new_state.healer_hp_percent == 45
            assert new_state.healer_mouse_speed == 1.5
            assert new_state.healer_min_mana == 30
            assert new_state.healer_max_mana == 35
        finally:
            os.unlink(path)


class TestApplyLoadedDefaults:
    """Test that apply_loaded falls back to defaults when keys are missing."""

    def test_apply_empty_dict_uses_defaults(self):
        state = AppState()
        payload = {"cfg": {}, "jobs": [], "spots": [], "alarm_region": None,
                   "char_status_region": None, "char_status_hp_region": None,
                   "char_status_mana_region": None, "char_status_cap_region": None,
                   "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.afk_min_ms == 70_000
        assert state.rclick_mode == "timer"

    def test_apply_invalid_int_falls_back(self):
        """Non-numeric values should fall back to defaults."""
        state = AppState()
        payload = {
            "cfg": {"afk_min_ms": "not_a_number", "rclick_pos_x": "abc"},
            "jobs": [], "spots": [], "alarm_region": None,
            "char_status_region": None, "char_status_hp_region": None,
            "char_status_mana_region": None, "char_status_cap_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.afk_min_ms == 70_000  # default

    def test_apply_clamps_fish_session_minutes(self):
        """fish_session_minutes should be clamped to [1, 40]."""
        state = AppState()
        payload = {"cfg": {"fish_session_minutes": "0"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.fish_session_minutes == 1  # clamped to min

    def test_apply_clamps_healer_hp_percent(self):
        """healer_hp_percent should be clamped to [1, 100]."""
        state = AppState()
        payload = {"cfg": {"healer_hp_percent": "200"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.healer_hp_percent == 100  # clamped to max

    def test_apply_clamps_healer_mouse_speed(self):
        """healer_mouse_speed should be clamped to [0.2, 3.0]."""
        state = AppState()
        payload = {"cfg": {"healer_mouse_speed": "10.0"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.healer_mouse_speed == 3.0  # clamped to max

    def test_apply_clamps_char_status_poll_ms(self):
        """char_status_poll_ms should be clamped to >= 250."""
        state = AppState()
        payload = {"cfg": {"char_status_poll_ms": "10"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.char_status_poll_ms == 250

    def test_apply_clamps_rune_mouse_move_max(self):
        """rune_mouse_move_max should be >= rune_mouse_move_min."""
        state = AppState()
        state.rune_mouse_move_min_ms = 100
        payload = {"cfg": {"rune_mouse_move_max_ms": "50"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rune_mouse_move_max_ms >= 100

    def test_apply_clears_jobs_and_resets_counter(self):
        """apply_loaded should clear existing jobs and reset counter."""
        state = AppState()
        state.jobs.append(HotkeyJob(job_id=99))
        state.job_counter = 99
        payload = {"cfg": {}, "jobs": [], "spots": [], "alarm_region": None,
                   "char_status_region": None, "char_status_hp_region": None,
                   "char_status_mana_region": None, "char_status_cap_region": None,
                   "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.jobs == []
        assert state.job_counter == 0

    def test_apply_loads_multiple_jobs(self):
        """Should load multiple jobs from payload."""
        state = AppState()
        payload = {
            "cfg": {},
            "jobs": [
                {"job_id": "1", "key": "F1", "min_ms": "500", "max_ms": "2000"},
                {"job_id": "2", "key": "F2", "min_ms": "300", "max_ms": "1000"},
            ],
            "spots": [], "alarm_region": None,
            "char_status_region": None, "char_status_hp_region": None,
            "char_status_mana_region": None, "char_status_cap_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert len(state.jobs) == 2
        assert state.jobs[0].key == "F1"
        assert state.jobs[1].key == "F2"

    def test_apply_loads_hotkey_bindings(self):
        """Should update hotkey bindings from payload."""
        state = AppState()
        payload = {
            "cfg": {}, "jobs": [], "spots": [], "alarm_region": None,
            "char_status_region": None, "char_status_hp_region": None,
            "char_status_mana_region": None, "char_status_cap_region": None,
            "hotkeys": {"pause": "ctrl+shift+p", "stop_all": "delete"},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.hotkey_bindings["pause"] == "ctrl+shift+p"
        assert state.hotkey_bindings["stop_all"] == "delete"

    def test_apply_ignores_unknown_hotkeys(self):
        """Should not add unknown hotkey actions."""
        state = AppState()
        payload = {
            "cfg": {}, "jobs": [], "spots": [], "alarm_region": None,
            "char_status_region": None, "char_status_hp_region": None,
            "char_status_mana_region": None, "char_status_cap_region": None,
            "hotkeys": {"unknown_action": "x"},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert "unknown_action" not in state.hotkey_bindings


class TestApplyLoadedRanges:
    """Test value clamping behavior across all fields."""

    def test_rclick_food_burst_count_min(self):
        state = AppState()
        payload = {"cfg": {"rclick_food_burst_count": "0"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rclick_food_burst_count >= 1

    def test_rclick_food_burst_interval_min(self):
        state = AppState()
        payload = {"cfg": {"rclick_food_burst_interval_ms": "0"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rclick_food_burst_interval_ms >= 50

    def test_alarm_hp_percent_clamped(self):
        state = AppState()
        payload = {"cfg": {"alarm_hp_percent": "-10"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.alarm_hp_percent >= 0

    def test_healer_hp_value_min(self):
        state = AppState()
        payload = {"cfg": {"healer_hp_value": "0"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.healer_hp_value >= 1

    def test_healer_rune_delay_min(self):
        state = AppState()
        payload = {"cfg": {"healer_rune_delay_ms": "0"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.healer_rune_delay_ms >= 50

    def test_light_freeze_color_value_clamped(self):
        state = AppState()
        payload = {"cfg": {"light_freeze_color_value": "-1"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.light_freeze_color_value >= 0

    def test_light_freeze_interval_min(self):
        state = AppState()
        payload = {"cfg": {"light_freeze_interval_ms": "10"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.light_freeze_interval_ms >= 30

    def test_rune_mouse_press_max_clamped(self):
        state = AppState()
        state.rune_mouse_press_min_ms = 100
        payload = {"cfg": {"rune_mouse_press_max_ms": "50"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rune_mouse_press_max_ms >= 100

    def test_rune_mouse_settle_max_clamped(self):
        state = AppState()
        state.rune_mouse_settle_min_ms = 50
        payload = {"cfg": {"rune_mouse_settle_max_ms": "30"}, "jobs": [], "spots": [],
                   "alarm_region": None, "char_status_region": None,
                   "char_status_hp_region": None, "char_status_mana_region": None,
                   "char_status_cap_region": None, "hotkeys": {}}
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rune_mouse_settle_max_ms >= 50
