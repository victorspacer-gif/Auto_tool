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
        state.attached_window_title = "Client - Sir Test"
        state.character_name = "Sir Test"
        state.character_name_normalized = "Sir_Test"
        state.alarm_region = (10, 20, 30, 40)
        state.char_status_region = (11, 21, 31, 41)
        state.char_status_hp_region = (12, 22, 32, 42)
        state.char_status_mana_region = (13, 23, 33, 43)
        state.char_status_cap_region = (14, 24, 34, 44)
        state.rune_hand_pos = (501, 601)
        state.rune_storage_pos = (502, 602)
        state.rune_blank_pos = (503, 603)
        state.healer_character_pos = (701, 801)
        state.healer_rune_pos = (702, 802)
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
            assert restored.attached_window_title == "Client - Sir Test"
            assert restored.character_name == "Sir Test"
            assert restored.character_name_normalized == "Sir_Test"
            assert restored.alarm_region == (10, 20, 30, 40)
            assert restored.char_status_region == (11, 21, 31, 41)
            assert restored.char_status_hp_region == (12, 22, 32, 42)
            assert restored.char_status_mana_region == (13, 23, 33, 43)
            assert restored.char_status_cap_region == (14, 24, 34, 44)
            assert restored.rune_hand_pos == (501, 601)
            assert restored.rune_storage_pos == (502, 602)
            assert restored.rune_blank_pos == (503, 603)
            assert restored.healer_character_pos == (701, 801)
            assert restored.healer_rune_pos == (702, 802)
            assert restored.rclick_food_min_minutes == 12
            assert restored.fish_spots == [(100, 200), (300, 400)]
            assert restored.hotkey_bindings["pause"] == "ctrl+p"
            assert restored.jobs[0].job_id == 3
            assert restored.jobs[0].burst_enabled is True
        finally:
            os.unlink(path)

    def test_save_json_can_include_metadata(self):
        state = AppState()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
            path = handle.name

        try:
            ConfigSerializer.save_json(path, state, metadata={"schema_version": 1, "character": "Sir Test"})
            payload = ConfigSerializer.load_file(path)

            assert payload["metadata"]["schema_version"] == 1
            assert payload["metadata"]["character"] == "Sir Test"
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
