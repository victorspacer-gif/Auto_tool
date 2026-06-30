"""CaveBot service — waypoint navigation orchestrator with image-based detection.

Adapted from the TibiaAuto12 CaveBotController:
  1. Load script → find active waypoint
  2. Walk to waypoint (image-detected mark OR coordinate fallback)
  3. Stand still for N seconds
  4. Attack window — image-based IsAttacking border analysis:
     a. Wait for coloured battle border (combat starts)
     b. Wait for border to disappear (monster killed)
     c. Falls back to timing when border images are unavailable
  5. Signal AutoLooter to loot
  6. Advance to next waypoint
  7. Loop back to start on completion

Walking uses OpenCV template matching to locate the waypoint mark icon on the
minimap (like TibiaAuto12), falling back to absolute coordinate clicks when
image detection fails or is disabled.

Arrival detection uses the same technique — checks whether the mark icon is
near the centre of the minimap to confirm arrival before advancing.

All mouse/keyboard input goes through InputRouter which supports two modes:
  - "hardware" (pynput — physical cursor movement)
  - "direct" (Win32 SendMessage — background window injection)
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from ..runtime import (
    AppRuntime,
    HAS_CV2,
    HAS_MSS,
    HAS_NUMPY,
    cv2,
    mss,
    np,
)
from ..constants import (
    EXEC_WAIT_TIMEOUT_DEFAULT,
    INPUT_POST_CLICK_SLEEP,
)
from ..theme import GREEN, ORANGE, RED
from .image_finder import (
    is_attacking,
    locate_center_image,
    locate_image,
    get_map_settings_dir,
    list_available_images as _list_marks,
    wait_until_attacking,
    wait_until_not_attacking,
)

# Default scripts directory
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "scripts")

# Maximum retries for image-based waypoint location before falling back to coords
MAX_IMAGE_RETRIES = 3


def _ensure_scripts_dir() -> str:
    scripts_dir = os.environ.get("CAVEBOT_SCRIPTS_DIR") or SCRIPTS_DIR
    scripts_dir = os.path.abspath(scripts_dir)
    os.makedirs(scripts_dir, exist_ok=True)
    return scripts_dir


def _get_project_root() -> str:
    """Return the Auto_tool project root directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CaveBotService:
    """Background waypoint walker and cavebot orchestrator."""

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._stop_event = threading.Event()
        self.chase_target_service: object | None = None
        self.auto_looter_service: object | None = None

    # ── Public API ────────────────────────────────────────────────────

    def start(self) -> None:
        state = self.runtime.state.cavebot
        if state.active:
            return
        if not state.script_name.strip():
            self.runtime.ui.log("⚠️  No cavebot script selected")
            self.runtime.ui.set_status("Select a script first", ORANGE)
            return
        state.active = True
        self._stop_event.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.module_state_changed("cavebot", True)
        self.runtime.ui.set_status("🤖 CaveBot started", GREEN)

    def stop(self) -> None:
        state = self.runtime.state.cavebot
        if not state.active:
            return
        if self.chase_target_service is not None:
            try:
                self.chase_target_service.stop()
            except Exception:
                pass
        if self.auto_looter_service is not None:
            try:
                self.auto_looter_service.stop()
            except Exception:
                pass
        self._stop_event.set()
        state.active = False
        self.runtime.ui.module_state_changed("cavebot", False)
        self.runtime.ui.set_status("🤖 CaveBot stopped", RED)

    # ── Script management ────────────────────────────────────────────

    @staticmethod
    def list_scripts() -> list[str]:
        scripts_dir = _ensure_scripts_dir()
        return sorted(p.stem for p in Path(scripts_dir).glob("*.json"))

    @staticmethod
    def load_script(name: str) -> list[dict]:
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_script(name: str, data: list[dict]) -> None:
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def create_default_script(name: str) -> None:
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        if not os.path.isfile(path):
            default = [{"mark": "", "x": 0, "y": 0, "type": 1, "status": "NotConfigured"}]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=4)

    @staticmethod
    def delete_script(name: str) -> None:
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        if os.path.isfile(path):
            os.remove(path)

    # ── Image assets ──────────────────────────────────────────────────

    @staticmethod
    def list_available_marks() -> list[str]:
        """Return names of available mark images (without extension)."""
        return _list_marks("MapSettings")

    # ── Image-based waypoint detection ────────────────────────────────

    def _locate_mark_on_minimap(self, mark_name: str, map_region: tuple[int, int, int, int]) -> tuple[int, int] | None:
        """Find a waypoint mark icon on the minimap using OpenCV template matching.

        This is the core navigation method, matching TibiaAuto12's approach in
        CaveBotController.py line 67: ``LocateCenterImage('images/MapSettings/X.png', Region=map, Precision=0.8)``

        Uses ImageFinder's ``locate_center_image()`` which captures the minimap
        region via mss and runs ``cv2.matchTemplate()`` against the mark PNG.

        Args:
            mark_name: The mark name (e.g. 'CheckMark', 'Star').
            map_region: (left, top, width, height) of the minimap area.

        Returns:
            (centre_x, centre_y) in **screen** coordinates, or None if not found.
        """
        if not HAS_CV2 or not HAS_MSS or not HAS_NUMPY:
            return None

        img_dir = get_map_settings_dir()
        mark_path = os.path.join(img_dir, f"{mark_name}.png")
        if not os.path.isfile(mark_path):
            return None

        precision = self.runtime.state.cavebot.image_detection_precision
        return locate_center_image(mark_path, region=map_region, precision=precision)

    def _check_arrived_at_waypoint(self, mark_name: str, map_region: tuple[int, int, int, int]) -> bool:
        """Check if the player has arrived at the waypoint.

        Mirrors TibiaAuto12's ``CheckWaypoint()`` (Scanners.py line 32):
        checks whether the mark icon is found **near the centre** of the minimap
        (with a 48px margin), indicating the character has walked close enough.

        Uses ImageFinder's ``locate_image()`` on the centre-cropped minimap region.

        Args:
            mark_name: The mark name (e.g. 'CheckMark').
            map_region: (left, top, width, height) of the minimap area.

        Returns:
            True if the mark is found in the centre region of the minimap.
        """
        if not HAS_CV2 or not HAS_MSS or not HAS_NUMPY:
            return False

        img_dir = get_map_settings_dir()
        mark_path = os.path.join(img_dir, f"{mark_name}.png")
        if not os.path.isfile(mark_path):
            return False

        precision = self.runtime.state.cavebot.image_detection_precision

        # Crop to centre region (48px margin on each side, matching TibiaAuto12)
        left, top, width, height = map_region
        centre_margin = 48
        if width > centre_margin * 2 and height > centre_margin * 2:
            centre_region = (
                left + centre_margin,
                top + centre_margin,
                width - centre_margin * 2,
                height - centre_margin * 2,
            )
        else:
            centre_region = map_region

        pos = locate_image(mark_path, region=centre_region, precision=precision)
        return pos is not None

    # ── Internal worker ──────────────────────────────────────────────

    def _worker(self) -> None:
        state = self.runtime.state.cavebot
        router = self.runtime.input_router

        # Log image availability
        img_status = "enabled" if (state.image_detection_enabled and HAS_CV2 and HAS_MSS) else "disabled"
        avail_marks = len(self.list_available_marks())
        self.runtime.ui.log(
            f"▶ CaveBot started — script: {state.script_name} "
            f"(input: {self.runtime.state.input_mode}, image-detection: {img_status}, "
            f"marks-available: {avail_marks})"
        )

        script_data = self.load_script(state.script_name)
        if not script_data:
            self.runtime.ui.log(f"❌ Script '{state.script_name}' not found or empty")
            state.active = False
            self.runtime.ui.module_state_changed("cavebot", False)
            return

        if script_data and script_data[0].get("status") == "NotConfigured":
            self.runtime.ui.log("⚠️  Script has no configured waypoints. Add waypoints first.")
            state.active = False
            self.runtime.ui.module_state_changed("cavebot", False)
            return

        self._start_companions()

        try:
            while not self._stop_event.is_set():
                self.runtime.pause.wait()
                if self._stop_event.is_set():
                    break

                script_data = self.load_script(state.script_name)
                if not script_data:
                    break

                current_idx = self._find_active_waypoint(script_data)
                if current_idx is None:
                    if script_data:
                        script_data[0]["status"] = True
                        self.save_script(state.script_name, script_data)
                    continue

                waypoint = script_data[current_idx]
                mark_name = waypoint.get("mark", "")
                wp_x = waypoint.get("x", 0)
                wp_y = waypoint.get("y", 0)
                wp_type = waypoint.get("type", 1)
                total = len(script_data)
                self.runtime.ui.log(f"📍 [{current_idx + 1}/{total}] {mark_name or f'({wp_x},{wp_y})'} type={wp_type}")

                # ── Phase 1: Walk to waypoint ─────────────────
                if state.walking_enabled:
                    self._walk_to_waypoint(mark_name, wp_x, wp_y, state, router)

                # ── Phase 2: Stand still ──────────────────────
                if state.stand_seconds > 0:
                    if not self._wait_interruptible(state.stand_seconds):
                        break

                # ── Phase 3: Arrival check (image detection) ──
                if state.arrival_detection_enabled and state.image_detection_enabled and mark_name and state.map_region:
                    arrived = False
                    for attempt in range(3):
                        if self._stop_event.is_set():
                            break
                        if self._check_arrived_at_waypoint(mark_name, state.map_region):
                            arrived = True
                            break
                        if not self._wait_interruptible(0.3):
                            break
                    if not arrived and mark_name:
                        self.runtime.ui.log(f"   ⏳ Waiting for arrival at {mark_name}...")
                        # Retry with longer wait
                        for _ in range(5):
                            if self._stop_event.is_set():
                                break
                            if self._check_arrived_at_waypoint(mark_name, state.map_region):
                                arrived = True
                                break
                            if not self._wait_interruptible(0.5):
                                break
                    if arrived:
                        self.runtime.ui.log(f"   ✅ Arrived at {mark_name}")
                    else:
                        self.runtime.ui.log(f"   ⚠️  Could not confirm arrival at {mark_name} (continuing)")

                # ── Phase 4: Attack window (image-based IsAttacking) ─
                if state.monsters_to_attack:
                    # Resolve battle region: use chase_target's config if available
                    battle_region = None
                    chase_region = self.runtime.state.chase_target.battle_region
                    if chase_region is not None and all(v > 0 for v in chase_region):
                        battle_region = chase_region

                    if battle_region is not None and HAS_CV2 and HAS_MSS and HAS_NUMPY:
                        # ── Image-based attack window ──────────────
                        # Wait for combat to start (max 5s — monster may be far)
                        combat_started = wait_until_attacking(
                            battle_region, timeout=5.0, check_interval=0.15, precision=0.8,
                        )
                        if combat_started:
                            self.runtime.ui.log("   ⚔️  Combat started (border detected)")
                            # Wait for combat to end (max 20s — typical kill time)
                            combat_ended = wait_until_not_attacking(
                                battle_region, timeout=20.0, check_interval=0.25, precision=0.8,
                            )
                            if combat_ended:
                                self.runtime.ui.log("   ✅ Combat ended")
                            else:
                                self.runtime.ui.log("   ⚠️  Combat timeout (20s) — proceeding")
                        else:
                            self.runtime.ui.log("   ⏳ No target found in 5s — continuing")
                    else:
                        # ── Fallback: timing-based window ───────────
                        attack_time = max(2.0, state.stand_seconds * 2)
                        self.runtime.ui.log(f"   ⏱️  Timing-based attack window ({attack_time:.1f}s)")
                        if not self._wait_interruptible(attack_time):
                            break

                # ── Phase 5: Loot ─────────────────────────────
                if state.looting_enabled and state.sqm_positions:
                    self._loot_cycle(state, router)
                    if not self._wait_interruptible(random.uniform(0.3, 0.6)):
                        break
                    self._loot_cycle(state, router)

                # ── Advance to next waypoint ──────────────────
                script_data[current_idx]["status"] = False
                next_idx = (current_idx + 1) % len(script_data)
                script_data[next_idx]["status"] = True
                self.save_script(state.script_name, script_data)

        except Exception as exc:
            logger.exception("CaveBot worker crashed")
            self.runtime.ui.log(f"❌ CaveBot error: {exc}")
        finally:
            state.active = False
            self.runtime.ui.module_state_changed("cavebot", False)
            self.runtime.ui.log("⏹ CaveBot ended")

    # ── Companion services ───────────────────────────────────────────

    def _start_companions(self) -> None:
        if self.chase_target_service is not None:
            try:
                chase_state = self.runtime.state.chase_target
                if chase_state.monster_names and chase_state.battle_list_x > 0:
                    self.chase_target_service.start()
            except Exception:
                pass
        if self.auto_looter_service is not None:
            try:
                looter_state = self.runtime.state.auto_looter
                if looter_state.sqm_positions:
                    self.auto_looter_service.start()
            except Exception:
                pass

    # ── Walking ──────────────────────────────────────────────────────

    def _walk_to_waypoint(self, mark_name: str, wp_x: int, wp_y: int, state, router) -> None:
        map_region = state.map_region
        if not map_region:
            self.runtime.ui.log("⚠️  Map region not configured — cannot walk")
            return

        # ── Strategy 1: Image-based mark detection (primary) ──────
        image_clicked = False
        if state.image_detection_enabled and HAS_CV2 and HAS_MSS and mark_name:
            for attempt in range(MAX_IMAGE_RETRIES):
                if self._stop_event.is_set():
                    return

                pos = self._locate_mark_on_minimap(mark_name, map_region)
                if pos is not None:
                    click_x, click_y = pos
                    # Add jitter for human-like movement
                    jx, jy = click_x + random.randint(-2, 2), click_y + random.randint(-2, 2)

                    if not self.runtime.execution.acquire(
                        self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
                    ):
                        if self._stop_event.is_set():
                            return
                        continue

                    try:
                        router.human_move_and_click(jx, jy, "left")
                        time.sleep(INPUT_POST_CLICK_SLEEP)
                    finally:
                        self.runtime.execution.release()

                    image_clicked = True
                    self.runtime.ui.log(f"   [img] Found {mark_name} → clicked ({jx}, {jy})")
                    break
                else:
                    # Arrow refresh to scroll minimap (like TibiaAuto12 WalkForRefresh)
                    if state.walk_for_debug:
                        self._do_arrow_refresh(router)
                    if not self._wait_interruptible(random.uniform(0.5, 1.0)):
                        return

        # ── Strategy 2: Coordinate fallback ────────────────────────
        if not image_clicked:
            if wp_x > 0 and wp_y > 0:
                click_x, click_y = wp_x, wp_y
            else:
                click_x = map_region[0] + map_region[2] // 2
                click_y = map_region[1] + map_region[3] // 2

            for attempt in range(3):
                if self._stop_event.is_set():
                    return

                jx, jy = click_x + random.randint(-3, 3), click_y + random.randint(-3, 3)

                if not self.runtime.execution.acquire(
                    self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
                ):
                    if self._stop_event.is_set():
                        return
                    continue

                try:
                    router.human_move_and_click(jx, jy, "left")
                    time.sleep(INPUT_POST_CLICK_SLEEP)
                finally:
                    self.runtime.execution.release()

                if not self._wait_interruptible(random.uniform(0.8, 1.2)):
                    return

                if state.walk_for_debug:
                    self._do_arrow_refresh(router)

            mode = "coord" if (wp_x > 0 and wp_y > 0) else "map-centre"
            self.runtime.ui.log(f"   Walked → ({click_x}, {click_y}) [{mode}]")

    def _do_arrow_refresh(self, router) -> None:
        """Press arrow keys to scroll the minimap (helps find lost marks)."""
        if not self.runtime.execution.acquire(
            self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
        ):
            return
        try:
            for key in ["up", "left", "down", "right"]:
                router.tap_key(key, hold_seconds=0.04)
                time.sleep(0.04)
        finally:
            self.runtime.execution.release()

    # ── Looting ──────────────────────────────────────────────────────

    def _loot_cycle(self, state, router) -> None:
        if not state.sqm_positions:
            return

        for sqm in state.sqm_positions:
            if self._stop_event.is_set():
                return

            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
            ):
                continue

            try:
                jx = sqm[0] + random.randint(-2, 2)
                jy = sqm[1] + random.randint(-2, 2)
                router.right_click(jx, jy)
                time.sleep(random.uniform(0.08, 0.15))
            finally:
                self.runtime.execution.release()

            if not self._wait_interruptible(random.uniform(0.1, 0.2)):
                return

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _find_active_waypoint(script_data: list[dict]) -> int | None:
        for idx, wp in enumerate(script_data):
            if wp.get("status") is True:
                return idx
        return None

    def _wait_interruptible(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop_event.is_set():
                return False
            self.runtime.pause.wait()
            time.sleep(0.05)
        return True
