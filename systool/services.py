"""Automation features and infrastructure services."""

from __future__ import annotations

import math
import os
import random
import re
import threading
import time
from collections.abc import Callable

import psutil

try:
    from studiomemuer_light_module.light_profile import DEFAULT_PROFILE as DEFAULT_LIGHT_PROFILE
    from studiomemuer_light_module.memory_backend import (
        LightMemoryController,
        MemoryWriteError,
        ProcessNotFoundError,
    )

    HAS_LIGHT_MODULE = True
except ImportError:
    DEFAULT_LIGHT_PROFILE = None
    LightMemoryController = None
    MemoryWriteError = RuntimeError
    ProcessNotFoundError = RuntimeError
    HAS_LIGHT_MODULE = False

from .models import HotkeyJob
from .runtime import (
    AppRuntime,
    HAS_CV2,
    HAS_MSS,
    HAS_NUMPY,
    HAS_PYGAME,
    HAS_PYNPUT,
    HAS_TESSERACT,
    HAS_WIN32,
    CV2_IMPORT_ERROR,
    MSS_IMPORT_ERROR,
    NUMPY_IMPORT_ERROR,
    TESSERACT_IMPORT_ERROR,
    cv2,
    configure_tesseract_runtime,
    mss,
    np,
    pygame,
    pynput_kb,
    pynput_mouse,
    pytesseract,
    resolve_tesseract_cmd,
    win32con,
    win32gui,
)
from .theme import GREEN, ORANGE, RED, TEAL


class HumanMouse:
    @staticmethod
    def jitter(pos: tuple[int, int], amount: int) -> tuple[int, int]:
        return (
            pos[0] + random.randint(-amount, amount),
            pos[1] + random.randint(-amount, amount),
        )

    @staticmethod
    def move(mouse, target: tuple[int, int], duration: float | None = None) -> None:
        sx, sy = mouse.position
        ex, ey = target
        dx, dy = ex - sx, ey - sy
        distance = math.hypot(dx, dy)
        if distance < 1:
            mouse.position = (int(ex), int(ey))
            return
        if duration is None:
            duration = max(0.12, min(0.55, distance / random.uniform(900, 1500)))
        steps = max(10, int(distance / 7))
        control_scale = random.uniform(-35, 35)
        cx = (sx + ex) / 2 + (-dy / distance) * control_scale
        cy = (sy + ey) / 2 + (dx / distance) * control_scale
        step_duration = duration / steps
        for index in range(steps):
            t_value = index / steps
            eased = t_value * t_value * (3.0 - 2.0 * t_value)
            x_pos = (1 - eased) ** 2 * sx + 2 * (1 - eased) * eased * cx + eased**2 * ex
            y_pos = (1 - eased) ** 2 * sy + 2 * (1 - eased) * eased * cy + eased**2 * ey
            fade = 1.0 - t_value
            x_pos += random.uniform(-0.9, 0.9) * fade
            y_pos += random.uniform(-0.9, 0.9) * fade
            mouse.position = (int(x_pos), int(y_pos))
            time.sleep(step_duration)
        mouse.position = (int(ex), int(ey))

    @staticmethod
    def drag(
        mouse,
        source: tuple[int, int],
        dest: tuple[int, int],
        *,
        move_duration: float | None = None,
        press_delay_range: tuple[float, float] = (0.06, 0.14),
        hold_delay_range: tuple[float, float] = (0.05, 0.10),
        settle_delay_range: tuple[float, float] = (0.04, 0.09),
    ) -> None:
        HumanMouse.move(mouse, source, duration=move_duration)
        time.sleep(random.uniform(*press_delay_range))
        mouse.press(pynput_mouse.Button.left)
        time.sleep(random.uniform(*hold_delay_range))
        HumanMouse.move(mouse, dest, duration=move_duration)
        time.sleep(random.uniform(*settle_delay_range))
        mouse.release(pynput_mouse.Button.left)


class SafeKeyboardSession:
    """Tracks pressed keys and guarantees they are released in reverse order."""

    def __init__(self, keyboard) -> None:
        self.keyboard = keyboard
        self._pressed: list[object] = []

    def tap(self, key, hold_seconds: float = 0.03) -> None:
        self.press(key)
        time.sleep(max(0.0, hold_seconds))
        self.release(key)

    def press(self, key) -> None:
        self.keyboard.press(key)
        self._pressed.append(key)

    def release(self, key) -> None:
        self.keyboard.release(key)
        for index in range(len(self._pressed) - 1, -1, -1):
            if self._pressed[index] == key:
                del self._pressed[index]
                break

    def release_all(self) -> None:
        while self._pressed:
            key = self._pressed.pop()
            try:
                self.keyboard.release(key)
            except Exception:
                pass


