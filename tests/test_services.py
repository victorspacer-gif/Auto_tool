"""Tests for service-layer logic: HumanMouse, SafeKeyboardSession, PauseController, ExecutionGate."""

import math
import random
import sys
import threading
import time
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

# Mock pynput only for tests that need mocked mouse/keyboard objects.
with patch("systool.runtime.pynput_kb"), \
     patch("systool.runtime.pynput_mouse"):
    from systool.services import CharacterStatusService, HumanMouse, RightClickService, SafeKeyboardSession
    from systool.services import input_services
    from systool.services import monitoring as monitoring_module
    from systool.services.monitoring import AlarmService, HpService, LightControlService, MpService
    from systool.runtime import AppRuntime

# Skip HotkeyServiceKeyMapping tests if pynput is not available (Linux CI).
try:
    import pynput.keyboard  # noqa: F401
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False


class TestHumanMouseJitter:
    """Test the jitter method adds randomness within bounds."""

    def test_jitter_same_position(self):
        """Jitter at (0, 0) should stay near origin."""
        result = HumanMouse.jitter((0, 0), 5)
        assert -5 <= result[0] <= 5
        assert -5 <= result[1] <= 5

    def test_jitter_offset_position(self):
        """Jitter at (100, 200) should stay within bounds."""
        result = HumanMouse.jitter((100, 200), 10)
        assert 90 <= result[0] <= 110
        assert 190 <= result[1] <= 210

    def test_jitter_zero_amount(self):
        """Jitter with amount=0 should return exact position."""
        result = HumanMouse.jitter((50, 75), 0)
        assert result == (50, 75)

    def test_jitter_returns_tuple(self):
        """Result must be a tuple of two ints."""
        result = HumanMouse.jitter((100, 200), 5)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_jitter_is_random(self):
        """Multiple calls should produce different results."""
        results = [HumanMouse.jitter((50, 50), 10) for _ in range(20)]
        unique = set(results)
        assert len(unique) > 1, "Jitter should produce varied results"


class TestHumanMouseMove:
    class _FakeMouse:
        def __init__(self, position=(0, 0)):
            self.position = position

    @staticmethod
    def _straight_curve(mouse, start, end, duration, **_kwargs):
        mouse.position = end

    def test_move_disables_target_error_by_default(self):
        mouse = self._FakeMouse()

        with patch("systool.services.input_services.time.sleep", return_value=None), \
             patch("systool.services.input_services._curve_move", side_effect=self._straight_curve), \
             patch("systool.services.input_services._apply_target_error") as apply_target_error:
            HumanMouse.move(mouse, (25, 30), duration=0.1)

        apply_target_error.assert_not_called()
        assert mouse.position == (25, 30)

    def test_move_uses_target_error_when_enabled(self):
        mouse = self._FakeMouse()

        with patch("systool.services.input_services.time.sleep", return_value=None), \
             patch("systool.services.input_services._curve_move", side_effect=self._straight_curve), \
             patch(
                 "systool.services.input_services._apply_target_error",
                 return_value=(27, 33, "overshoot"),
             ) as apply_target_error:
            HumanMouse.move(mouse, (25, 30), duration=0.1, target_error_enabled=True)

        apply_target_error.assert_called_once()
        assert mouse.position == (25, 30)

    def test_apply_target_error_prefers_none_for_short_moves(self):
        with patch("systool.services.input_services.random.random", return_value=0.2):
            tx, ty, error_type = input_services._apply_target_error(0, 0, 20, 20, distance=10)
        assert (tx, ty, error_type) == (20, 20, "none")

    def test_curve_move_finishes_on_exact_target(self):
        mouse = self._FakeMouse()
        with patch("systool.services.input_services.time.sleep", return_value=None):
            input_services._curve_move(
                mouse,
                start=(0, 0),
                end=(25, 30),
                duration=0.1,
                noise_scale=0.0,
                smooth=True,
                settle_mode=True,
            )
        assert mouse.position == (25, 30)


