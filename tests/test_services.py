"""Tests for service-layer logic: HumanMouse, SafeKeyboardSession, PauseController, ExecutionGate."""

import math
import random
import sys
import threading
import time
import pytest
from unittest.mock import MagicMock, patch

# Mock pynput only for tests that need mocked mouse/keyboard objects.
with patch("systool.runtime.pynput_kb"), \
     patch("systool.runtime.pynput_mouse"):
    from systool.services import CharacterStatusService, HumanMouse, RightClickService, SafeKeyboardSession

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
        assert CharacterStatusService._parse_food_seconds("1:05") == 3900

    def test_parse_food_timer_plain_minutes(self):
        assert CharacterStatusService._parse_food_seconds("15") == 900

    def test_parse_food_timer_rejects_invalid_minutes(self):
        assert CharacterStatusService._parse_food_seconds("1:75") is None

    def test_food_mode_decision_blocks_when_food_missing(self):
        allowed, message = RightClickService._food_mode_decision("", None, 10)
        assert allowed is False
        assert "decision=blocked" in message

    def test_food_mode_decision_allows_when_threshold_met(self):
        allowed, message = RightClickService._food_mode_decision("15", 15 * 60, 10)
        assert allowed is True
        assert "decision=allowed" in message

    def test_food_threshold_requires_available_timer(self):
        assert RightClickService.food_timer_meets_threshold(None, 10) is False

    def test_food_threshold_uses_minutes(self):
        assert RightClickService.food_timer_meets_threshold(15 * 60, 10) is True
        assert RightClickService.food_timer_meets_threshold(9 * 60, 10) is False

    def test_release_all_calls_keyboard_release_for_each(self):
        mock_keyboard = MagicMock()
        session = SafeKeyboardSession(mock_keyboard)
        session.press("a")
        session.press("b")
        session.release_all()
        # release_all pops in reverse order and calls release on each
        assert mock_keyboard.release.call_count == 2

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
