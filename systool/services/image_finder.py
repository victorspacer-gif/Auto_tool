"""ImageFinder — OpenCV-based screen detection utilities for Auto_tool.

Mirrors the functionality of TibiaAuto12's HookWindow.py (LocateImage,
LocateCenterImage, LocateAllImages, PixelMatchesColor) but adapted for
Auto_tool's runtime architecture.

Provides:
  - Full-window PrintWindow capture (via monitoring's _capture_window_region)
  - mss screen-grab fallback
  - OpenCV template matching for mark/UI element/item detection
  - Digit-by-digit number scanning (alternative to Tesseract OCR)
  - Tool/item auto-detection in inventory

All functions gracefully return None/0 when OpenCV, mss, or numpy aren't available.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from ..runtime import HAS_CV2, HAS_MSS, HAS_NUMPY, cv2, mss, np

# ── Project paths ────────────────────────────────────────────────────


def _get_project_root() -> str:
    """Return the Auto_tool project root directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ensure_images_subdir(*parts: str) -> str:
    """Return the path to a subdirectory under images/, creating it if needed."""
    img_dir = os.path.join(_get_project_root(), "images", *parts)
    os.makedirs(img_dir, exist_ok=True)
    return img_dir


# ── Image directory constants ────────────────────────────────────────

def get_images_dir() -> str:
    return _ensure_images_subdir()


def get_map_settings_dir() -> str:
    return _ensure_images_subdir("MapSettings")


def get_number_images_dir() -> str:
    return _ensure_images_subdir("PlayerStats", "Numbers")


def get_tool_frames_dir() -> str:
    return _ensure_images_subdir("Items", "Frames", "Tools")


def get_tool_corners_dir() -> str:
    return _ensure_images_subdir("Items", "Corners", "Tools")


def get_tibia_settings_dir() -> str:
    return _ensure_images_subdir("TibiaSettings")


# ── Core image detection ─────────────────────────────────────────────


def _capture_region(region: tuple[int, int, int, int]) -> np.ndarray | None:
    """Capture a screen region using mss.

    Args:
        region: (left, top, width, height) in screen coordinates.

    Returns:
        RGB numpy array, or None if capture failed or deps missing.
    """
    if not HAS_MSS or not HAS_NUMPY or mss is None or np is None:
        return None
    left, top, width, height = region
    if width <= 0 or height <= 0:
        return None
    try:
        with mss.mss() as sct:
            monitor = {"left": left, "top": top, "width": width, "height": height}
            screenshot = np.array(sct.grab(monitor))
        # mss returns BGRA; convert to RGB
        return screenshot[:, :, :3][:, :, ::-1].copy()
    except Exception:
        logger.debug("mss capture failed", exc_info=True)
        return None


def locate_image(
    image_path: str,
    region: tuple[int, int, int, int] | None = None,
    precision: float = 0.8,
) -> tuple[int, int] | None:
    """Find an image on the screen (or within a region) via OpenCV template matching.

    Mirrors TibiaAuto12's ``LocateImage()`` in HookWindow.py.

    Args:
        image_path: Path to the template PNG (absolute or relative to project root).
        region:    (left, top, width, height) screen region to search.
        precision: Confidence threshold (0.0–1.0).

    Returns:
        (x, y) top-left coordinate of the match, or None if not found.
    """
    if not HAS_CV2 or not HAS_NUMPY or cv2 is None or np is None:
        return None

    # Resolve relative path
    if not os.path.isabs(image_path):
        image_path = os.path.join(_get_project_root(), image_path)

    if not os.path.isfile(image_path):
        return None

    template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        return None

    if region:
        frame = _capture_region(region)
    else:
        # Full screen capture as fallback (not recommended — prefer region)
        if not HAS_MSS:
            return None
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                frame = np.array(sct.grab(mon))[:, :, :3][:, :, ::-1].copy()
        except Exception:
            return None

    if frame is None or frame.size == 0:
        return None

    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    except Exception:
        return None

    try:
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
    except Exception:
        return None

    if max_val >= precision:
        return (max_loc[0], max_loc[1])
    return None


