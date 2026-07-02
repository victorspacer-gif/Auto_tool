"""Tests for per-character profile helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from systool.app import SystemMonitorApp
from systool.character_profiles import (
    AUTOSAVE_FOLDER_NAME,
    PROFILE_LIGHT_CFG_KEYS,
    build_identity,
    build_ocr_region_metadata,
    build_profile_path,
    load_character_profile,
    normalize_character_name,
    remap_ocr_regions_from_profile,
    save_character_profile,
)
from systool.config import ConfigSerializer
from systool.models import AppState


def test_build_identity_extracts_name_after_hyphen():
    identity = build_identity("miracle_gl.exe", "Miracle 7.4 - Sir Test-Name")

    assert identity.character_name == "Sir Test-Name"
    assert identity.normalized_name == "Sir_Test_Name"


def test_normalize_character_name_replaces_spaces_and_quotes():
    assert normalize_character_name("D'Artagnan \"Prime\"") == "D_Artagnan_Prime"


def test_build_profile_path_uses_aututu_folder(tmp_path: Path):
    profile_path = build_profile_path("Knight Test", base_dir=tmp_path)

    assert profile_path.parent == tmp_path / AUTOSAVE_FOLDER_NAME
    assert profile_path.name == "autosave_Knight_Test.json"


def test_build_ocr_region_metadata_stores_window_relative_regions():
    state = AppState()
    state.char_status_region = (150, 250, 300, 200)
    state.char_status_hp_region = (180, 290, 60, 20)
    metadata = build_ocr_region_metadata(state, window_rect=(100, 200, 600, 400))

    assert metadata is not None
    assert metadata["window_rect"] == [100, 200, 600, 400]
    hp_meta = metadata["regions"]["char_status_hp_region"]
    assert hp_meta["absolute"] == [180, 290, 60, 20]
    assert hp_meta["window_relative"] == [80 / 600, 90 / 400, 60 / 600, 20 / 400]


def test_remap_ocr_regions_from_profile_uses_current_window_rect():
    payload = {
        "metadata": {
            "ocr_regions": {
                "window_rect": [100, 200, 600, 400],
                "regions": {
                    "char_status_region": {
                        "absolute": [150, 250, 300, 200],
                        "window_relative": [50 / 600, 50 / 400, 300 / 600, 200 / 400],
                    },
                    "char_status_hp_region": {
                        "absolute": [180, 290, 60, 20],
                        "window_relative": [80 / 600, 90 / 400, 60 / 600, 20 / 400],
                    },
                },
            },
        },
    }

    remapped = remap_ocr_regions_from_profile(payload, current_window_rect=(1000, 500, 1200, 800))

    assert remapped["char_status_region"] == (1100, 600, 600, 400)
    assert remapped["char_status_hp_region"] == (1160, 680, 120, 40)


def test_load_character_profile_blocks_flash_window_setting(tmp_path: Path):
    state = AppState()
    path = tmp_path / "autosave_Sir_Test.json"
    state.light_freeze_enabled = True
    state.light_custom_color_value = 99
    ConfigSerializer.save_json(path, state)
    raw = path.read_text(encoding="utf-8")
    raw = raw.replace('"alarm.flash_window": false', '"alarm.flash_window": true')
    raw = raw.replace('"alarm.system_sound": true', '"alarm.system_sound": true,\n  "alarm_flash_window": true')
    path.write_text(raw, encoding="utf-8")

    payload = load_character_profile(path)
    restored = AppState()
    ConfigSerializer.apply_loaded(restored, payload)

    assert "alarm.flash_window" in payload["cfg"]
    assert "alarm_flash_window" in payload["cfg"]
    assert "light_freeze_enabled" not in payload["cfg"]
    assert "light_custom_color_value" not in payload["cfg"]
    assert restored.alarm_flash_window is True
    assert restored.light_freeze_enabled is False
    assert restored.light_custom_color_value == 215


def test_save_character_profile_omits_light_settings(tmp_path: Path):
    state = AppState()
    state.light_process_name = "custom_client.exe"
    state.light_direct_address_hex = "ABCDEF"
    state.light_freeze_enabled = True
    state.light_freeze_color_value = 123
    state.light_custom_intensity_value = 42
    identity = build_identity("miracle_gl.exe", "Miracle 7.4 - Sir Test")
    path = tmp_path / "autosave_Sir_Test.json"

    save_character_profile(path, state, identity)
    raw = path.read_text(encoding="utf-8")

    for key in PROFILE_LIGHT_CFG_KEYS:
        assert f'"{key}"' not in raw


def test_save_current_character_profile_skips_disk_write_when_state_is_unchanged(monkeypatch):
    app = object.__new__(SystemMonitorApp)
    app.runtime = SimpleNamespace(
        state=AppState(),
        ui=SimpleNamespace(log=lambda _msg: None),
    )
    app.current_character_profile_path = "C:/profiles/autosave_Sir_Test.json"
    app.light_service = SimpleNamespace(controller=None)
    app.runtime.state.light_process_name = "miracle_gl.exe"
    app.runtime.state.attached_window_title = "Client - Sir Test"
    app.runtime.state.character_name = "Sir Test"
    app.runtime.state.character_name_normalized = "Sir_Test"
    app._poll_settings = lambda schedule_next=False: None

    app._last_saved_json_hash = SystemMonitorApp._compute_profile_payload_hash(app)

    called = {"count": 0}

    def fake_save_character_profile(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("systool.app.save_character_profile", fake_save_character_profile)

    saved = SystemMonitorApp._save_current_character_profile(app, log_success=True)

    assert saved is False
    assert called["count"] == 0


def test_save_current_character_profile_skips_disk_write_for_light_only_change(monkeypatch):
    app = object.__new__(SystemMonitorApp)
    app.runtime = SimpleNamespace(
        state=AppState(),
        ui=SimpleNamespace(log=lambda _msg: None),
    )
    app.current_character_profile_path = "C:/profiles/autosave_Sir_Test.json"
    app.light_service = SimpleNamespace(controller=None)
    app.runtime.state.light_process_name = "miracle_gl.exe"
    app.runtime.state.attached_window_title = "Client - Sir Test"
    app.runtime.state.character_name = "Sir Test"
    app.runtime.state.character_name_normalized = "Sir_Test"
    app._poll_settings = lambda schedule_next=False: None

    app._last_saved_json_hash = SystemMonitorApp._compute_profile_payload_hash(app)
    app.runtime.state.light_custom_color_value = 99
    app.runtime.state.light_freeze_enabled = True

    called = {"count": 0}

    def fake_save_character_profile(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("systool.app.save_character_profile", fake_save_character_profile)
    app._refresh_last_saved_profile_hash = lambda: None
    app._get_attached_window_rect = lambda: None

    saved = SystemMonitorApp._save_current_character_profile(app, log_success=True)

    assert saved is False
    assert called["count"] == 0


def test_load_attached_profile_ignores_profile_light_freeze(monkeypatch):
    app = object.__new__(SystemMonitorApp)
    app.runtime = SimpleNamespace(
        state=AppState(),
        ui=SimpleNamespace(log=lambda _msg: None, set_status=lambda _msg, _color: None),
    )
    app.ui_vars = {}
    app.current_character_profile_path = None
    app.light_service = SimpleNamespace(
        controller=SimpleNamespace(pid=1234),
        start_freeze=lambda: (True, "Light freeze enabled."),
        stop_freeze=lambda: None,
    )
    app.char_status_service = SimpleNamespace(restart_if_needed=lambda: None, stop=lambda: None)
    app._refresh_module_indicator = lambda _module, _enabled: None
    app._set_light_status = lambda _ok, _message: None
    app._sync_ui_from_state = lambda: None
    app._restart_global_listener = lambda: None
    app._refresh_last_saved_profile_hash = lambda: None

    start_calls = {"count": 0}

    def fake_start_freeze():
        start_calls["count"] += 1
        return True, "Light freeze enabled."

    app.light_service.start_freeze = fake_start_freeze

    monkeypatch.setattr("systool.app.get_window_title_for_pid", lambda _pid: "Miracle 7.4 - Sir Test")
    monkeypatch.setattr("systool.app.get_window_rect_for_pid", lambda _pid: (100, 200, 800, 600))
    monkeypatch.setattr(
        "systool.app.build_identity",
        lambda _process_name, _window_title: SimpleNamespace(
            process_name="miracle_gl.exe",
            window_title="Miracle 7.4 - Sir Test",
            character_name="Sir Test",
            normalized_name="Sir_Test",
        ),
    )
    monkeypatch.setattr("systool.app.find_latest_profile_for", lambda _name: Path("/tmp/autosave_Sir_Test.json"))
    monkeypatch.setattr(
        "systool.app.load_character_profile",
        lambda _path: {
            "cfg": {},
            "jobs": [],
            "spots": [],
            "alarm_region": None,
            "char_status_region": None,
            "char_status_hp_region": None,
            "char_status_mana_region": None,
            "char_status_cap_region": None,
            "hotkeys": {},
        },
    )
    monkeypatch.setattr("systool.app.remap_ocr_regions_from_profile", lambda _payload, _window_rect: {})

    message = SystemMonitorApp._load_or_create_attached_character_profile(app)

    assert message == "character=Sir Test"
    assert app.runtime.state.light_freeze_enabled is False
    assert start_calls["count"] == 0
