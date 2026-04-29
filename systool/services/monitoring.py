"""Monitoring, OCR, alarm, and pointer-based services."""

from __future__ import annotations

import logging
import os
import re
import threading
import time

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
)
from ..theme import GREEN, ORANGE, RED, TEAL
from ..constants import LIGHT_FREEZE_MIN_INTERVAL_MS, MIN_POLL_MS, MONITOR_POLL_SLEEP, MONITOR_ERROR_RETRY_SLEEP

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

    def play_alarm(self) -> None:
        path = self.runtime.state.alarm_mp3
        if not path or not os.path.exists(path):
            self.runtime.ui.log("⚠️  Alert sound file not found")
            return

        def play() -> None:
            try:
                if HAS_PYGAME:
                    pygame.mixer.music.set_volume(1.0)
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
                        poll_ms = max(MIN_POLL_MS, state.char_status_poll_ms)
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
                        break
        finally:
            state.char_status_active = False
            self.runtime.ui.module_state_changed("char_status", False)
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
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if minutes >= 60:
            return None
        return hours * 3600 + minutes * 60

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
