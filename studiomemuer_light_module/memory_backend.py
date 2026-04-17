from __future__ import annotations

from dataclasses import dataclass

import psutil
import pymem


class ProcessNotFoundError(RuntimeError):
    pass


class MemoryWriteError(RuntimeError):
    pass


@dataclass
class PatchResult:
    address: int
    old_value: int
    new_value: int


class LightMemoryController:
    def __init__(self, process_name: str) -> None:
        self.process_name = process_name
        self.pm: pymem.Pymem | None = None

    def attach(self) -> None:
        pid = self._find_pid_by_name(self.process_name)
        if pid is None:
            raise ProcessNotFoundError(f"Process not found: {self.process_name}")

        self.pm = pymem.Pymem()
        self.pm.open_process_from_id(pid)

    def detach(self) -> None:
        if self.pm is not None:
            self.pm.close_process()
            self.pm = None

    def read_byte(self, address: int) -> int:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")
        return self.pm.read_uchar(address)

    def write_byte(self, address: int, value: int) -> PatchResult:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")

        try:
            old_value = self.pm.read_uchar(address)
            self.pm.write_uchar(address, value)
            return PatchResult(address=address, old_value=old_value, new_value=value)
        except Exception as exc:  # noqa: BLE001
            raise MemoryWriteError(f"Failed to write byte at 0x{address:X}: {exc}") from exc

    def apply_light_value(self, address_hex: str, value_hex: str) -> PatchResult:
        address = int(address_hex, 16)
        value = int(value_hex, 16)
        return self.write_byte(address, value)

    @staticmethod
    def _find_pid_by_name(process_name: str) -> int | None:
        target = process_name.lower()
        for proc in psutil.process_iter(attrs=["name", "pid"]):
            name = proc.info.get("name")
            if name and name.lower() == target:
                return int(proc.info["pid"])
        return None
