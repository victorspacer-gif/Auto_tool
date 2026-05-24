"""Monitoring, OCR, alarm, and pointer-based services."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

import psutil

try:
    from ..pointers import (
        AddressResolveError,
        DEFAULT_LIGHT_PROFILE,
        LightMemoryController,
        MemoryWriteError,
        PointerReader,
        ProcessNotFoundError,
    )

    HAS_LIGHT_MODULE = True
except ImportError:
    DEFAULT_LIGHT_PROFILE = None
    LightMemoryController = None
    AddressResolveError = RuntimeError
    MemoryWriteError = RuntimeError
    ProcessNotFoundError = RuntimeError
    PointerReader = None
    HAS_LIGHT_MODULE = False

from ..runtime import (
    AppRuntime,
    HAS_CV2,
    HAS_MSS,
    HAS_NUMPY,
    HAS_PYAUTOGUI,
    HAS_PYGAME,
    HAS_TESSERACT,
    HAS_WIN32,
    CV2_IMPORT_ERROR,
    MSS_IMPORT_ERROR,
    NUMPY_IMPORT_ERROR,
    TESSERACT_IMPORT_ERROR,
    create_ocr_engine,
    describe_ocr_environment,
    cv2,
    mss,
    np,
    pyautogui,
    pygame,
    resolve_tesseract_cmd,
    win32con,
    win32gui,
)

try:
    import ctypes
    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False
from ..theme import GREEN, ORANGE, RED, TEAL
from ..config import CHAR_STATUS_POLL_MS_MIN
from ..constants import (  # Monitoring timing and alarm constants
    LIGHT_FREEZE_MIN_INTERVAL_MS,  # Light freeze poll interval (milliseconds)
    MONITOR_ERROR_RETRY_SLEEP,  # Error retry sleep interval (seconds)
    MONITOR_POLL_SLEEP,  # Monitor poll sleep interval (seconds)
    ALARM_SOUND_FILENAME,  # Default alarm sound filename bundled with the app
)

class LightControlService:
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller = None
        self.pointer_reader: PointerReader | None = None
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
            self.pointer_reader = PointerReader(self.controller)
            return True, f"Attached to {process_name} | pointer list loaded"
        except ProcessNotFoundError as exc:
            fallback_name = self._find_game_process_name()
            if not fallback_name:
                return False, str(exc)
            try:
                self.controller = LightMemoryController(fallback_name)
                self.controller.attach()
                self.pointer_reader = PointerReader(self.controller)
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
                logger.debug("Light controller detach failed")
            self.controller = None
            self.pointer_reader = None
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
            f"every {LIGHT_FREEZE_MIN_INTERVAL_MS}ms"
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
            # Convert ms interval to seconds for Event.wait() timeout (seconds)
            delay = LIGHT_FREEZE_MIN_INTERVAL_MS / 1000.0
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
            if self.pointer_reader is None:
                raise RuntimeError("PointerReader unavailable.")
            color_address, intensity_address = self.pointer_reader.resolve_light_pair_addresses()
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
        # Match names that start with "miracle_dx" or "miracle_gl" and
        # allow zero or more hyphen-number suffix segments before the .exe
        # (e.g. miracle_gl-123.exe or miracle_gl-123-456.exe)
        pattern = re.compile(r"^(miracle_(?:dx|gl))(?:-\d+)*\.exe$", re.IGNORECASE)
        for proc in psutil.process_iter(attrs=["name"]):
            name = (proc.info.get("name") or "").strip()
            if pattern.fullmatch(name):
                return name
        return None

    def _require_controller(self):
        if self.controller is None:
            raise ProcessNotFoundError("Attach to the game process first.")
        return self.controller

class StatPointerService:
    """Shared pointer-backed stat reader with OCR fallback."""

    stat_label = "Stat"
    stat_name = ""
    pointer_address_attr = ""
    source_attr = ""
    value_attr = ""
    fallback_attr = ""
    state_resolved_attr: str | None = None
    local_address_attr = "_resolved_address"
    local_cache_attr = "_cache_time"
    local_ttl_attr = "_CACHE_TTL"
    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller: LightMemoryController | None = None
        self.pointer_reader: PointerReader | None = None
        setattr(self, self.local_address_attr, None)
        setattr(self, self.local_cache_attr, 0.0)
        setattr(self, self.local_ttl_attr, 60.0)

    def attach(self) -> tuple[bool, str]:
        process_name = self.runtime.state.light_process_name.strip() or "miracle_gl"

        try:
            self.controller = LightMemoryController(process_name)
            self.controller.attach()
            self.pointer_reader = PointerReader(
                self.controller,
                cache_ttl=getattr(self, self.local_ttl_attr)
            )

        except ProcessNotFoundError as exc:
            fallback_name = self._find_game_process_name()

            if not fallback_name:
                return False, str(exc)

            try:
                self.controller = LightMemoryController(fallback_name)
                self.controller.attach()
                self.pointer_reader = PointerReader(
                    self.controller,
                    cache_ttl=getattr(self, self.local_ttl_attr)
                )

                self.runtime.state.light_process_name = fallback_name

            except Exception as fallback_exc:
                return False, f"{exc} | fallback attach failed: {fallback_exc}"

        except Exception as exc:
            return False, f"Attach failed: {exc}"

        # After successful attach, try to resolve pointer and read initial value
        address = self._resolve_pointer()
        parts = []
        if address is not None:
            self._store_resolved_address(address)
            parts.append(f"{self.stat_label} pointer resolved at 0x{address:X}")
            try:
                value = self._read_pointer_value()
                with self.runtime.settings_lock:
                    setattr(self.runtime.state, self.value_attr, value)
                if isinstance(value, int):
                    parts.append(f"{self.stat_label}={value}")
                else:
                    parts.append(f"{self.stat_label}={value:.1f}")
            except Exception as exc:
                parts.append(f"{self.stat_label} read failed: {exc}")

        message = " | ".join(parts) if parts else "No pointers resolved"
        return True, f"Attached to {process_name} | {message}"

    def detach(self) -> tuple[bool, str]:
        if self.controller is not None:
            self.controller.detach()
        self.controller = None
        self.pointer_reader = None
        setattr(self, self.local_address_attr, None)
        return True, "Detached"

    def _is_address_valid(self) -> bool:
        address = getattr(self, self.local_address_attr)
        if address is None or self.controller is None:
            return False
        cache_time = getattr(self, self.local_cache_attr)
        ttl = getattr(self, self.local_ttl_attr)
        return time.time() - cache_time < ttl

    def _ensure_address_resolved(self) -> bool:
        if self.controller is None:
            return False
        address = self._resolve_pointer()
        if address is None:
            return False
        self._store_resolved_address(address)
        return True

    def _store_resolved_address(self, address: int) -> None:
        state = self.runtime.state
        setattr(self, self.local_address_attr, address)
        setattr(self, self.local_cache_attr, time.time())
        setattr(state, self.pointer_address_attr, f"{address:X}")
        setattr(state, self.source_attr, "pointer")
        if self.state_resolved_attr:
            setattr(state, self.state_resolved_attr, address)

    def _resolve_pointer(self) -> int | None:
        if self.pointer_reader is None or not self.stat_name:
            return None
        try:
            return self.pointer_reader.resolve_address(self.stat_name)
        except Exception:
            return None

    def _get_fallback_value(self) -> float | None:
        with self.runtime.settings_lock:
            fallback_value = getattr(self.runtime.state, self.fallback_attr)
        if fallback_value is not None and fallback_value > 0:
            return float(fallback_value)
        return None

    def _read_pointer_value(self) -> float | int:
        if self.pointer_reader is None or not self.stat_name:
            raise RuntimeError("Pointer reader unavailable.")
        read_method = getattr(self.pointer_reader, f"read_{self.stat_name}")
        return read_method()

    def _get_value(self) -> float | None:
        state = self.runtime.state
        if not self._is_address_valid():
            self._ensure_address_resolved()

        address = getattr(self, self.local_address_attr)
        if address is not None and self.pointer_reader is not None:
            try:
                value = self._read_pointer_value()
                with self.runtime.settings_lock:
                    setattr(state, self.value_attr, value)
                return value
            except Exception:
                logger.debug("Pointer read failed")
        return self._get_fallback_value()

    @staticmethod
    def _find_game_process_name() -> str | None:
        # Match names that start with "miracle_dx" or "miracle_gl" and
        # allow zero or more hyphen-number suffix segments before the .exe
        # (e.g. miracle_gl-123.exe or miracle_gl-123-456.exe)
        pattern = re.compile(r"^(miracle_(?:dx|gl))(?:-\d+)*\.exe$", re.IGNORECASE)
        for proc in psutil.process_iter(attrs=["name"]):
            name = (proc.info.get("name") or "").strip()
            if pattern.fullmatch(name):
                return name
        return None


class HpService(StatPointerService):
    """HP value reader with pointer-first resolution and OCR fallback."""

    stat_label = "HP"
    stat_name = "hp"
    pointer_address_attr = "hp_pointer_address_hex"
    source_attr = "hp_source"
    value_attr = "hp_value"
    fallback_attr = "char_status_hp"
    local_address_attr = "_hp_address"
    local_cache_attr = "_hp_cache_time"
    local_ttl_attr = "_HP_CACHE_TTL"

    def __init__(self, runtime: AppRuntime) -> None:
        super().__init__(runtime)
        self._light_address: int | None = None

    def is_available(self) -> bool:
        return HAS_LIGHT_MODULE

    def attach(self) -> tuple[bool, str]:
        if not HAS_LIGHT_MODULE:
            return False, "Install psutil and pymem to use HP pointer"

        ok, message = super().attach()
        if not ok:
            return ok, message

        parts = message.split(" | ")[1:] if " | " in message else []
        try:
            light_address = self.pointer_reader.resolve_light_address() if self.pointer_reader else None
        except Exception:
            light_address = None

        if light_address is not None:
            self._light_address = light_address
            parts.append(f"Light pointer resolved at 0x{light_address:X}")

        process_name = self.runtime.state.light_process_name.strip() or "miracle_gl.exe"
        suffix = " | ".join(parts) if parts else "No pointers resolved"
        return True, f"Attached to {process_name} | {suffix}"

    def detach(self) -> tuple[bool, str]:
        result = super().detach()
        self._light_address = None
        return result

    def get_hp(self) -> float | None:
        return self._get_value()

    def get_hp_peak(self) -> int:
        with self.runtime.settings_lock:
            return self.runtime.state.char_status_hp_peak

    def _read_all_stats(self) -> tuple[float | None, float | None, float | None]:
        """Read HP/MP/Cap/Food from pointers, falling back to OCR when unavailable.

        Returns (hp_val, mp_val, cap_val) from pointers (may be None).  When a
        pointer read fails the corresponding state attribute is populated from the
        OCR channel so that downstream consumers (healer, fishing, runes, alarm)
        always have a numeric value to work with instead of None.
        """
        state = self.runtime.state
        hp_val = None
        mp_val = None
        cap_val = None
        food_val = None

        if self.pointer_reader is not None:
            try:
                hp_val = float(self.pointer_reader.read_hp())
                with self.runtime.settings_lock:
                    state.hp_source = "pointer"
            except Exception:
                logger.debug("HP pointer read failed")

        if getattr(state, "_mp_resolved_addr", None) is not None and self.pointer_reader is not None:
            try:
                mp_val = self.pointer_reader.read_mp()
                with self.runtime.settings_lock:
                    state.mp_source = "pointer"
            except Exception:
                logger.debug("MP pointer read failed")

        if getattr(state, "_cap_resolved_addr", None) is not None and self.pointer_reader is not None:
            try:
                cap_val = self.pointer_reader.read_cap()
                with self.runtime.settings_lock:
                    state.cap_source = "pointer"
            except Exception:
                logger.debug("Cap pointer read failed")

        if getattr(state, "_food_resolved_addr", None) is not None and self.pointer_reader is not None:
            try:
                food_val = self.pointer_reader.read_food()
                with self.runtime.settings_lock:
                    state.food_source = "pointer"
            except Exception:
                logger.debug("Food pointer read failed")

        # Promote OCR fallback values when pointer reads are unavailable.
        # This ensures auto-heal, auto-food, runes, alarm etc. always have a
        # numeric value to work with instead of None when pointers fail
        # (client update, game restart, etc.).
        with self.runtime.settings_lock:
            if hp_val is None:
                ocr_hp = getattr(state, "char_status_hp", None)
                if ocr_hp is not None and ocr_hp > 0:
                    hp_val = float(ocr_hp)
                    state.hp_value = hp_val
                    state.hp_source = "ocr"
            if mp_val is None:
                ocr_mp = getattr(state, "char_status_mana", None)
                if ocr_mp is not None and ocr_mp > 0:
                    mp_val = float(ocr_mp)
                    state.mp_value = mp_val
                    state.mp_source = "ocr"
            if cap_val is None:
                ocr_cap = getattr(state, "char_status_cap", None)
                if ocr_cap is not None and ocr_cap > 0:
                    cap_val = float(ocr_cap)
                    state.cap_value = cap_val
                    state.cap_source = "ocr"
            if food_val is None:
                ocr_food = getattr(state, "char_status_food_seconds", None)
                if ocr_food is not None and ocr_food > 0:
                    food_val = int(ocr_food)
                    state.food_value = food_val
                    state.food_source = "ocr"

            # Always write whatever we have (pointer or OCR) to state attrs
            if hp_val is not None:
                state.hp_value = hp_val
            if mp_val is not None:
                state.mp_value = mp_val
            if cap_val is not None:
                state.cap_value = cap_val
            if food_val is not None:
                state.food_value = food_val

        return (hp_val, mp_val, cap_val)


class MpService(StatPointerService):
    """MP (Mana) value reader with pointer-first resolution and OCR fallback."""

    stat_label = "MP"
    stat_name = "mp"
    pointer_address_attr = "mp_pointer_address_hex"
    source_attr = "mp_source"
    value_attr = "mp_value"
    fallback_attr = "char_status_mana"
    state_resolved_attr = "_mp_resolved_addr"
    local_address_attr = "_mp_address"
    local_cache_attr = "_mp_cache_time"
    local_ttl_attr = "_MP_CACHE_TTL"

    def get_mp(self) -> float | None:
        return self._get_value()


class CapService(StatPointerService):
    """Cap value reader with pointer-first resolution and OCR fallback."""

    stat_label = "Cap"
    stat_name = "cap"
    pointer_address_attr = "cap_pointer_address_hex"
    source_attr = "cap_source"
    value_attr = "cap_value"
    fallback_attr = "char_status_cap"
    state_resolved_attr = "_cap_resolved_addr"
    local_address_attr = "_cap_address"
    local_cache_attr = "_cap_cache_time"
    local_ttl_attr = "_CAP_CACHE_TTL"

    def get_cap(self) -> float | None:
        return self._get_value()

    def get_cap_peak(self) -> int:
        with self.runtime.settings_lock:
            return self.runtime.state.char_status_cap_peak


class FoodService(StatPointerService):
    """Food timer value reader with pointer-first resolution and OCR fallback."""

    stat_label = "Food"
    stat_name = "food"
    pointer_address_attr = "food_pointer_address_hex"
    source_attr = "food_source"
    value_attr = "food_value"
    fallback_attr = "char_status_food_seconds"
    state_resolved_attr = "_food_resolved_addr"
    local_address_attr = "_food_address"
    local_cache_attr = "_food_cache_time"
    local_ttl_attr = "_FOOD_CACHE_TTL"

    def get_food(self) -> int | None:
        value = self._get_value()
        return int(value) if value is not None else None


class AlarmService:
    BATTLE_COOLDOWN_SECONDS = 3.0

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime

    @staticmethod
    def _resolve_alarm_audio_path(raw_path: str) -> str:
        cleaned = (raw_path or "").strip().strip('"').strip("'")
        if not cleaned:
            return ""

        candidate = Path(cleaned).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate

        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            resolved = candidate
        return str(resolved)

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
        self.runtime.ui.module_state_changed("alarm", True)
        self.runtime.ui.set_status("Screen watch active…", TEAL)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.alarm_active:
            return
        self.runtime.alarm_stop.set()
        state.alarm_active = False
        self.runtime.ui.module_state_changed("alarm", False)
        self.runtime.ui.set_status("Screen watch stopped", RED)

    def _resolve_alarm_sound_path(self) -> str:
        """Resolve the alarm audio file path, falling back to bundled default."""
        # First try user-configured path
        raw = (self.runtime.state.alarm_mp3 or "").strip()
        if raw:
            resolved = self._resolve_alarm_audio_path(raw)
            if os.path.exists(resolved):
                return resolved

        # Fall back to bundled alarm sound in systool/services/
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_path = os.path.join(base_dir, "services", ALARM_SOUND_FILENAME)
            if os.path.exists(default_path):
                return default_path
        except Exception:
            pass

        return ""

    def _flash_game_window(self) -> None:
        """Flash the game window's taskbar icon using win32gui."""
        if not HAS_WIN32 or not win32gui or not win32con:
            return
        try:
            # Try to find the game process window (miracle_gl.exe)
            def enum_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    _, process_name = win32gui.GetWindowText(hwnd), None
                    # Check process name from window title or class
                    try:
                        pid = win32gui.GetWindowThreadProcessId(hwnd)
                        import psutil
                        proc = psutil.Process(pid[1])
                        pname = proc.name().lower()
                        if "miracle" in pname or "game" in pname.lower():
                            results.append((hwnd, process_name))
                    except Exception:
                        pass

            handles = []
            win32gui.EnumWindows(enum_callback, handles)
            for hwnd, title in handles[:1]:  # Flash first matching window
                try:
                    FLASH_INFO = (win32con.FW_RUNNABLEONCALLBACK |
                                  win32con.FW_RESTORECONFOFF |
                                  50)  # flash 5 times
                    win32gui.FlashWindow(hwnd, True)
                except Exception:
                    pass
        except Exception:
            pass

    def _play_system_sound(self) -> None:
        """Play a standard Windows system sound (SystemAsterisk)."""
        if not HAS_CTYPES:
            return
        try:
            ctypes.windll.user32.MessageBeep(0x40)  # MB_OK | MB_ICONASTERISK = SystemAsterisk
        except Exception:
            pass

    def _has_attached_game_window(self) -> bool:
        light_service = getattr(self.runtime, "light_service", None)
        controller = getattr(light_service, "controller", None) if light_service is not None else None
        return controller is not None

    def _prepare_battle_frame(self, frame):
        if frame is None or frame.size == 0:
            return None
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if HAS_CV2 else frame.mean(axis=2).astype(np.uint8)
        else:
            gray = frame
        height, width = gray.shape[:2]
        scale = min(1.0, 96.0 / max(width, height))
        if scale < 1.0:
            gray = cv2.resize(
                gray,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        return gray

    def _battle_changed_ratio(self, previous, current) -> float:
        if previous is None or current is None or previous.shape != current.shape:
            return 0.0
        diff = np.abs(current.astype(np.int16) - previous.astype(np.int16))
        return float(np.mean(diff > 18))

    def _execute_battle_hotkey(self) -> bool:
        if not HAS_PYAUTOGUI:
            self.runtime.ui.log("Battle reaction needs pyautogui")
            return False
        try:
            pyautogui.keyDown("ctrl")
            time.sleep(0.02)

            pyautogui.keyDown("q")
            time.sleep(0.05)

            pyautogui.keyUp("q")
            return True
        except Exception as exc:
            self.runtime.ui.log(f"Battle CTRL+Q failed: {exc}")
            return False
        finally:
            try:
                pyautogui.keyUp("ctrl")
            except Exception:
                logger.debug("Battle CTRL key release failed")

    def play_alarm(self) -> None:
        path = self._resolve_alarm_sound_path()
        if path:
            self.runtime.state.alarm_mp3 = path

        state = self.runtime.state
        flash_window = getattr(state, 'alarm_flash_window', True)  # Default: enabled
        system_sound = getattr(state, 'alarm_system_sound', False)  # Default: disabled

        def play() -> None:
            try:
                # Play Windows system sound if enabled (non-blocking, instant feedback)
                if system_sound and HAS_CTYPES:
                    self._play_system_sound()

                # Flash game window taskbar icon if enabled
                if flash_window and HAS_WIN32:
                    self._flash_game_window()

                # Play MP3 alarm sound via pygame or shell
                if path and os.path.exists(path):
                    if HAS_PYGAME:
                        try:
                            pygame.mixer.music.load(path)
                            pygame.mixer.music.play()
                        except Exception as exc:
                            logger.warning("pygame mixer failed, falling back to shell playback: %s", exc)
                            os.startfile(path)
                    else:
                        os.startfile(path)
                elif not system_sound and not flash_window:
                    self.runtime.ui.log("⚠️  No alarm sound configured")
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
                    return {
                        "top": region[1],  # y-coordinate (index 1)
                        "left": region[0],  # x-coordinate (index 0)
                        "width": region[2],  # width (index 2)
                        "height": region[3],  # height (index 3)
                        "mon": 1,  # Monitor index: primary display
                    }
                size = 200  # Default alarm region side length in pixels (200x200 square)
                return {"top": screen_h // 2 - size // 2, "left": screen_w // 2 - size // 2, "width": size, "height": size, "mon": 1}

            last_frame = None
            battle_last_frame = None
            battle_was_changed = False
            battle_cooldown_until = 0.0
            battle_cooldown_log_at = 0.0
            battle_started_logged = False
            cooldown_until = 0.0
            while not self.runtime.alarm_stop.is_set():
                time.sleep(MONITOR_POLL_SLEEP)
                now = time.monotonic()
                with self.runtime.settings_lock:
                    hp_percent = state.alarm_hp_percent
                    hp_peak = state.char_status_hp_peak
                    auto_pause = state.alarm_auto_pause
                    threshold = state.alarm_threshold
                    alarm_hp_value = state.alarm_hp_value
                    alarm_mp_value = state.alarm_mp_value
                    alarm_cap_value = state.alarm_cap_value
                    battle_enabled = state.alarm_battle_enabled
                    battle_region = state.alarm_battle_region
                    battle_threshold = state.alarm_battle_threshold
                # Try pointer-based HP first, fall back to OCR
                hp_value = None
                if self.runtime.hp_service is not None:
                    try:
                        hp_value = self.runtime.hp_service.get_hp()
                    except Exception:
                        logger.debug("HP read failed in alarm loop")
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
                # Absolute value alerts (no % needed — uses live pointer reads)
                mp_value = None
                cap_value = None
                if self.runtime.mp_service is not None:
                    try:
                        mp_value = self.runtime.mp_service.get_mp()
                    except Exception:
                        logger.debug("MP read failed in alarm loop")
                if mp_value is None:
                    with self.runtime.settings_lock:
                        mp_value = state.char_status_mana
                if self.runtime.cap_service is not None:
                    try:
                        cap_value = self.runtime.cap_service.get_cap()
                    except Exception:
                        logger.debug("Cap read failed in alarm loop")
                if cap_value is None:
                    with self.runtime.settings_lock:
                        cap_value = state.char_status_cap
                # Low HP (absolute value)
                if alarm_hp_value > 0 and hp_value is not None and now >= cooldown_until:
                    if hp_value <= alarm_hp_value:
                        cooldown_until = now + state.alarm_cooldown
                        with self.runtime.record_lock:
                            state.stats["alarms"] += 1
                        self.runtime.ui.log(f"🚨 LOW HP — {hp_value:.0f} (below {alarm_hp_value})")
                        self.runtime.ui.set_status(f"⚠️  LOW HP — {hp_value:.0f}", RED)
                        self.play_alarm()
                        self.runtime.ui.refresh_stats()
                        if auto_pause and not self.runtime.pause.paused:
                            self.runtime.ui.log("⏸  Auto-pausing all activities due to low HP")
                            self.runtime.ui.dispatch(self.runtime.pause.toggle)
                # Low MP (absolute value)
                elif alarm_mp_value > 0 and mp_value is not None and now >= cooldown_until:
                    if mp_value <= alarm_mp_value:
                        cooldown_until = now + state.alarm_cooldown
                        with self.runtime.record_lock:
                            state.stats["alarms"] += 1
                        self.runtime.ui.log(f"🚨 LOW MP — {mp_value:.0f} (below {alarm_mp_value})")
                        self.runtime.ui.set_status(f"⚠️  LOW MP — {mp_value:.0f}", RED)
                        self.play_alarm()
                        self.runtime.ui.refresh_stats()
                        if auto_pause and not self.runtime.pause.paused:
                            self.runtime.ui.log("⏸  Auto-pausing all activities due to low MP")
                            self.runtime.ui.dispatch(self.runtime.pause.toggle)
                # Low Cap (absolute value)
                elif alarm_cap_value > 0 and cap_value is not None and now >= cooldown_until:
                    if cap_value <= alarm_cap_value:
                        cooldown_until = now + state.alarm_cooldown
                        with self.runtime.record_lock:
                            state.stats["alarms"] += 1
                        self.runtime.ui.log(f"🚨 LOW CAP — {cap_value:.0f} (below {alarm_cap_value})")
                        self.runtime.ui.set_status(f"⚠️  LOW CAP — {cap_value:.0f}", RED)
                        self.play_alarm()
                        self.runtime.ui.refresh_stats()
                        if auto_pause and not self.runtime.pause.paused:
                            self.runtime.ui.log("⏸  Auto-pausing all activities due to low Cap")
                            self.runtime.ui.dispatch(self.runtime.pause.toggle)
                try:
                    frame = np.array(sct.grab(get_region()))[:, :, :3]
                except Exception as exc:
                    self.runtime.ui.log(f"❌ Capture: {exc}")
                    continue
                if last_frame is not None and last_frame.shape == frame.shape:
                    if now >= cooldown_until:
                        diff = np.abs(frame.astype(np.int16) - last_frame.astype(np.int16))
                        # Pixel-level difference: sum channels, then count pixels where diff > 30 (threshold)
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

                if not battle_enabled:
                    battle_last_frame = None
                    battle_was_changed = False
                    battle_started_logged = False
                    continue
                if (
                    not state.alarm_active
                    or self.runtime.pause.paused
                    or not battle_region
                    or not self._has_attached_game_window()
                ):
                    battle_last_frame = None
                    battle_was_changed = False
                    continue
                if not battle_started_logged:
                    self.runtime.ui.log("Battle monitor started")
                    battle_started_logged = True
                try:
                    battle_frame = np.array(sct.grab({
                        "top": battle_region[1],
                        "left": battle_region[0],
                        "width": battle_region[2],
                        "height": battle_region[3],
                        "mon": 1,
                    }))[:, :, :3]
                except Exception as exc:
                    self.runtime.ui.log(f"Battle capture: {exc}")
                    continue
                prepared_battle_frame = self._prepare_battle_frame(battle_frame)
                current_changed = False
                if battle_last_frame is not None:
                    changed_ratio = self._battle_changed_ratio(battle_last_frame, prepared_battle_frame)
                    threshold_ratio = max(0.0, min(1.0, battle_threshold))
                    current_changed = changed_ratio >= threshold_ratio
                    if current_changed and not battle_was_changed:
                        if now >= battle_cooldown_until:
                            self.runtime.ui.log(f"Battle change detected: {changed_ratio * 100:.1f}%")
                            if self._execute_battle_hotkey():
                                battle_cooldown_until = now + self.BATTLE_COOLDOWN_SECONDS
                                self.runtime.ui.log("CTRL+Q executed")
                        elif now >= battle_cooldown_log_at:
                            remaining = max(0.0, battle_cooldown_until - now)
                            self.runtime.ui.log(f"Battle cooldown active ({remaining:.1f}s)")
                            battle_cooldown_log_at = now + 1.0
                battle_was_changed = current_changed
                battle_last_frame = prepared_battle_frame
        self.runtime.state.alarm_active = False
        self.runtime.ui.module_state_changed("alarm", False)
        self.runtime.ui.log("⏹ Screen watch end")

class CharacterStatusService:
    # Maximum allowed food timer value in seconds (40 min). Values above this are rejected as unrealistic OCR artifacts.
    MAX_FOOD_SECONDS = 2400

    # Base dimensions of the full character status window in pixels (width, height)
    BASE_SIZE = (170, 203)
    # ROI (Region of Interest) coordinates for stat extraction — each tuple is (left, top, right, bottom)
    # Coordinates are relative to BASE_SIZE and scaled dynamically per actual frame size.
    ROI_MAP = {
        "level": [
            (0, 18, 169, 40),
            (0, 14, 169, 44),
        ],
        "hp": [
            (132, 1, 169, 19),   # HP box A: left=132, top=1, right=169, bottom=19
            (124, 0, 169, 21),   # HP box B (fallback): left=124, top=0, right=169, bottom=21
        ],
        "mana": [
            (136, 21, 169, 39),  # Mana box A: left=136, top=21, right=169, bottom=39
            (128, 20, 169, 41),  # Mana box B (fallback): left=128, top=20, right=169, bottom=41
        ],
        "cap": [
            (0, 180, 42, 203),   # Cap box A: left=0, top=180, right=42, bottom=203
            (0, 164, 44, 203),   # Cap box B (fallback): left=0, top=164, right=44, bottom=203
        ],
        "food": [
            (128, 59, 169, 77),  # Food timer box A: left=128, top=59, right=169, bottom=77
            (124, 57, 169, 79),  # Food timer box B (fallback): left=124, top=57, right=169, bottom=79
        ],
    }

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self._regen_history: dict[str, list[tuple[float, int]]] = {"hp": [], "mana": []}
        self._ocr_engine = None
        physical_cores = os.cpu_count() or 1
        worker_count = max(1, min(physical_cores, 4))
        self._ocr_pool = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="char-ocr")
        self._frame_cache: dict[str, tuple[bytes, dict[str, int | None | str]]] = {}
        self._perf_snapshot: dict[str, float | int | str] = {
            "backend": "uninitialized",
            "cycle_ms": 0.0,
            "capture_ms": 0.0,
            "preprocess_ms": 0.0,
            "ocr_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "confidence": 0.0,
        }

    def get_dependency_error(self) -> str | None:
        state = self.runtime.state
        if not HAS_MSS:
            return "mss import failed" + (f": {MSS_IMPORT_ERROR}" if MSS_IMPORT_ERROR else "")
        if not HAS_NUMPY:
            return "numpy import failed" + (f": {NUMPY_IMPORT_ERROR}" if NUMPY_IMPORT_ERROR else "")
        if not HAS_CV2:
            return "opencv-python import failed" + (f": {CV2_IMPORT_ERROR}" if CV2_IMPORT_ERROR else "")
        if not HAS_TESSERACT:
            return "OCR backend import failed" + (f": {TESSERACT_IMPORT_ERROR}" if TESSERACT_IMPORT_ERROR else "")
        if not resolve_tesseract_cmd(state.char_status_tesseract_path):
            return "Tesseract executable not found"
        return None

    def get_perf_summary(self) -> str:
        snapshot = dict(self._perf_snapshot)
        return (
            f"OCR backend={snapshot.get('backend', 'n/a')} "
            f"cycle={snapshot.get('cycle_ms', 0.0):.1f}ms "
            f"capture={snapshot.get('capture_ms', 0.0):.1f}ms "
            f"pre={snapshot.get('preprocess_ms', 0.0):.1f}ms "
            f"ocr={snapshot.get('ocr_ms', 0.0):.1f}ms "
            f"cache={int(snapshot.get('cache_hits', 0))}/{int(snapshot.get('cache_hits', 0)) + int(snapshot.get('cache_misses', 0)) if int(snapshot.get('cache_hits', 0)) + int(snapshot.get('cache_misses', 0)) else 0} "
            f"conf={snapshot.get('confidence', 0.0):.2f}"
        )

    def get_backend_diagnostic(self) -> str:
        return describe_ocr_environment()

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
        try:
            self._ocr_engine = create_ocr_engine(state.char_status_tesseract_path)
            self._perf_snapshot["backend"] = getattr(self._ocr_engine, "backend", "unknown")
        except Exception as exc:
            state.char_status_last_error = str(exc)
            self.runtime.ui.log(f"❌ Character status OCR unavailable: {exc}")
            self.runtime.ui.set_status(f"Character status OCR unavailable: {exc}", RED)
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
        self.runtime.ui.module_state_changed("char_status", True)
        self.runtime.ui.set_status("Character status watcher active", GREEN)

    def stop(self) -> None:
        state = self.runtime.state
        if not state.char_status_active:
            return
        self.runtime.char_status_stop.set()
        state.char_status_active = False
        self.runtime.ui.module_state_changed("char_status", False)
        self.runtime.ui.set_status("Character status watcher stopped", RED)

    def restart_if_needed(self) -> None:
        self.stop()
        state = self.runtime.state
        if state.char_status_region or all([state.char_status_hp_region, state.char_status_mana_region, state.char_status_cap_region]):
            self.start()

    def _worker(self) -> None:
        state = self.runtime.state
        self.runtime.ui.log("▶ Character status watcher start")
        try:
            with mss.mss() as sct:
                while not self.runtime.char_status_stop.is_set():
                    cycle_started = time.perf_counter()
                    with self.runtime.settings_lock:
                        region = state.char_status_region
                        hp_region = state.char_status_hp_region
                        mana_region = state.char_status_mana_region
                        cap_region = state.char_status_cap_region
                        poll_ms = max(CHAR_STATUS_POLL_MS_MIN, state.char_status_poll_ms)
                        sample_count = max(1, state.char_status_samples)
                        sample_delay_ms = max(0, state.char_status_sample_delay_ms)
                    if not region and not all([hp_region, mana_region, cap_region]):
                        break
                    try:
                        samples = []
                        cycle_perf = {
                            "capture_ms": 0.0,
                            "preprocess_ms": 0.0,
                            "ocr_ms": 0.0,
                            "confidence": 0.0,
                        }
                        sample_confidences: list[float] = []
                        for sample_index in range(sample_count):
                            parsed_sample: dict[str, int | None | str] = {}
                            region_confidences: list[float] = []
                            if region:
                                capture_started = time.perf_counter()
                                frame = self._capture_region(sct, region)
                                cycle_perf["capture_ms"] += (time.perf_counter() - capture_started) * 1000.0
                                extracted, perf = self._extract_values(frame, cache_key="window")
                                parsed_sample.update(extracted)
                                cycle_perf["preprocess_ms"] += perf["preprocess_ms"]
                                cycle_perf["ocr_ms"] += perf["ocr_ms"]
                                region_confidences.extend(perf["confidences"])
                            if all([hp_region, mana_region, cap_region]):
                                capture_started = time.perf_counter()
                                region_frames = {
                                    "hp": self._capture_region(sct, hp_region),
                                    "mana": self._capture_region(sct, mana_region),
                                    "cap": self._capture_region(sct, cap_region),
                                }
                                cycle_perf["capture_ms"] += (time.perf_counter() - capture_started) * 1000.0
                                extracted_regions, perf = self._extract_values_from_regions(region_frames)
                                parsed_sample.update(extracted_regions)
                                cycle_perf["preprocess_ms"] += perf["preprocess_ms"]
                                cycle_perf["ocr_ms"] += perf["ocr_ms"]
                                region_confidences.extend(perf["confidences"])
                            samples.append(parsed_sample)
                            if region_confidences:
                                sample_confidences.append(sum(region_confidences) / len(region_confidences))
                            if sample_index < sample_count - 1:
                                # Convert ms sample delay to seconds for time.sleep() (seconds)
                                time.sleep(sample_delay_ms / 1000.0)
                        parsed = self._aggregate_samples(samples)
                    except Exception as exc:
                        with self.runtime.settings_lock:
                            state.char_status_failures += 1
                            state.char_status_last_error = str(exc)
                        time.sleep(MONITOR_ERROR_RETRY_SLEEP)
                        continue

                    cycle_perf["cycle_ms"] = (time.perf_counter() - cycle_started) * 1000.0
                    cycle_perf["confidence"] = (sum(sample_confidences) / len(sample_confidences)) if sample_confidences else 0.0
                    self._perf_snapshot.update(cycle_perf)

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
                        # Convert ms poll interval to seconds for Event.wait() timeout (seconds)
                        break
        finally:
            state.char_status_active = False
            self.runtime.ui.module_state_changed("char_status", False)
            self.runtime.ui.log("⏹ Character status watcher end")

    @staticmethod
    def _region_to_monitor(region: tuple[int, int, int, int]) -> dict[str, int]:
        return {
            "left": region[0],
            "top": region[1],
            "width": region[2],
            "height": region[3],
            "mon": 1,
        }

    def _capture_region(self, sct, region: tuple[int, int, int, int]):
        return np.array(sct.grab(self._region_to_monitor(region)))[:, :, :3]

    def _frame_signature(self, frame) -> bytes:
        if frame is None or frame.size == 0:
            return b""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        thumb = cv2.resize(gray, (24, 24), interpolation=cv2.INTER_AREA)
        return thumb.tobytes()

    def _get_cached_result(self, cache_key: str, frame):
        signature = self._frame_signature(frame)
        cached = self._frame_cache.get(cache_key)
        if cached and cached[0] == signature:
            self._perf_snapshot["cache_hits"] = int(self._perf_snapshot["cache_hits"]) + 1
            return dict(cached[1])
        self._perf_snapshot["cache_misses"] = int(self._perf_snapshot["cache_misses"]) + 1
        return None

    def _store_cached_result(self, cache_key: str, frame, values: dict[str, int | None | str]) -> None:
        self._frame_cache[cache_key] = (self._frame_signature(frame), dict(values))

    def _extract_values(self, frame, cache_key: str = "window") -> tuple[dict[str, int | None | str], dict[str, float | list[float]]]:
        cached = self._get_cached_result(cache_key, frame)
        if cached is not None:
            return cached, {"preprocess_ms": 0.0, "ocr_ms": 0.0, "confidences": []}

        tasks = {
            "hp": lambda fr: self._ocr_digits(fr, "hp"),
            "mana": lambda fr: self._ocr_digits(fr, "mana"),
        }
        futures = {
            key: self._ocr_pool.submit(func, frame)
            for key, func in tasks.items()
        }
        values: dict[str, int | None | str] = {
            "level": None,
            "hp": None,
            "mana": None,
            "cap": None,
            "food_seconds": None,
            "food_text": "",
        }
        perf = {"preprocess_ms": 0.0, "ocr_ms": 0.0, "confidences": []}
        for key, future in futures.items():
            result = future.result()
            values[key] = result["value"]
            perf["preprocess_ms"] += result["preprocess_ms"]
            perf["ocr_ms"] += result["ocr_ms"]
            if result["confidence"] > 0:
                perf["confidences"].append(result["confidence"])

        context_keys = {"level", "cap", "food_seconds", "food_text"}
        if values.get("hp") is None:
            context_keys.add("hp")
        if values.get("mana") is None:
            context_keys.add("mana")
        contextual = self._extract_contextual_stats(frame, required_keys=context_keys)
        for key, value in contextual["values"].items():
            if key in {"level", "cap", "food_seconds"} and value is not None:
                values[key] = value
            elif key == "food_text" and contextual["values"].get("food_seconds") is not None:
                values[key] = value
            elif key in {"hp", "mana"} and values.get(key) is None and value is not None:
                values[key] = value
        perf["preprocess_ms"] += contextual["preprocess_ms"]
        perf["ocr_ms"] += contextual["ocr_ms"]
        if contextual["confidence"] > 0:
            perf["confidences"].append(contextual["confidence"])

        final_values = values if any(value is not None for value in values.values()) else {}
        if final_values:
            self._store_cached_result(cache_key, frame, final_values)
        return final_values, perf

    def _extract_values_from_regions(self, region_frames: dict[str, object]) -> tuple[dict[str, int | None], dict[str, float | list[float]]]:
        futures = {
            key: self._ocr_pool.submit(self._ocr_cap_region if key == "cap" else self._ocr_digits, frame, key)
            for key, frame in region_frames.items()
        }
        values: dict[str, int | None] = {}
        perf = {"preprocess_ms": 0.0, "ocr_ms": 0.0, "confidences": []}
        for key, future in futures.items():
            result = future.result()
            values[key] = result["value"]
            perf["preprocess_ms"] += result["preprocess_ms"]
            perf["ocr_ms"] += result["ocr_ms"]
            if result["confidence"] > 0:
                perf["confidences"].append(result["confidence"])
        return values if any(value is not None for value in values.values()) else {}, perf

    def _extract_food_from_roi(self, frame) -> dict[str, float | int | str | None]:
        best_value: int | None = None
        best_text = ""
        best_confidence = 0.0
        preprocess_ms = 0.0
        ocr_ms = 0.0
        for box in self.ROI_MAP["food"]:
            crop = self._crop(frame, box)
            if crop.size == 0:
                continue
            variants, prep_elapsed = self._build_variants(crop, key="food", upscale=2)
            preprocess_ms += prep_elapsed
            for image_variant in variants:
                started = time.perf_counter()
                read = self._ocr_engine.recognize(image_variant, psm="7", oem="1", whitelist="0123456789:")
                ocr_ms += (time.perf_counter() - started) * 1000.0
                normalized = re.sub(r"[^0-9:]+", " ", read.text.lower())
                match = re.search(r"(\d{1,2}:\d{2}|\d{1,3})", normalized)
                if not match:
                    continue
                candidate_text = match.group(1)
                candidate_value = CharacterStatusService._parse_food_seconds(candidate_text)
                if candidate_value is None:
                    continue
                best_value = candidate_value
                best_text = candidate_text
                best_confidence = max(best_confidence, read.confidence)
                break
            if best_value is not None:
                break
        return {
            "value": best_value,
            "text": best_text,
            "confidence": best_confidence,
            "preprocess_ms": preprocess_ms,
            "ocr_ms": ocr_ms,
        }

    def _ocr_level(self, frame) -> dict[str, float | int | None]:
        preprocess_ms = 0.0
        ocr_ms = 0.0
        best_value: int | None = None
        best_confidence = 0.0
        for box in self.ROI_MAP["level"]:
            crop = self._crop(frame, box)
            if crop.size == 0:
                continue
            variants, prep_elapsed = self._build_variants(crop, key="level", upscale=2)
            preprocess_ms += prep_elapsed
            for image_variant in variants:
                started = time.perf_counter()
                read = self._ocr_engine.recognize(image_variant, psm="6", oem="1", whitelist="Levellevel0123456789 ")
                ocr_ms += (time.perf_counter() - started) * 1000.0
                normalized = re.sub(r"[^a-z0-9 ]+", " ", read.text.lower())
                match = re.search(r"level\s+(\d+)", normalized)
                if not match:
                    match = re.search(r"\b(\d+)\b", normalized)
                if match:
                    best_value = int(match.group(1))
                    best_confidence = max(best_confidence, read.confidence)
                    break
            if best_value is not None:
                break
        return {
            "value": best_value,
            "confidence": best_confidence,
            "preprocess_ms": preprocess_ms,
            "ocr_ms": ocr_ms,
        }

    def _extract_contextual_stats(self, frame, required_keys: set[str]) -> dict[str, object]:
        variants, preprocess_ms = self._build_variants(frame, key="window_text", upscale=2)
        values: dict[str, int | str | None] = {key: None for key in required_keys}
        if "food_text" in required_keys:
            values["food_text"] = ""
        field_patterns = {
            "level": [r"level\s+(\d+)", r"leve[li]\s+(\d+)"],
            "hp": [r"hit\s*points\s+(\d+)", r"hit\s*point[s]?\s+(\d+)"],
            "mana": [r"mana\s+(\d+)"],
            "cap": [r"capacity\s+(\d+)", r"capacit[yv]\s+(\d+)"],
        }
        best_confidence = 0.0
        ocr_ms = 0.0
        for image_variant in variants:
            ocr_started = time.perf_counter()
            read = self._ocr_engine.recognize(
                image_variant,
                psm="6",
                oem="1",
                whitelist="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :",
            )
            ocr_ms += (time.perf_counter() - ocr_started) * 1000.0
            normalized = re.sub(r"[^a-z0-9:\n ]+", " ", read.text.lower())
            best_confidence = max(best_confidence, read.confidence)
            for key in required_keys:
                if key in {"food_seconds", "food_text"}:
                    continue
                if values[key] is not None:
                    continue
                for pattern in field_patterns[key]:
                    match = re.search(pattern, normalized)
                    if match:
                        values[key] = int(match.group(1))
                        break
            if "food_seconds" in required_keys and values.get("food_seconds") is None:
                match = re.search(r"food\s+(\d{1,2}:\d{2}|\d{1,3})", normalized)
                if match:
                    food_text = match.group(1)
                    food_seconds = CharacterStatusService._parse_food_seconds(food_text)
                    if food_seconds is not None:
                        values["food_seconds"] = food_seconds
                        if "food_text" in values:
                            values["food_text"] = food_text
            if all(value is not None for value in values.values()):
                break
        return {
            "values": values,
            "preprocess_ms": preprocess_ms,
            "ocr_ms": ocr_ms,
            "confidence": best_confidence,
        }

    def _ocr_cap_region(self, crop, key: str) -> dict[str, float | int | None]:
        contextual = self._extract_contextual_stats(crop, required_keys={"cap"})
        cap_value = contextual["values"].get("cap")
        if cap_value is not None:
            return {
                "value": cap_value,
                "confidence": contextual["confidence"],
                "preprocess_ms": contextual["preprocess_ms"],
                "ocr_ms": contextual["ocr_ms"],
            }
        return self._ocr_digits(crop, key)

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
        # Trim history older than 3 minutes — keeps a rolling 180-second window for regen rate calc (seconds)
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
                # Numeric fields use median aggregation to reject OCR outliers
                numeric_values = [v for v in values if isinstance(v, int)]
                if numeric_values:
                    sorted_vals = sorted(numeric_values)
                    mid = len(sorted_vals) // 2  # Median index (integer division)
                    aggregated[key] = sorted_vals[mid]
            elif key == "food_text":
                # For text, most common
                from collections import Counter
                text_values = [v for v in values if isinstance(v, str)]
                if text_values:
                    aggregated[key] = Counter(text_values).most_common(1)[0][0]
        return aggregated

    @staticmethod
    def _parse_food_seconds(text: str) -> int | None:
        normalized = text.strip()
        if not normalized:
            return None
        # Regex for HH:MM format — 1-2 digit hours, exactly 2-digit minutes
        colon_match = re.fullmatch(r"(\d{1,2}):(\d{2})", normalized)
        if colon_match:
            hours = int(colon_match.group(1))
            minutes = int(colon_match.group(2))
            # Minutes must be < 60 (valid time format validation)
            if minutes >= 60:
                return None
            # Convert to total seconds: hours * 3600 + minutes * 60
            parsed_seconds = hours * 3600 + minutes * 60
            if parsed_seconds > CharacterStatusService.MAX_FOOD_SECONDS:
                return None
            return parsed_seconds
        # Regex for plain minute count — 1-3 digit number (e.g., "45" = 45 minutes)
        minute_match = re.fullmatch(r"(\d{1,3})", normalized)
        if minute_match:
            parsed_seconds = int(minute_match.group(1)) * 60
            if parsed_seconds > CharacterStatusService.MAX_FOOD_SECONDS:
                return None
            return parsed_seconds
        if normalized:
            logger.info("[FOOD] rejected_parse=%r", normalized)
        return None

    def _crop(self, frame, box: tuple[int, int, int, int]):
        base_w, base_h = self.BASE_SIZE  # Base resolution (800x600) for coordinate scaling
        frame_h, frame_w = frame.shape[:2]
        x1 = max(0, int(round(box[0] / base_w * frame_w)))  # Left edge from box index 0
        y1 = max(0, int(round(box[1] / base_h * frame_h)))  # Top edge from box index 1
        x2 = min(frame_w, int(round(box[2] / base_w * frame_w)))  # Right edge from box index 2
        y2 = min(frame_h, int(round(box[3] / base_h * frame_h)))  # Bottom edge from box index 3
        return frame[y1:y2, x1:x2]

    def _build_variants(self, crop, *, key: str, upscale: int = 2) -> tuple[list[object], float]:
        started = time.perf_counter()
        if crop is None or crop.size == 0:  # Empty frame check (OpenCV array size = 0)
            return [], 0.0
        enlarged = cv2.resize(crop, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC) if upscale > 1 else crop
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY) if len(enlarged.shape) == 3 else enlarged
        gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            25,
            5,
        )
        variants = [binary, cv2.bitwise_not(binary), adaptive]
        if key in {"hp", "mana", "cap"}:
            kernel = np.ones((2, 2), np.uint8)
            variants.append(cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel))
        return variants, (time.perf_counter() - started) * 1000.0

    def _ocr_digits(self, crop, key: str) -> dict[str, float | int | None]:
        scale = 3 if key == "cap" else 2
        variants, preprocess_ms = self._build_variants(crop, key=key, upscale=scale)
        psm_modes = ["7", "8"] if key in {"hp", "mana"} else ["7", "6"]
        best_value: int | None = None
        best_confidence = 0.0
        ocr_ms = 0.0
        for image_variant in variants:
            for psm in psm_modes:
                started = time.perf_counter()
                read = self._ocr_engine.recognize(image_variant, psm=psm, oem="1", whitelist="0123456789")
                ocr_ms += (time.perf_counter() - started) * 1000.0
                groups = [group for group in re.findall(r"\d+", read.text) if group]
                if not groups:
                    continue
                candidate = max(groups, key=len) if key in {"hp", "mana"} else groups[-1]
                if key in {"hp", "mana"} and len(candidate) < 2:
                    continue
                best_value = int(candidate)
                best_confidence = max(best_confidence, read.confidence)
                return {
                    "value": best_value,
                    "confidence": best_confidence,
                    "preprocess_ms": preprocess_ms,
                    "ocr_ms": ocr_ms,
                }
        return {
            "value": best_value,
            "confidence": best_confidence,
            "preprocess_ms": preprocess_ms,
            "ocr_ms": ocr_ms,
        }