class TestAlarmAudioPath:
    def test_resolve_alarm_audio_path_normalizes_relative_path(self):
        path = AlarmService._resolve_alarm_audio_path("alerts/test.mp3")
        assert path.endswith("alerts\\test.mp3") or path.endswith("alerts/test.mp3")


class TestLightControlReset:
    @dataclass
    class _PatchResult:
        address: int
        old_value: int
        new_value: int

    @dataclass
    class _LightPatchResult:
        color: object
        intensity: object

    class _FakeLightController:
        def __init__(self, color_value=90, intensity_value=4):
            self.memory = {
                0x1000: color_value,
                0x1001: intensity_value,
            }

        def write_light_pair(self, color_address, color_value, intensity_value):
            intensity_address = color_address + 1
            old_color = self.memory[color_address]
            old_intensity = self.memory[intensity_address]
            self.memory[color_address] = color_value
            self.memory[intensity_address] = intensity_value
            return TestLightControlReset._LightPatchResult(
                color=TestLightControlReset._PatchResult(color_address, old_color, color_value),
                intensity=TestLightControlReset._PatchResult(intensity_address, old_intensity, intensity_value),
            )

    def test_reset_restores_first_game_values_after_multiple_client_applies(self):
        runtime = AppRuntime()
        runtime.state.light_direct_address_hex = "1000"
        service = LightControlService(runtime)
        service.controller = self._FakeLightController(color_value=90, intensity_value=4)

        runtime.state.light_custom_color_value = 10
        runtime.state.light_custom_intensity_value = 20
        ok, _message = service.apply_custom()
        assert ok is True

        runtime.state.light_custom_color_value = 30
        runtime.state.light_custom_intensity_value = 40
        ok, _message = service.apply_custom()
        assert ok is True

        assert runtime.state.light_original_color_value == 90
        assert runtime.state.light_original_intensity_value == 4

        ok, _message = service.reset_original()
        assert ok is True
        assert service.controller.memory[0x1000] == 90
        assert service.controller.memory[0x1001] == 4


class TestSafeKeyboardSession:
    """Test SafeKeyboardSession stack-based key tracking."""

    def test_press_adds_to_stack(self):
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        assert "a" in session._pressed

    def test_release_removes_key(self):
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.release("a")
        assert "a" not in session._pressed

    def test_release_calls_keyboard_release(self):
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.release("a")
        mock_keyboard.release.assert_called_once_with("a")

    def test_press_multiple_keys(self):
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.press("b")
        assert "a" in session._pressed
        assert "b" in session._pressed

    def test_release_all_clears_stack(self):
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.press("b")
        session.release_all()
        assert session._pressed == []


