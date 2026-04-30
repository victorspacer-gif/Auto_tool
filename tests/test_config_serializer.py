"""Tests for ConfigSerializer error handling and edge cases.

Rules: tests only, no implementation changes, skip if behavior doesn't exist.
"""

import json
import os
import tempfile
import textwrap

import pytest

from systool.config import ConfigSerializer
from systool.models import AppState


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def state():
    """Fresh default AppState for serialization tests."""
    return AppState()


@pytest.fixture
def valid_json_path(state):
    """Write a complete, valid JSON config to a temp file and return the path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as fh:
        json.dump(ConfigSerializer.to_dict(state), fh, indent=2)
        path = fh.name
    yield path
    os.unlink(path)


# ── load_file error paths ───────────────────────────────────────────


class TestLoadFileErrors:

    def test_missing_file_raises_error(self):
        """load_file on a non-existent path should raise an exception."""
        with pytest.raises((FileNotFoundError, OSError)):
            ConfigSerializer.load_file("/nonexistent/path/config.json")

    def test_malformed_json_raises_error(self):
        """load_file with invalid JSON content should raise json.JSONDecodeError."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            fh.write("{ this is not valid json }")
            path = fh.name

        try:
            with pytest.raises(json.JSONDecodeError):
                ConfigSerializer.load_file(path)
        finally:
            os.unlink(path)

    def test_empty_json_raises_error(self):
        """load_file with an empty file should raise JSONDecodeError."""
        path = tempfile.mktemp(suffix=".json")
        try:
            # Create a completely empty file.
            with open(path, "w") as fh:
                pass  # write nothing

            with pytest.raises(json.JSONDecodeError):
                ConfigSerializer.load_file(path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_missing_alarm_region_defaults_to_none(self):
        """load_file with JSON missing 'alarm_region' should NOT raise — it defaults to None."""
        payload = {"cfg": {}, "jobs": [], "fish_spots": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(payload, fh)
            path = fh.name

        try:
            result = ConfigSerializer.load_file(path)
            assert result["alarm_region"] is None
        finally:
            os.unlink(path)


# ── save_json error paths ───────────────────────────────────────────


class TestSaveJsonErrors:

    def test_save_to_unwritable_path_raises_error(self, state):
        """save_json to a directory (not file) should raise an exception."""
        with pytest.raises((OSError, IsADirectoryError)):
            ConfigSerializer.save_json("/tmp", state)


# ── Partial config defaults ────────────────────────────────────────


class TestPartialConfigDefaults:

    def test_apply_loaded_with_minimal_payload(self, state):
        """apply_loaded with only essential keys should use existing defaults."""
        payload = {
            "cfg": {},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        # Should not raise — all fields fall back to current state values.
        ConfigSerializer.apply_loaded(state, payload)

    def test_apply_loaded_with_empty_cfg_keeps_defaults(self, state):
        """Empty cfg dict should leave every field at its default."""
        original = AppState()
        payload = {
            "cfg": {},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)

        # Spot-check a few fields — they should match the original defaults.
        assert state.afk_min_ms == original.afk_min_ms
        assert state.rclick_mode == original.rclick_mode
        assert state.rune_spell_key == original.rune_spell_key


# ── Legacy migration ───────────────────────────────────────────────


class TestLegacyMigration:

    def test_legacy_rclick_food_min_secs_fallback(self, state):
        """rclick_food_min_secs (seconds) should be converted to minutes."""
        # 120 seconds → 2 minutes.
        payload = {
            "cfg": {"rclick_food_min_secs": "120"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rclick_food_min_minutes == 2

    def test_legacy_rclick_food_min_secs_clamped(self, state):
        """Legacy seconds value that converts to >40 min should be clamped."""
        # 5000 seconds → ~83 minutes, but max is 40.
        payload = {
            "cfg": {"rclick_food_min_secs": "5000"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rclick_food_min_minutes == 40

    def test_legacy_rclick_food_min_secs_below_minimum(self, state):
        """Legacy seconds value that converts to <1 min should be clamped."""
        # 30 seconds → 0.5 minutes, but min is 1.
        payload = {
            "cfg": {"rclick_food_min_secs": "30"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.rclick_food_min_minutes == 1


# ── to_json completeness ───────────────────────────────────────────


class TestToJsonCompleteness:

    def test_to_dict_serializes_all_direct_attrs(self, state):
        """to_dict should include every direct AppState attribute."""
        d = ConfigSerializer.to_dict(state)

        expected = [
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
        for attr in expected:
            assert attr in d, f"Missing key '{attr}' in to_dict output"

    def test_to_dict_serializes_special_fields(self, state):
        """to_dict should include hotkey_bindings, jobs, fish_spots."""
        d = ConfigSerializer.to_dict(state)
        assert "hotkey_bindings" in d
        assert "jobs" in d
        assert "fish_spots" in d

    def test_to_dict_flattens_nested_groups(self, state):
        """to_dict should flatten alarm, char_status, fishing, rune, healer groups."""
        d = ConfigSerializer.to_dict(state)
        for group in ("alarm", "char_status", "fishing", "rune", "healer"):
            prefix = f"{group}."
            found = [k for k in d if k.startswith(prefix)]
            assert len(found) > 0, f"No keys starting with '{prefix}'"

    def test_to_dict_flattens_sandbox(self, state):
        """to_dict should flatten sandbox group."""
        d = ConfigSerializer.to_dict(state)
        found = [k for k in d if k.startswith("sandbox.")]
        assert len(found) > 0, "No keys starting with 'sandbox.'"

    def test_to_json_roundtrip(self, state):
        """Serialize → JSON string → parse back should yield identical dict."""
        d1 = ConfigSerializer.to_dict(state)
        raw = json.dumps(d1, indent=2)
        d2 = json.loads(raw)
        assert d1 == d2

    def test_to_json_handles_tuple_positions(self, state):
        """Position tuples should be split into x/y keys in the dict."""
        state.rclick_pos = (100, 200)
        d = ConfigSerializer.to_dict(state)
        assert "rclick_pos_x" in d and d["rclick_pos_x"] == 100
        assert "rclick_pos_y" in d and d["rclick_pos_y"] == 200

    def test_to_json_handles_fish_spots_tuples(self, state):
        """fish_spots list of tuples should become list of lists."""
        state.fishing.spots = [(10, 20), (30, 40)]
        d = ConfigSerializer.to_dict(state)
        assert isinstance(d["fish_spots"], list)
        for item in d["fish_spots"]:
            assert isinstance(item, list)

    def test_to_json_handles_jobs(self, state):
        """Jobs should be serialized with all expected fields."""
        from systool.models import HotkeyJob
        job = HotkeyJob(job_id=1, key="F2", min_ms=5000, max_ms=10000)
        state.jobs.append(job)

        d = ConfigSerializer.to_dict(state)
        assert len(d["jobs"]) == 1
        j = d["jobs"][0]
        assert j["job_id"] == 1
        assert j["key"] == "F2"
        assert j["min_ms"] == 5000
        assert j["max_ms"] == 10000


# ── Fishing mouse speed serialization ───────────────────────────────


class TestFishMouseSpeedConfig:
    """Tests for fish_mouse_speed config field in ConfigSerializer."""

    def test_to_dict_includes_fish_mouse_speed(self, state):
        """to_dict should include the fishing.mouse_speed field."""
        d = ConfigSerializer.to_dict(state)
        assert "fishing.mouse_speed" in d
        from systool.config import FISH_MOUSE_SPEED_DEFAULT
        assert d["fishing.mouse_speed"] == FISH_MOUSE_SPEED_DEFAULT

    def test_apply_loaded_reads_fish_mouse_speed(self, state):
        """apply_loaded should read fishing.mouse_speed from payload."""
        payload = {
            "cfg": {"fishing.mouse_speed": "2.5"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.fishing.mouse_speed == 2.5

    def test_apply_loaded_clamps_fish_mouse_speed_to_max(self, state):
        """Values above max should be clamped to FISH_MOUSE_SPEED_MAX."""
        from systool.config import FISH_MOUSE_SPEED_MAX
        payload = {
            "cfg": {"fishing.mouse_speed": "9.0"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.fishing.mouse_speed == FISH_MOUSE_SPEED_MAX

    def test_apply_loaded_clamps_fish_mouse_speed_to_min(self, state):
        """Values below min should be clamped to FISH_MOUSE_SPEED_MIN."""
        from systool.config import FISH_MOUSE_SPEED_MIN
        payload = {
            "cfg": {"fishing.mouse_speed": "0.1"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.fishing.mouse_speed == FISH_MOUSE_SPEED_MIN

    def test_apply_loaded_defaults_to_1_when_missing(self, state):
        """Missing fishing.mouse_speed should keep the default (1.0)."""
        from systool.config import FISH_MOUSE_SPEED_DEFAULT
        payload = {
            "cfg": {},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.fishing.mouse_speed == FISH_MOUSE_SPEED_DEFAULT

    def test_apply_loaded_handles_invalid_string(self, state):
        """Non-numeric fishing.mouse_speed should fall back to current value."""
        original = 1.5
        state.fishing.mouse_speed = original
        payload = {
            "cfg": {"fishing.mouse_speed": "not_a_number"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "hotkeys": {},
        }
        ConfigSerializer.apply_loaded(state, payload)
        assert state.fishing.mouse_speed == original

    def test_json_round_trip_preserves_fish_mouse_speed(self, state):
        """Full JSON save/load should preserve fishing.mouse_speed value."""
        from systool.config import FISH_MOUSE_SPEED_DEFAULT
        state.fishing.mouse_speed = 2.0
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
            path = fh.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            restored = AppState()
            ConfigSerializer.apply_loaded(restored, payload)
            assert restored.fishing.mouse_speed == 2.0
        finally:
            os.unlink(path)
