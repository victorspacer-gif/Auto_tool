"""Tests for per-character profile helpers."""

from __future__ import annotations

from pathlib import Path

from systool.character_profiles import (
    AUTOSAVE_FOLDER_NAME,
    build_identity,
    build_profile_path,
    normalize_character_name,
)


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