class TestFoodTimerParsing:
    def test_parse_food_timer_h_mm(self):
        # "1:05" (3900s) exceeds MAX_FOOD_SECONDS (2400), so it's rejected
        assert CharacterStatusService._parse_food_seconds("1:05") is None
        # Valid HH:MM within cap — 40 min boundary
        assert CharacterStatusService._parse_food_seconds("0:40") == 2400

    def test_parse_food_timer_rejects_over_cap(self):
        assert CharacterStatusService._parse_food_seconds("999") is None
        assert CharacterStatusService._parse_food_seconds("1:01") is None
        # Just above cap — rejected
        assert CharacterStatusService._parse_food_seconds("0:45") is None

    def test_food_mode_decision_blocks_when_food_missing(self):
        allowed, message = RightClickService._food_mode_decision("", None, 10)
        assert allowed is False
        assert "decision=blocked" in message

    def test_food_mode_decision_allows_when_threshold_met(self):
        # With <= logic: allowed when remaining time drops to or below threshold (time to eat)
        # food_seconds=5*60=300, threshold=10min=600s → 300 <= 600 → allowed
        allowed, message = RightClickService._food_mode_decision("5", 5 * 60, 10)
        assert allowed is True
        assert "decision=allowed" in message

    def test_food_threshold_requires_available_timer(self):
        assert RightClickService.food_timer_meets_threshold(None, 10) is False

    def test_food_threshold_uses_minutes(self):
        # <= logic: True when remaining time <= threshold (time to eat)
        assert RightClickService.food_timer_meets_threshold(5 * 60, 10) is True     # 300s < 600s → allowed
        assert RightClickService.food_timer_meets_threshold(9 * 60, 10) is True      # 540s < 600s → allowed
        assert RightClickService.food_timer_meets_threshold(15 * 60, 10) is False    # 900s > 600s → blocked (still full)

    def test_food_mode_decision_with_hysteresis_restart_blocked(self):
        """When restart threshold is set and food_seconds exceeds it, eating should be blocked."""
        # X=15min=900s, random_lower_bound=200s → restart_threshold=700s (11m 40s)
        restart_threshold = 700
        allowed, message = RightClickService._food_mode_decision(
            "13:00", 13 * 60, 15, restart_threshold_seconds=restart_threshold
        )
        assert allowed is False  # 780s > 700s → blocked
        assert "restart_threshold=700s" in message
        assert "decision=blocked" in message

    def test_food_mode_decision_with_hysteresis_restart_allowed(self):
        """When restart threshold is set and food_seconds drops below it, eating should be allowed."""
        # X=15min=900s, random_lower_bound=200s → restart_threshold=700s (11m 40s)
        restart_threshold = 700
        allowed, message = RightClickService._food_mode_decision(
            "10:00", 10 * 60, 15, restart_threshold_seconds=restart_threshold
        )
        assert allowed is True   # 600s <= 700s → allowed
        assert "restart_threshold=700s" in message
        assert "decision=allowed" in message

    def test_food_mode_decision_hysteresis_uses_restart_not_fixed(self):
        """Hysteresis restart threshold takes precedence over the fixed threshold."""
        # Fixed threshold = 10min = 600s, but restart_threshold = 500s (lower)
        # food_seconds = 550s: should be blocked because it exceeds restart threshold.
        allowed, message = RightClickService._food_mode_decision(
            "9:10", 550, 10, restart_threshold_seconds=500
        )
        assert allowed is False  # 550 > 500 → blocked (even though 550 < 600 fixed threshold)

    def test_food_mode_decision_hysteresis_fallback_to_fixed(self):
        """When restart_threshold_seconds is None, falls back to fixed threshold."""
        allowed, message = RightClickService._food_mode_decision(
            "5:00", 300, 10, restart_threshold_seconds=None
        )
        assert allowed is True   # 300 <= 600 → allowed
        assert "restart_threshold=" not in message  # No hysteresis info in message

    def test_release_all_calls_keyboard_release_for_each(self):
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.press("b")
        session.release_all()
        # release_all pops in reverse order and calls release on each
        assert mock_keyboard.release.call_count == 2


