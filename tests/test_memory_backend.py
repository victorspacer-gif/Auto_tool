from __future__ import annotations

import struct

import pytest

import systool.pointers.memory_backend as mb
from systool.pointers.memory_backend import (
    AddressResolveError,
    DbvmBridgeBackend,
    LightMemoryController,
    MemoryReadError,
)


class FakeBackend:
    def __init__(self) -> None:
        self.pid = 1234
        self.module_base = 0x7FF600000000
        self.memory: dict[int, int] = {}

    def attach(self, process_name: str) -> None:
        self.pid = 1234

    def detach(self) -> None:
        self.pid = None

    def get_module_base(self, module_substr: str) -> int:
        return self.module_base

    def read_bytes(self, address: int, size: int) -> bytes:
        try:
            return bytes(self.memory[address + offset] for offset in range(size))
        except KeyError as exc:
            raise MemoryReadError(f"missing byte at 0x{address:X}") from exc

    def write_bytes(self, address: int, data: bytes) -> None:
        for offset, value in enumerate(data):
            self.memory[address + offset] = value


def write_u64(fake: FakeBackend, address: int, value: int) -> None:
    fake.write_bytes(address, struct.pack("<Q", value))


def test_resolve_pointer_chain_reads_64_bit_pointers() -> None:
    fake = FakeBackend()
    controller = LightMemoryController("target.exe", backend=fake)

    first_pointer_address = fake.module_base + 0x100
    high_target = 0x000001FABCDE0000
    write_u64(fake, first_pointer_address, high_target)
    fake.write_bytes(high_target + 0x20, b"\xD7")

    resolved = controller.resolve_pointer_chain(fake.module_base, [0x100, 0x20])

    assert resolved == high_target + 0x20
    assert controller.read_byte(resolved) == 0xD7


def test_empty_pointer_chain_is_rejected() -> None:
    controller = LightMemoryController("target.exe", backend=FakeBackend())

    with pytest.raises(AddressResolveError):
        controller.resolve_pointer_chain(0x1000, [])


def test_dbvm_backend_accepts_configured_cr3(monkeypatch) -> None:
    _install_fake_dbvm(monkeypatch, FakeDbvmDll())

    backend = DbvmBridgeBackend(cr3="0x12345000")

    assert backend.cr3 == 0x12345000


class FakeDllFunction:
    def __init__(self, func):
        self.func = func
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.func(*args)


class FakeDbvmDll:
    def __init__(
        self,
        resolved_cr3: int | None = 0xABCDEF000,
        resolve_status: int = 0,
        include_cr3_export: bool = True,
    ) -> None:
        self.resolved_cr3 = resolved_cr3
        self.resolve_status = resolve_status
        self.smem_initialize = FakeDllFunction(lambda: 0)
        self.smem_shutdown = FakeDllFunction(lambda: 0)
        if include_cr3_export:
            self.smem_resolve_process_cr3 = FakeDllFunction(self._resolve_process_cr3)
        self.smem_dbvm_initialize = FakeDllFunction(lambda: 0)
        self.smem_dbvm_get_version = FakeDllFunction(self._dbvm_get_version)
        self.smem_dbvm_read_physical = FakeDllFunction(lambda *args: 0)
        self.smem_dbvm_write_physical = FakeDllFunction(lambda *args: 0)
        self.smem_dbvm_read_virtual = FakeDllFunction(lambda *args: 0)
        self.smem_dbvm_write_virtual = FakeDllFunction(lambda *args: 0)
        self.smem_last_error = FakeDllFunction(self._last_error)

    def _resolve_process_cr3(self, _pid, out_cr3) -> int:
        if self.resolve_status != 0:
            return self.resolve_status
        out_cr3._obj.value = int(self.resolved_cr3 or 0)
        return 0

    @staticmethod
    def _dbvm_get_version(out_version) -> int:
        out_version._obj.value = 0xCE
        return 0

    @staticmethod
    def _last_error(buffer, _buffer_chars) -> int:
        buffer.value = "fake driver error"
        return 0


def _install_fake_dbvm(monkeypatch, fake_dll: FakeDbvmDll) -> None:
    monkeypatch.setattr(mb.ct, "WinDLL", lambda *_args, **_kwargs: fake_dll, raising=False)
    monkeypatch.setattr(mb, "_find_pid_by_name", lambda _process_name: 4321)


def test_dbvm_attach_resolves_cr3_from_pid(monkeypatch) -> None:
    fake_dll = FakeDbvmDll(resolved_cr3=0xABCDEF123)
    _install_fake_dbvm(monkeypatch, fake_dll)

    backend = DbvmBridgeBackend()
    backend.attach("target.exe")

    assert backend.pid == 4321
    assert backend.cr3 == 0xABCDEF123
    assert backend.version == 0xCE
    assert fake_dll.smem_initialize.calls
    assert fake_dll.smem_resolve_process_cr3.calls[0][0].value == 4321


def test_dbvm_attach_prefers_explicit_cr3(monkeypatch) -> None:
    fake_dll = FakeDbvmDll(resolved_cr3=0xABCDEF123)
    _install_fake_dbvm(monkeypatch, fake_dll)

    backend = DbvmBridgeBackend(cr3="0x12345000")
    backend.attach("target.exe")

    assert backend.pid == 4321
    assert backend.cr3 == 0x12345000
    assert not fake_dll.smem_initialize.calls
    assert not fake_dll.smem_resolve_process_cr3.calls


def test_dbvm_attach_falls_back_to_env_cr3(monkeypatch) -> None:
    fake_dll = FakeDbvmDll(resolve_status=mb.SmemStatus.DRIVER_UNAVAILABLE)
    _install_fake_dbvm(monkeypatch, fake_dll)
    monkeypatch.setenv("STUDIOMEM_DBVM_CR3", "0x55555000")

    backend = DbvmBridgeBackend()
    backend.attach("target.exe")

    assert backend.pid == 4321
    assert backend.cr3 == 0x55555000


def test_dbvm_attach_reports_missing_cr3_export(monkeypatch) -> None:
    fake_dll = FakeDbvmDll(include_cr3_export=False)
    _install_fake_dbvm(monkeypatch, fake_dll)

    backend = DbvmBridgeBackend()

    with pytest.raises(mb.DriverBridgeError, match="does not export smem_resolve_process_cr3"):
        backend.attach("target.exe")