def locate_center_image(
    image_path: str,
    region: tuple[int, int, int, int] | None = None,
    precision: float = 0.8,
) -> tuple[int, int] | None:
    """Find an image and return its **centre** coordinates in screen space.

    Mirrors TibiaAuto12's ``LocateCenterImage()``.
    """
    pos = locate_image(image_path, region, precision)
    if pos is None:
        return None

    # Read template dimensions to compute centre
    if not os.path.isabs(image_path):
        image_path = os.path.join(_get_project_root(), image_path)
    try:
        template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            return pos
        h, w = template.shape
        return (pos[0] + w // 2, pos[1] + h // 2)
    except Exception:
        return pos


def locate_all_images(
    image_path: str,
    region: tuple[int, int, int, int] | None = None,
    precision: float = 0.8,
) -> int:
    """Count all occurrences of an image within a region.

    Mirrors TibiaAuto12's ``LocateAllImages()``.
    """
    if not HAS_CV2 or not HAS_NUMPY or cv2 is None or np is None:
        return 0

    if not os.path.isabs(image_path):
        image_path = os.path.join(_get_project_root(), image_path)

    if not os.path.isfile(image_path):
        return 0

    template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        return 0

    if region:
        frame = _capture_region(region)
    else:
        return 0

    if frame is None or frame.size == 0:
        return 0

    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= precision)
        return len(list(zip(*loc[::-1])))
    except Exception:
        return 0


def pixel_matches_color(
    x: int, y: int,
    expected_rgb: tuple[int, int, int],
    tolerance: int = 5,
) -> bool:
    """Check if a pixel on the screen matches the expected RGB colour.

    Mirrors TibiaAuto12's ``PixelMatchesColor()`` but adds tolerance.
    """
    frame = _capture_region((x, y, 1, 1))
    if frame is None or frame.size == 0:
        return False
    try:
        pixel = tuple(int(v) for v in frame[0, 0])
        return all(abs(pixel[i] - expected_rgb[i]) <= tolerance for i in range(3))
    except Exception:
        return False


# ── Number / digit scanning ──────────────────────────────────────────

# Cache for number templates (loaded once)
_NUMBER_CACHE: dict[int, np.ndarray] | None = None


def _load_number_templates() -> dict[int, np.ndarray]:
    """Load digit 0-9 grayscale templates from PlayerStats/Numbers/."""
    global _NUMBER_CACHE
    if _NUMBER_CACHE is not None:
        return _NUMBER_CACHE
    if not HAS_CV2 or cv2 is None:
        _NUMBER_CACHE = {}
        return _NUMBER_CACHE
    num_dir = get_number_images_dir()
    templates: dict[int, np.ndarray] = {}
    for digit in range(10):
        path = os.path.join(num_dir, f"{digit}.png")
        if os.path.isfile(path):
            tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if tpl is not None:
                templates[digit] = tpl
    _NUMBER_CACHE = templates
    return templates


def scan_digit(
    region: tuple[int, int, int, int],
    precision: float = 0.92,
) -> int | None:
    """Scan a screen region for a single digit and return its value.

    Mirrors TibiaAuto12's ScanCap digit-by-digit approach:
    ``pyautogui.locateOnScreen('images/PlayerStats/Numbers/X.png', ...)``

    Scans digits from 9 down to 0 (matching TibiaAuto12's order) so that
    higher digits take priority when there's ambiguity.

    Args:
        region: (left, top, width, height) containing ONE digit.
        precision: Confidence threshold (TibiaAuto12 uses 0.92).

    Returns:
        The digit (0-9) or None if no digit matched.
    """
    templates = _load_number_templates()
    if not templates:
        return None

    if not HAS_CV2 or not HAS_NUMPY or cv2 is None or np is None:
        return None

    frame = _capture_region(region)
    if frame is None or frame.size == 0:
        return None

    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    except Exception:
        return None

    # Scan 9→0 (TibiaAuto12 order — higher digits first)
    for digit in range(9, -1, -1):
        tpl = templates.get(digit)
        if tpl is None:
            continue
        try:
            result = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= precision:
                return digit
        except Exception:
            continue

    return None