class TestCharacterStatusPerf:
    def test_cached_result_reuses_previous_values(self):
        service = CharacterStatusService(runtime=MagicMock())
        frame = MagicMock()

        with patch.object(service, "_frame_signature", return_value=b"same"):
            service._store_cached_result("window", frame, {"hp": 123})
            cached = service._get_cached_result("window", frame)

        assert cached == {"hp": 123}
        assert service._perf_snapshot["cache_hits"] == 1

    def test_extract_values_returns_cached_path_without_ocr_work(self):
        service = CharacterStatusService(runtime=MagicMock())
        frame = MagicMock()

        with patch.object(service, "_frame_signature", return_value=b"same"):
            service._store_cached_result("window", frame, {"mana": 45})
            values, perf = service._extract_values(frame, cache_key="window")

        assert values == {"mana": 45}
        assert perf["preprocess_ms"] == 0.0
        assert perf["ocr_ms"] == 0.0

    def test_perf_summary_reports_backend_and_cycle(self):
        service = CharacterStatusService(runtime=MagicMock())
        service._perf_snapshot.update({
            "backend": "tesserocr",
            "cycle_ms": 123.4,
            "capture_ms": 10.0,
            "preprocess_ms": 15.0,
            "ocr_ms": 20.0,
            "cache_hits": 3,
            "cache_misses": 1,
            "confidence": 0.87,
        })

        summary = service.get_perf_summary()

        assert "backend=tesserocr" in summary
        assert "cycle=123.4ms" in summary
        assert "cache=3/4" in summary

    def test_release_lifo_order(self):
        """release_all should pop keys in LIFO (last-in-first-out) order."""
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.press("b")
        session.press("c")
        session.release_all()
        # Should release c, b, a in that order (LIFO)
        calls = [call.args[0] for call in mock_keyboard.release.call_args_list]
        assert calls == ["c", "b", "a"]

    def test_release_specific_key_removes_only_that_key(self):
        """release('a') should only remove 'a', not other keys."""
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.press("b")
        session.release("a")
        assert "a" not in session._pressed
        assert "b" in session._pressed

    def test_release_nonexistent_key_does_not_crash(self):
        """Releasing a key that isn't pressed should not crash."""
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        # Try to release 'b' which was never pressed
        session.release("b")
        assert "a" in session._pressed

    def test_tap_presses_and_releases(self):
        """tap should press, sleep, then release."""
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.tap("a", hold_seconds=0.01)
        assert "a" not in session._pressed

    def test_tap_calls_press_and_release(self):
        """tap should call both press and release."""
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        with patch("time.sleep", return_value=0):
            session.tap("a")
        mock_keyboard.press.assert_called_once_with("a")
        mock_keyboard.release.assert_called_once_with("a")

    def test_release_all_handles_exceptions(self):
        """release_all should not crash if keyboard.release raises."""
        mock_keyboard = MagicMock()
        mock_keyboard.release.side_effect = Exception("boom")
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        # Should not raise
        session.release_all()
        assert session._pressed == []


