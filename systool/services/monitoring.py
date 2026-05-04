"""Monitoring, OCR, alarm, and pointer-based services."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

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

from ..runtime import (
    AppRuntime,
    HAS_CV2,
    HAS_MSS,
    HAS_NUMPY,
    HAS_PYGAME,
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
    pytesseract,
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
                logger.debug("Light controller detach failed")
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

class StatPointerService:
    """Shared pointer-backed stat reader with OCR fallback."""

    stat_label = "Stat"
    pointer_address_attr = ""
    source_attr = ""
    value_attr = ""
    fallback_attr = ""
    state_resolved_attr: str | None = None
    local_address_attr = "_resolved_address"
    local_cache_attr = "_cache_time"
    local_ttl_attr = "_CACHE_TTL"
    profile_module = ""
    profile_name = ""

    def __init__(self, runtime: AppRuntime) -> None:
        self.runtime = runtime
        self.controller: LightMemoryController | None = None
        setattr(self, self.local_address_attr, None)
        setattr(self, self.local_cache_attr, 0.0)
        setattr(self, self.local_ttl_attr, 60.0)

    def attach(self) -> tuple[bool, str]:
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

        address = self._resolve_pointer()
        parts = []
        if address is not None:
            self._store_resolved_address(address)
            parts.append(f"{self.stat_label} pointer resolved at 0x{address:X}")
            try:
                value = self.controller.read_double(address)
                with self.runtime.settings_lock:
                    setattr(self.runtime.state, self.value_attr, value)
                parts.append(f"{self.stat_label}={value:.1f}")
            except Exception as exc:
                parts.append(f"{self.stat_label} read failed: {exc}")

        message = " | ".join(parts) if parts else "No pointers resolved"
        return True, f"Attached to {process_name} | {message}"

    def detach(self) -> tuple[bool, str]:
        if self.controller is not None:
            self.controller.detach()
        self.controller = None
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
        ctrl = self.controller
        if ctrl is None:
            return None
        module = __import__(self.profile_module, fromlist=[self.profile_name])
        profile = getattr(module, self.profile_name)
        module_base = ctrl.get_module_base(profile.module_name)
        for chain in profile.pointer_chains:
            try:
                base_candidate = ctrl.resolve_pointer_chain(module_base, chain)
                target_candidate = base_candidate + profile.structure_value_offset
                ctrl.read_double(target_candidate)
                return target_candidate
            except Exception:
                continue
        return None

    def _get_fallback_value(self) -> float | None:
        with self.runtime.settings_lock:
            fallback_value = getattr(self.runtime.state, self.fallback_attr)
        if fallback_value is not None and fallback_value > 0:
            return float(fallback_value)
        return None

    def _get_value(self) -> float | None:
        state = self.runtime.state
        if not self._is_address_valid():
            self._ensure_address_resolved()

        address = getattr(self, self.local_address_attr)
        if address is not None and self.controller is not None:
            try:
                value = self.controller.read_double(address)
                with self.runtime.settings_lock:
                    setattr(state, self.value_attr, value)
                return value
            except Exception:
                logger.debug("Pointer read failed")
        return self._get_fallback_value()

    @staticmethod
    def _find_game_process_name() -> str | None:
        pattern = re.compile(r"^(miracle_(?:dx|gl))(?:-\d+)?\.exe$", re.IGNORECASE)
        for proc in psutil.process_iter(attrs=["name"]):
            name = (proc.info.get("name") or "").strip()
            if pattern.fullmatch(name):
                return name
        return None


class HpService(StatPointerService):
    """HP value reader with pointer-first resolution and OCR fallback."""

    stat_label = "HP"
    pointer_address_attr = "hp_pointer_address_hex"
    source_attr = "hp_source"
    value_attr = "hp_value"
    fallback_attr = "char_status_hp"
    local_address_attr = "_hp_address"
    local_cache_attr = "_hp_cache_time"
    local_ttl_attr = "_HP_CACHE_TTL"
    profile_module = "studiomemuer_hp_module.hp_profile"
    profile_name = "DEFAULT_HP_PROFILE"

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
            from studiomemuer_light_module.light_profile import DEFAULT_PROFILE as LIGHT_PROFILE

            light_address = self.controller.resolve_light_address(
                module_name=LIGHT_PROFILE.module_name,
                pointer_chains=LIGHT_PROFILE.pointer_chains,
                structure_value_offset=LIGHT_PROFILE.structure_value_offset,
                signature_pattern=LIGHT_PROFILE.signature_pattern,
                signature_offset_to_base=LIGHT_PROFILE.signature_offset_to_base,
            )
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
        state = self.runtime.state
        hp_val = None
        mp_val = None
        cap_val = None

        if self._hp_address is not None and self.controller is not None:
            try:
                hp_val = self.controller.read_double(self._hp_address)
            except Exception:
                logger.debug("HP pointer read failed")

        mp_addr = getattr(state, "_mp_resolved_addr", None)
        if mp_addr is not None and self.controller is not None:
            try:
                mp_val = self.controller.read_double(mp_addr)
            except Exception:
                logger.debug("MP pointer read failed")

        cap_addr = getattr(state, "_cap_resolved_addr", None)
        if cap_addr is not None and self.controller is not None:
            try:
                cap_val = self.controller.read_double(cap_addr)
            except Exception:
                logger.debug("Cap pointer read failed")

        with self.runtime.settings_lock:
            if hp_val is not None:
                state.hp_value = hp_val
            if mp_val is not None:
                state.mp_value = mp_val
            if cap_val is not None:
                state.cap_value = cap_val

        return (hp_val, mp_val, cap_val)


class MpService(StatPointerService):
    """MP (Mana) value reader with pointer-first resolution and OCR fallback."""

    stat_label = "MP"
    pointer_address_attr = "mp_pointer_address_hex"
    source_attr = "mp_source"
    value_attr = "mp_value"
    fallback_attr = "char_status_mana"
    state_resolved_attr = "_mp_resolved_addr"
    local_address_attr = "_mp_address"
    local_cache_attr = "_mp_cache_time"
    local_ttl_attr = "_MP_CACHE_TTL"
    profile_module = "studiomemuer_mp_module.mp_profile"
    profile_name = "DEFAULT_MP_PROFILE"

    def get_mp(self) -> float | None:
        return self._get_value()


class CapService(StatPointerService):
    """Cap value reader with pointer-first resolution and OCR fallback."""

    stat_label = "Cap"
    pointer_address_attr = "cap_pointer_address_hex"
    source_attr = "cap_source"
    value_attr = "cap_value"
    fallback_attr = "char_status_cap"
    state_resolved_attr = "_cap_resolved_addr"
    local_address_attr = "_cap_address"
    local_cache_attr = "_cap_cache_time"
    local_ttl_attr = "_CAP_CACHE_TTL"
    profile_module = "studiomemuer_cap_module.cap_profile"
    profile_name = "DEFAULT_CAP_PROFILE"

    def get_cap(self) -> float | None:
        return self._get_value()

    def get_cap_peak(self) -> int:
        with self.runtime.settings_lock:
            return self.runtime.state.char_status_cap_peak


class AlarmService:
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
        self.runtime.state.alarm_active = False
        self.runtime.ui.module_state_changed("alarm", False)
        self.runtime.ui.log("⏹ Screen watch end")

class CharacterStatusService:
    # Maximum allowed food timer value in seconds (1 hour). Values above this are rejected as unrealistic OCR artifacts.
    MAX_FOOD_SECONDS = 3600

    # Base dimensions of the full character status window in pixels (width, height)
    BASE_SIZE = (170, 203)
    # ROI (Region of Interest) coordinates for stat extraction — each tuple is (left, top, right, bottom)
    # Coordinates are relative to BASE_SIZE and scaled dynamically per actual frame size.
    ROI_MAP = {
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
                    with self.runtime.settings_lock:
                        region = state.char_status_region
                        hp_region = state.char_status_hp_region
                        mana_region = state.char_status_mana_region
                        cap_region = state.char_status_cap_region
                        poll_ms = max(CHAR_STATUS_POLL_MS_MIN, state.char_status_poll_ms)
                    if not region and not all([hp_region, mana_region, cap_region]):
                        break
                    try:
                        samples = []
                        for _ in range(state.char_status_samples):
                            parsed_sample: dict[str, int | None] = {}
                            if region:
                                monitor = {
                                    "left": region[0],  # x-coordinate (index 0)
                                    "top": region[1],   # y-coordinate (index 1)
                                    "width": region[2], # width (index 2)
                                    "height": region[3],# height (index 3)
                                    "mon": 1,           # Monitor index: primary display
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
                                # Convert ms sample delay to seconds for time.sleep() (seconds)
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
                        time.sleep(MONITOR_ERROR_RETRY_SLEEP)
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
                        # Convert ms poll interval to seconds for Event.wait() timeout (seconds)
                        break
        finally:
            state.char_status_active = False
            self.runtime.ui.module_state_changed("char_status", False)
            self.runtime.ui.log("⏹ Character status watcher end")

    def _extract_food_from_roi(self, frame) -> dict[str, int | None | str]:
        """Extract food timer from a cropped ROI region using OCR + regex.

        Replaces the previous full-frame regex approach to prevent false positives
        when unrelated UI text contains 'food' followed by digits.
        """
        values: dict[str, int | None | str] = {
            "food_seconds": None,
            "food_text": "",
        }
        for box in self.ROI_MAP["food"]:
            crop = self._crop(frame, box)
            if crop.size == 0:
                continue
            # Enlarge crop 3x to improve OCR accuracy on small text regions
            enlarged = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
            # Gaussian blur with 3x3 kernel (odd dimensions required for OpenCV filters)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            variants = []
            # OTSU threshold: auto-computes optimal binarization; output max value is 255
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(binary)
            variants.append(cv2.bitwise_not(binary))
            # Adaptive threshold: 255=max output, 31=block size (odd), 7=C constant subtracted from local mean
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7)
            variants.append(adaptive)
            variants.append(cv2.bitwise_not(adaptive))
            for image_variant in variants:
                text = pytesseract.image_to_string(image_variant, config="--psm 6")  # PSM 6: assume uniform block of text
                normalized = re.sub(r"[^a-z0-9:\n ]+", " ", text.lower())
                match = re.search(r"food\s+(\d{1,2}:\d{2}|\d{1,3})", normalized)
                if match:
                    food_text = match.group(1)
                    values["food_text"] = food_text
                    values["food_seconds"] = CharacterStatusService._parse_food_seconds(food_text)
                    break
            if values["food_seconds"] is not None:
                break
        return values

    def _extract_values(self, frame) -> dict[str, int | None]:
        values: dict[str, int | None] = self._extract_values_from_text(frame)
        for key, boxes in self.ROI_MAP.items():
            if key == "food":
                # Food is handled separately via ROI crop + regex (not _ocr_digits)
                continue
            if values.get(key) is not None:
                continue
            for box in boxes:
                crop = self._crop(frame, box)
                value = self._ocr_digits(crop, key)
                if value is not None:
                    values[key] = value
                    break
        # Extract food from ROI (separate path — cropped region + regex)
        food_values = self._extract_food_from_roi(frame)
        # Only distribute food fields when they are consistent together.
        # _parse_food_seconds can return None even when OCR succeeds,
        # so we must not set food_text if food_seconds is None (and vice versa).
        if food_values.get("food_seconds") is not None:
            values["food_seconds"] = food_values["food_seconds"]
            values["food_text"] = food_values["food_text"]
        return values if any(value is not None for value in values.values()) else {}

    def _extract_values_from_regions(self, sct, regions: dict[str, tuple[int, int, int, int]]) -> dict[str, int | None]:
        values: dict[str, int | None] = {}
        for key, region in regions.items():
            monitor = {
                "left": region[0],  # x-coordinate (index 0)
                "top": region[1],   # y-coordinate (index 1)
                "width": region[2], # width (index 2)
                "height": region[3],# height (index 3)
                "mon": 1,           # Monitor index: primary display
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

    def _extract_values_from_text(self, frame) -> dict[str, int | None | str]:
        values: dict[str, int | None] = {
            "level": None,
            "hp": None,
            "mana": None,
            "cap": None,
        }
        # Enlarge frame 3x to improve OCR accuracy on small text regions
        enlarged = cv2.resize(frame, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        # Gaussian blur with 3x3 kernel (odd dimensions required for OpenCV filters)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        variants = []
        # OTSU threshold: auto-computes optimal binarization; output max value is 255
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(binary)
        variants.append(cv2.bitwise_not(binary))
        # Adaptive threshold: 255=max output, 31=block size (odd), 7=C constant subtracted from local mean
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7)
        variants.append(adaptive)
        variants.append(cv2.bitwise_not(adaptive))
        # Regex patterns for extracting stat values from OCR text output (field → list of patterns)
        field_patterns = {
            "level": [r"level\s+(\d+)", r"leve[li]\s+(\d+)"],  # English or localized "level/levele/l evel"
            "hp": [r"hit\s*points\s+(\d+)", r"hit\s*point[s]?\s+(\d+)"],  # "hit points" with optional plural
            "mana": [r"mana\s+(\d+)"],  # Simple "mana <number>" pattern
            "cap": [r"capacity\s+(\d+)", r"capacit[yv]\s+(\d+)"],  # "capacity/capacity" variants
        }
        for image_variant in variants:
            text = pytesseract.image_to_string(image_variant, config="--psm 6")  # PSM 6: assume uniform block of text
            normalized = re.sub(r"[^a-z0-9:\n ]+", " ", text.lower())
            for key, patterns in field_patterns.items():
                if values[key] is not None:
                    continue
                for pattern in patterns:
                    match = re.search(pattern, normalized)
                    if not match:
                        continue
                    values[key] = int(match.group(1))
                    break
        return values

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
        return None

    def _crop(self, frame, box: tuple[int, int, int, int]):
        base_w, base_h = self.BASE_SIZE  # Base resolution (800x600) for coordinate scaling
        frame_h, frame_w = frame.shape[:2]
        x1 = max(0, int(round(box[0] / base_w * frame_w)))  # Left edge from box index 0
        y1 = max(0, int(round(box[1] / base_h * frame_h)))  # Top edge from box index 1
        x2 = min(frame_w, int(round(box[2] / base_w * frame_w)))  # Right edge from box index 2
        y2 = min(frame_h, int(round(box[3] / base_h * frame_h)))  # Bottom edge from box index 3
        return frame[y1:y2, x1:x2]

    @staticmethod
    def _ocr_digits(crop, key: str) -> int | None:
        if crop is None or crop.size == 0:  # Empty frame check (OpenCV array size = 0)
            return None
        # Cap digits are smaller — use 7x scale; HP/Mana use 6x scale
        scale = 7 if key == "cap" else 6
        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        # Gaussian blur with 3x3 kernel (odd dimensions required for OpenCV filters)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        variants = []
        # OTSU threshold: auto-computes optimal binarization; output max value is 255
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(binary)
        variants.append(cv2.bitwise_not(binary))
        # Adaptive threshold: 255=max output, 31=block size (odd), 7=C constant subtracted from local mean
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
        # Morphology closing kernel: 2x2 to connect nearby pixel fragments (odd not required for MORPH_CLOSE)
        kernel = np.ones((2, 2), np.uint8)
        variants.append(cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel))
        # HP/Mana use PSM 7+8 (single column); Cap adds PSM 6 (uniform digits) for broader coverage
        psm_modes = ["7", "8"] if key in {"hp", "mana"} else ["7", "6", "8"]
        best_digits = ""
        for image_variant in variants:
            for psm in psm_modes:
                config = f"--psm {psm} -c tessedit_char_whitelist=0123456789"
                text = pytesseract.image_to_string(image_variant, config=config)
                groups = [group for group in re.findall(r"\d+", text) if group]
                # HP/Mana require ≥2 digits (single-digit is noise); Cap accepts ≥1 digit
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