class WindowService:
    @staticmethod
    def get_foreground_hwnd():
        if not HAS_WIN32:
            return None
        try:
            return win32gui.GetForegroundWindow()
        except Exception:
            return None

    @staticmethod
    def focus_window_by_name(name_fragment: str) -> bool:
        if not HAS_WIN32:
            return False
        found = [None]

        def callback(hwnd, _):
            if found[0]:
                return
            try:
                title = win32gui.GetWindowText(hwnd)
                if name_fragment.lower() in title.lower() and win32gui.IsWindowVisible(hwnd):
                    found[0] = hwnd
            except Exception:
                pass

        try:
            win32gui.EnumWindows(callback, None)
            if found[0]:
                win32gui.ShowWindow(found[0], win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(found[0])
                time.sleep(0.08)
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def restore(hwnd) -> None:
        if not HAS_WIN32 or not hwnd:
            return
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass


class LightControlService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller = None
        self._freeze_stop = threading.Event()
        self._freeze_thread: threading.Thread | None = None

    def is_available(self) -> bool:
        return HAS_LIGHT_MODULE

    def _profile(self):
        if DEFAULT_LIGHT_PROFILE is None:
            raise RuntimeError("Light profile unavailable")
        return DEFAULT_LIGHT_PROFILE

    def attach(self) -> tuple[bool, str]:
        if not HAS_LIGHT_MODULE:
            return False, "Install psutil and pymem to use light control"

        process_name = self.runtime.state.light_process_name.strip()
        try:
            self.controller = LightMemoryController(process_name)
            self.controller.attach()
            return True, f"Attached to {process_name} | pointer list loaded"
        except ProcessNotFoundError as exc:
            fallback_name = self._find_game_process_name()
            if not fallback_name:
                return False, str(exc)
            try:
                self.controller = LightMemoryController(fallback_name)
                self.controller.attach()
                self.runtime.state.light_process_name = fallback_name
                return True, f"Attached to {fallback_name} | auto-detected game process"
            except Exception as fallback_exc:
                return False, f"{exc} | fallback attach failed: {fallback_exc}"
        except Exception as exc:
            return False, f"Attach failed: {exc}"

    def detach(self) -> tuple[bool, str]:
        self.stop_freeze()
        if self.controller is not None:
            try:
                self.controller.detach()
            except Exception:
                pass
            self.controller = None
        return True, "Detached"

    def apply_default(self) -> tuple[bool, str]:
        profile = self._profile()
        ok, message = self._apply(
            color_value=profile.color_enabled_value,
            intensity_value=profile.default_intensity_value,
        )
        if ok:
            self.runtime.state.light_freeze_color_value = profile.color_enabled_value
            self.runtime.state.light_freeze_intensity_value = profile.default_intensity_value
            self.runtime.state.light_last_mode = "default"
        return ok, message

    def apply_boosted(self) -> tuple[bool, str]:
        profile = self._profile()
        ok, message = self._apply(
            color_value=profile.color_enabled_value,
            intensity_value=profile.boosted_intensity_value,
        )
        if ok:
            self.runtime.state.light_freeze_color_value = profile.color_enabled_value
            self.runtime.state.light_freeze_intensity_value = profile.boosted_intensity_value
            self.runtime.state.light_last_mode = "boosted"
        return ok, message

    def reset_original(self) -> tuple[bool, str]:
        state = self.runtime.state
        if not state.light_last_color_address_hex or not state.light_last_intensity_address_hex:
            return False, "No previous light target has been captured yet."
        if state.light_original_color_value is None or state.light_original_intensity_value is None:
            return False, "Original light values are not available yet."

        ok, message = self._write_direct_pair(
            color_address=int(state.light_last_color_address_hex, 16),
            color_value=state.light_original_color_value,
            intensity_value=state.light_original_intensity_value,
            remember_original=False,
        )
        if ok:
            state.light_freeze_color_value = state.light_original_color_value
            state.light_freeze_intensity_value = state.light_original_intensity_value
            state.light_last_mode = "reset"
        return ok, message

    def set_freeze_enabled(self, enabled: bool) -> tuple[bool, str]:
        self.runtime.state.light_freeze_enabled = bool(enabled)
        if enabled:
            return self.start_freeze()
        self.stop_freeze()
        return True, "Light freeze disabled."

    def start_freeze(self) -> tuple[bool, str]:
        if self._freeze_thread is not None and self._freeze_thread.is_alive():
            return True, "Light freeze already running."
        if self.controller is None:
            return False, "Attach to the game process first."
        ok, message = self._apply(
            color_value=self.runtime.state.light_freeze_color_value,
            intensity_value=self.runtime.state.light_freeze_intensity_value,
        )
        if not ok:
            self.runtime.state.light_freeze_enabled = False
            return False, f"Light freeze could not start: {message}"
        self._freeze_stop.clear()
        self._freeze_thread = threading.Thread(target=self._freeze_worker, daemon=True)
        self._freeze_thread.start()
        return True, (
            "Light freeze enabled: "
            f"color={self.runtime.state.light_freeze_color_value} "
            f"intensity={self.runtime.state.light_freeze_intensity_value} "
            f"every {max(30, self.runtime.state.light_freeze_interval_ms)}ms"
        )

    def stop_freeze(self) -> None:
        self._freeze_stop.set()

    def _freeze_worker(self) -> None:
        while not self._freeze_stop.is_set():
            if not self.runtime.state.light_freeze_enabled:
                break
            if self.controller is None:
                break
            self._apply(
                color_value=self.runtime.state.light_freeze_color_value,
                intensity_value=self.runtime.state.light_freeze_intensity_value,
                remember_original=False,
            )
            delay = max(30, self.runtime.state.light_freeze_interval_ms) / 1000.0
            if self._freeze_stop.wait(delay):
                break

    def _apply(self, color_value: int, intensity_value: int, remember_original: bool = True) -> tuple[bool, str]:
        try:
            state = self.runtime.state
            direct_address_hex = state.light_direct_address_hex.strip()
            if direct_address_hex:
                return self._write_direct_pair(
                    color_address=int(direct_address_hex, 16),
                    color_value=color_value,
                    intensity_value=intensity_value,
                    remember_original=remember_original,
                )

            ctrl = self._require_controller()
            profile = self._profile()
            color_address, intensity_address = ctrl.resolve_light_pair_addresses(
                module_name=profile.module_name,
                pointer_chains=[list(chain) for chain in profile.pointer_chains],
                structure_value_offset=profile.structure_value_offset,
                signature_pattern=profile.signature_pattern,
                signature_offset_to_base=profile.signature_offset_to_base,
            )
            return self._write_direct_pair(
                color_address=color_address,
                color_value=color_value,
                intensity_value=intensity_value,
                remember_original=remember_original,
                intensity_address=intensity_address,
            )
        except Exception as exc:
            return False, str(exc)

    def _write_direct_pair(
        self,
        color_address: int,
        color_value: int,
        intensity_value: int,
        remember_original: bool,
        intensity_address: int | None = None,
    ) -> tuple[bool, str]:
        ctrl = self._require_controller()
        intensity_address = color_address + 1 if intensity_address is None else intensity_address
        result = ctrl.write_light_pair(color_address, color_value, intensity_value)
        state = self.runtime.state
        state.light_last_color_address_hex = f"{color_address:X}"
        state.light_last_intensity_address_hex = f"{intensity_address:X}"
        if remember_original:
            state.light_original_color_value = result.color.old_value
            state.light_original_intensity_value = result.intensity.old_value
        mode_label = "direct" if state.light_direct_address_hex.strip() else "pointer"
        return True, (
            f"Light applied ({mode_label}) | color 0x{result.color.address:X}: "
            f"{result.color.old_value} -> {result.color.new_value} | "
            f"intensity 0x{result.intensity.address:X}: "
            f"{result.intensity.old_value} -> {result.intensity.new_value}"
        )

    @staticmethod
    def _find_game_process_name() -> str | None:
        pattern = re.compile(r"^(miracle_(?:dx|gl))(?:-\d+)?\.exe$", re.IGNORECASE)
        for proc in psutil.process_iter(attrs=["name"]):
            name = (proc.info.get("name") or "").strip()
            if pattern.fullmatch(name):
                return name
        return None

    def _require_controller(self):
        if self.controller is None:
            raise ProcessNotFoundError("Attach to the game process first.")
        return self.controller


class HpService:
    """HP value reader with pointer-first resolution and OCR fallback.

    On attach, resolves all known pointer chains (HP, light) against the
    target process using a Double-precision read.  If a pointer resolves
    successfully its address is cached and used as the primary HP source.
    When the pointer fails to resolve the service falls back to OCR-derived
    HP from the character status window.

    Public API::

        hp_service.attach()          -> (bool, str)   # hook into process + resolve pointers
        hp_service.get_hp()          -> float | None  # current HP value (pointer or OCR)
        hp_service.get_hp_peak()     -> int           # peak HP from OCR (0 if unavailable)
        hp_service.detach()          -> (bool, str)   # release process handle
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller = None  # LightMemoryController instance
        self._hp_address: int | None = None  # resolved HP pointer address
        self._light_address: int | None = None  # resolved light pointer address (for logging)
        self._hp_cache_time: float = 0.0  # timestamp of last successful resolution
        self._HP_CACHE_TTL: float = 60.0  # seconds — re-resolve after this interval

    def _is_address_valid(self, cached_addr: int | None, cache_time: float) -> bool:
        """Check if a cached pointer address is still within its TTL window."""
        if cached_addr is None or self.controller is None:
            return False
        if time.time() - cache_time < self._HP_CACHE_TTL:
            return True
        # Cache expired — force re-resolution on next get_hp() call
        self.runtime.ui.log(f"[HP] Pointer cache expired ({self._HP_CACHE_TTL}s), will re-resolve")
        return False

    def _ensure_address_resolved(self) -> bool:
        """Re-resolve HP pointer chain if address is stale or missing. Returns True on success."""
        state = self.runtime.state
        if self.controller is None:
            return False
        new_addr = self._resolve_hp_pointer()
        if new_addr is not None:
            self._hp_address = new_addr
            self._hp_cache_time = time.time()
            state.hp_pointer_address_hex = f"{new_addr:X}"
            state.hp_source = "pointer"
            self.runtime.ui.log(f"[HP] Re-resolved pointer -> 0x{new_addr:X}")
            return True
        return False

    def is_available(self) -> bool:
        return HAS_LIGHT_MODULE

    def attach(self) -> tuple[bool, str]:
        """Hook into the target process and resolve all known pointers.

        Returns ``(success, message)`` describing what was found.
        """
        if not HAS_LIGHT_MODULE:
            return False, "Install psutil and pymem to use HP pointer"

        process_name = self.runtime.state.light_process_name.strip() or "miracle_gl.exe"
        try:
            self.controller = LightMemoryController(process_name)
            self.controller.attach()
        except ProcessNotFoundError as exc:
            fallback_name = self._find_game_process_name()
            if not fallback_name:
                return False, str(exc)
            try:
                self.controller = LightMemoryController(fallback_name)
                self.controller.attach()
                self.runtime.state.light_process_name = fallback_name
            except Exception as fallback_exc:
                return False, f"{exc} | fallback attach failed: {fallback_exc}"
        except Exception as exc:
            return False, f"Attach failed: {exc}"

        # Resolve HP pointer chain
        hp_address = self._resolve_hp_pointer()

        # Resolve light pointer (for logging / future use)
        light_address = None
        try:
            from studiomemuer_light_module.light_profile import DEFAULT_PROFILE as LIGHT_PROFILE
            light_address = self.controller.resolve_light_address(
                module_name=LIGHT_PROFILE.module_name,
                pointer_chains=LIGHT_PROFILE.pointer_chains,
                structure_value_offset=LIGHT_PROFILE.structure_value_offset,
                signature_pattern=LIGHT_PROFILE.signature_pattern,
                signature_offset_to_base=LIGHT_PROFILE.signature_offset_to_base,
            )
        except Exception:
            pass

        # Build status message
        parts = []
        if hp_address is not None:
            self._hp_address = hp_address
            self._hp_cache_time = time.time()  # start TTL clock on first resolution
            state = self.runtime.state
            state.hp_pointer_address_hex = f"{hp_address:X}"
            state.hp_source = "pointer"
            parts.append(f"HP pointer resolved at 0x{hp_address:X}")

            # Read current HP value from pointer (Double, same as MP/Cap)
            try:
                hp_val = self.controller.read_double(hp_address)
                with self.runtime.settings_lock:
                    state.hp_value = hp_val
                parts.append(f"HP={hp_val:.1f}")
            except Exception as exc:
                parts.append(f"HP read failed: {exc}")

        if light_address is not None:
            self._light_address = light_address
            parts.append(f"Light pointer resolved at 0x{light_address:X}")

        msg = " | ".join(parts) if parts else "No pointers resolved"
        return True, f"Attached to {process_name} | {msg}"

    def detach(self) -> tuple[bool, str]:
        self.controller.detach()
        self.controller = None
        self._hp_address = None
        self._light_address = None
        return True, "Detached"

    def get_hp(self) -> float | None:
        """Return current HP value.  Uses pointer if available, otherwise OCR."""
        state = self.runtime.state
        # Try pointer first (primary source) — Double precision like MP/Cap
        if not self._is_address_valid(self._hp_address, self._hp_cache_time):
            # Cache expired or never resolved — re-resolve once
            self._ensure_address_resolved()

        if self._hp_address is not None and self.controller is not None:
            try:
                hp_val = self.controller.read_double(self._hp_address)
                with self.runtime.settings_lock:
                    state.hp_value = hp_val
                self.runtime.ui.log(f"[HP] Live read -> 0x{self._hp_address:X} = {hp_val:.1f}")
                return hp_val
            except Exception as exc:
                self.runtime.ui.log(f"[HP] Pointer read failed at 0x{self._hp_address:X}: {exc}")

        # Fallback to OCR-derived HP from character status service
        with self.runtime.settings_lock:
            ocr_hp = state.char_status_hp
        if ocr_hp is not None and ocr_hp > 0:
            self.runtime.ui.log(f"[HP] OCR fallback -> {ocr_hp}")
            return float(ocr_hp)
        self.runtime.ui.log("[HP] No value available (pointer failed + no OCR)")
        return None

    def get_hp_peak(self) -> int:
        """Return peak HP value (from OCR)."""
        with self.runtime.settings_lock:
            return self.runtime.state.char_status_hp_peak

    def _read_all_stats(self) -> tuple[float | None, float | None, float | None]:
        """Batch read HP, MP, Cap from memory in a single controller call.

        Since all three stats share the same base address (0x00A783E0), batching
        reduces redundant module lookups and pointer chain resolution overhead.
        Returns ``(hp_val, mp_val, cap_val)`` — any value can be None if its
        specific address wasn't resolved yet.
        """
        state = self.runtime.state

        # Try batch read from HP service's controller (primary source)
        hp_val = None
        mp_val = None
        cap_val = None

        if self._hp_address is not None and self.controller is not None:
            try:
                hp_val = self.controller.read_double(self._hp_address)
            except Exception as exc:
                self.runtime.ui.log(f"[HP] Batch read failed at 0x{self._hp_address:X}: {exc}")

        # Read MP if address resolved (from MpService)
        mp_addr = getattr(state, "_mp_resolved_addr", None)
        if mp_addr is not None and self.controller is not None:
            try:
                mp_val = self.controller.read_double(mp_addr)
            except Exception as exc:
                self.runtime.ui.log(f"[MP] Batch read failed at 0x{mp_addr:X}: {exc}")

        # Read Cap if address resolved (from CapService)
        cap_addr = getattr(state, "_cap_resolved_addr", None)
        if cap_addr is not None and self.controller is not None:
            try:
                cap_val = self.controller.read_double(cap_addr)
            except Exception as exc:
                self.runtime.ui.log(f"[Cap] Batch read failed at 0x{cap_addr:X}: {exc}")

        # Update state with batch results under lock once
        with self.runtime.settings_lock:
            if hp_val is not None:
                state.hp_value = hp_val
            if mp_val is not None:
                state.mp_value = mp_val
            if cap_val is not None:
                state.cap_value = cap_val

        # Log batch results
        parts = []
        if hp_val is not None:
            parts.append(f"HP={hp_val:.1f}")
        if mp_val is not None:
            parts.append(f"MP={mp_val:.1f}")
        if cap_val is not None:
            parts.append(f"Cap={cap_val:.1f}")
        if parts:
            self.runtime.ui.log(f"[Batch] {' | '.join(parts)}")

        return (hp_val, mp_val, cap_val)

    @staticmethod
    def _find_game_process_name() -> str | None:
        pattern = re.compile(r"^(miracle_(?:dx|gl))(?:-\d+)?\.exe$", re.IGNORECASE)
        for proc in psutil.process_iter(attrs=["name"]):
            name = (proc.info.get("name") or "").strip()
            if pattern.fullmatch(name):
                return name
        return None

    def _resolve_hp_pointer(self) -> int | None:
        """Resolve the HP pointer chain and verify readability.

        Returns the resolved address or None on failure.
        """
        from studiomemuer_hp_module.hp_profile import DEFAULT_HP_PROFILE as HP_PROFILE

        ctrl = self.controller
        if ctrl is None:
            return None

        module_base = ctrl.get_module_base(HP_PROFILE.module_name)
        self.runtime.ui.log(f"[HP] Module base: 0x{module_base:X}")
        self.runtime.ui.log(f"[HP] Pointer chains: {HP_PROFILE.pointer_chains}, offset: +0x{HP_PROFILE.structure_value_offset:X}")

        for chain_idx, chain in enumerate(HP_PROFILE.pointer_chains):
            self.runtime.ui.log(f"[HP] Trying chain #{chain_idx}: {chain}")
            try:
                base_candidate = ctrl.resolve_pointer_chain(module_base, chain)
                target_candidate = base_candidate + HP_PROFILE.structure_value_offset
                self.runtime.ui.log(f"[HP] Chain resolved -> base=0x{base_candidate:X}, target=0x{target_candidate:X}")
                # Verify we can read the double at this address (same type as MP/Cap)
                hp_verify = ctrl.read_double(target_candidate)
                self.runtime.ui.log(f"[HP] Verification read: {hp_verify} (type={type(hp_verify).__name__})")
                return target_candidate
            except Exception as exc:
                self.runtime.ui.log(f"[HP] Chain #{chain_idx} failed: {exc}")
                continue

        return None


class MpService:
    """MP (Mana) value reader with pointer-first resolution and OCR fallback.

    On attach, resolves the MP pointer chain against the target process using
    a Double-precision read.  If the pointer resolves successfully its address
    is cached and used as the primary MP source.  When the pointer fails to
    resolve the service falls back to OCR-derived MP from the character status
    window.

    Public API::

        mp_service.attach()          -> (bool, str)   # hook into process + resolve pointers
        mp_service.get_mp()          -> float | None  # current MP value (pointer or OCR)
        mp_service.detach()          -> (bool, str)   # release process handle
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller: LightMemoryController | None = None
        self._mp_address: int | None = None  # resolved MP pointer address
        self._mp_cache_time: float = 0.0  # timestamp of last successful resolution
        self._MP_CACHE_TTL: float = 60.0  # seconds — re-resolve after this interval

    def _is_mp_address_valid(self, cached_addr: int | None, cache_time: float) -> bool:
        """Check if a cached MP pointer address is still within its TTL window."""
        if cached_addr is None or self.controller is None:
            return False
        if time.time() - cache_time < self._MP_CACHE_TTL:
            return True
        self.runtime.ui.log(f"[MP] Pointer cache expired ({self._MP_CACHE_TTL}s), will re-resolve")
        return False

    def _ensure_mp_address_resolved(self) -> bool:
        """Re-resolve MP pointer chain if address is stale or missing. Returns True on success."""
        state = self.runtime.state
        if self.controller is None:
            return False
        new_addr = self._resolve_mp_pointer()
        if new_addr is not None:
            self._mp_address = new_addr
            self._mp_cache_time = time.time()
            state.mp_pointer_address_hex = f"{new_addr:X}"
            state.mp_source = "pointer"
            state._mp_resolved_addr = new_addr  # also update batch-read address
            self.runtime.ui.log(f"[MP] Re-resolved pointer -> 0x{new_addr:X}")
            return True
        return False

    def attach(self) -> tuple[bool, str]:
        """Hook into the target process and resolve the MP pointer.

        Returns ``(success, message)`` describing what was found.
        """
        process_name = self.runtime.state.light_process_name.strip() or "miracle_gl.exe"
        try:
            self.controller = LightMemoryController(process_name)
            self.controller.attach()
        except ProcessNotFoundError as exc:
            fallback_name = HpService._find_game_process_name()
            if not fallback_name:
                return False, str(exc)
            try:
                self.controller = LightMemoryController(fallback_name)
                self.controller.attach()
                self.runtime.state.light_process_name = fallback_name
            except Exception as fallback_exc:
                return False, f"{exc} | fallback attach failed: {fallback_exc}"
        except Exception as exc:
            return False, f"Attach failed: {exc}"

        # Resolve MP pointer chain (same base as HP, different offset)
        mp_address = self._resolve_mp_pointer()

        parts = []
        if mp_address is not None:
            self._mp_address = mp_address
            self._mp_cache_time = time.time()  # start TTL clock on first resolution
            state = self.runtime.state
            state.mp_pointer_address_hex = f"{mp_address:X}"
            state.mp_source = "pointer"
            # Store resolved address for batch reads
            state._mp_resolved_addr = mp_address
            parts.append(f"MP pointer resolved at 0x{mp_address:X}")

            # Read current MP value from pointer (Double)
            try:
                mp_val = self.controller.read_double(mp_address)
                with self.runtime.settings_lock:
                    state.mp_value = mp_val
                parts.append(f"MP={mp_val:.1f}")
            except Exception as exc:
                parts.append(f"MP read failed: {exc}")

        msg = " | ".join(parts) if parts else "No pointers resolved"
        return True, f"Attached to {process_name} | {msg}"

    def detach(self) -> tuple[bool, str]:
        self.controller.detach()
        self.controller = None
        self._mp_address = None
        return True, "Detached"

    def get_mp(self) -> float | None:
        """Return current MP value.  Uses pointer if available, otherwise OCR."""
        state = self.runtime.state
        # Try pointer first (primary source)
        if not self._is_mp_address_valid(self._mp_address, self._mp_cache_time):
            # Cache expired or never resolved — re-resolve once
            self._ensure_mp_address_resolved()

        if self._mp_address is not None and self.controller is not None:
            try:
                mp_val = self.controller.read_double(self._mp_address)
                with self.runtime.settings_lock:
                    state.mp_value = mp_val
                self.runtime.ui.log(f"[MP] Live read -> 0x{self._mp_address:X} = {mp_val:.1f}")
                return mp_val
            except Exception as exc:
                self.runtime.ui.log(f"[MP] Pointer read failed at 0x{self._mp_address:X}: {exc}")

        # Fallback to OCR-derived MP from character status service
        with self.runtime.settings_lock:
            ocr_mana = state.char_status_mana
        if ocr_mana is not None and ocr_mana > 0:
            self.runtime.ui.log(f"[MP] OCR fallback -> {ocr_mana}")
            return float(ocr_mana)
        self.runtime.ui.log("[MP] No value available (pointer failed + no OCR)")
        return None

    def _resolve_mp_pointer(self) -> int | None:
        """Resolve the MP pointer chain and verify readability.

        Returns the resolved address or None on failure.
        """
        from studiomemuer_mp_module.mp_profile import DEFAULT_MP_PROFILE as MP_PROFILE

        ctrl = self.controller
        if ctrl is None:
            return None

        module_base = ctrl.get_module_base(MP_PROFILE.module_name)
        self.runtime.ui.log(f"[MP] Module base: 0x{module_base:X}")
        self.runtime.ui.log(f"[MP] Pointer chains: {MP_PROFILE.pointer_chains}, offset: +0x{MP_PROFILE.structure_value_offset:X}")

        for chain_idx, chain in enumerate(MP_PROFILE.pointer_chains):
            self.runtime.ui.log(f"[MP] Trying chain #{chain_idx}: {chain}")
            try:
                base_candidate = ctrl.resolve_pointer_chain(module_base, chain)
                target_candidate = base_candidate + MP_PROFILE.structure_value_offset
                self.runtime.ui.log(f"[MP] Chain resolved -> base=0x{base_candidate:X}, target=0x{target_candidate:X}")
                # Verify we can read the double at this address
                mp_verify = ctrl.read_double(target_candidate)
                self.runtime.ui.log(f"[MP] Verification read: {mp_verify} (type={type(mp_verify).__name__})")
                return target_candidate
            except Exception as exc:
                self.runtime.ui.log(f"[MP] Chain #{chain_idx} failed: {exc}")
                continue

        return None


class CapService:
    """Cap (Max HP) value reader with pointer-first resolution and OCR fallback.

    On attach, resolves the Cap pointer chain against the target process using
    a Double-precision read.  If the pointer resolves successfully its address
    is cached and used as the primary Cap source.  When the pointer fails to
    resolve the service falls back to OCR-derived Cap from the character status
    window.

    Public API::

        cap_service.attach()          -> (bool, str)   # hook into process + resolve pointers
        cap_service.get_cap()         -> float | None  # current Cap value (pointer or OCR)
        cap_service.detach()          -> (bool, str)   # release process handle
    """

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller: LightMemoryController | None = None
        self._cap_address: int | None = None  # resolved Cap pointer address
        self._cap_cache_time: float = 0.0  # timestamp of last successful resolution
        self._CAP_CACHE_TTL: float = 60.0  # seconds — re-resolve after this interval

    def _is_cap_address_valid(self, cached_addr: int | None, cache_time: float) -> bool:
        """Check if a cached Cap pointer address is still within its TTL window."""
        if cached_addr is None or self.controller is None:
            return False
        if time.time() - cache_time < self._CAP_CACHE_TTL:
            return True
        self.runtime.ui.log(f"[Cap] Pointer cache expired ({self._CAP_CACHE_TTL}s), will re-resolve")
        return False

    def _ensure_cap_address_resolved(self) -> bool:
        """Re-resolve Cap pointer chain if address is stale or missing. Returns True on success."""
        state = self.runtime.state
        if self.controller is None:
            return False
        new_addr = self._resolve_cap_pointer()
        if new_addr is not None:
            self._cap_address = new_addr
            self._cap_cache_time = time.time()
            state.cap_pointer_address_hex = f"{new_addr:X}"
            state.cap_source = "pointer"
            state._cap_resolved_addr = new_addr  # also update batch-read address
            self.runtime.ui.log(f"[Cap] Re-resolved pointer -> 0x{new_addr:X}")
            return True
        return False

    def attach(self) -> tuple[bool, str]:
        """Hook into the target process and resolve the Cap pointer.

        Returns ``(success, message)`` describing what was found.
        """
        process_name = self.runtime.state.light_process_name.strip() or "miracle_gl.exe"
        try:
            self.controller = LightMemoryController(process_name)
            self.controller.attach()
        except ProcessNotFoundError as exc:
            fallback_name = HpService._find_game_process_name()
            if not fallback_name:
                return False, str(exc)
            try:
                self.controller = LightMemoryController(fallback_name)
                self.controller.attach()
                self.runtime.state.light_process_name = fallback_name
            except Exception as fallback_exc:
                return False, f"{exc} | fallback attach failed: {fallback_exc}"
        except Exception as exc:
            return False, f"Attach failed: {exc}"

        # Resolve Cap pointer chain (same base as HP, different offset)
        cap_address = self._resolve_cap_pointer()

        parts = []
        if cap_address is not None:
            self._cap_address = cap_address
            self._cap_cache_time = time.time()  # start TTL clock on first resolution
            state = self.runtime.state
            state.cap_pointer_address_hex = f"{cap_address:X}"
            state.cap_source = "pointer"
            # Store resolved address for batch reads
            state._cap_resolved_addr = cap_address
            parts.append(f"Cap pointer resolved at 0x{cap_address:X}")

            # Read current Cap value from pointer (Double)
            try:
                cap_val = self.controller.read_double(cap_address)
                with self.runtime.settings_lock:
                    state.cap_value = cap_val
                parts.append(f"Cap={cap_val:.1f}")
            except Exception as exc:
                parts.append(f"Cap read failed: {exc}")

        msg = " | ".join(parts) if parts else "No pointers resolved"
        return True, f"Attached to {process_name} | {msg}"

    def detach(self) -> tuple[bool, str]:
        self.controller.detach()
        self.controller = None
        self._cap_address = None
        return True, "Detached"

    def get_cap(self) -> float | None:
        """Return current Cap value.  Uses pointer if available, otherwise OCR."""
        state = self.runtime.state
        # Try pointer first (primary source)
        if not self._is_cap_address_valid(self._cap_address, self._cap_cache_time):
            # Cache expired or never resolved — re-resolve once
            self._ensure_cap_address_resolved()

        if self._cap_address is not None and self.controller is not None:
            try:
                cap_val = self.controller.read_double(self._cap_address)
                with self.runtime.settings_lock:
                    state.cap_value = cap_val
                self.runtime.ui.log(f"[Cap] Live read -> 0x{self._cap_address:X} = {cap_val:.1f}")
                return cap_val
            except Exception as exc:
                self.runtime.ui.log(f"[Cap] Pointer read failed at 0x{self._cap_address:X}: {exc}")

        # Fallback to OCR-derived Cap from character status service
        with self.runtime.settings_lock:
            ocr_cap = state.char_status_cap
        if ocr_cap is not None and ocr_cap > 0:
            self.runtime.ui.log(f"[Cap] OCR fallback -> {ocr_cap}")
            return float(ocr_cap)
        self.runtime.ui.log("[Cap] No value available (pointer failed + no OCR)")
        return None

    def _resolve_cap_pointer(self) -> int | None:
        """Resolve the Cap pointer chain and verify readability.

        Returns the resolved address or None on failure.
        """
        from studiomemuer_cap_module.cap_profile import DEFAULT_CAP_PROFILE as CAP_PROFILE

        ctrl = self.controller
        if ctrl is None:
            return None

        module_base = ctrl.get_module_base(CAP_PROFILE.module_name)
        self.runtime.ui.log(f"[Cap] Module base: 0x{module_base:X}")
        self.runtime.ui.log(f"[Cap] Pointer chains: {CAP_PROFILE.pointer_chains}, offset: +0x{CAP_PROFILE.structure_value_offset:X}")

        for chain_idx, chain in enumerate(CAP_PROFILE.pointer_chains):
            self.runtime.ui.log(f"[Cap] Trying chain #{chain_idx}: {chain}")
            try:
                base_candidate = ctrl.resolve_pointer_chain(module_base, chain)
                target_candidate = base_candidate + CAP_PROFILE.structure_value_offset
                self.runtime.ui.log(f"[Cap] Chain resolved -> base=0x{base_candidate:X}, target=0x{target_candidate:X}")
                # Verify we can read the double at this address
                cap_verify = ctrl.read_double(target_candidate)
                self.runtime.ui.log(f"[Cap] Verification read: {cap_verify} (type={type(cap_verify).__name__})")
                return target_candidate
            except Exception as exc:
                self.runtime.ui.log(f"[Cap] Chain #{chain_idx} failed: {exc}")
                continue

        return None


class PositionCaptureService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def capture(self, on_done: Callable[[tuple[int, int]], None], label: str) -> None:
        threading.Thread(target=self._worker, args=(on_done, label), daemon=True).start()

    def _worker(self, on_done: Callable[[tuple[int, int]], None], label: str) -> None:
        state = self.runtime.state
        self.runtime.ui.log(f"🎯 Move mouse to {label} → press record_pos hotkey (30 s)…")
        self.runtime.ui.set_status(
            f"Move to {label} → press {state.hotkey_bindings.get('record_pos', 'f12').upper()}",
            ORANGE,
        )
        captured = threading.Event()
        holder = [None]
        record_key = HotkeyService.key_str_to_pynput(state.hotkey_bindings.get("record_pos", "f12"))

        def on_press(key):
            if key == record_key:
                holder[0] = pynput_mouse.Controller().position
                captured.set()
                return False
            return None

        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            return

        listener = pynput_kb.Listener(on_press=on_press)
        listener.start()
        captured.wait(timeout=30)
        listener.stop()
        if holder[0]:
            on_done(holder[0])
        else:
            self.runtime.ui.log("⚠️  Capture timed out")
            self.runtime.ui.set_status("Capture timed out", ORANGE)


class AntiAfkService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.afk_active:
            return
        state.afk_active = True
        self.runtime.afk_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Activity monitor active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.afk_active:
            return
        self.runtime.afk_stop.set()
        state.afk_active = False
        self.runtime.ui.set_status("Activity monitor stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(f"▶ Activity monitor start — {state.afk_min_ms}–{state.afk_max_ms} ms")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.afk_active = False
            return
        keyboard = pynput_kb.Controller()
        directions = {
            "up": pynput_kb.Key.up,
            "down": pynput_kb.Key.down,
            "left": pynput_kb.Key.left,
            "right": pynput_kb.Key.right,
        }
        while not self.runtime.afk_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.afk_stop.is_set():
                break
            with self.runtime.settings_lock:
                min_ms = state.afk_min_ms
                max_ms = state.afk_max_ms
            if not self.runtime.pause.wait_interruptible(random.randint(min_ms, max_ms) / 1000.0, self.runtime.afk_stop):
                break
            direction_name, direction_key = random.choice(list(directions.items()))
            if not self.runtime.execution.acquire(self.runtime.afk_stop, max_wait=0.50, module_id="afk"):
                if self.runtime.afk_stop.is_set():
                    break
                continue
            session = SafeKeyboardSession(keyboard)
            try:
                session.press(pynput_kb.Key.ctrl)
                time.sleep(random.uniform(0.04, 0.08))
                session.press(direction_key)
                time.sleep(random.uniform(0.03, 0.06))
                session.release(direction_key)
                time.sleep(random.uniform(0.02, 0.04))
            except Exception as exc:
                self.runtime.ui.log(f"❌ AFK: {exc}")
            finally:
                session.release_all()
                self.runtime.execution.release()
            with self.runtime.record_lock:
                state.stats["afk_moves"] += 1
            self.runtime.ui.log(f"🚶 AFK Ctrl+{direction_name}")
            self.runtime.ui.refresh_stats()
        state.afk_active = False
        self.runtime.ui.log("⏹ Activity monitor end")


class RightClickService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.rclick_active:
            return
        if state.rclick_pos == (0, 0):
            self.runtime.ui.log("⚠️  Record a position first")
            self.runtime.ui.set_status("Record position first", ORANGE)
            return
        state.rclick_active = True
        self.runtime.rclick_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Right-click macro active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.rclick_active:
            return
        self.runtime.rclick_stop.set()
        state.rclick_active = False
        self.runtime.ui.set_status("Right-click macro stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Right-click macro start")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.rclick_active = False
            return
        mouse = pynput_mouse.Controller()
        while not self.runtime.rclick_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.rclick_stop.is_set():
                break
            with self.runtime.settings_lock:
                min_ms = state.rclick_min_ms
                max_ms = state.rclick_max_ms
                target = state.rclick_pos
                mode = state.rclick_mode
                food_seconds = state.char_status_food_seconds
                food_min_secs = state.rclick_food_min_secs
                burst_count_min = state.rclick_food_burst_count_min
                burst_count_max = state.rclick_food_burst_count_max
                burst_interval_ms = state.rclick_food_burst_interval_ms
                click_delay_min_ms = state.rclick_click_delay_min_ms
                click_delay_max_ms = state.rclick_click_delay_max_ms
                post_settle_ms = state.rclick_post_click_settle_ms
            if mode == "food":
                if food_seconds is not None and food_seconds >= food_min_secs:
                    if not self.runtime.pause.wait_interruptible(1.0, self.runtime.rclick_stop):
                        break
                    continue
                clicks_to_send = random.randint(burst_count_min, burst_count_max)
                queue_window = max(
                    0.35,
                    clicks_to_send * (click_delay_max_ms / 1000.0) + max(0, clicks_to_send - 1) * max(click_delay_min_ms / 1000.0, burst_interval_ms / 1000.0),
                )
            else:
                if not self.runtime.pause.wait_interruptible(random.randint(min_ms, max_ms) / 1000.0, self.runtime.rclick_stop):
                    break
                if state.rclick_require_food and food_seconds is not None and food_seconds >= food_min_secs:
                    continue
                clicks_to_send = 1
                queue_window = 0.80
            if not self.runtime.mouse.acquire(self.runtime.rclick_stop, max_wait=queue_window, module_id="right_click"):
                if self.runtime.rclick_stop.is_set():
                    break
                continue
            try:
                HumanMouse.move(mouse, target)
                for click_index in range(clicks_to_send):
                    # Add slight random variation between clicks for natural rhythm
                    inter_click = max(0.02, burst_interval_ms / 1000.0 + random.uniform(-0.05, 0.08))
                    time.sleep(inter_click)
                    mouse.click(pynput_mouse.Button.right, 1)
                # Settle after all clicks — lets the game register and adds human-like pause
                time.sleep(post_settle_ms / 1000.0)
            except Exception as exc:
                self.runtime.ui.log(f"❌ R-click: {exc}")
            finally:
                self.runtime.mouse.release()
            with self.runtime.record_lock:
                state.stats["right_clicks"] += clicks_to_send
            if mode == "food":
                self.runtime.ui.log(f"🖱️  Food burst at {target} ×{clicks_to_send}")
                if not self.runtime.pause.wait_interruptible(1.5, self.runtime.rclick_stop):
                    break
            else:
                self.runtime.ui.log(f"🖱️  Right-click at {target}")
            self.runtime.ui.refresh_stats()
        self.runtime.ui.log("⏹ Right-click end")


class AlarmService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.alarm_active:
            return
        if not HAS_MSS:
            self.runtime.ui.log("❌ Install mss and numpy")
            return
        state.alarm_active = True
        self.runtime.alarm_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Screen watch active…", TEAL)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.alarm_active:
            return
        self.runtime.alarm_stop.set()
        state.alarm_active = False
        self.runtime.ui.set_status("Screen watch stopped", RED)

    def play_alarm(self) -> None:
        path = self.runtime.state.alarm_mp3
        if not path or not os.path.exists(path):
            self.runtime.ui.log("⚠️  Alert sound file not found")
            return

        def play() -> None:
            try:
                if HAS_PYGAME:
                    pygame.mixer.music.load(path)
                    pygame.mixer.music.play()
                else:
                    os.startfile(path)
            except Exception as exc:
                self.runtime.ui.log(f"❌ Audio: {exc}")

        threading.Thread(target=play, daemon=True).start()

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Screen watch start")
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screen_w = monitor["width"]
            screen_h = monitor["height"]

            def get_region() -> dict:
                with self.runtime.settings_lock:
                    region = state.alarm_region
                if region:
                    return {"top": region[1], "left": region[0], "width": region[2], "height": region[3], "mon": 1}
                size = 200
                return {"top": screen_h // 2 - size // 2, "left": screen_w // 2 - size // 2, "width": size, "height": size, "mon": 1}

            last_frame = None
            cooldown_until = 0.0
            while not self.runtime.alarm_stop.is_set():
                time.sleep(0.1)
                now = time.monotonic()
                with self.runtime.settings_lock:
                    hp_percent = state.alarm_hp_percent
                    hp_peak = state.char_status_hp_peak
                    auto_pause = state.alarm_auto_pause
                    threshold = state.alarm_threshold
                # Try pointer-based HP first, fall back to OCR
                hp_value = None
                if self.runtime.hp_service is not None:
                    try:
                        hp_value = self.runtime.hp_service.get_hp()
                    except Exception:
                        pass
                if hp_value is None:
                    with self.runtime.settings_lock:
                        hp_value = state.char_status_hp
                if hp_percent > 0 and hp_value is not None and hp_peak > 0 and now >= cooldown_until:
                    hp_ratio = (hp_value / hp_peak) * 100.0
                    if hp_ratio <= hp_percent:
                        cooldown_until = now + state.alarm_cooldown
                        with self.runtime.record_lock:
                            state.stats["alarms"] += 1
                        self.runtime.ui.log(f"🚨 LOW HP — {hp_value}/{hp_peak} ({hp_ratio:.1f}%)")
                        self.runtime.ui.set_status(f"⚠️  LOW HP — {hp_ratio:.1f}% remaining", RED)
                        self.play_alarm()
                        self.runtime.ui.refresh_stats()
                        if auto_pause and not self.runtime.pause.paused:
                            self.runtime.ui.log("⏸  Auto-pausing all activities due to low HP")
                            self.runtime.ui.dispatch(self.runtime.pause.toggle)
                        continue
                try:
                    frame = np.array(sct.grab(get_region()))[:, :, :3]
                except Exception as exc:
                    self.runtime.ui.log(f"❌ Capture: {exc}")
                    continue
                if last_frame is not None and last_frame.shape == frame.shape:
                    if now >= cooldown_until:
                        diff = np.abs(frame.astype(np.int16) - last_frame.astype(np.int16))
                        changed = float(np.mean(diff.sum(axis=2) > 30))
                        if changed >= threshold:
                            cooldown_until = now + state.alarm_cooldown
                            with self.runtime.record_lock:
                                state.stats["alarms"] += 1
                            self.runtime.ui.log(f"🚨 ALARM — {changed * 100:.1f}% pixels changed!")
                            self.runtime.ui.set_status(f"⚠️  PIXEL ALARM — {changed * 100:.1f}% changed!", RED)
                            self.play_alarm()
                            self.runtime.ui.refresh_stats()
                            if auto_pause and not self.runtime.pause.paused:
                                self.runtime.ui.log("⏸  Auto-pausing all activities due to screen watch event")
                                self.runtime.ui.dispatch(self.runtime.pause.toggle)
                last_frame = frame
        self.runtime.ui.log("⏹ Screen watch end")


class CharacterStatusService:
    BASE_SIZE = (170, 203)
    ROI_MAP = {
        "hp": [(132, 1, 169, 19), (124, 0, 169, 21)],
        "mana": [(136, 21, 169, 39), (128, 20, 169, 41)],
        "cap": [(0, 180, 42, 203), (0, 164, 44, 203)],
    }

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._regen_history: dict[str, list[tuple[float, int]]] = {"hp": [], "mana": []}

    def get_dependency_error(self) -> str | None:
        state = self.runtime.state
        if not HAS_MSS:
            return "mss import failed" + (f": {MSS_IMPORT_ERROR}" if MSS_IMPORT_ERROR else "")
        if not HAS_NUMPY:
            return "numpy import failed" + (f": {NUMPY_IMPORT_ERROR}" if NUMPY_IMPORT_ERROR else "")
        if not HAS_CV2:
            return "opencv-python import failed" + (f": {CV2_IMPORT_ERROR}" if CV2_IMPORT_ERROR else "")
        if not HAS_TESSERACT:
            return "pytesseract import failed" + (f": {TESSERACT_IMPORT_ERROR}" if TESSERACT_IMPORT_ERROR else "")
        tesseract_cmd = resolve_tesseract_cmd(state.char_status_tesseract_path)
        if not tesseract_cmd:
            return "Tesseract executable not found"
        configure_tesseract_runtime(tesseract_cmd)
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        return None

    def start(self) -> None:
        state = self.runtime.state
        if state.char_status_active:
            return
        dependency_error = self.get_dependency_error()
        if dependency_error:
            state.char_status_last_error = dependency_error
            self.runtime.ui.log(f"❌ Character status OCR unavailable: {dependency_error}")
            self.runtime.ui.set_status(f"Character status OCR unavailable: {dependency_error}", RED)
            return
        has_window = bool(state.char_status_region)
        has_field_regions = all([state.char_status_hp_region, state.char_status_mana_region, state.char_status_cap_region])
        if not has_window and not has_field_regions:
            self.runtime.ui.log("⚠️  Select HP, Mana, and Cap areas or select the full character status window first")
            self.runtime.ui.set_status("Select stat areas or a full status window first", ORANGE)
            return
        state.char_status_active = True
        state.char_status_last_error = ""
        self.runtime.char_status_stop.clear()
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Character status watcher active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.char_status_active:
            return
        self.runtime.char_status_stop.set()
        state.char_status_active = False
        self.runtime.ui.set_status("Character status watcher stopped", RED)

    def restart_if_needed(self) -> None:
        self.stop()
        if self.runtime.state.char_status_region:
            self.start()

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Character status watcher start")
        try:
            with mss.mss() as sct:
                while not self.runtime.char_status_stop.is_set():
                    with self.runtime.settings_lock:
                        region = state.char_status_region
                        hp_region = state.char_status_hp_region
                        mana_region = state.char_status_mana_region
                        cap_region = state.char_status_cap_region
                        poll_ms = max(250, state.char_status_poll_ms)
                    if not region and not all([hp_region, mana_region, cap_region]):
                        break
                    try:
                        samples = []
                        for _ in range(state.char_status_samples):
                            parsed_sample: dict[str, int | None] = {}
                            if region:
                                monitor = {
                                    "left": region[0],
                                    "top": region[1],
                                    "width": region[2],
                                    "height": region[3],
                                    "mon": 1,
                                }
                                frame = np.array(sct.grab(monitor))[:, :, :3]
                                parsed_sample = self._extract_values(frame)
                            if all([hp_region, mana_region, cap_region]):
                                parsed_sample.update(
                                    self._extract_values_from_regions(
                                        sct,
                                        {
                                            "hp": hp_region,
                                            "mana": mana_region,
                                            "cap": cap_region,
                                        },
                                    )
                                )
                            samples.append(parsed_sample)
                            if _ < state.char_status_samples - 1:
                                time.sleep(state.char_status_sample_delay_ms / 1000.0)
                        parsed = self._aggregate_samples(samples)
                    except pytesseract.TesseractNotFoundError:
                        with self.runtime.settings_lock:
                            state.char_status_last_error = "Tesseract executable not found"
                        self.runtime.ui.log("❌ Tesseract executable not found for character status OCR")
                        self.runtime.ui.set_status("Configure a Tesseract path in Character Status", RED)
                        self.runtime.char_status_stop.set()
                        break
                    except Exception as exc:
                        with self.runtime.settings_lock:
                            state.char_status_failures += 1
                            state.char_status_last_error = str(exc)
                        time.sleep(0.5)
                        continue

                    if parsed:
                        with self.runtime.settings_lock:
                            for key, value in parsed.items():
                                if value is not None or key == "food_text":
                                    setattr(state, f"char_status_{key}", value)
                            if state.char_status_hp is not None:
                                state.char_status_hp_peak = max(state.char_status_hp_peak, state.char_status_hp)
                            self._update_regen(state)
                            state.char_status_reads += 1
                            state.char_status_last_seen = time.time()
                            state.char_status_last_error = ""
                    else:
                        with self.runtime.settings_lock:
                            state.char_status_failures += 1
                            state.char_status_last_error = "No digits recognized"
                    if self.runtime.char_status_stop.wait(poll_ms / 1000.0):
                        break
        finally:
            state.char_status_active = False
            self.runtime.ui.log("⏹ Character status watcher end")

    def _extract_values(self, frame) -> dict[str, int | None]:
        values: dict[str, int | None] = self._extract_values_from_text(frame)
        for key, boxes in self.ROI_MAP.items():
            if values.get(key) is not None:
                continue
            for box in boxes:
                crop = self._crop(frame, box)
                value = self._ocr_digits(crop, key)
                if value is not None:
                    values[key] = value
                    break
        return values if any(value is not None for value in values.values()) else {}

    def _extract_values_from_regions(self, sct, regions: dict[str, tuple[int, int, int, int]]) -> dict[str, int | None]:
        values: dict[str, int | None] = {}
        for key, region in regions.items():
            monitor = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3],
                "mon": 1,
            }
            frame = np.array(sct.grab(monitor))[:, :, :3]
            values[key] = self._ocr_digits(frame, key)
        return values if any(value is not None for value in values.values()) else {}

    def _update_regen(self, state) -> None:
        now = time.monotonic()
        self._push_regen_sample("hp", now, state.char_status_hp)
        self._push_regen_sample("mana", now, state.char_status_mana)
        state.char_status_hp_regen_per_min = self._compute_regen_rate("hp")
        state.char_status_mana_regen_per_min = self._compute_regen_rate("mana")

    def _push_regen_sample(self, key: str, now: float, value: int | None) -> None:
        if value is None:
            return
        history = self._regen_history[key]
        if not history or history[-1][1] != value:
            history.append((now, value))
        cutoff = now - 180.0
        while len(history) > 1 and history[0][0] < cutoff:
            history.pop(0)

    def _compute_regen_rate(self, key: str) -> float:
        history = self._regen_history[key]
        if len(history) < 2:
            return 0.0
        gained = 0
        for index in range(1, len(history)):
            delta = history[index][1] - history[index - 1][1]
            if delta > 0:
                gained += delta
        elapsed_minutes = max((history[-1][0] - history[0][0]) / 60.0, 1e-6)
        return gained / elapsed_minutes

    def _aggregate_samples(self, samples: list[dict[str, int | None | str]]) -> dict[str, int | None | str]:
        if not samples:
            return {}
        aggregated: dict[str, int | None | str] = {}
        keys = set()
        for sample in samples:
            keys.update(sample.keys())
        for key in keys:
            values = [sample.get(key) for sample in samples if key in sample and sample[key] is not None]
            if not values:
                continue
            if key in {"level", "hp", "mana", "cap", "food_seconds"}:
                # For numeric, take median
                numeric_values = [v for v in values if isinstance(v, int)]
                if numeric_values:
                    sorted_vals = sorted(numeric_values)
                    mid = len(sorted_vals) // 2
                    aggregated[key] = sorted_vals[mid]
            elif key == "food_text":
                # For text, most common
                from collections import Counter
                text_values = [v for v in values if isinstance(v, str)]
                if text_values:
                    aggregated[key] = Counter(text_values).most_common(1)[0][0]
        return aggregated

    def _extract_values_from_text(self, frame) -> dict[str, int | None | str]:
        values: dict[str, int | None] = {
            "level": None,
            "hp": None,
            "mana": None,
            "cap": None,
            "food_seconds": None,
            "food_text": "",
        }
        enlarged = cv2.resize(frame, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        variants = []
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(binary)
        variants.append(cv2.bitwise_not(binary))
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7)
        variants.append(adaptive)
        variants.append(cv2.bitwise_not(adaptive))
        field_patterns = {
            "level": [r"level\s+(\d+)", r"leve[li]\s+(\d+)"],
            "hp": [r"hit\s*points\s+(\d+)", r"hit\s*point[s]?\s+(\d+)"],
            "mana": [r"mana\s+(\d+)"],
            "cap": [r"capacity\s+(\d+)", r"capacit[yv]\s+(\d+)"],
            "food": [r"food\s+(\d{1,2}:\d{2})"],
        }
        for image_variant in variants:
            text = pytesseract.image_to_string(image_variant, config="--psm 6")
            normalized = re.sub(r"[^a-z0-9:\n ]+", " ", text.lower())
            for key, patterns in field_patterns.items():
                if key == "food" and values["food_seconds"] is not None:
                    continue
                if key != "food" and values[key] is not None:
                    continue
                for pattern in patterns:
                    match = re.search(pattern, normalized)
                    if not match:
                        continue
                    if key == "food":
                        food_text = match.group(1)
                        values["food_text"] = food_text
                        values["food_seconds"] = CharacterStatusService._parse_food_seconds(food_text)
                    else:
                        values[key] = int(match.group(1))
                    break
        return values

    @staticmethod
    def _parse_food_seconds(text: str) -> int | None:
        match = re.match(r"(\d{1,2}):(\d{2})", text.strip())
        if not match:
            return None
        # Format is HH:MM, converting to seconds
        return (int(match.group(1)) * 60 + int(match.group(2))) * 60

    def _crop(self, frame, box: tuple[int, int, int, int]):
        base_w, base_h = self.BASE_SIZE
        frame_h, frame_w = frame.shape[:2]
        x1 = max(0, int(round(box[0] / base_w * frame_w)))
        y1 = max(0, int(round(box[1] / base_h * frame_h)))
        x2 = min(frame_w, int(round(box[2] / base_w * frame_w)))
        y2 = min(frame_h, int(round(box[3] / base_h * frame_h)))
        return frame[y1:y2, x1:x2]

    @staticmethod
    def _ocr_digits(crop, key: str) -> int | None:
        if crop is None or crop.size == 0:
            return None
        scale = 7 if key == "cap" else 6
        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        variants = []
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(binary)
        variants.append(cv2.bitwise_not(binary))
        adaptive = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            7,
        )
        variants.append(adaptive)
        variants.append(cv2.bitwise_not(adaptive))
        kernel = np.ones((2, 2), np.uint8)
        variants.append(cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel))
        psm_modes = ["7", "8"] if key in {"hp", "mana"} else ["7", "6", "8"]
        best_digits = ""
        for image_variant in variants:
            for psm in psm_modes:
                config = f"--psm {psm} -c tessedit_char_whitelist=0123456789"
                text = pytesseract.image_to_string(image_variant, config=config)
                groups = [group for group in re.findall(r"\d+", text) if group]
                if groups:
                    candidate = max(groups, key=len) if key in {"hp", "mana"} else groups[-1]
                    if len(candidate) > len(best_digits):
                        best_digits = candidate
                    if key in {"hp", "mana"} and len(candidate) >= 2:
                        return int(candidate)
                    if key == "cap" and len(candidate) >= 1:
                        return int(candidate)
        if best_digits:
            return int(best_digits)
        return None


