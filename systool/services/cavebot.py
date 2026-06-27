"""CaveBot service — waypoint navigation orchestrator.

Adapted from the TibiaAuto12 CaveBotController:
  1. Load script → find active waypoint
  2. Walk to waypoint coordinate (minimap click)
  3. Stand still for N seconds
  4. Signal ChaseTarget to attack monsters
  5. Signal AutoLooter to loot
  6. Advance to next waypoint
  7. Loop back to start on completion

When walking is disabled, the cavebot stays at the current position and
only runs the attack + loot cycle (camping mode).

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

# Default scripts directory
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "scripts")


def _ensure_scripts_dir() -> str:
    scripts_dir = os.environ.get("CAVEBOT_SCRIPTS_DIR") or SCRIPTS_DIR
    scripts_dir = os.path.abspath(scripts_dir)
    os.makedirs(scripts_dir, exist_ok=True)
    return scripts_dir


class CaveBotService:
    """Background waypoint walker and cavebot orchestrator.

    Lifecycle:
        - ``start()`` spins up a daemon thread running the main loop.
        - ``stop()`` signals the thread to exit gracefully.
        - The loop respects PauseController (pauses when paused).
        - All mouse/keyboard input goes through ExecutionGate / MouseGate.
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._stop_event = threading.Event()

        # Optional references to companion services (set via wiring)
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
        # Also stop chase target and auto looter when cavebot stops
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

        if script_data and script_data[0].get("status") == "NotConfigured":
            self.runtime.ui.log("⚠️  Script has no configured waypoints. Add waypoints first.")
            state.active = False
            self.runtime.ui.module_state_changed("cavebot", False)
            return

        mouse = pynput_mouse.Controller() if HAS_PYNPUT else None

        # Start companion services if configured
        self._start_companions()

        try:
            while not self._stop_event.is_set():
                self.runtime.pause.wait()
                if self._stop_event.is_set():
                    break

                # Re-load script data each iteration
                script_data = self.load_script(state.script_name)
                if not script_data:
                    break

                # Find current active waypoint
                current_idx = self._find_active_waypoint(script_data)
                if current_idx is None:
                    # Loop back to start
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
                if state.walking_enabled and mouse:
                    self._walk_to_waypoint(mark_name, wp_x, wp_y, state, mouse)

                # ── Phase 2: Stand still ──────────────────────
                if state.stand_seconds > 0:
                    if not self._wait_interruptible(state.stand_seconds):
                        break

                # ── Phase 3: Attack window (let chase target work) ──
                if state.monsters_to_attack:
                    # Wait while chase target attacks — check every 0.5s
                    attack_time = max(2.0, state.stand_seconds * 2)
                    if not self._wait_interruptible(attack_time):
                        break

                # ── Phase 4: Loot ─────────────────────────────
                if state.looting_enabled and state.sqm_positions:
                    self._loot_cycle(state, mouse)
                    # Second pass for nearby corpses
                    if not self._wait_interruptible(random.uniform(0.3, 0.6)):
                        break
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

    # ── Companion services ───────────────────────────────────────────

    def _start_companions(self) -> None:
        """Start chase target and auto looter if they are configured."""
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

    def _walk_to_waypoint(self, mark_name: str, wp_x: int, wp_y: int, state, mouse) -> None:
        """Navigate to a waypoint using minimap crosshair click.

        If the waypoint has coordinates (x, y), clicks at that position
        on the minimap. Otherwise falls back to minimap centre-click.
        """
        if not HAS_PYNPUT:
            return

        map_region = state.map_region
        if not map_region:
            self.runtime.ui.log("⚠️  Map region not configured — cannot walk")
            return

        # Determine click position
        if wp_x > 0 and wp_y > 0:
            # Use waypoint coordinates directly
            click_x = wp_x
            click_y = wp_y
        else:
            # Fallback to minimap centre
            click_x = map_region[0] + map_region[2] // 2
            click_y = map_region[1] + map_region[3] // 2

        max_attempts = 3
        for attempt in range(max_attempts):
            if self._stop_event.is_set():
                return

            jitter_x = click_x + random.randint(-3, 3)
            jitter_y = click_y + random.randint(-3, 3)

            if not self.runtime.execution.acquire(
                self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
            ):
                if self._stop_event.is_set():
                    return
                continue

            try:
                HumanMouse.move(mouse, (jitter_x, jitter_y))
                time.sleep(random.uniform(0.03, 0.08))
                mouse.click(pynput_mouse.Button.left)
                time.sleep(INPUT_POST_CLICK_SLEEP)
            finally:
                self.runtime.execution.release()

            # Wait for character to start moving
            if not self._wait_interruptible(random.uniform(0.8, 1.2)):
                return

            # Walk-for-debug: do arrow-key refresh to force minimap update
            if state.walk_for_debug:
                self._do_arrow_refresh()

        self.runtime.ui.log(f"   Walked → ({click_x}, {click_y})")

    def _do_arrow_refresh(self) -> None:
        """Press arrow keys briefly to force minimap refresh (debug mode)."""
        if not HAS_PYNPUT:
            return
        keyboard = pynput_kb.Controller()
        if not self.runtime.execution.acquire(
            self._stop_event, max_wait=EXEC_WAIT_TIMEOUT_DEFAULT, module_id="cavebot"
        ):
            return
        try:
            session = SafeKeyboardSession(keyboard)
            for key in [pynput_kb.Key.up, pynput_kb.Key.left, pynput_kb.Key.down, pynput_kb.Key.right]:
                session.tap(key, hold_seconds=0.04)
                time.sleep(0.04)
        finally:
            self.runtime.execution.release()

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
