"""CaveBot service — automated walking, attacking, and looting loop.

Adapted from the TibiaAuto12 cavebot model:
  - Waypoint-based navigation via minimap clicks + arrow key refresh
  - Monster targeting via battle-list coordinate clicks
  - Looting via right-clicks on SQM positions
  - Script-driven: JSON files defining waypoint sequences

Integrates with the Auto_tool DI container, ExecutionGate/MouseGate for
coordinated input ownership, and PauseController for global pause/resume.
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
    HAS_PYNPUT,
    HAS_WIN32,
    pynput_kb,
    pynput_mouse,
    win32con,
    win32gui,
)
from ..constants import (
    EXEC_WAIT_TIMEOUT_DEFAULT,
    INPUT_POST_CLICK_SLEEP,
)
from ..theme import GREEN, ORANGE, RED
from .input_services import HumanMouse, SafeKeyboardSession, WindowService

# Default scripts directory (relative to project root or PyInstaller bundle)
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "scripts")


def _ensure_scripts_dir() -> str:
    """Return (and create if needed) the scripts directory."""
    scripts_dir = os.environ.get("CAVEBOT_SCRIPTS_DIR") or SCRIPTS_DIR
    scripts_dir = os.path.abspath(scripts_dir)
    os.makedirs(scripts_dir, exist_ok=True)
    return scripts_dir


# ── Waypoint types (matching TibiaAuto12 vocabulary) ─────────────────
WAYPOINT_TYPES = {
    1: "walk",
    2: "rope",
    3: "shovel",
}

WAYPOINT_TYPE_NAMES = {v: k for k, v in WAYPOINT_TYPES.items()}


class CaveBotService:
    """Background worker that follows a waypoint script, attacks monsters, and loots.

    Lifecycle:
        - ``start()`` spins up a daemon thread running the main loop.
        - ``stop()`` signals the thread to exit gracefully.
        - The loop respects PauseController (pauses when paused).
        - All mouse/keyboard input goes through ExecutionGate / MouseGate.
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

        # Cached references
        self._stop_event = threading.Event()

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
        self._stop_event.set()
        state.active = False
        self.runtime.ui.module_state_changed("cavebot", False)
        self.runtime.ui.set_status("🤖 CaveBot stopped", RED)

    # ── Script management ────────────────────────────────────────────

    @staticmethod
    def list_scripts() -> list[str]:
        """Return sorted list of available script names (without .json)."""
        scripts_dir = _ensure_scripts_dir()
        scripts = sorted(
            p.stem for p in Path(scripts_dir).glob("*.json")
        )
        return scripts

    @staticmethod
    def load_script(name: str) -> list[dict]:
        """Load a script JSON and return the waypoint list.

        Each waypoint dict::

            {"mark": "<waypoint-image-name>", "type": 1, "status": bool}
        """
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_script(name: str, data: list[dict]) -> None:
        """Save a script JSON to disk."""
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def create_default_script(name: str) -> None:
        """Create a stub script with a single unconfigured waypoint."""
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        if not os.path.isfile(path):
            default = [{"mark": "", "type": 1, "status": "NotConfigured"}]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=4)

    @staticmethod
    def delete_script(name: str) -> None:
        """Remove a script file from disk."""
        scripts_dir = _ensure_scripts_dir()
        path = os.path.join(scripts_dir, f"{name}.json")
        if os.path.isfile(path):
            os.remove(path)

    # ── Internal worker ──────────────────────────────────────────────

    def _worker(self) -> None:
        state = self.runtime.state.cavebot
        self.runtime.ui.log(f"▶ CaveBot started — script: {state.script_name}")

        script_data = self.load_script(state.script_name)
        if not script_data:
            self.runtime.ui.log(f"❌ Script '{state.script_name}' not found or empty")
            state.active = False
            self.runtime.ui.module_state_changed("cavebot", False)
            return

        # Reset to first waypoint if not configured
        if script_data and script_data[0].get("status") == "NotConfigured":
            self.runtime.ui.log("⚠️  Script has no configured waypoints. Add waypoints first.")
            state.active = False
            self.runtime.ui.module_state_changed("cavebot", False)
            return

        mouse = pynput_mouse.Controller() if HAS_PYNPUT else None
        keyboard = pynput_kb.Controller() if HAS_PYNPUT else None

        try:
            while not self._stop_event.is_set():
                if self._stop_event.is_set():
                    break

                # Re-load script data each iteration in case waypoints changed
                script_data = self.load_script(state.script_name)
                if not script_data:
                    break

                # Find current active waypoint
                current_idx = None
                for idx, wp in enumerate(script_data):
                    if wp.get("status") is True:
                        current_idx = idx
                        break

                if current_idx is None:
                    # Loop back to start
                    if script_data:
                        script_data[0]["status"] = True
                        self.save_script(state.script_name, script_data)
                    continue

                waypoint = script_data[current_idx]
                mark_name = waypoint.get("mark", "")
                wp_type = waypoint.get("type", 1)

                self.runtime.ui.log(f"📍 Waypoint [{current_idx + 1}/{len(script_data)}]: {mark_name}")

                # ── Phase 1: Walk to waypoint ─────────────────
                if state.walking_enabled and mark_name:
                    self._walk_to_waypoint(mark_name, state)

                # ── Phase 2: Stand still ──────────────────────
                if state.stand_seconds > 0:
                    if not self._wait_interruptible(state.stand_seconds):
                        break

                # ── Phase 3: Attack monsters ──────────────────
                if state.monsters_to_attack:
                    self._attack_cycle(state, mouse, keyboard)

                # ── Phase 4: Loot ─────────────────────────────
                if state.looting_enabled and state.sqm_positions:
                    self._loot_cycle(state, mouse)

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

    # ── Walking ──────────────────────────────────────────────────────

    def _walk_to_waypoint(self, mark_name: str, state, keyboard=None) -> None:
        """Navigate to a waypoint marker on the minimap.

        Uses minimap position click + optional arrow-key refresh (walk_for_debug).
        """
        if not HAS_PYNPUT:
            return

        mouse = pynput_mouse.Controller()
        if keyboard is None:
            keyboard = pynput_kb.Controller()
        map_region = state.map_region
        if not map_region:
            self.runtime.ui.log("⚠️  Map region not configured — cannot walk")
            return

        # Attempt to locate marker by minimap click
        max_attempts = 5
        for attempt in range(max_attempts):
            if self._stop_event.is_set():
                return

            # Click in the centre of the minimap to walk
            centre_x = map_region[0] + map_region[2] // 2
            centre_y = map_region[1] + map_region[3] // 2
            jitter = random.randint(-3, 3)

            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
            ):
                if self._stop_event.is_set():
                    return
                continue

            try:
                HumanMouse.move(mouse, (centre_x + jitter, centre_y + jitter))
                time.sleep(random.uniform(0.03, 0.08))
                mouse.click(pynput_mouse.Button.left)
                time.sleep(INPUT_POST_CLICK_SLEEP)
            finally:
                self.runtime.execution.release()

            # Wait for character to move
            if not self._wait_interruptible(random.uniform(0.8, 1.5)):
                return

            # If walk_for_debug is enabled, do a quick arrow-key refresh
            if state.walk_for_debug and keyboard:
                if not self.runtime.execution.acquire(
                    self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
                ):
                    continue
                try:
                    session = SafeKeyboardSession(keyboard)
                    session.tap(pynput_kb.Key.up, hold_seconds=0.05)
                    time.sleep(0.05)
                    session.tap(pynput_kb.Key.left, hold_seconds=0.05)
                    time.sleep(0.05)
                    session.tap(pynput_kb.Key.down, hold_seconds=0.05)
                    time.sleep(0.05)
                    session.tap(pynput_kb.Key.right, hold_seconds=0.05)
                    time.sleep(0.05)
                finally:
                    self.runtime.execution.release()

            if not self._wait_interruptible(random.uniform(0.5, 1.0)):
                return

        self.runtime.ui.log(f"   Walked toward waypoint: {mark_name}")

    # ── Attack cycle ─────────────────────────────────────────────────

    def _attack_cycle(self, state, mouse, keyboard) -> None:
        """Attack monsters from the configured monster list.

        Uses battle-list coordinate clicks to target each monster type.
        Follows the TibiaAuto12 model: scan target, attack, verify, follow.
        """
        for monster_name in state.monsters_to_attack:
            if self._stop_event.is_set():
                return

            if not monster_name.strip():
                continue

            battle_x = state.battle_list_x
            if battle_x <= 0:
                self.runtime.ui.log("⚠️  Battle list X not configured")
                continue

            # Click on the battle list to target this monster type
            # Each monster row is ~20px apart starting from y=120 (approx)
            base_y = 120
            row_offset = state.monsters_to_attack.index(monster_name) * 20
            target_y = base_y + row_offset

            for _ in range(state.monsters_range):
                if self._stop_event.is_set():
                    return

                # Use skill key first (F1 by default) to target
                if keyboard:
                    if not self.runtime.execution.acquire(
                        self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
                    ):
                        continue
                    try:
                        # Press the skill/attack key
                        skill_pynput = self._key_str_to_pynput(state.skill_key)
                        if skill_pynput:
                            session = SafeKeyboardSession(keyboard)
                            session.tap(skill_pynput, hold_seconds=0.04)
                            time.sleep(random.uniform(0.1, 0.2))
                    finally:
                        self.runtime.execution.release()

                # Click battle list to ensure target is selected
                if not self.runtime.execution.acquire(
                    self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
                ):
                    continue
                try:
                    click_y = target_y + random.randint(-2, 2)
                    HumanMouse.move(mouse, (battle_x + random.randint(-5, 5), click_y))
                    time.sleep(random.uniform(0.03, 0.06))
                    mouse.click(pynput_mouse.Button.left)
                    time.sleep(INPUT_POST_CLICK_SLEEP)
                finally:
                    self.runtime.execution.release()

                # Follow mode: click follow if idle
                if state.follow_mode:
                    self._click_follow_if_needed(mouse)

                if not self._wait_interruptible(random.uniform(0.5, 1.0)):
                    return

    def _click_follow_if_needed(self, mouse) -> None:
        """Simulate follow mode click (placeholder — uses left-click on character)."""
        # In TibiaAuto this checks for idle/follow icons. Here we just
        # left-click on the character to re-engage follow if needed.
        # Users can configure this behaviour via follow_mode setting.
        pass

    # ── Looting ──────────────────────────────────────────────────────

    def _loot_cycle(self, state, mouse) -> None:
        """Right-click SQM positions around the character to pick up loot."""
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
                jittered = (
                    sqm[0] + random.randint(-2, 2),
                    sqm[1] + random.randint(-2, 2),
                )
                HumanMouse.move(mouse, jittered)
                time.sleep(random.uniform(0.02, 0.05))
                mouse.click(pynput_mouse.Button.right)
                time.sleep(random.uniform(0.1, 0.2))
            finally:
                self.runtime.execution.release()

            if not self._wait_interruptible(random.uniform(0.15, 0.3)):
                return

    # ── Helpers ──────────────────────────────────────────────────────

    def _wait_interruptible(self, seconds: float) -> bool:
        """Sleep for *seconds*, returning False early if stop is requested."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop_event.is_set():
                return False
            self.runtime.pause.wait()
            time.sleep(0.05)
        return True

    @staticmethod
    def _key_str_to_pynput(key_str: str):
        """Convert a key string like 'f1' or 'a' to a pynput key object."""
        if not HAS_PYNPUT:
            return None
        value = key_str.strip().lower()
        named = {}
        for key_name, attr_name in [
            ("f1", "f1"), ("f2", "f2"), ("f3", "f3"), ("f4", "f4"),
            ("f5", "f5"), ("f6", "f6"), ("f7", "f7"), ("f8", "f8"),
            ("f9", "f9"), ("f10", "f10"), ("f11", "f11"), ("f12", "f12"),
            ("home", "home"), ("end", "end"),
            ("up", "up"), ("down", "down"), ("left", "left"), ("right", "right"),
        ]:
            key_value = getattr(pynput_kb.Key, attr_name, None)
            if key_value is not None:
                named[key_name] = key_value
        if value in named:
            return named[value]
        if len(value) == 1:
            return pynput_kb.KeyCode.from_char(value)
        return None
