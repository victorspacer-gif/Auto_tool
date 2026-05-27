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
OCR_REGION_KEYS = (
    "char_status_region",
    "char_status_hp_region",
    "char_status_mana_region",
    "char_status_cap_region",
)
PROFILE_LOAD_BLOCKED_CFG_KEYS = frozenset(
    (
        "alarm.flash_window",
        "alarm_flash_window",
    )
)


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


def find_latest_profile_for(normalized_name: str, base_dir: os.PathLike[str] | str | None = None) -> Path | None:
    """Find the most recent autosave profile matching *normalized_name* (case-insensitive).

    Scans all ``{AUTOSAVE_PREFIX}*.json`` files in the autosave directory and picks
    the one whose normalized character name matches (case-insensitive) with the
    highest modification time.  Returns ``None`` when no match is found.
    """
    norm_lower = normalized_name.lower()
    autosave_dir = ensure_autosave_directory(base_dir=base_dir)

    best: Path | None = None
    for candidate in autosave_dir.glob(f"{AUTOSAVE_PREFIX}*.json"):
        # Strip prefix and suffix to get the stored name.
        inner = candidate.name[len(AUTOSAVE_PREFIX):-len(AUTOSAVE_SUFFIX)]
        if normalize_character_name(inner).lower() == norm_lower:
            if best is None or candidate.stat().st_mtime > best.stat().st_mtime:
                best = candidate

    return best


def _coerce_rect(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x_val, y_val, width, height = (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return (x_val, y_val, width, height)


def _region_to_relative(region: tuple[int, int, int, int], window_rect: tuple[int, int, int, int]) -> list[float] | None:
    window_x, window_y, window_width, window_height = window_rect
    if window_width <= 0 or window_height <= 0:
        return None
    x_val, y_val, width, height = region
    return [
        (x_val - window_x) / window_width,
        (y_val - window_y) / window_height,
        width / window_width,
        height / window_height,
    ]


def _relative_to_region(relative: list[float] | tuple[float, float, float, float], window_rect: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    if len(relative) != 4:
        return None
    window_x, window_y, window_width, window_height = window_rect
    if window_width <= 0 or window_height <= 0:
        return None
    try:
        rel_x, rel_y, rel_width, rel_height = (float(relative[0]), float(relative[1]), float(relative[2]), float(relative[3]))
    except (TypeError, ValueError):
        return None

    x_val = window_x + int(round(rel_x * window_width))
    y_val = window_y + int(round(rel_y * window_height))
    width = max(1, int(round(rel_width * window_width)))
    height = max(1, int(round(rel_height * window_height)))
    return (x_val, y_val, width, height)


def build_ocr_region_metadata(state, window_rect: tuple[int, int, int, int] | None = None) -> dict[str, object] | None:
    metadata: dict[str, object] = {}
    if window_rect is not None:
        metadata["window_rect"] = list(window_rect)

    regions: dict[str, object] = {}
    for key in OCR_REGION_KEYS:
        region = _coerce_rect(getattr(state, key, None))
        if region is None:
            continue
        entry: dict[str, object] = {"absolute": list(region)}
        if window_rect is not None:
            relative = _region_to_relative(region, window_rect)
            if relative is not None:
                entry["window_relative"] = relative
        regions[key] = entry

    if regions:
        metadata["regions"] = regions
    return metadata or None


def profile_metadata(identity: CharacterIdentity, state=None, window_rect: tuple[int, int, int, int] | None = None) -> dict[str, object]:
    metadata = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_name": identity.process_name,
        "window_title": identity.window_title,
        "character_name": identity.character_name,
        "character_name_normalized": identity.normalized_name,
    }
    if state is not None:
        ocr_region_metadata = build_ocr_region_metadata(state, window_rect=window_rect)
        if ocr_region_metadata:
            metadata["ocr_regions"] = ocr_region_metadata
    return metadata


def save_character_profile(
    path: os.PathLike[str] | str,
    state,
    identity: CharacterIdentity,
    *,
    window_rect: tuple[int, int, int, int] | None = None,
) -> None:
    ConfigSerializer.save_json(str(path), state, metadata=profile_metadata(identity, state=state, window_rect=window_rect))


def load_character_profile(path: os.PathLike[str] | str) -> dict:
    payload = ConfigSerializer.load_file(str(path))
    cfg = payload.get("cfg")
    if isinstance(cfg, dict):
        for key in PROFILE_LOAD_BLOCKED_CFG_KEYS:
            cfg.pop(key, None)
    return payload


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


def get_window_rect_for_pid(pid: int) -> tuple[int, int, int, int] | None:
    """Return the first visible top-level window rect for a process id."""
    if pid <= 0 or os.name != "nt":
        return None

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    found_rect: list[tuple[int, int, int, int] | None] = [None]

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    is_window_visible = user32.IsWindowVisible
    is_window_visible.argtypes = [wintypes.HWND]
    is_window_visible.restype = wintypes.BOOL

    get_window_text_length = user32.GetWindowTextLengthW
    get_window_text_length.argtypes = [wintypes.HWND]
    get_window_text_length.restype = ctypes.c_int

    get_window_rect = user32.GetWindowRect
    get_window_rect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    get_window_rect.restype = wintypes.BOOL

    get_window_thread_process_id = user32.GetWindowThreadProcessId
    get_window_thread_process_id.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_window_thread_process_id.restype = wintypes.DWORD

    @EnumWindowsProc
    def callback(hwnd, _lparam):
        window_pid = wintypes.DWORD()
        get_window_thread_process_id(hwnd, ctypes.byref(window_pid))
        if window_pid.value != pid or not is_window_visible(hwnd):
            return True
        if get_window_text_length(hwnd) <= 0:
            return True
        if not get_window_rect(hwnd, ctypes.byref(rect)):
            return True

        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return True

        found_rect[0] = (int(rect.left), int(rect.top), width, height)
        return False

    user32.EnumWindows(callback, 0)
    return found_rect[0]


def remap_ocr_regions_from_profile(
    payload: dict,
    current_window_rect: tuple[int, int, int, int] | None,
) -> dict[str, tuple[int, int, int, int]]:
    """Remap saved OCR regions onto the currently attached client window."""
    if current_window_rect is None:
        return {}

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return {}
    ocr_metadata = metadata.get("ocr_regions", {})
    if not isinstance(ocr_metadata, dict):
        return {}

    saved_window_rect = _coerce_rect(ocr_metadata.get("window_rect"))
    saved_regions = ocr_metadata.get("regions", {})
    if saved_window_rect is None or not isinstance(saved_regions, dict):
        return {}

    remapped: dict[str, tuple[int, int, int, int]] = {}
    for key in OCR_REGION_KEYS:
        region_meta = saved_regions.get(key)
        if not isinstance(region_meta, dict):
            continue
        relative = region_meta.get("window_relative")
        region = None
        if isinstance(relative, (list, tuple)):
            region = _relative_to_region(relative, current_window_rect)
        if region is None:
            absolute = _coerce_rect(region_meta.get("absolute"))
            if absolute is None:
                absolute = _coerce_rect(payload.get(key))
            if absolute is None:
                continue
            region = _relative_to_region(_region_to_relative(absolute, saved_window_rect) or [], current_window_rect)
        if region is not None:
            remapped[key] = region

    return remapped