class TestPauseController:
    """Test PauseController toggle and wait behavior."""

    def test_initial_state_paused(self):
        controller = type("FakeUI", (), {"log": lambda *a: None, "set_pause_label": lambda *a: None})()
        from systool.runtime import PauseController
        pause = PauseController(controller)
        assert pause.paused
        assert not pause._event.is_set()

    def test_toggle_changes_state(self):
        """Toggle should flip paused state."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController
        controller = PauseController(ui, start_paused=False)
        assert not controller.paused
        controller.toggle()
        assert controller.paused
        controller.toggle()
        assert not controller.paused

    def test_toggle_clears_event_when_paused(self):
        """When paused, the internal event should be cleared."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController
        controller = PauseController(ui, start_paused=False)
        assert controller._event.is_set()
        controller.toggle()
        assert not controller._event.is_set()

    def test_toggle_sets_event_when_resumed(self):
        """When resumed, the internal event should be set."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController
        controller = PauseController(ui)
        assert not controller._event.is_set()
        controller.toggle()  # resume
        assert controller._event.is_set()

    def test_wait_returns_when_not_paused(self):
        """wait should return immediately when not paused."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController
        controller = PauseController(ui, start_paused=False)
        start = time.monotonic()
        controller.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # should be nearly instant

    def test_wait_blocks_when_paused(self):
        """wait should block when paused and unblock on resume."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController
        controller = PauseController(ui)

        def resume_after_delay():
            time.sleep(0.15)
            controller.toggle()  # resume

        thread = threading.Thread(target=resume_after_delay, daemon=True)
        thread.start()
        start = time.monotonic()
        controller.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.12  # should have waited at least a bit


class TestPointerFallbackGuard:
    def test_hp_invalid_pointer_falls_back_to_ocr_and_stays_disabled(self):
        runtime = AppRuntime()
        runtime.ui.log = MagicMock()
        runtime.state.char_status_hp = 321

        service = HpService(runtime)
        service.controller = MagicMock()
        service.pointer_reader = MagicMock()
        service.pointer_reader.read_hp.return_value = -50
        service._hp_address = 0x123456
        service._hp_cache_time = time.time()
        runtime.state.hp_pointer_address_hex = "123456"
        runtime.state.hp_source = "pointer"

        value = service.get_hp()

        assert value == 321
        assert isinstance(value, int)
        assert runtime.state.hp_value == 321
        assert isinstance(runtime.state.hp_value, int)
        assert runtime.state.hp_source == "ocr"
        assert runtime.state._hp_pointer_invalid is True
        assert runtime.state.hp_pointer_address_hex == ""
        assert service._hp_address is None
        service.pointer_reader.read_hp.assert_called_once()

        service.pointer_reader.read_hp.reset_mock()
        second_value = service.get_hp()

        assert second_value == 321
        assert isinstance(second_value, int)
        service.pointer_reader.read_hp.assert_not_called()

    def test_hp_fractional_pointer_falls_back_to_ocr_and_stays_disabled(self):
        runtime = AppRuntime()
        runtime.ui.log = MagicMock()
        runtime.state.char_status_hp = 321

        service = HpService(runtime)
        service.controller = MagicMock()
        service.pointer_reader = MagicMock()
        service.pointer_reader.read_hp.return_value = 5.6823
        service._hp_address = 0x123456
        service._hp_cache_time = time.time()
        runtime.state.hp_pointer_address_hex = "123456"
        runtime.state.hp_source = "pointer"

        value = service.get_hp()

        assert value == 321
        assert isinstance(value, int)
        assert runtime.state.hp_value == 321
        assert isinstance(runtime.state.hp_value, int)
        assert runtime.state.hp_source == "ocr"
        assert runtime.state._hp_pointer_invalid is True
        assert runtime.state.hp_pointer_address_hex == ""

    def test_integer_float_pointer_is_kept_as_int(self):
        runtime = AppRuntime()
        runtime.ui.log = MagicMock()

        service = HpService(runtime)

        assert service._validate_pointer_value(500.0) == 500

    def test_batch_read_invalidates_mp_pointer_and_shared_state_forces_ocr(self):
        runtime = AppRuntime()
        runtime.ui.log = MagicMock()
        runtime.state.char_status_hp = 500
        runtime.state.char_status_mana = 180
        runtime.state._mp_resolved_addr = 0xABCDEF

        hp_service = HpService(runtime)
        mp_service = MpService(runtime)
        runtime.hp_service = hp_service
        runtime.mp_service = mp_service

        hp_service.pointer_reader = MagicMock()
        hp_service.pointer_reader.read_hp.return_value = 500
        hp_service.pointer_reader.read_mp.return_value = float("inf")
        mp_service.pointer_reader = hp_service.pointer_reader

        hp_value, mp_value, cap_value = hp_service._read_all_stats()

        assert hp_value == 500
        assert isinstance(hp_value, int)
        assert mp_value == 180
        assert isinstance(mp_value, int)
        assert cap_value is None
        assert runtime.state.mp_source == "ocr"
        assert runtime.state.mp_value == 180
        assert isinstance(runtime.state.mp_value, int)
        assert runtime.state._mp_pointer_invalid is True
        assert runtime.state._mp_resolved_addr is None
        assert runtime.state.mp_pointer_address_hex == ""

        mp_service.controller = MagicMock()
        mp_service._mp_address = 0xABCDEF
        mp_service._mp_cache_time = time.time()
        mp_service.pointer_reader.read_mp.reset_mock()

        direct_value = mp_service.get_mp()

        assert direct_value == 180
        assert isinstance(direct_value, int)
        mp_service.pointer_reader.read_mp.assert_not_called()

    def test_batch_read_invalidates_fractional_mp_pointer(self):
        runtime = AppRuntime()
        runtime.ui.log = MagicMock()
        runtime.state.char_status_hp = 500
        runtime.state.char_status_mana = 180
        runtime.state._mp_resolved_addr = 0xABCDEF

        hp_service = HpService(runtime)
        mp_service = MpService(runtime)
        runtime.hp_service = hp_service
        runtime.mp_service = mp_service

        hp_service.pointer_reader = MagicMock()
        hp_service.pointer_reader.read_hp.return_value = 500
        hp_service.pointer_reader.read_mp.return_value = 5.6823
        mp_service.pointer_reader = hp_service.pointer_reader

        hp_value, mp_value, cap_value = hp_service._read_all_stats()

        assert hp_value == 500
        assert isinstance(hp_value, int)
        assert mp_value == 180
        assert isinstance(mp_value, int)
        assert cap_value is None
        assert runtime.state.mp_source == "ocr"
        assert runtime.state.mp_value == 180
        assert isinstance(runtime.state.mp_value, int)
        assert runtime.state._mp_pointer_invalid is True
        assert runtime.state._mp_resolved_addr is None
        assert runtime.state.mp_pointer_address_hex == ""


class TestAlarmEnhancements:
    def test_play_system_sound_prefers_winsound_alias(self):
        runtime = AppRuntime()
        service = AlarmService(runtime)

        with patch.object(monitoring_module, "HAS_WINSOUND", True), \
             patch.object(monitoring_module, "winsound") as winsound_mock:
            service._play_system_sound()

        winsound_mock.PlaySound.assert_called_once_with(
            "SystemAsterisk",
            winsound_mock.SND_ALIAS | winsound_mock.SND_ASYNC | winsound_mock.SND_NODEFAULT,
        )

    def test_flash_game_window_uses_attached_window_handle(self):
        runtime = AppRuntime()
        service = AlarmService(runtime)

        flash_func = MagicMock()
        fake_user32 = MagicMock(FlashWindowEx=flash_func)

        with patch.object(monitoring_module, "HAS_WIN32", True), \
             patch.object(monitoring_module, "HAS_CTYPES", True), \
             patch.object(monitoring_module, "win32gui", object()), \
             patch.object(monitoring_module, "win32con", object()), \
             patch.object(service, "_resolve_attached_game_window", return_value=12345), \
             patch.object(monitoring_module.ctypes, "windll", MagicMock(user32=fake_user32), create=True):
            service._flash_game_window()

        assert flash_func.call_count == 1

    def test_notify_logout_success_uses_popup_timeout_and_path(self):
        runtime = AppRuntime()
        runtime.ui.show_logout_popup = MagicMock()
        runtime.state.alarm.battle_logout_popup_timeout_sec = 9
        service = AlarmService(runtime)

        service._notify_logout_success("C:/tmp/logout.png")

        runtime.ui.show_logout_popup.assert_called_once()
        args = runtime.ui.show_logout_popup.call_args.args
        assert args[0] == "Battle Logout Executed"
        assert "logout was executed successfully" in args[1]
        assert "C:/tmp/logout.png" in args[1]
        assert args[2] == 9


class TestExecutionGate:
    """Test ExecutionQueue fairness and queue management."""

    def test_acquire_returns_true_when_idle(self):
        """First acquire should return True immediately."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController, ExecutionGate
        pause = PauseController(ui, start_paused=False)
        gate = ExecutionGate(pause)
        stop_evt = threading.Event()
        result = gate.acquire(stop_evt, max_wait=0.1, module_id="test")
        assert result is True

    def test_release_clears_owner(self):
        """release should clear the owner."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController, ExecutionGate
        pause = PauseController(ui, start_paused=False)
        gate = ExecutionGate(pause)
        stop_evt = threading.Event()
        gate.acquire(stop_evt, max_wait=0.1, module_id="test")
        gate.release()
        assert gate._owner is None

    def test_queue_prunes_expired(self):
        """Expired requests should be pruned from the queue."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController, ExecutionGate, CursorRequest
        pause = PauseController(ui, start_paused=False)
        gate = ExecutionGate(pause)

        # Manually add an expired request
        with gate._condition:
            request = CursorRequest(expires_at=time.monotonic() - 1.0, module_id="test")
            gate._queue_request_locked(request)
            gate._prune_expired_locked()
            assert not any(r.token is request.token for r in gate._queue)

    def test_fairness_rebalance(self):
        """Should rebalance queue to prevent same-module dominance."""
        ui = MagicMock()
        ui.log = MagicMock()
        ui.set_pause_label = MagicMock()
        from systool.runtime import PauseController, ExecutionGate, CursorRequest
        pause = PauseController(ui, start_paused=False)
        gate = ExecutionGate(pause)

        # Set up: last_module_id is "test", consecutive_grants >= max
        gate._last_module_id = "test"
        gate._consecutive_grants = 3  # >= _max_consecutive_grants (2)

        # Add dominant module first, then different module
        with gate._condition:
            req_test = CursorRequest(module_id="test")
            req_other = CursorRequest(module_id="other")
            gate._queue.append(req_test)
            gate._queue.append(req_other)
            gate._rebalance_queue_for_fairness_locked()
            # "test" (dominant) should have been moved to the back
            assert gate._queue[0].module_id == "other"


