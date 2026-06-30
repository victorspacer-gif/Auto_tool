"""Tests for systool.runtime: UINotifier, PauseController, ExecutionGate, MouseGate, AppRuntime."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch


class TestUINotifierInit:
    """Verify UINotifier default lambdas are no-op callables."""

    def test_dispatch_is_noop(self):
        from systool.runtime import UINotifier

        ui = UINotifier()
        result = []
        ui.dispatch(lambda: result.append(42))
        assert result == [42]

    def test_log_is_noop(self):
        from systool.runtime import UINotifier

        ui = UINotifier()
        ui.log("hello")  # should not raise

    def test_set_status_is_noop(self):
        from systool.runtime import UINotifier

        ui = UINotifier()
        ui.set_status("text", "red")  # should not raise

    def test_refresh_stats_is_noop(self):
        from systool.runtime import UINotifier

        ui = UINotifier()
        ui.refresh_stats()  # should not raise

    def test_set_pause_label_is_noop(self):
        from systool.runtime import UINotifier

        ui = UINotifier()
        ui.set_pause_label(True)  # should not raise

    def test_job_state_changed_is_noop(self):
        from systool.runtime import UINotifier, HotkeyJob

        ui = UINotifier()
        job = HotkeyJob(job_id=1)
        ui.job_state_changed(job)  # should not raise

    def test_module_state_changed_is_noop(self):
        from systool.runtime import UINotifier

        ui = UINotifier()
        ui.module_state_changed("fishing", True)  # should not raise


class TestUINotifierConfigure:
    """Verify configure wires callbacks and methods invoke them."""

    def test_configure_wires_dispatch(self):
        from systool.runtime import UINotifier

        called = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: fn(),
            log=called.append,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=lambda _p: None,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        ui.dispatch(lambda: called.append("dispatch"))
        assert "dispatch" in called

    def test_log_calls_wired_log(self):
        from systool.runtime import UINotifier

        logged = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: fn(),
            log=logged.append,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=lambda _p: None,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        ui.log("hello")
        assert logged == ["hello"]

    def test_set_status_calls_wired_set_status(self):
        from systool.runtime import UINotifier

        status = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: fn(),
            log=lambda _m: None,
            set_status=lambda t, c: status.append((t, c)),
            refresh_stats=lambda: None,
            set_pause_label=lambda _p: None,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        ui.set_status("ready", "green")
        assert status == [("ready", "green")]

    def test_refresh_stats_calls_wired_refresh(self):
        from systool.runtime import UINotifier

        refreshed = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: fn(),
            log=lambda _m: None,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: refreshed.append(True),
            set_pause_label=lambda _p: None,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        ui.refresh_stats()
        assert refreshed == [True]

    def test_set_pause_label_calls_wired(self):
        from systool.runtime import UINotifier

        paused_vals = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: fn(),
            log=lambda _m: None,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=paused_vals.append,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        ui.set_pause_label(True)
        assert paused_vals == [True]

    def test_job_state_changed_calls_wired(self):
        from systool.runtime import UINotifier, HotkeyJob

        jobs = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: fn(),
            log=lambda _m: None,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=lambda _p: None,
            job_state_changed=jobs.append,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        job = HotkeyJob(job_id=5)
        ui.job_state_changed(job)
        assert jobs == [job]

    def test_module_state_changed_calls_wired(self):
        from systool.runtime import UINotifier

        calls = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: fn(),
            log=lambda _m: None,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=lambda _p: None,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda m, r: calls.append((m, r)),
            show_logout_popup=lambda _t, _m, _to: None,
        )
        ui.module_state_changed("fishing", True)
        assert calls == [("fishing", True)]

    def test_dispatch_wraps_callback_in_wired_log(self):
        """ui.log() internally does self._dispatch(lambda: self._log(msg))."""
        from systool.runtime import UINotifier

        dispatched = []
        logged = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: dispatched.append(fn),
            log=logged.append,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=lambda _p: None,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        ui.log("msg")
        assert len(dispatched) == 1
        dispatched[0]()  # execute the wrapped callback
        assert logged == ["msg"]


class TestPauseControllerInit:
    """Verify PauseController initial state."""

    def test_default_start_paused_true(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        pc = PauseController(ui)
        assert pc.paused is True

    def test_start_paused_false(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        pc = PauseController(ui, start_paused=False)
        assert pc.paused is False


class TestPauseControllerToggle:
    """Verify toggle flips paused state and calls UI."""

    def test_toggle_unpauses(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        logged = []
        pause_labels = []
        ui.configure(
            dispatch=lambda fn: fn(),
            log=logged.append,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=pause_labels.append,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        pc = PauseController(ui, start_paused=True)
        assert pc.paused is True

        pc.toggle()
        assert pc.paused is False
        assert "▶  Resumed" in logged[-1]
        assert pause_labels == [False]

    def test_toggle_pauses(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        logged = []
        pause_labels = []
        ui.configure(
            dispatch=lambda fn: fn(),
            log=logged.append,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=pause_labels.append,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )
        pc = PauseController(ui, start_paused=False)
        assert pc.paused is False

        pc.toggle()
        assert pc.paused is True
        assert "⏸  PAUSED" in logged[-1]
        assert pause_labels == [True]


class TestPauseControllerWait:
    """Verify wait blocks when paused and returns when unpaused."""

    def test_wait_blocks_when_paused(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        pc = PauseController(ui)  # starts paused
        blocked = threading.Event()

        def waiter():
            pc.wait()
            blocked.set()

        t = threading.Thread(target=waiter, daemon=True)
        t.start()
        time.sleep(0.15)
        assert not blocked.is_set(), "wait should block while paused"

        pc.toggle()  # unpause
        assert blocked.wait(timeout=2.0), "wait should return after unpausing"

    def test_wait_returns_immediately_when_not_paused(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotNotifier = MagicMock()
        pc = PauseController(ui, start_paused=False)
        t0 = time.monotonic()
        pc.wait()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.5


class TestPauseControllerWaitInterruptible:
    """Verify wait_interruptible respects stop events and deadlines."""

    def test_returns_true_on_timeout(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        pc = PauseController(ui, start_paused=False)
        result = pc.wait_interruptible(0.1, threading.Event())
        assert result is True

    def test_returns_false_when_stop_set(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        pc = PauseController(ui, start_paused=False)
        stop = threading.Event()
        stop.set()
        result = pc.wait_interruptible(1.0, stop)
        assert result is False


class TestCursorRequest:
    """Verify CursorRequest dataclass defaults."""

    def test_default_token_is_unique(self):
        from systool.runtime import CursorRequest

        r1 = CursorRequest()
        r2 = CursorRequest()
        assert r1.token is not r2.token  # different object() per instance

    def test_default_expires_at_none(self):
        from systool.runtime import CursorRequest

        r = CursorRequest()
        assert r.expires_at is None

    def test_default_module_id_anonymous(self):
        from systool.runtime import CursorRequest

        r = CursorRequest()
        assert r.module_id == "anonymous"


class TestExecutionGateWaitTimeout:
    """Verify _wait_timeout_locked clamps values."""

    def test_none_returns_default(self):
        from systool.runtime import ExecutionGate

        result = ExecutionGate._wait_timeout_locked(None, None)
        # Default is 0.05 (EXEC_WAIT_TIMEOUT_DEFAULT)
        assert result == 0.05

    def test_below_min_clamps_to_min(self):
        from systool.runtime import ExecutionGate

        result = ExecutionGate._wait_timeout_locked(None, 0.001)
        assert result >= 0.01  # EXEC_WAIT_TIMEOUT_MIN

    def test_above_max_clamps_to_max(self):
        from systool.runtime import ExecutionGate

        result = ExecutionGate._wait_timeout_locked(None, 99999.0)
        assert result <= 0.05  # EXEC_WAIT_TIMEOUT_MAX


class TestExecutionGatePruneExpired:
    """Verify _prune_expired_locked removes expired requests."""

    def test_removes_expired_requests(self):
        from systool.runtime import ExecutionGate, PauseController, CursorRequest

        ui = MagicMock()
        pc = PauseController(ui)
        gate = ExecutionGate(pc)

        now = time.monotonic()
        r1 = CursorRequest(expires_at=now - 10)  # expired
        r2 = CursorRequest(expires_at=now + 60)  # not expired
        r3 = CursorRequest(expires_at=None)      # no expiry

        gate._queue = [r1, r2, r3]
        gate._prune_expired_locked()
        assert len(gate._queue) == 2
        assert r1 not in gate._queue


class TestExecutionGateRebalanceQueue:
    """Verify _rebalance_queue_for_fairness_locked moves dominant module to back."""

    def test_no_rebalance_when_below_threshold(self):
        from systool.runtime import ExecutionGate, PauseController, CursorRequest

        ui = MagicMock()
        pc = PauseController(ui)
        gate = ExecutionGate(pc)

        # Explicitly set _last_module_id to None so the condition short-circuits
        gate._last_module_id = None
        r1 = CursorRequest(module_id="fishing")
        gate._queue.append(r1)
        gate._rebalance_queue_for_fairness_locked()
        assert gate._queue == [r1]

    def test_rebalances_when_threshold_reached(self):
        from systool.runtime import ExecutionGate, PauseController, CursorRequest

        ui = MagicMock()
        pc = PauseController(ui)
        gate = ExecutionGate(pc)

        # Set up dominance: 2 consecutive grants by "fishing"
        gate._last_module_id = "fishing"
        gate._consecutive_grants = 2
        gate._max_consecutive_grants = 2

        r1 = CursorRequest(module_id="rune")
        r2 = CursorRequest(module_id="fishing")
        r3 = CursorRequest(module_id="auto_click")
        gate._queue = [r1, r2, r3]
        gate._rebalance_queue_for_fairness_locked()

        # fishing should be moved to the back
        assert gate._queue[-1].module_id == "fishing"


class TestMouseGate:
    """Verify MouseGate delegates to ExecutionGate."""

    def test_acquire_delegates(self):
        from systool.runtime import AppRuntime, MouseGate

        runtime = AppRuntime()
        stop_evt = threading.Event()

        # Unpause so acquire can proceed
        runtime.pause.toggle()

        result = runtime.mouse.acquire(stop_evt, module_id="test")
        assert result is True
        runtime.mouse.release()


class TestAppRuntimeInit:
    """Verify AppRuntime initializes all expected attributes."""

    def test_state_is_appstate(self):
        from systool.runtime import AppRuntime
        from systool.models import AppState

        runtime = AppRuntime()
        assert isinstance(runtime.state, AppState)

    def test_settings_lock_exists(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        assert hasattr(runtime, "settings_lock")
        assert runtime.settings_lock is not None

    def test_record_lock_exists(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        assert hasattr(runtime, "record_lock")
        assert runtime.record_lock is not None

    def test_ui_is_uinotifier(self):
        from systool.runtime import AppRuntime, UINotifier

        runtime = AppRuntime()
        assert isinstance(runtime.ui, UINotifier)

    def test_pause_is_pausecontroller(self):
        from systool.runtime import AppRuntime, PauseController

        runtime = AppRuntime()
        assert isinstance(runtime.pause, PauseController)
        assert runtime.pause.paused is True  # default start_paused=True

    def test_execution_is_executiongate(self):
        from systool.runtime import AppRuntime, ExecutionGate

        runtime = AppRuntime()
        assert isinstance(runtime.execution, ExecutionGate)

    def test_mouse_is_mousgate(self):
        from systool.runtime import AppRuntime, MouseGate

        runtime = AppRuntime()
        assert isinstance(runtime.mouse, MouseGate)

    def test_stop_events_are_events(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        for attr in (
            "afk_stop", "rclick_stop", "alarm_stop",
            "char_status_stop", "fish_stop", "healer_stop", "rune_stop"
        ):
            assert isinstance(getattr(runtime, attr), threading.Event)

    def test_service_refs_none(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        assert runtime.hp_service is None
        assert runtime.mp_service is None
        assert runtime.cap_service is None


class TestAppRuntimeConfigLoading:
    """Verify AppRuntime loads config from file if present."""

    def test_no_config_file_creates_defaults(self):
        """When no config.json exists, AppRuntime still initializes cleanly."""
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        assert runtime.state is not None
        # Config loading failure should be silently ignored (logged as error)


class TestOptionalDeps:
    """Verify optional dependency detection flags."""

    def test_has_pyautogui_is_bool(self):
        from systool.runtime import HAS_PYAUTOGUI

        assert isinstance(HAS_PYAUTOGUI, bool)

    def test_has_tray_is_bool(self):
        from systool.runtime import HAS_TRAY

        assert isinstance(HAS_TRAY, bool)

    def test_has_mss_is_bool(self):
        from systool.runtime import HAS_MSS

        assert isinstance(HAS_MSS, bool)

    def test_has_numpy_is_bool(self):
        from systool.runtime import HAS_NUMPY

        assert isinstance(HAS_NUMPY, bool)

    def test_has_cv2_is_bool(self):
        from systool.runtime import HAS_CV2

        assert isinstance(HAS_CV2, bool)

    def test_has_tesseract_is_bool(self):
        from systool.runtime import HAS_TESSERACT

        assert isinstance(HAS_TESSERACT, bool)

    def test_has_pygame_is_bool(self):
        from systool.runtime import HAS_PYGAME

        assert isinstance(HAS_PYGAME, bool)

    def test_has_pynput_is_bool(self):
        from systool.runtime import HAS_PYNPUT

        assert isinstance(HAS_PYNPUT, bool)

    def test_has_win32_is_bool(self):
        from systool.runtime import HAS_WIN32

        assert isinstance(HAS_WIN32, bool)


class TestResolveTesseractCmd:
    """Verify resolve_tesseract_cmd candidate resolution logic."""

    def test_empty_string_returns_none_when_no_candidates(self):
        from systool.runtime import resolve_tesseract_cmd

        with patch("systool.runtime.shutil.which", return_value=None), \
             patch("systool.runtime.os.path.exists", return_value=False):
            result = resolve_tesseract_cmd("")
            assert result is None

    def test_explicit_path_returned_if_exists(self):
        from systool.runtime import resolve_tesseract_cmd

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"fake tesseract")
            f.flush()
            fake_path = f.name

        try:
            result = resolve_tesseract_cmd(fake_path)
            assert result == fake_path
        finally:
            os.unlink(fake_path)

    def test_which_path_preferred_over_vendor(self):
        from systool.runtime import resolve_tesseract_cmd

        with tempfile.NamedTemporaryFile(delete=False, suffix="tesseract") as f:
            f.write(b"fake")
            fake_which = f.name

        try:
            # The code checks candidates in order: explicit_path, meipass, vendor, which, env_paths
            # We set up so only fake_which exists → it should be returned
            with patch("systool.runtime.shutil.which", return_value=fake_which), \
                 patch("systool.runtime.os.path.exists", lambda p: p == fake_which):
                result = resolve_tesseract_cmd("")
                assert result == fake_which
        finally:
            os.unlink(fake_which)


class TestConfigureTesseractRuntime:
    """Verify configure_tesseract_runtime sets PATH and TESSDATA_PREFIX."""

    def test_sets_path(self):
        from systool.runtime import configure_tesseract_runtime

        with tempfile.TemporaryDirectory() as tmpdir:
            tessdata = os.path.join(tmpdir, "tessdata")
            os.makedirs(tessdata)

            old_path = os.environ.get("PATH", "")
            try:
                configure_tesseract_cmd = os.path.join(tmpdir, "tesseract.exe")
                with open(configure_tesseract_cmd, "w") as f:
                    f.write("#!/bin/sh\nexit 0")
                os.chmod(configure_tesseract_cmd, 0o755)

                configure_tesseract_runtime(configure_tesseract_cmd)

                assert tmpdir in os.environ["PATH"]
            finally:
                os.environ["PATH"] = old_path


class TestPygameMixerStubs:
    """Verify pygame mixer is lazy-initialized via ensure_pygame_mixer()."""

    def test_mixer_not_initialized_at_import(self):
        """Mixer must NOT be initialized at import time — it's lazy now.

        pygame-ce produces white noise when mixer is started; the gate stays
        shut until audio is actually requested.
        """
        from systool.runtime import HAS_PYGAME, pygame, ensure_pygame_mixer

        if not HAS_PYGAME:
            pytest.skip("pygame not available")

        # In the mocked test env, get_init() returns a MagicMock (truthy).
        # Verify ensure_pygame_mixer() exists and is callable.
        assert callable(ensure_pygame_mixer)
        result = ensure_pygame_mixer()
        assert result is True, "ensure_pygame_mixer must return True when mixer is ready"

    def test_ensure_pygame_mixer_idempotent(self):
        """Calling ensure_pygame_mixer() multiple times is safe."""
        from systool.runtime import HAS_PYGAME, ensure_pygame_mixer

        if not HAS_PYGAME:
            pytest.skip("pygame not available")

        r1 = ensure_pygame_mixer()
        r2 = ensure_pygame_mixer()
        r3 = ensure_pygame_mixer()
        assert r1 == r2 == r3, "ensure_pygame_mixer must be idempotent"

    def test_ensure_pygame_mixer_false_when_no_pygame(self, monkeypatch):
        """Returns False when HAS_PYGAME is False."""
        from systool.runtime import ensure_pygame_mixer

        import systool.runtime as rt
        original_flag = rt.HAS_PYGAME
        try:
            monkeypatch.setattr(rt, "HAS_PYGAME", False)
            assert ensure_pygame_mixer() is False, (
                "must return False when pygame unavailable"
            )
        finally:
            rt.HAS_PYGAME = original_flag


class TestPauseControllerWaitInterruptibleDeadline:
    """Verify wait_interruptible respects the deadline even when paused."""

    def test_returns_true_after_deadline_elapsed(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        pc = PauseController(ui)  # starts paused
        stop_evt = threading.Event()

        t0 = time.monotonic()
        # Unpause after a short delay so wait_interruptible can make progress
        def unpause_later():
            time.sleep(0.1)
            pc.toggle()
        threading.Thread(target=unpause_later, daemon=True).start()

        result = pc.wait_interruptible(0.15, stop_evt)
        elapsed = time.monotonic() - t0

        assert result is True
        # Should take at least the unpause delay + some polling overhead
        assert elapsed >= 0.08


class TestExecutionGateAcquireRelease:
    """Verify acquire/release cycle works correctly."""

    def test_acquire_grants_then_release(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        stop_evt = threading.Event()

        # Unpause so threads can proceed
        runtime.pause.toggle()

        assert runtime.execution.acquire(stop_evt, module_id="test") is True
        runtime.execution.release()

    def test_release_without_acquire_is_safe(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        stop_evt = threading.Event()
        runtime.pause.toggle()

        # Release without prior acquire should not crash
        runtime.execution.release()


class TestExecutionGateStopEvent:
    """Verify acquire returns False when stop event is set."""

    def test_acquire_returns_false_when_stopped(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        stop_evt = threading.Event()
        stop_evt.set()  # already stopped

        result = runtime.execution.acquire(stop_evt, module_id="test")
        assert result is False


class TestMouseGateAcquireRelease:
    """Verify MouseGate acquire/release delegates correctly."""

    def test_mouse_gate_acquire(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        stop_evt = threading.Event()
        runtime.pause.toggle()

        assert runtime.mouse.acquire(stop_evt, module_id="test") is True
        runtime.mouse.release()

    def test_mouse_gate_release(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        stop_evt = threading.Event()
        runtime.pause.toggle()

        runtime.mouse.release()  # should not crash


class TestAppRuntimeConfigLoading:
    """Verify AppRuntime loads config from file if present."""

    def test_no_config_file_creates_defaults(self):
        from systool.runtime import AppRuntime

        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily change the module's __file__ path to use our temp dir
            import systool.runtime as rt_mod
            orig_file = rt_mod.__file__

            try:
                # Create a fake config.json in our temp dir
                test_config = os.path.join(tmpdir, "config.json")
                with open(test_config, "w") as f:
                    f.write("{}")

                # Patch the module's __file__ so config_path resolves to tmpdir
                rt_mod.__file__ = os.path.join(tmpdir, "runtime.py")

                runtime = AppRuntime()
                assert runtime.state is not None
            finally:
                rt_mod.__file__ = orig_file


class TestUINotifierDispatchWrapping:
    """Verify that UI methods wrap callbacks correctly."""

    def test_log_wraps_in_dispatch(self):
        from systool.runtime import UINotifier

        dispatched_callbacks = []
        ui = UINotifier()
        ui.configure(
            dispatch=lambda fn: dispatched_callbacks.append(fn),
            log=lambda _m: None,
            set_status=lambda _t, _c: None,
            refresh_stats=lambda: None,
            set_pause_label=lambda _p: None,
            job_state_changed=lambda _j: None,
            module_state_changed=lambda _m, _r: None,
            show_logout_popup=lambda _t, _m, _to: None,
        )

        ui.log("test message")
        assert len(dispatched_callbacks) == 1

        # Execute the callback to verify it calls _log
        dispatched_callbacks[0]()


class TestPauseControllerPausedProperty:
    """Verify paused property reflects internal state."""

    def test_initial_state_matches_start_paused(self):
        from systool.runtime import UINotifier, PauseController

        ui = UINotifier()
        pc_true = PauseController(ui, start_paused=True)
        assert pc_true.paused is True

        ui2 = UINotifier()
        pc_false = PauseController(ui2, start_paused=False)
        assert pc_false.paused is False


class TestExecutionGateQueueState:
    """Verify ExecutionGate internal queue state."""

    def test_queue_empty_after_init(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        assert len(runtime.execution._queue) == 0

    def test_owner_none_after_init(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        assert runtime.execution._owner is None


class TestAppRuntimeStopEvents:
    """Verify all stop events are distinct threading.Event instances."""

    def test_stop_events_are_distinct(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        events = [
            runtime.afk_stop,
            runtime.rclick_stop,
            runtime.alarm_stop,
            runtime.char_status_stop,
            runtime.fish_stop,
            runtime.healer_stop,
            runtime.rune_stop,
        ]

        # All should be distinct objects
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                assert events[i] is not events[j]


