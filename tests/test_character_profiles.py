"""Tests for per-character profile helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from systool.app import SystemMonitorApp
from systool.character_profiles import (
    AUTOSAVE_FOLDER_NAME,
    build_identity,
    build_ocr_region_metadata,
    build_profile_path,
    normalize_character_name,
    remap_ocr_regions_from_profile,
)
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
