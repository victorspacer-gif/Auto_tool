"""Tests for the global FIFO execution scheduler."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch


class TestExecutionGateFIFO:
    def test_execution_gate_grants_requests_in_fifo_order(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        stop_evt = threading.Event()
        order: list[str] = []

        release_first = threading.Event()
        release_second = threading.Event()
        release_third = threading.Event()
        first_granted = threading.Event()
        second_granted = threading.Event()
        third_granted = threading.Event()

        def worker(module_id: str, granted_evt: threading.Event, release_evt: threading.Event) -> None:
            assert runtime.execution.acquire(stop_evt, module_id=module_id)
            order.append(module_id)
            granted_evt.set()
            release_evt.wait(timeout=2.0)
            runtime.execution.release()

        first = threading.Thread(
            target=worker,
            args=("fishing", first_granted, release_first),
            daemon=True,
        )
        second = threading.Thread(
            target=worker,
            args=("rune", second_granted, release_second),
            daemon=True,
        )
        third = threading.Thread(
            target=worker,
            args=("auto_click", third_granted, release_third),
            daemon=True,
        )

        # Unpause so threads can acquire the execution gate
        runtime.pause.toggle()

        first.start()
        assert first_granted.wait(timeout=2.0)

        second.start()
        time.sleep(0.05)
        third.start()
        time.sleep(0.05)

        release_first.set()
        assert second_granted.wait(timeout=2.0)
        release_second.set()
        assert third_granted.wait(timeout=2.0)
        release_third.set()

        first.join(timeout=2.0)
        second.join(timeout=2.0)
        third.join(timeout=2.0)

        assert order == ["fishing", "rune", "auto_click"]

    def test_same_module_cannot_run_twice_while_another_waits(self):
        from systool.runtime import AppRuntime

        runtime = AppRuntime()
        stop_evt = threading.Event()
        order: list[str] = []

        release_fishing_first = threading.Event()
        release_rune = threading.Event()
        release_fishing_second = threading.Event()
        fishing_first_granted = threading.Event()
        fishing_second_granted = threading.Event()
        rune_granted = threading.Event()

        def fishing_worker() -> None:
            assert runtime.execution.acquire(stop_evt, module_id="fishing")
            order.append("fishing-1")
            fishing_first_granted.set()
            release_fishing_first.wait(timeout=2.0)
            runtime.execution.release()

            assert runtime.execution.acquire(stop_evt, module_id="fishing")
            order.append("fishing-2")
            fishing_second_granted.set()
            release_fishing_second.wait(timeout=2.0)
            runtime.execution.release()

        def rune_worker() -> None:
            assert runtime.execution.acquire(stop_evt, module_id="rune")
            order.append("rune-1")
            rune_granted.set()
            release_rune.wait(timeout=2.0)
            runtime.execution.release()

        fishing = threading.Thread(target=fishing_worker, daemon=True)
        rune = threading.Thread(target=rune_worker, daemon=True)

        # Unpause so threads can acquire the execution gate
        runtime.pause.toggle()

        fishing.start()
        assert fishing_first_granted.wait(timeout=2.0)

        rune.start()
        time.sleep(0.05)

        release_fishing_first.set()
        assert rune_granted.wait(timeout=2.0)
        release_rune.set()
        assert fishing_second_granted.wait(timeout=2.0)
        release_fishing_second.set()

        fishing.join(timeout=2.0)
        rune.join(timeout=2.0)

        assert order == ["fishing-1", "rune-1", "fishing-2"]


class TestFishingCycle:
    def test_fishing_cycle_right_clicks_then_casts_without_returning_to_start(self):
        from systool.runtime import AppRuntime
        from systool.services import FishingService

        runtime = AppRuntime()
        state = runtime.state
        state.fish_active = True
        state.fish_rod_pos = (100, 200)
        state.fish_spots = [(300, 400)]
        state.fish_session_remaining_secs = 60
        state.fish_session_deadline = time.monotonic() + 60

        release_calls: list[str] = []
        move_click_calls: list[tuple] = []

        class FakeRouter:
            def human_move_and_click(self, x, y, button, duration=None):
                move_click_calls.append((button, (x, y)))

        runtime.pause.wait = lambda: None
        runtime.pause.wait_interruptible = lambda _seconds, _stop_evt: False
        runtime.mouse.acquire = lambda *_args, **_kwargs: True
        runtime.mouse.release = lambda: release_calls.append("released")
        runtime.input_router = FakeRouter()

        service = FishingService(runtime)

        with patch(
            "systool.services.HumanMouse.jitter", side_effect=lambda pos, _amount: pos
        ):
            service._worker()

        assert move_click_calls == [
            ("right", (100, 200)),
            ("left", (300, 400)),
        ]
        assert release_calls == ["released"]
        assert state.stats["fish_casts"] == 1
        assert state.fish_active is False
