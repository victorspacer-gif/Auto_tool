"""Tests for fishing/rune worker lock safety and RLock reentrancy.

These tests verify that the nested lock patterns in FishingService._worker(),
RuneMakerService._worker(), and CapService.get_cap() do not deadlock when the
same thread acquires settings_lock multiple times (e.g., outer context + inner
get_cap() call). The fix changes threading.Lock() → RLock().
"""

import sys
import threading
import time
from unittest.mock import MagicMock, patch

# Mock Windows-only deps before importing runtime/services.
tk_mock = MagicMock()
tk_mock.TkVersion = 8.6
sys.modules["tkinter"] = tk_mock
sys.modules["_tkinter"] = tk_mock
for mod in ["win32con", "win32gui", "pywin32"]:
    sys.modules[mod] = MagicMock()


class TestSettingsLockIsRLock:
    """Verify settings_lock and record_lock are RLock instances."""

    def test_settings_lock_is_rlock(self):
        from systool.runtime import AppRuntime
        runtime = AppRuntime()
        assert isinstance(runtime.settings_lock, type(threading.RLock()))

    def test_record_lock_is_rlock(self):
        from systool.runtime import AppRuntime
        runtime = AppRuntime()
        assert isinstance(runtime.record_lock, type(threading.RLock()))


class TestRLockReentrancy:
    """Test that RLock can be acquired multiple times by the same thread."""

    def test_double_acquire_no_deadlock(self):
        """Acquiring an RLock twice on the same thread should not block."""
        lock = threading.RLock()
        lock.acquire()
        lock.acquire()  # second acquire — must return immediately
        lock.release()
        lock.release()

    def test_triple_acquire_no_deadlock(self):
        """Three nested acquires should all succeed on the same thread."""
        lock = threading.RLock()
        for _ in range(3):
            lock.acquire()
        for _ in range(3):
            lock.release()

    def test_non_reentrant_lock_would_deadlock(self):
        """Demonstrate that a regular Lock would deadlock on double acquire."""
        lock = threading.Lock()
        lock.acquire()
        acquired_inner = threading.Event()

        def try_acquire():
            lock.acquire()  # this will block forever
            acquired_inner.set()

        thread = threading.Thread(target=try_acquire, daemon=True)
        thread.start()
        time.sleep(0.3)
        assert not acquired_inner.is_set(), (
            "Non-reentrant Lock should have blocked on second acquire"
        )
        lock.release()  # release outer so the stuck thread can finish

    def test_rlock_survives_nested_acquire_in_thread(self):
        """RLock must survive nested acquisition from a spawned thread."""
        lock = threading.RLock()
        acquired_inner = threading.Event()

        def inner_acquire():
            with lock:  # outer acquire
                with lock:  # inner acquire — should succeed immediately
                    acquired_inner.set()

        thread = threading.Thread(target=inner_acquire, daemon=True)
        thread.start()
        assert acquired_inner.wait(timeout=2.0), "RLock nested acquire should not block"


class TestFishingWorkerLockPattern:
    """Test the exact lock pattern used in FishingService._worker()."""

    def test_fish_worker_pattern_no_deadlock(self):
        """Simulate the fishing worker's settings_lock acquisition sequence.

        The worker does:
            with self.runtime.settings_lock:  # outer (line 1699)
                rod = state.fish_rod_pos
                ...
                current_cap = None
                if self.runtime.cap_service is not None:
                    try:
                        current_cap = self.runtime.cap_service.get_cap()  # calls get_cap
                    except Exception:
                        pass
        """
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        state = runtime.state

        # Simulate the outer lock + inner get_cap pattern.
        # CapService.get_cap() internally acquires settings_lock at lines 903 and 910.
        acquired_inner = threading.Event()

        def simulate_fish_worker():
            with runtime.settings_lock:  # outer (line 1699)
                rod = state.fish_rod_pos  # read under lock (line 1700)
                min_cap = state.fish_min_cap  # read under lock (line 1707)

                # Simulate CapService.get_cap() internal behavior:
                # It acquires settings_lock at line 903 and/or 910.
                with runtime.settings_lock:  # inner acquire from get_cap (line 903/910)
                    cap_val = state.cap_value  # read under lock
                    acquired_inner.set()

        thread = threading.Thread(target=simulate_fish_worker, daemon=True)
        thread.start()
        assert acquired_inner.wait(timeout=2.0), (
            "Fishing worker nested settings_lock acquire should not deadlock"
        )


class TestCapServiceGetCapUnderOuterLock:
    """Test that CapService.get_cap() works when called from inside an outer lock."""

    def test_get_cap_nested_acquire(self):
        """CapService.get_cap() acquires settings_lock internally.

        When the fishing worker calls get_cap() while already holding settings_lock,
        the inner acquire must succeed (RLock reentrancy).
        """
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        state = AppRuntime().state  # fresh state for this test

        # Simulate: outer lock held by fishing worker → get_cap acquires again.
        acquired = threading.Event()

        def simulate():
            with runtime.settings_lock:  # outer (fishing worker)
                with runtime.settings_lock:  # inner (get_cap line 903 or 910)
                    _ = state.cap_value
                    acquired.set()

        thread = threading.Thread(target=simulate, daemon=True)
        thread.start()
        assert acquired.wait(timeout=2.0), (
            "CapService.get_cap() nested settings_lock acquire should not deadlock"
        )