class FishingService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.fish_active:
            return
        if state.fish_rod_pos == (0, 0):
            self.runtime.ui.log("❌ Record rod position first")
            self.runtime.ui.set_status("Record rod position first", ORANGE)
            return
        if not state.fish_spots:
            self.runtime.ui.log("❌ Record at least one spot")
            self.runtime.ui.set_status("Record at least one fishing spot", ORANGE)
            return
        if state.fish_min_cap > 0:
            # Use pointer-based Cap first, fall back to OCR
            fish_cap = None
            if self.runtime.cap_service is not None:
                try:
                    fish_cap = self.runtime.cap_service.get_cap()
                except Exception:
                    pass
            if fish_cap is None:
                with self.runtime.settings_lock:
                    fish_cap = state.char_status_cap
            if fish_cap is not None and fish_cap <= state.fish_min_cap:
                self.runtime.ui.log("⚠️  Capacity is already at or below the fishing stop threshold")
                self.runtime.ui.set_status("Capacity too low to start fishing", ORANGE)
                return
        self.runtime.fish_stop.clear()
        
        # Calculate random bonus time scaled by user configuration (up to 15 minutes at 60min mark)
        max_bonus_mins = max(1.0, 15.0 * (state.fish_session_minutes / 60.0))
        bonus_secs = random.randint(60, max(60, int(max_bonus_mins * 60)))
        total_seconds = max(1, state.fish_session_minutes * 60) + bonus_secs
        
        state.fish_session_remaining_secs = total_seconds
        state.fish_session_deadline = time.monotonic() + total_seconds
        state.fish_active = True
        threading.Thread(target=self._worker, daemon=True).start()
        
        self.runtime.ui.set_status(
            f"Fishing session running ({state.fish_session_minutes} min + {bonus_secs//60} min random bonus)",
            GREEN,
        )
        self.runtime.ui.log(f"🎣 Session setup: {state.fish_session_minutes} min base + {bonus_secs//60}m {bonus_secs%60}s randomized padding")

    def stop(self) -> None:
        state = self.runtime.state
        if not state.fish_active:
            return
        self.runtime.fish_stop.set()
        state.fish_active = False
        state.fish_session_remaining_secs = 0
        state.fish_session_deadline = None
        self.runtime.ui.set_status("Fishing session stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(f"▶ Fishing start — rod={state.fish_rod_pos}  spots={len(state.fish_spots)}")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.fish_active = False
            state.fish_session_remaining_secs = 0
            state.fish_session_deadline = None
            return
        mouse = pynput_mouse.Controller()
        deck = list(state.fish_spots)
        random.shuffle(deck)
        index = 0
        session_deadline = state.fish_session_deadline or (time.monotonic() + max(1, state.fish_session_remaining_secs))

        def update_remaining() -> bool:
            remaining = max(0, int(math.ceil(session_deadline - time.monotonic())))
            state.fish_session_remaining_secs = remaining
            return remaining > 0

        def wait_with_session_limit(seconds: float) -> bool:
            while seconds > 0:
                if not update_remaining():
                    return False
                chunk = min(seconds, 0.25, max(0.0, session_deadline - time.monotonic()))
                if chunk <= 0:
                    return False
                if not self.runtime.pause.wait_interruptible(chunk, self.runtime.fish_stop):
                    return False
                seconds -= chunk
            return update_remaining()

        while not self.runtime.fish_stop.is_set():
            if not update_remaining():
                self.runtime.ui.log("⏲️ Fishing session complete")
                self.runtime.ui.set_status("Fishing session finished", ORANGE)
                self.runtime.fish_stop.set()
                break
            self.runtime.pause.wait()
            with self.runtime.settings_lock:
                rod = state.fish_rod_pos
                rod_jitter = state.fish_rod_jitter
                spot_jitter = state.fish_spot_jitter
                cast_min = state.fish_cast_min_ms
                cast_max = state.fish_cast_max_ms
                wait_min = state.fish_wait_min_ms
                wait_max = state.fish_wait_max_ms
                min_cap = state.fish_min_cap
                # Use pointer-based Cap first, fall back to OCR
                current_cap = None
                if self.runtime.cap_service is not None:
                    try:
                        current_cap = self.runtime.cap_service.get_cap()
                    except Exception:
                        pass
                if current_cap is None:
                    with self.runtime.settings_lock:
                        current_cap = state.char_status_cap
            if min_cap > 0 and current_cap is not None and current_cap <= min_cap:
                self.runtime.ui.log(f"📦 Fishing stopped — capacity {current_cap} is at/below limit {min_cap}")
                self.runtime.ui.set_status("Fishing stopped by capacity threshold", ORANGE)
                self.runtime.fish_stop.set()
                break
            cycle_locked = False
            try:
                cycle_window = max(0.90, max(cast_max, 0) / 1000.0 + 1.20)
                cycle_locked = self.runtime.mouse.acquire(
                    self.runtime.fish_stop,
                    max_wait=cycle_window,
                    module_id="fishing",
                )
                if not cycle_locked:
                    if self.runtime.fish_stop.is_set():
                        break
                    continue
                rod_target = HumanMouse.jitter(rod, rod_jitter)
                HumanMouse.move(mouse, rod_target)
                time.sleep(random.uniform(0.07, 0.17))
                mouse.click(pynput_mouse.Button.right, 1)
                self.runtime.ui.log(f"🎣 Rod clicked at {rod_target}")
                if not wait_with_session_limit(random.randint(cast_min, cast_max) / 1000.0):
                    break
                if index >= len(deck):
                    deck = list(state.fish_spots)
                    random.shuffle(deck)
                    index = 0
                spot_target = HumanMouse.jitter(deck[index], spot_jitter)
                index += 1
                HumanMouse.move(mouse, spot_target)
                time.sleep(random.uniform(0.10, 0.26))
                mouse.click(pynput_mouse.Button.left, 1)
                with self.runtime.record_lock:
                    state.stats["fish_casts"] += 1
                self.runtime.ui.log(f"🪣 Cast → {spot_target}")
                self.runtime.ui.refresh_stats()
            except Exception as exc:
                self.runtime.ui.log(f"❌ Fish cycle: {exc}")
                self.runtime.fish_stop.set()
                break
            finally:
                if cycle_locked:
                    self.runtime.mouse.release()
            if not update_remaining():
                self.runtime.ui.log("⏲️ Fishing session complete")
                self.runtime.ui.set_status("Fishing session finished", ORANGE)
                self.runtime.fish_stop.set()
                break
            if not wait_with_session_limit(random.randint(wait_min, wait_max) / 1000.0):
                break
        state.fish_active = False
        if self.runtime.fish_stop.is_set():
            state.fish_session_remaining_secs = 0
            state.fish_session_deadline = None
        self.runtime.ui.log(f"⏹ Fishing stopped — {state.stats['fish_casts']} casts")


class AutoHealerService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.healer_active:
            return
        if state.healer_mode == "rune" and (
            state.healer_character_pos == (0, 0) or state.healer_rune_pos == (0, 0)
        ):
            self.runtime.ui.log("⚠️  Record character center and healing rune position first")
            self.runtime.ui.set_status("Record healer positions first", ORANGE)
            return
        self.runtime.healer_stop.clear()
        state.healer_active = True
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Auto healer active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.healer_active:
            return
        self.runtime.healer_stop.set()
        state.healer_active = False
        self.runtime.ui.set_status("Auto healer stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Auto healer start")
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.healer_active = False
            return
        keyboard = pynput_kb.Controller()
        mouse = pynput_mouse.Controller()
        cooldown_until = 0.0
        while not self.runtime.healer_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.healer_stop.is_set():
                break
            now = time.monotonic()
            if now < cooldown_until:
                if not self.runtime.pause.wait_interruptible(min(0.1, cooldown_until - now), self.runtime.healer_stop):
                    break
                continue
            with self.runtime.settings_lock:
                hp_peak = state.char_status_hp_peak
                # Use pointer-based MP first, fall back to OCR
                mana_value = None
                if self.runtime.mp_service is not None:
                    try:
                        mana_value = self.runtime.mp_service.get_mp()
                    except Exception:
                        pass
                mode = state.healer_mode
                spell_key_name = state.healer_spell_key
                use_percent = state.healer_use_percent
                hp_percent = state.healer_hp_percent
                hp_fixed = state.healer_hp_value
                min_mana = state.healer_min_mana
                character_pos = state.healer_character_pos
                rune_pos = state.healer_rune_pos
                mouse_speed = state.healer_mouse_speed
                rune_delay_ms = state.healer_rune_delay_ms
            # Try pointer-based HP first, fall back to OCR
            hp_value = None
            if self.runtime.hp_service is not None:
                try:
                    hp_value = self.runtime.hp_service.get_hp()
                except Exception:
                    pass
            if hp_value is None:
                if not self.runtime.pause.wait_interruptible(0.15, self.runtime.healer_stop):
                    break
                continue
            should_heal = False
            if use_percent:
                if hp_peak > 0 and (hp_value / hp_peak) * 100.0 <= hp_percent:
                    should_heal = True
            elif hp_value <= hp_fixed:
                should_heal = True
            if not should_heal:
                if not self.runtime.pause.wait_interruptible(0.12, self.runtime.healer_stop):
                    break
                continue
            if min_mana > 0 and mana_value is not None and mana_value < min_mana:
                if not self.runtime.pause.wait_interruptible(0.2, self.runtime.healer_stop):
                    break
                continue
            try:
                if mode == "spell":
                    spell_key = HotkeyService.key_str_to_pynput(spell_key_name)
                    if not spell_key:
                        self.runtime.ui.log(f"❌ Unknown healer spell key: {spell_key_name}")
                        break
                    if not self.runtime.execution.acquire(self.runtime.healer_stop, max_wait=0.25, module_id="healer"):
                        if self.runtime.healer_stop.is_set():
                            break
                        cooldown_until = time.monotonic() + 0.05
                        continue
                    session = SafeKeyboardSession(keyboard)
                    try:
                        session.tap(spell_key, hold_seconds=0.03)
                    finally:
                        session.release_all()
                        self.runtime.execution.release()
                    cooldown_until = time.monotonic() + 0.35
                    self.runtime.ui.log(f"❤️ Spell heal ({spell_key_name.upper()}) at HP {hp_value}")
                else:
                    if not self.runtime.mouse.acquire(self.runtime.healer_stop, max_wait=0.35, module_id="healer"):
                        if self.runtime.healer_stop.is_set():
                            break
                        cooldown_until = time.monotonic() + 0.08
                        continue
                    try:
                        HumanMouse.move(mouse, rune_pos, duration=max(0.05, 0.20 / max(mouse_speed, 0.2)))
                        time.sleep(0.04)
                        mouse.click(pynput_mouse.Button.right, 1)
                        if not self.runtime.pause.wait_interruptible(rune_delay_ms / 1000.0, self.runtime.healer_stop):
                            break
                        HumanMouse.move(mouse, character_pos, duration=max(0.05, 0.20 / max(mouse_speed, 0.2)))
                        time.sleep(0.04)
                        mouse.click(pynput_mouse.Button.left, 1)
                    finally:
                        self.runtime.mouse.release()
                    cooldown_until = time.monotonic() + max(0.45, rune_delay_ms / 1000.0 + 0.15)
                    self.runtime.ui.log(f"❤️ Rune heal at HP {hp_value}")
                with self.runtime.record_lock:
                    state.stats["heals"] += 1
                self.runtime.ui.refresh_stats()
            except Exception as exc:
                self.runtime.ui.log(f"❌ Auto healer: {exc}")
                break
        state.healer_active = False
        self.runtime.ui.log("⏹ Auto healer end")


class RuneMakerService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    def start(self) -> None:
        state = self.runtime.state
        if state.rune_active:
            return
        if any(position == (0, 0) for position in [state.rune_hand_pos, state.rune_storage_pos, state.rune_blank_pos]):
            self.runtime.ui.log("⚠️  Record all 3 positions before starting")
            self.runtime.ui.set_status("Record all 3 rune positions first", ORANGE)
            return
        self.runtime.rune_stop.clear()
        state.rune_active = True
        threading.Thread(target=self._worker, daemon=True).start()
        self.runtime.ui.set_status("Rune session running…", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.rune_active:
            return
        self.runtime.rune_stop.set()
        state.rune_active = False
        self.runtime.ui.set_status("Rune session stopped", RED)

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log(
            f"▶ Rune session start — spell={state.rune_spell_key.upper()}  "
            f"cycle={state.rune_cycle_delay_ms}ms  post-settle={state.rune_post_cast_settle_ms}ms"
        )
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            state.rune_active = False
            return
        keyboard = pynput_kb.Controller()
        mouse = pynput_mouse.Controller()
        spell = HotkeyService.key_str_to_pynput(state.rune_spell_key)
        if not spell:
            self.runtime.ui.log(f"❌ Unknown spell key: {state.rune_spell_key}")
            state.rune_active = False
            return

        cycles_completed = 0
        while not self.runtime.rune_stop.is_set():
            self.runtime.pause.wait()
            if self.runtime.rune_stop.is_set():
                break
            with self.runtime.settings_lock:
                hand = state.rune_hand_pos
                storage = state.rune_storage_pos
                blank = state.rune_blank_pos
                jitter = state.rune_jitter
                cast_delay_ms = state.rune_cast_delay_ms
                cycle_delay_ms = state.rune_cycle_delay_ms
                cycle_variation_ms = state.rune_cycle_delay_variation_ms
                min_mana = state.rune_min_mana
                # Use pointer-based MP first, fall back to OCR
                current_mana = None
                if self.runtime.mp_service is not None:
                    try:
                        current_mana = self.runtime.mp_service.get_mp()
                    except Exception:
                        pass
                if current_mana is None:
                    with self.runtime.settings_lock:
                        current_mana = state.char_status_mana
                blank_rune_limit = state.rune_available_blank_runes
                move_min_ms = state.rune_mouse_move_min_ms
                move_max_ms = state.rune_mouse_move_max_ms
                press_min_ms = state.rune_mouse_press_min_ms
                press_max_ms = state.rune_mouse_press_max_ms
                settle_min_ms = state.rune_mouse_settle_min_ms
                settle_max_ms = state.rune_mouse_settle_max_ms
                post_cast_settle_ms = state.rune_post_cast_settle_ms
            if blank_rune_limit > 0 and cycles_completed >= blank_rune_limit:
                self.runtime.ui.log(f"⏲️ Rune session stopped — avb blank runes limit reached ({blank_rune_limit})")
                self.runtime.ui.set_status("Rune session finished by avb blank runes limit", ORANGE)
                break
            if min_mana > 0 and current_mana is not None and current_mana < min_mana:
                if not self.runtime.pause.wait_interruptible(1.0, self.runtime.rune_stop):
                    break
                continue
            queue_window = max(
                0.90,
                cast_delay_ms / 1000.0
                + (move_max_ms * 2 + press_max_ms * 2 + settle_max_ms * 2) / 1000.0
                + post_cast_settle_ms / 1000.0
                + 0.40,
            )
            if not self.runtime.execution.acquire(self.runtime.rune_stop, max_wait=queue_window, module_id="rune"):
                if self.runtime.rune_stop.is_set():
                    break
                if not self.runtime.pause.wait_interruptible(0.15, self.runtime.rune_stop):
                    break
                continue
            session = SafeKeyboardSession(keyboard)
            try:
                session.tap(spell, hold_seconds=0.04)
                self.runtime.ui.log(f"✨ Spell cast ({state.rune_spell_key.upper()})")
                if not self.runtime.pause.wait_interruptible(cast_delay_ms / 1000.0, self.runtime.rune_stop):
                    break

                move_duration = random.uniform(move_min_ms, move_max_ms) / 1000.0
                press_delay_range = (press_min_ms / 1000.0, press_max_ms / 1000.0)
                settle_delay_range = (settle_min_ms / 1000.0, settle_max_ms / 1000.0)

                HumanMouse.drag(
                    mouse,
                    HumanMouse.jitter(hand, jitter),
                    HumanMouse.jitter(storage, jitter),
                    move_duration=move_duration,
                    press_delay_range=press_delay_range,
                    hold_delay_range=press_delay_range,
                    settle_delay_range=settle_delay_range,
                )
                self.runtime.ui.log("📦 Rune moved → storage")
                time.sleep(random.uniform(*settle_delay_range))
                HumanMouse.drag(
                    mouse,
                    HumanMouse.jitter(blank, jitter),
                    HumanMouse.jitter(hand, jitter),
                    move_duration=random.uniform(move_min_ms, move_max_ms) / 1000.0,
                    press_delay_range=press_delay_range,
                    hold_delay_range=press_delay_range,
                    settle_delay_range=settle_delay_range,
                )
                self.runtime.ui.log("📥 Blank rune → hand slot")
                # Settle before next cast — lets mana deplete and OCR catch up
                time.sleep(post_cast_settle_ms / 1000.0)
            except Exception as exc:
                self.runtime.ui.log(f"❌ Rune cycle: {exc}")
                break
            finally:
                session.release_all()
                self.runtime.execution.release()
            with self.runtime.record_lock:
                state.stats["runes_made"] += 1
            cycles_completed += 1
            self.runtime.ui.refresh_stats()
            wait_s = random.randint(
                max(0, cycle_delay_ms - cycle_variation_ms),
                max(0, cycle_delay_ms + cycle_variation_ms),
            ) / 1000.0
            self.runtime.ui.log(f"⏳ Waiting {wait_s:.1f}s before next cast…")
            if not self.runtime.pause.wait_interruptible(wait_s, self.runtime.rune_stop):
                break
        state.rune_active = False
        self.runtime.ui.log(f"⏹ Rune session stopped — {state.stats['runes_made']} runes moved")


class HotkeyJobService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.key_map = self._build_key_map()

    def _build_key_map(self) -> dict:
        if not HAS_PYNPUT:
            return {}
        mapping = {f"F{i}": getattr(pynput_kb.Key, f"f{i}") for i in range(1, 13)}
        for label, attr_name in [
            ("ESC", "esc"),
            ("ENTER", "enter"),
            ("SPACE", "space"),
            ("TAB", "tab"),
            ("UP", "up"),
            ("DOWN", "down"),
            ("LEFT", "left"),
            ("RIGHT", "right"),
            ("HOME", "home"),
            ("END", "end"),
            ("DELETE", "delete"),
            ("INSERT", "insert"),
            ("PAGEUP", "page_up"),
            ("PAGEDOWN", "page_down"),
        ]:
            key_value = getattr(pynput_kb.Key, attr_name, None)
            if key_value is not None:
                mapping[label] = key_value
        for char in "abcdefghijklmnopqrstuvwxyz0123456789":
            mapping[char.upper()] = pynput_kb.KeyCode.from_char(char)
        return mapping

    def start_job(self, job: HotkeyJob) -> None:
        if job.running:
            return
        job.stop_evt.clear()
        job.running = True
        threading.Thread(target=self._worker, args=(job,), daemon=True).start()
        self.runtime.ui.job_state_changed(job)
        self.runtime.ui.set_status(f"Job #{job.job_id} ({job.key}) started", GREEN)

    def stop_job(self, job: HotkeyJob) -> None:
        job.stop_evt.set()

    def stop_all(self, stop_afk, stop_rclick, stop_alarm, stop_fishing, stop_rune) -> None:
        for job in list(self.runtime.state.jobs):
            self.stop_job(job)
        stop_afk()
        stop_rclick()
        stop_alarm()
        stop_fishing()
        stop_rune()
        if self.runtime.pause.paused:
            self.runtime.pause.toggle()
        self.runtime.ui.log("🛑 ALL STOPPED (stop_all hotkey)")
        self.runtime.ui.set_status("All stopped", RED)

    def _worker(self, job: HotkeyJob) -> None:
        if not HAS_PYNPUT:
            self.runtime.ui.log("❌ pynput missing")
            job.running = False
            return
        keyboard = pynput_kb.Controller()
        pressed_key = self.key_map.get(job.key.upper())
        if not pressed_key:
            self.runtime.ui.log(f"❌ Unknown key {job.key}")
            job.running = False
            return
        self.runtime.ui.log(f"▶ Job #{job.job_id} — key={job.key} {job.min_ms}–{job.max_ms}ms focus={job.use_focus}")
        while not job.stop_evt.is_set():
            self.runtime.pause.wait()
            delay = random.randint(job.min_ms, job.max_ms) / 1000.0
            if not self.runtime.pause.wait_interruptible(delay, job.stop_evt):
                break
            prev_hwnd = None
            if job.min_mana > 0:
                # Use pointer-based MP first, fall back to OCR
                current_mana = None
                if self.runtime.mp_service is not None:
                    try:
                        current_mana = self.runtime.mp_service.get_mp()
                    except Exception:
                        pass
                if current_mana is None:
                    with self.runtime.settings_lock:
                        current_mana = self.runtime.state.char_status_mana
                if current_mana is not None and current_mana < job.min_mana:
                    continue
            if job.use_focus and job.window_name.strip():
                prev_hwnd = WindowService.get_foreground_hwnd()
                if not WindowService.focus_window_by_name(job.window_name.strip()):
                    self.runtime.ui.log(f"⚠️  Job #{job.job_id}: window '{job.window_name}' not found")
            if not self.runtime.execution.acquire(job.stop_evt, max_wait=0.45, module_id=f"job:{job.job_id}"):
                if job.stop_evt.is_set():
                    break
                continue
            if job.burst_enabled and random.random() < job.burst_chance:
                count = random.randint(job.burst_cnt_min, job.burst_cnt_max)
                sent = 0
                try:
                    for _ in range(count):
                        if job.stop_evt.is_set():
                            break
                        self._press_key(keyboard, pressed_key)
                        sent += 1
                        # Add slight random variation between burst clicks for natural rhythm
                        inter_click = max(0.02, job.burst_int_ms / 1000.0 + random.uniform(-0.05, 0.08))
                        time.sleep(inter_click)
                finally:
                    self.runtime.execution.release()
                with self.runtime.record_lock:
                    self.runtime.state.stats["hotkeys"] += sent
                    if sent:
                        self.runtime.state.stats["bursts"] += 1
                if sent:
                    self.runtime.ui.log(f"⚡ Job #{job.job_id} burst {job.key} ×{sent}")
            else:
                try:
                    self._press_key(keyboard, pressed_key)
                finally:
                    self.runtime.execution.release()
                with self.runtime.record_lock:
                    self.runtime.state.stats["hotkeys"] += 1
                self.runtime.ui.log(f"🎮 Job #{job.job_id} pressed {job.key}")
            if job.use_focus and job.restore_focus and prev_hwnd:
                time.sleep(0.05)
                WindowService.restore(prev_hwnd)
            self.runtime.ui.refresh_stats()
        job.running = False
        self.runtime.ui.log(f"⏹ Job #{job.job_id} stopped")
        self.runtime.ui.job_state_changed(job)

    @staticmethod
    def _press_key(keyboard, pressed_key) -> None:
        session = SafeKeyboardSession(keyboard)
        try:
            session.tap(pressed_key, hold_seconds=0.03)
        finally:
            session.release_all()


class HotkeyService:
    @staticmethod
    def key_str_to_pynput(key_str: str):
        if not HAS_PYNPUT:
            return None
        value = key_str.strip().lower()
        named = {}
        for key_name, attr_name in [
            ("f1", "f1"),
            ("f2", "f2"),
            ("f3", "f3"),
            ("f4", "f4"),
            ("f5", "f5"),
            ("f6", "f6"),
            ("f7", "f7"),
            ("f8", "f8"),
            ("f9", "f9"),
            ("f10", "f10"),
            ("f11", "f11"),
            ("f12", "f12"),
            ("home", "home"),
            ("end", "end"),
            ("esc", "esc"),
            ("enter", "enter"),
            ("space", "space"),
            ("tab", "tab"),
            ("delete", "delete"),
            ("insert", "insert"),
            ("page_up", "page_up"),
            ("page_down", "page_down"),
            ("up", "up"),
            ("down", "down"),
            ("left", "left"),
            ("right", "right"),
        ]:
            key_value = getattr(pynput_kb.Key, attr_name, None)
            if key_value is not None:
                named[key_name] = key_value
        if value in named:
            return named[value]
        if len(value) == 1:
            return pynput_kb.KeyCode.from_char(value)
        return None

    @staticmethod
    def pynput_key_to_str(key) -> str:
        try:
            if hasattr(key, "char") and key.char:
                return key.char.lower()
            return key.name.lower()
        except AttributeError:
            return str(key).lower().replace("key.", "")

    @staticmethod
    def matches(pressed_key, binding_str: str) -> bool:
        target = HotkeyService.key_str_to_pynput(binding_str)
        return target is not None and pressed_key == target
