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
    HAS_PYNPUT,
    HAS_WIN32,
    pynput_kb,
)
from ..constants import (
    EXEC_WAIT_TIMEOUT_DEFAULT,
    INPUT_POST_CLICK_SLEEP,
)
from ..theme import GREEN, ORANGE, RED
from .input_services import HumanMouse, SafeKeyboardSession

# Default scripts directory
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "scripts")


def _ensure_scripts_dir() -> str:
    scripts_dir = os.environ.get("CAVEBOT_SCRIPTS_DIR") or SCRIPTS_DIR
    scripts_dir = os.path.abspath(scripts_dir)
    os.makedirs(scripts_dir, exist_ok=True)
    return scripts_dir


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

    # ── Internal worker ──────────────────────────────────────────────

    def _worker(self) -> None:
        state = self.runtime.state.cavebot
        router = self.runtime.input_router
        self.runtime.ui.log(f"▶ CaveBot started — script: {state.script_name} (input: {self.runtime.state.input_mode})")

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

                # ── Phase 3: Attack window ────────────────────
                if state.monsters_to_attack:
                    attack_time = max(2.0, state.stand_seconds * 2)
                    if not self._wait_interruptible(attack_time):
                        break

                # ── Phase 4: Loot ─────────────────────────────
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

        if wp_x > 0 and wp_y > 0:
            click_x, click_y = wp_x, wp_y
        else:
            click_x = map_region[0] + map_region[2] // 2
            click_y = map_region[1] + map_region[3] // 2

        max_attempts = 3
        for attempt in range(max_attempts):
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

        mode = self.runtime.state.input_mode
        self.runtime.ui.log(f"   Walked → ({click_x}, {click_y}) [{mode}]")

    def _do_arrow_refresh(self, router) -> None:
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
