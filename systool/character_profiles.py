"""Helpers for per-character profile discovery and persistence."""

from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigSerializer

AUTOSAVE_PREFIX = "autosave_"
AUTOSAVE_SUFFIX = ".json"
AUTOSAVE_FOLDER_NAME = "aututu"
AUTOSAVE_INTERVAL_MS = 120_000
PROFILE_SCHEMA_VERSION = 1
UNKNOWN_CHARACTER_NAME = "unknown_character"


@dataclass(frozen=True)
class CharacterIdentity:
    process_name: str
    window_title: str
    character_name: str
    normalized_name: str


def extract_character_name_from_window_title(window_title: str) -> str:
    """Extract the character name from the window title.

    The preferred source is the substring after the first "-". If that is not
    available, fall back to the full title so the caller can still create a
    deterministic profile file.
    """
    title = (window_title or "").strip()
    if not title:
        return UNKNOWN_CHARACTER_NAME

    if "-" in title:
        _, _, tail = title.partition("-")
        candidate = tail.strip()
        if candidate:
            return candidate

    return title


def normalize_character_name(character_name: str) -> str:
    """Normalize a character name into a filesystem-safe identifier."""
    cleaned = (character_name or "").strip()
    if not cleaned:
        return UNKNOWN_CHARACTER_NAME

    normalized = re.sub(r"[\s\-\'\"`]+", "_", cleaned, flags=re.UNICODE)
    normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or UNKNOWN_CHARACTER_NAME


def build_identity(process_name: str, window_title: str) -> CharacterIdentity:
    character_name = extract_character_name_from_window_title(window_title)
    normalized_name = normalize_character_name(character_name)
    return CharacterIdentity(
        process_name=(process_name or "").strip(),
        window_title=(window_title or "").strip(),
        character_name=character_name,
        normalized_name=normalized_name,
    )


def get_documents_directory() -> Path:
    home = Path.home()
    documents = home / "Documents"
    return documents if documents.exists() else home


def ensure_autosave_directory(base_dir: os.PathLike[str] | str | None = None) -> Path:
    root_dir = Path(base_dir) if base_dir is not None else get_documents_directory()
    target_dir = root_dir / AUTOSAVE_FOLDER_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def build_profile_path(normalized_name: str, base_dir: os.PathLike[str] | str | None = None) -> Path:
    safe_name = normalize_character_name(normalized_name)
    return ensure_autosave_directory(base_dir=base_dir) / f"{AUTOSAVE_PREFIX}{safe_name}{AUTOSAVE_SUFFIX}"


def profile_metadata(identity: CharacterIdentity) -> dict[str, object]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_name": identity.process_name,
        "window_title": identity.window_title,
        "character_name": identity.character_name,
        "character_name_normalized": identity.normalized_name,
    }


def save_character_profile(path: os.PathLike[str] | str, state, identity: CharacterIdentity) -> None:
    ConfigSerializer.save_json(str(path), state, metadata=profile_metadata(identity))


def load_character_profile(path: os.PathLike[str] | str) -> dict:
    return ConfigSerializer.load_file(str(path))


def get_window_title_for_pid(pid: int) -> str:
    """Return the first visible top-level window title for a process id."""
    if pid <= 0 or os.name != "nt":
        return ""

    user32 = ctypes.windll.user32
    titles: list[str] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    get_window_text_length = user32.GetWindowTextLengthW
    get_window_text_length.argtypes = [wintypes.HWND]
    get_window_text_length.restype = ctypes.c_int

    get_window_text = user32.GetWindowTextW
    get_window_text.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    get_window_text.restype = ctypes.c_int

    is_window_visible = user32.IsWindowVisible
    is_window_visible.argtypes = [wintypes.HWND]
    is_window_visible.restype = wintypes.BOOL

    get_window_thread_process_id = user32.GetWindowThreadProcessId
    get_window_thread_process_id.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_window_thread_process_id.restype = wintypes.DWORD

    @EnumWindowsProc
    def callback(hwnd, _lparam):
        window_pid = wintypes.DWORD()
        get_window_thread_process_id(hwnd, ctypes.byref(window_pid))
        if window_pid.value != pid or not is_window_visible(hwnd):
            return True

        length = get_window_text_length(hwnd)
        if length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        get_window_text(hwnd, buffer, len(buffer))
        title = buffer.value.strip()
        if title:
            titles.append(title)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return titles[0] if titles else ""