@pytest.mark.skipif(not _HAS_PYNPUT, reason="pynput not installed (Linux)")
class TestHotkeyServiceKeyMapping:
    """Test HotkeyService key string to pynput mapping."""

    @classmethod
    def setup_class(cls):
        # Import HotkeyService fresh (before any patches) using real pynput.
        import sys
        # Reload services module to get unmocked HotkeyService
        if "systool.services" in sys.modules:
            del sys.modules["systool.services"]
        from systool import services
        cls.HotkeyService = services.HotkeyService

    def test_f1_to_f12_map(self):
        for i in range(1, 13):
            result = self.HotkeyService.key_str_to_pynput(f"f{i}")
            assert result is not None, f"Failed to map f{i}"

    def test_named_keys_map(self):
        for key in ["home", "end", "esc", "enter", "space", "tab", "delete"]:
            result = self.HotkeyService.key_str_to_pynput(key)
            assert result is not None, f"Failed to map {key}"

    def test_single_char_maps(self):
        for char in ["a", "b", "1", "2"]:
            result = self.HotkeyService.key_str_to_pynput(char)
            assert result is not None, f"Failed to map {char}"

    def test_uppercase_maps(self):
        for char in ["A", "B", "1", "2"]:
            result = self.HotkeyService.key_str_to_pynput(char)
            assert result is not None, f"Failed to map uppercase {char}"

    def test_invalid_key_returns_none(self):
        result = self.HotkeyService.key_str_to_pynput("nonexistent_key_xyz")
        assert result is None

    def test_empty_string_returns_none(self):
        result = self.HotkeyService.key_str_to_pynput("")
        # Empty string: len("") == 0, so it won't match single char
        assert result is None