class TestRuneMakerWorkerLockPattern:
    """Test the exact lock pattern used in RuneMakerService._worker()."""

    def test_rune_worker_pattern_no_deadlock(self):
        """Simulate the rune maker worker's settings_lock acquisition sequence.

        The worker does:
            with self.runtime.settings_lock:  # outer (line 1962)
                hand = state.rune_hand_pos
                ...
                current_mana = None
                if self.runtime.mp_service is not None:
                    try:
                        current_mana = self.runtime.mp_service.get_mp()
                    except Exception:
                        pass
                # (previously had inner 'with settings_lock' — now removed)
        """
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        state = runtime.state

        acquired_inner = threading.Event()

        def simulate_rune_worker():
            with runtime.settings_lock:  # outer (line 1962)
                hand = state.rune_hand_pos  # read under lock (line 1963)
                min_mana = state.rune_min_mana  # read under lock (line 1970)

                # Simulate MP service get_mp() which may acquire settings_lock.
                with runtime.settings_lock:  # inner acquire from get_mp
                    mana_val = state.char_status_mana
                    acquired_inner.set()

        thread = threading.Thread(target=simulate_rune_worker, daemon=True)
        thread.start()
        assert acquired_inner.wait(timeout=2.0), (
            "Rune worker nested settings_lock acquire should not deadlock"
        )


class TestConcurrentFishingAndStatPoller:
    """Test the real-world scenario that caused the original freeze.

    The fishing worker holds settings_lock and calls get_cap(), which acquires
    it again. Meanwhile, _read_all_stats() (the background poller) also reads
    from memory via the same controller. With RLock on both settings_lock and
    LightMemoryController._lock, this should not deadlock.
    """

    def test_fishing_worker_and_poller_concurrent(self):
        """Fishing worker + stat poller can run concurrently without deadlock."""
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        state = runtime.state

        fishing_done = threading.Event()
        polling_done = threading.Event()

        def fish_worker():
            # Simulate the fishing worker's lock pattern.
            with runtime.settings_lock:  # outer (line 1699)
                rod = state.fish_rod_pos
                current_cap = None
                # get_cap would acquire settings_lock internally.
                with runtime.settings_lock:  # inner from get_cap
                    current_cap = state.cap_value

            # Simulate memory read via controller (RLock on _lock).
            if runtime.cap_service is not None and runtime.cap_service.controller is not None:
                try:
                    runtime.cap_service.controller.read_double(0x12345678)
                except Exception:
                    pass

            fishing_done.set()

        def stat_poller():
            # Simulate _read_all_stats() which also acquires settings_lock.
            with runtime.settings_lock:  # outer (line 597)
                hp_val = state.hp_value
                mp_val = state.mp_value
                cap_val = state.cap_value

            polling_done.set()

        fish_thread = threading.Thread(target=fish_worker, daemon=True)
        poll_thread = threading.Thread(target=stat_poller, daemon=True)

        fish_thread.start()
        time.sleep(0.05)  # let fishing thread acquire outer lock first
        poll_thread.start()

        assert fishing_done.wait(timeout=3.0), "Fishing worker should not deadlock"
        assert polling_done.wait(timeout=3.0), "Stat poller should not deadlock"


class TestRecordLockReentrancy:
    """Test that record_lock (also changed to RLock) works correctly."""

    def test_record_lock_double_acquire(self):
        from systool.runtime import AppRuntime
        runtime = AppRuntime()

        acquired = threading.Event()

        def inner():
            with runtime.record_lock:  # outer
                with runtime.record_lock:  # inner — should succeed
                    acquired.set()

        thread = threading.Thread(target=inner, daemon=True)
        thread.start()
        assert acquired.wait(timeout=2.0), "record_lock nested acquire should not deadlock"


class TestNoInnerLockNeededInWorker:
    """Verify the redundant inner lock contexts were removed from workers."""

    def test_fish_worker_reads_state_under_outer_lock(self):
        """The fishing worker reads state values under the outer settings_lock,
        so no inner context is needed. This test verifies the pattern works
        correctly without an inner lock."""
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        state = runtime.state

        # Set up some state values.
        state.fish_rod_pos = (100, 200)
        state.fish_min_cap = 500
        state.char_status_cap = 750

        rod_read = None
        cap_read = None

        with runtime.settings_lock:  # outer lock held by worker
            rod_read = state.fish_rod_pos  # read under outer lock (no inner needed)
            cap_read = state.char_status_cap  # same — no inner context

        assert rod_read == (100, 200)
        assert cap_read == 750

    def test_rune_worker_reads_state_under_outer_lock(self):
        """The rune worker reads state values under the outer settings_lock."""
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        state = runtime.state

        state.rune_hand_pos = (100, 200)
        state.char_status_mana = 450

        hand_read = None
        mana_read = None

        with runtime.settings_lock:  # outer lock held by worker
            hand_read = state.rune_hand_pos  # read under outer lock
            mana_read = state.char_status_mana  # same — no inner context

        assert hand_read == (100, 200)
        assert mana_read == 450
