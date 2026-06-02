from __future__ import annotations

import struct

import pytest

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


def test_dbvm_backend_accepts_configured_cr3() -> None:
    backend = DbvmBridgeBackend(cr3="0x12345000")

    assert backend.cr3 == 0x12345000
