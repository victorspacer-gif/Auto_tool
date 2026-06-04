from __future__ import annotations

from systool.models import AppState
from systool.pointers import DbvmBridgeBackend, DriverBridgeBackend, PymemBackend
from systool.services.monitoring import LightControlService


class FakeLightController:
    pid = 1234

    def __init__(self, values: dict[int, int]) -> None:
        self.values = values

    def read_byte(self, address: int) -> int:
        return self.values[address]


def test_light_backend_defaults_to_dbvm() -> None:
    assert AppState().light_memory_backend == "pymem"


def test_light_service_selects_pymem_backend_by_default() -> None:
    runtime = type("Runtime", (), {"state": AppState()})()
    service = LightControlService(runtime)

    assert isinstance(service._make_backend(), PymemBackend)


def test_light_service_selects_studiomemuer_driver_backend() -> None:
    state = AppState()
    state.light_memory_backend = "studiomemuer"
    runtime = type("Runtime", (), {"state": state})()
    service = LightControlService(runtime)

    assert isinstance(service._make_backend(), DriverBridgeBackend)


def test_light_service_selects_pymem_backend() -> None:
    state = AppState()
    state.light_memory_backend = "pymem"
    runtime = type("Runtime", (), {"state": state})()
    service = LightControlService(runtime)

    assert isinstance(service._make_backend(), PymemBackend)


def test_light_service_reads_current_direct_pair() -> None:
    state = AppState()
    state.light_direct_address_hex = "1000"
    runtime = type("Runtime", (), {"state": state})()
    service = LightControlService(runtime)
    service.controller = FakeLightController({0x1000: 215, 0x1001: 8})

    ok, message = service.read_current()

    assert ok
    assert "color 0x1000: 215" in message
    assert "intensity 0x1001: 8" in message
    assert state.light_freeze_color_value == 215
    assert state.light_freeze_intensity_value == 8
    assert state.light_last_color_address_hex == "1000"
    assert state.light_last_intensity_address_hex == "1001"