class TestHotkeyServicePynputToStr:
    """Test pynput key to string conversion."""

    @classmethod
    def setup_class(cls):
        import sys
        if "systool.services" in sys.modules:
            del sys.modules["systool.services"]
        from systool import services
        cls.HotkeyService = services.HotkeyService

    def test_char_key_converts(self):
        try:
            import pynput.keyboard as pk
            char_key = pk.KeyCode.from_char("a")
            result = self.HotkeyService.pynput_key_to_str(char_key)
            assert result == "a"
        except ImportError:
            pass  # skip if pynput not available

    def test_named_key_converts(self):
        try:
            import pynput.keyboard as pk
            named_key = pk.Key.f1
            result = self.HotkeyService.pynput_key_to_str(named_key)
            assert "f1" in result.lower()
        except ImportError:
            pass


class TestHotkeyServiceMatches:
    """Test key matching logic."""

    @classmethod
    def setup_class(cls):
        import sys
        if "systool.services" in sys.modules:
            del sys.modules["systool.services"]
        from systool import services
        cls.HotkeyService = services.HotkeyService

    def test_matching_key(self):
        try:
            target = self.HotkeyService.key_str_to_pynput("a")
            assert self.HotkeyService.matches(target, "a") is True
        except Exception:
            pass

    def test_non_matching_key(self):
        try:
            a_key = self.HotkeyService.key_str_to_pynput("a")
            b_key = self.HotkeyService.key_str_to_pynput("b")
            assert self.HotkeyService.matches(b_key, "a") is False
        except Exception:
            pass