def scan_number(
    region: tuple[int, int, int, int],
    precision: float = 0.92,
) -> int | None:
    """Scan a multi-digit number from a screen region.

    Splits the region into individual digit slots and scans each.
    The region should tightly encompass the number (no extra padding).

    Uses a simple heuristic: divides the width by expected digit count.
    For a more robust approach, use scan_number_in_region() with explicit
    digit regions.

    Args:
        region: (left, top, width, height) containing ONLY the number.
        precision: Confidence threshold.

    Returns:
        The parsed integer, or None if no digits were found.
    """
    templates = _load_number_templates()
    if not templates:
        return None

    if not HAS_CV2 or not HAS_NUMPY or cv2 is None or np is None:
        return None

    left, top, width, height = region
    if width <= 0 or height <= 0:
        return None

    frame = _capture_region(region)
    if frame is None or frame.size == 0:
        return None

    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    except Exception:
        return None

    # Estimate digit width from templates (use average)
    avg_digit_w = 0
    count = 0
    for tpl in templates.values():
        avg_digit_w += tpl.shape[1]
        count += 1
    if count == 0:
        return None
    avg_digit_w //= count

    # Estimate number of digits
    gap = max(1, avg_digit_w // 4)  # typical gap between digits
    step = avg_digit_w + gap
    max_digits = width // step + 1

    # Try scanning with different expected digit counts
    result_digits: list[int] = []
    for offset in range(0, width - avg_digit_w, avg_digit_w // 2):
        test_region = gray[:, offset:offset + avg_digit_w + 2]
        if test_region.shape[1] < 3:
            continue

        best_digit = None
        best_val = 0.0
        for digit in range(9, -1, -1):
            tpl = templates.get(digit)
            if tpl is None:
                continue
            # If template is taller, resize test region
            try:
                res = cv2.matchTemplate(test_region, tpl, cv2.TM_CCOEFF_NORMED)
                _, val, _, _ = cv2.minMaxLoc(res)
                if val > best_val:
                    best_val = val
                    best_digit = digit
            except Exception:
                continue

        if best_digit is not None and best_val >= precision:
            result_digits.append(best_digit)

    if not result_digits:
        return None

    # Build number from digits
    num = 0
    for d in result_digits:
        num = num * 10 + d

    return num


# ── Item / tool detection ────────────────────────────────────────────


def find_item_in_inventory(
    item_name: str,
    inventory_region: tuple[int, int, int, int] | None = None,
    precision: float = 0.85,
    use_frame: bool = True,
) -> tuple[int, int] | None:
    """Find an item (tool, ring, amulet, etc.) in the inventory via image matching.

    Mirrors TibiaAuto12's SearchForRing / LocateCenterImage pattern:
    ``LocateCenterImage('images/Rings/MightRing.png', Precision=0.9)``

    Args:
        item_name: File stem (e.g. 'FishingRod', 'MightRing', 'Shovel').
        inventory_region: (left, top, width, height) of the inventory area.
            If None, searches the entire screen (slow — specify a region).
        precision: Confidence threshold.
        use_frame: If True, search in Items/Frames/<category>/ (with inventory
            slot border). If False, search Items/None/<category>/ (item icon only).

    Returns:
        (centre_x, centre_y) in screen coordinates, or None if not found.
    """
    # Try common categories
    categories = ["Tools", "Rings", "Amulets", "Potions", "Foods", "Runes", "Ammunitions", "Containers"]
    subdir = "Frames" if use_frame else "None"

    for cat in categories:
        if subdir == "Frames":
            img_dir = _ensure_images_subdir("Items", "Frames", cat)
        else:
            img_dir = _ensure_images_subdir("Items", "None", cat)

        img_path = os.path.join(img_dir, f"{item_name}.png")
        if not os.path.isfile(img_path):
            # Try Corners too
            img_dir = _ensure_images_subdir("Items", "Corners", cat)
            img_path = os.path.join(img_dir, f"{item_name}.png")

        if not os.path.isfile(img_path):
            continue

        pos = locate_center_image(img_path, region=inventory_region, precision=precision)
        if pos is not None:
            return pos

    # Fallback: try Rings/, Amulets/ etc. at top level
    top_level_dirs = ["Rings", "Amulets", "ActionBar/Potions"]
    for tld in top_level_dirs:
        img_dir = _ensure_images_subdir(tld)
        img_path = os.path.join(img_dir, f"{item_name}.png")
        if os.path.isfile(img_path):
            pos = locate_center_image(img_path, region=inventory_region, precision=precision)
            if pos is not None:
                return pos

    return None


# ── UI / window element detection ────────────────────────────────────


def find_ui_element(
    element_name: str,
    region: tuple[int, int, int, int] | None = None,
    precision: float = 0.85,
) -> tuple[int, int] | None:
    """Find a UI element (BattleList, Stop, Idle, etc.) on the game window.

    Mirrors TibiaAuto12's ``LocateCenterImage('images/TibiaSettings/BattleList.png')``

    Args:
        element_name: File stem in images/TibiaSettings/ (e.g. 'BattleList', 'Stop', 'Idle').
        region: Search region.
        precision: Confidence threshold.

    Returns:
        (centre_x, centre_y) or None.
    """
    img_dir = _ensure_images_subdir("TibiaSettings")
    img_path = os.path.join(img_dir, f"{element_name}.png")
    if not os.path.isfile(img_path):
        return None
    return locate_center_image(img_path, region=region, precision=precision)


def find_player_status_icon(
    icon_name: str,
    region: tuple[int, int, int, int] | None = None,
    precision: float = 0.85,
) -> tuple[int, int] | None:
    """Find a player status icon (Starving, PZ, Soul, Cap, etc.).

    Mirrors TibiaAuto12's ``LocateImage('images/PlayerStats/Starving.png')``

    Args:
        icon_name: File stem in images/PlayerStats/ (e.g. 'Starving', 'Cap', 'Soul').
        region: Search region.
        precision: Confidence threshold.

    Returns:
        (x, y) top-left or None.
    """
    img_dir = _ensure_images_subdir("PlayerStats")
    img_path = os.path.join(img_dir, f"{icon_name}.png")
    if not os.path.isfile(img_path):
        return None
    return locate_image(img_path, region=region, precision=precision)


# ── Available resources ──────────────────────────────────────────────


def list_available_images(subdir: str = "MapSettings") -> list[str]:
    """List available image names (without extension) in a subdirectory of images/."""
    img_dir = _ensure_images_subdir(subdir)
    if not os.path.isdir(img_dir):
        return []
    return sorted(
        fname[:-4] for fname in os.listdir(img_dir)
        if fname.endswith(".png")
    )


def list_available_tools() -> list[str]:
    """List available tool images (FishingRod, Shovel, Pick, etc.)."""
    items = set()
    for base in ["Frames", "Corners", "None"]:
        d = _ensure_images_subdir("Items", base, "Tools")
        if os.path.isdir(d):
            for fname in os.listdir(d):
                if fname.endswith(".png"):
                    items.add(fname[:-4])
    return sorted(items)


# ── Reference image capture ──────────────────────────────────────────
# Game-specific (Miracle) reference images live under images/Reference/
# These are screenshots of the actual UI elements the user captures.


def get_reference_dir() -> str:
    """Get the path to the game-specific reference image directory."""
    return _ensure_images_subdir("Reference")


def list_references() -> list[str]:
    """List available game-specific reference images."""
    ref_dir = get_reference_dir()
    return sorted(
        fname[:-4] for fname in os.listdir(ref_dir)
        if fname.endswith(".png")
    )


def save_reference_image(
    name: str,
    region: tuple[int, int, int, int],
) -> str | None:
    """Capture a screen region and save it as a reference PNG under images/Reference/.

    This is how the user creates game-specific reference images for auto-detection
    of UI elements (Battle window title bar, Center button, zoom +/- buttons, etc.).

    Args:
        name:  Reference name (e.g. 'Battle', 'CenterButton', 'ZoomIn').
        region: (left, top, width, height) screen region to capture.

    Returns:
        The absolute path to the saved PNG, or None on failure.
    """
    frame = _capture_region(region)
    if frame is None or frame.size == 0:
        return None

    if not HAS_CV2 or cv2 is None:
        return None

    ref_dir = get_reference_dir()
    out_path = os.path.join(ref_dir, f"{name}.png")

    try:
        # Convert RGB back to BGR for cv2.imwrite
        cv2.imwrite(out_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        return out_path
    except Exception:
        return None


def find_reference(
    ref_name: str,
    region: tuple[int, int, int, int] | None = None,
    precision: float = 0.85,
) -> tuple[int, int] | None:
    """Find a game-specific reference image on screen.

    Searches images/Reference/<ref_name>.png first (user-captured game-specific),
    then falls back to images/TibiaSettings/<ref_name>.png (TibiaAuto12 assets).

    Args:
        ref_name: Reference name (e.g. 'Battle', 'CenterButton').
        region:   Screen region to search.
        precision: Confidence threshold.

    Returns:
        (center_x, center_y) in screen coordinates, or None.
    """
    # Try Reference/ first (game-specific)
    ref_dir = get_reference_dir()
    ref_path = os.path.join(ref_dir, f"{ref_name}.png")
    if os.path.isfile(ref_path):
        pos = locate_center_image(ref_path, region=region, precision=precision)
        if pos is not None:
            return pos

    # Fallback: try TibiaSettings/ (TibiaAuto12 assets)
    ts_dir = _ensure_images_subdir("TibiaSettings")
    ts_path = os.path.join(ts_dir, f"{ref_name}.png")
    if os.path.isfile(ts_path):
        pos = locate_center_image(ts_path, region=region, precision=precision)
        if pos is not None:
            return pos

    return None


def detect_minimap_region(
    precision: float = 0.8,
) -> tuple[int, int, int, int] | None:
    """Auto-detect the minimap region on screen.

    Detection strategy (tried in order):
    1. Look for Reference/CenterButton.png — the "Center" text at top-left of minimap
    2. Look for MapSettings/MapSettings.png — the minimap border frame (Tibia-style)
    3. Look for Reference/ZoomIn.png or Reference/ZoomOut.png — +/- zoom controls

    Once the minimap position is found, calculates a ~110px square region.

    Returns:
        (left, top, width, height) of the minimap area, or None.
    """
    map_size = 110  # standard minimap size

    # Strategy 1: Find "Center" button at minimap top-left
    center_pos = find_reference("CenterButton", precision=precision)
    if center_pos is not None:
        # Center button is at top-left of the minimap
        # The minimap starts roughly above and left of it
        cx, cy = center_pos
        # The "Center" button is typically ~40px wide, 16px tall
        # Minimap top-left is about 2px above the button
        map_left = cx - 4
        map_top = cy - map_size + 20
        if map_top < 0:
            map_top = 0
        return (map_left, map_top, map_size, map_size)

    # Strategy 2: Find zoom buttons (Reference/ZoomIn or Reference/ZoomOut)
    for zoom_ref in ["ZoomIn", "ZoomOut", "ZoomPlus", "ZoomMinus"]:
        zoom_pos = find_reference(zoom_ref, precision=precision - 0.05)
        if zoom_pos is not None:
            # Zoom buttons are at bottom-right of the minimap
            zx, zy = zoom_pos
            map_left = zx - map_size + 20
            map_top = zy - map_size + 20
            if map_left < 0:
                map_left = 0
            if map_top < 0:
                map_top = 0
            return (map_left, map_top, map_size, map_size)

    # Strategy 3: Find minimap border (Tibia-style MapSettings.png)
    map_border = os.path.join(get_map_settings_dir(), "MapSettings.png")
    if os.path.isfile(map_border):
        pos = locate_image(map_border, region=None, precision=precision)
        if pos is not None:
            x, y = pos
            return (x - map_size + 4, y + 1, map_size - 4, map_size - 4)

    return None


def detect_battle_window(
    precision: float = 0.8,
) -> tuple[int, int, int, int] | None:
    """Auto-detect the Battle window region on screen.

    Looks for the battle window title bar (Reference/Battle.png or TibiaSettings/Battle.png)
    and returns the region of the full battle list panel below it.

    Returns:
        (left, top, width, height) of the battle list area, or None.
    """
    title_pos = find_reference("Battle", precision=precision)
    if title_pos is None:
        return None

    cx, cy = title_pos
    # Battle window is typically ~155px wide, ~415px tall below the title bar
    left = cx - 75
    top = cy + 15  # below title bar
    width = 155
    height = 415
    return (left, top, width, height)


# ── Battle list / monster scanners (from TibiaAuto12 Scanners.py) ─────


def get_monsters_attack_dir() -> str:
    """Get the MonstersAttack image directory (border analysis images)."""
    return _ensure_images_subdir("MonstersAttack")


def list_battle_attack_images() -> list[str]:
    """List available battle attack border images (LeftRed, TopRed, etc.)."""
    img_dir = get_monsters_attack_dir()
    return sorted(
        fname[:-4] for fname in os.listdir(img_dir)
        if fname.endswith(".png")
    )


def count_monsters_in_battle(
    monster_name: str,
    battle_region: tuple[int, int, int, int],
    precision: float = 0.8,
) -> int:
    """Count how many of a specific monster name appear in the battle list region.

    Mirrors TibiaAuto12's ``NumberOfTargets()`` in Scanners.py:
    ``LocateAllImages('images/Targets/Names/' + Monster + '.png', ...)``

    Args:
        monster_name: File stem in images/Targets/Names/.
        battle_region: (left, top, width, height) of the battle list area.
        precision: Confidence threshold.

    Returns:
        Number of occurrences found (0 if none or images missing).
    """
    img_dir = _ensure_images_subdir("Targets", "Names")
    img_path = os.path.join(img_dir, f"{monster_name}.png")
    if not os.path.isfile(img_path):
        return 0
    return locate_all_images(img_path, region=battle_region, precision=precision)


def scan_monster_in_battle(
    monster_name: str,
    battle_region: tuple[int, int, int, int],
    precision: float = 0.86,
) -> tuple[int, int] | None:
    """Find a monster name in the battle list and return clickable coordinates.

    Mirrors TibiaAuto12's ``ScanTarget()`` in Scanners.py.
    Finds the monster name via ``LocateCenterImage``, then adjusts the click
    point to the left of the name (health bar area).

    Args:
        monster_name: File stem in images/Targets/Names/.
        battle_region: (left, top, width, height) of the battle list area.
        precision: Confidence threshold (TibiaAuto12 uses 0.86).

    Returns:
        (x, y) screen coordinates to click, or None if not found.
    """
    img_dir = _ensure_images_subdir("Targets", "Names")
    img_path = os.path.join(img_dir, f"{monster_name}.png")
    if not os.path.isfile(img_path):
        return None

    left, top, width, height = battle_region
    target_pos = locate_center_image(img_path, region=battle_region, precision=precision)
    if target_pos is None:
        return None

    click_x, click_y = target_pos
    # Adjust to health bar area: offset left of name centre
    # Mirroring TibiaAuto12's coordinate adjustment
    click_x = left + (click_x - left) - 40
    click_y = top + (click_y - top) + 1
    click_x = max(0, click_x)
    click_y = max(0, click_y)
    return (click_x, click_y)


def is_attacking(
    battle_region: tuple[int, int, int, int],
    precision: float = 0.8,
) -> bool:
    """Detect if the character is currently attacking using battle border analysis.

    Mirrors TibiaAuto12's ``IsAttacking()`` in Scanners.py:
    Captures the battle list region and runs template matching against 16
    border images (4 sides x 4 colour variants). If ALL four sides of ANY
    colour variant match, the character is NOT attacking (idle border).

    Border images live in ``images/MonstersAttack/``:
      LeftRed, TopRed, RightRed, BottomRed        — red border
      LeftBlackRed, TopBlackRed, ...               — dark red
      LeftPink, TopPink, ...                       — pink
      LeftBlackPink, TopBlackPink, ...             — dark pink

    Args:
        battle_region: (left, top, width, height) of the battle list.
        precision: Confidence threshold.

    Returns:
        True if attacking (no idle border pattern matched).
        False if idle or border images are missing.
    """
    img_dir = get_monsters_attack_dir()
    sides = ["Left", "Top", "Right", "Bottom"]
    colour_variants = ["Red", "BlackRed", "Pink", "BlackPink"]

    if not HAS_CV2 or not HAS_MSS or not HAS_NUMPY or cv2 is None or np is None:
        return False

    # Quick check: at least one border image exists
    any_exists = any(
        os.path.isfile(os.path.join(img_dir, f"{side}{variant}.png"))
        for variant in colour_variants
        for side in sides
    )
    if not any_exists:
        return False

    # Capture battle region once
    frame = _capture_region(battle_region)
    if frame is None or frame.size == 0:
        return False

    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    except Exception:
        return False

    # Scan all 16 images, count hits per colour variant
    variant_hits: dict[str, int] = {}
    for variant in colour_variants:
        variant_hits[variant] = 0
        for side in sides:
            img_path = os.path.join(img_dir, f"{side}{variant}.png")
            if not os.path.isfile(img_path):
                continue
            try:
                template = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if template is None:
                    continue
                res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= precision:
                    variant_hits[variant] += 1
            except Exception:
                continue

    # Any variant with all 4 sides = idle border → NOT attacking
    for hits in variant_hits.values():
        if hits >= 4:
            return False
    return True


# ── Follow / Idle detection (from TibiaAuto12 Scanners.py) ────────────


def is_following_needed(precision: float = 0.7) -> bool:
    """Check if the character is in Idle mode (needs follow re-engagement).

    Mirrors TibiaAuto12's ``NeedFollow()``:
    ``LocateImage('images/TibiaSettings/Idle.png', Precision=0.7)``

    Returns:
        True if the Idle indicator is visible (needs follow click).
    """
    return find_ui_element("Idle", precision=precision) is not None


def is_following_active(precision: float = 0.7) -> bool:
    """Check if the character is in Following mode.

    Mirrors TibiaAuto12's ``NeedIdle()``:
    ``LocateImage('images/TibiaSettings/Following.png', Precision=0.7)``

    Returns:
        True if the Following indicator is visible.
    """
    return find_ui_element("Following", precision=precision) is not None
