"""Tests for JSON configuration serialization."""

import os
import tempfile

from systool.config import ConfigSerializer
from systool.models import AppState, HotkeyJob


class TestConfigSerializer:
    def test_to_dict_is_json_friendly(self):
        state = AppState()
        state.jobs.append(HotkeyJob(job_id=1, key="F3", burst_enabled=True))
        payload = ConfigSerializer.to_dict(state)

        assert payload["jobs"][0]["key"] == "F3"
        assert payload["rclick_food_min_minutes"] == state.rclick_food_min_minutes
        assert "time_unit" not in payload

    def test_json_round_trip_preserves_core_fields(self):
        state = AppState()
        state.afk_min_ms = 45_000
        state.afk_max_ms = 90_000
        state.rclick_pos = (150, 320)
        state.rclick_food_min_minutes = 12
        state.fish_spots = [(100, 200), (300, 400)]
        state.hotkey_bindings["pause"] = "ctrl+p"
        state.jobs.append(HotkeyJob(job_id=3, key="F9", min_ms=200, max_ms=800, burst_enabled=True))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
            path = handle.name

        try:
            ConfigSerializer.save_json(path, state)
            payload = ConfigSerializer.load_file(path)
            restored = AppState()
            ConfigSerializer.apply_loaded(restored, payload)

            assert restored.afk_min_ms == 45_000
            assert restored.afk_max_ms == 90_000
            assert restored.rclick_pos == (150, 320)
            assert restored.rclick_food_min_minutes == 12
            assert restored.fish_spots == [(100, 200), (300, 400)]
            assert restored.hotkey_bindings["pause"] == "ctrl+p"
            assert restored.jobs[0].job_id == 3
            assert restored.jobs[0].burst_enabled is True
        finally:
            os.unlink(path)

    def test_apply_loaded_accepts_legacy_food_seconds(self):
        state = AppState()
        payload = {
            "cfg": {
                "rclick_food_min_secs": "600",
                "rclick_food_min_minutes": "",
            },
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "char_status_region": None,
            "char_status_hp_region": None,
            "char_status_mana_region": None,
            "char_status_cap_region": None,
            "hotkeys": {},
        }

        ConfigSerializer.apply_loaded(state, payload)

        assert state.rclick_food_min_minutes == 10

    def test_apply_loaded_clamps_food_minutes(self):
        state = AppState()
        payload = {
            "cfg": {"rclick_food_min_minutes": "80"},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "char_status_region": None,
            "char_status_hp_region": None,
            "char_status_mana_region": None,
            "char_status_cap_region": None,
            "hotkeys": {},
        }

        ConfigSerializer.apply_loaded(state, payload)

        assert state.rclick_food_min_minutes == 40
