from __future__ import annotations

from systool.models import AppState
from systool.pointers import DbvmBridgeBackend, DriverBridgeBackend, PymemBackend
from systool.services.monitoring import LightControlService


def test_light_backend_defaults_to_dbvm() -> None:
    assert AppState().light_memory_backend == "dbvm"


def test_light_service_selects_dbvm_backend_by_default() -> None:
    runtime = type("Runtime", (), {"state": AppState()})()
    service = LightControlService(runtime)

    assert isinstance(service._make_backend(), DbvmBridgeBackend)


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
