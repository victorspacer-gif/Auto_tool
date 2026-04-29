from __future__ import annotations

from dataclasses import dataclass
import re
import threading

import psutil
import pymem
from pymem.exception import MemoryReadError


class ProcessNotFoundError(RuntimeError):
    pass


class MemoryWriteError(RuntimeError):
    pass


class AddressResolveError(RuntimeError):
    pass


@dataclass
class PatchResult:
    address: int
    old_value: int
    new_value: int


@dataclass
class LightPatchResult:
    color: PatchResult
    intensity: PatchResult


class LightMemoryController:
    """Thread-safe memory read/write controller for Windows processes.

    All public methods acquire an internal lock before calling into pymem,
    preventing concurrent ReadProcessMemory calls that can deadlock on Windows
    when the target process is momentarily unresponsive.
    """

    def __init__(self, process_name: str) -> None:
        self.process_name = process_name
        self.pm: pymem.Pymem | None = None
        self._lock = threading.RLock()

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
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")
            return self.pm.read_uchar(address)

    def write_byte(self, address: int, value: int) -> PatchResult:
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")

            try:
                old_value = self.pm.read_uchar(address)
                self.pm.write_uchar(address, value)
                return PatchResult(address=address, old_value=old_value, new_value=value)
            except Exception as exc:
                raise MemoryWriteError(f"Failed to write byte at 0x{address:X}: {exc}") from exc

    def read_double(self, address: int) -> float:
        """Read a double-precision floating-point value from the target process."""
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")
            return self.pm.read_double(address)

    def write_double(self, address: int, value: float) -> PatchResult:
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")

            try:
                old_value = self.pm.read_double(address)
                self.pm.write_double(address, value)
                return PatchResult(address=address, old_value=int(old_value), new_value=int(value))
            except Exception as exc:
                raise MemoryWriteError(f"Failed to write double at 0x{address:X}: {exc}") from exc

    @staticmethod
    def _find_pid_by_name(process_name: str) -> int | None:
        target = process_name.lower()
        for proc in psutil.process_iter(attrs=["name", "pid"]):
            name = proc.info.get("name")
            if name and target in name.lower():
                return int(proc.info["pid"])
        return None

    def get_module_base(self, module_substr: str) -> int:
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")

            modules = list(self.pm.list_modules())
            module_substr = module_substr.lower()
            for module in modules:
                if module_substr in module.name.lower():
                    return module.lpBaseOfDll

            # Some client variants rename the main executable (for example miracle_dx-*.exe)
            # while the imported CE pointers still reference the game's primary module base.
            # If the configured module name is absent, fall back to the attached process main module.
            for module in modules:
                if module.name.lower().endswith(".exe"):
                    return module.lpBaseOfDll

            if modules:
                return modules[0].lpBaseOfDll  # Fallback: use first module (usually main executable) when no substring match found

            raise ProcessNotFoundError(f"Module not found: {module_substr}")

    def resolve_pointer_chain(self, module_base: int, offsets: list[int]) -> int:
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")
            if not offsets:
                raise AddressResolveError("Pointer chain is empty.")

            cursor = module_base + offsets[0]  # First offset is relative to module base (not a pointer hop)
            if len(offsets) == 1:  # Single-element chain: direct address from module base, no indirection
                return cursor

            for index, offset in enumerate(offsets[1:], start=1):
                cursor = self.pm.read_int(cursor)
                if index < len(offsets) - 1:
                    cursor += offset
                else:
                    cursor = cursor + offset

            return cursor

    @staticmethod
    def _aob_to_regex(aob: str) -> bytes:
        tokens = [token for token in aob.strip().split() if token]
        parts: list[bytes] = []
        for token in tokens:
            if token == "??":
                parts.append(b".")
            elif re.fullmatch(r"[0-9a-fA-F]{2}", token):
                parts.append(re.escape(bytes.fromhex(token)))
            else:
                raise AddressResolveError(f"Invalid AOB token: {token}")
        return b"".join(parts)

    def scan_signature_address(self, aob_pattern: str) -> int | None:
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")

            signature = self._aob_to_regex(aob_pattern)

            for region in self.pm.list_modules():
                try:
                    data = self.pm.read_bytes(region.lpBaseOfDll, region.SizeOfImage)
                except Exception:
                    continue

                match = re.search(signature, data, flags=re.DOTALL)
                if match:
                    return region.lpBaseOfDll + match.start()

            return None

    def resolve_light_address(
        self,
        module_name: str,
        pointer_chains: list[list[int]],
        structure_value_offset: int,
        signature_pattern: str | None = None,
        signature_offset_to_base: int = 0,
    ) -> int:
        with self._lock:
            if self.pm is None:
                raise ProcessNotFoundError("Not attached to process.")

            module_base = self.get_module_base(module_name)

            for chain in pointer_chains:
                try:
                    base_candidate = self.resolve_pointer_chain(module_base, chain)
                    target_candidate = base_candidate + structure_value_offset
                    self.pm.read_uchar(target_candidate)
                    return target_candidate
                except (MemoryReadError, OSError, ValueError, AddressResolveError):
                    continue
                except Exception:
                    continue

            if signature_pattern:
                signature_addr = self.scan_signature_address(signature_pattern)
                if signature_addr is not None:
                    base_addr = signature_addr + signature_offset_to_base
                    target = base_addr + structure_value_offset
                    try:
                        self.pm.read_uchar(target)
                        return target
                    except Exception as exc:
                        raise AddressResolveError(
                            f"Signature found but computed target is invalid: 0x{target:X}"
                        ) from exc

            raise AddressResolveError("Unable to resolve light address from pointer chains/signature.")

    def apply_light_value(self, address_hex: str, value_hex: str) -> PatchResult:
        address = int(address_hex, 16)
        value = int(value_hex, 16)
        return self.write_byte(address, value)

    def apply_light_by_resolver(
        self,
        module_name: str,
        pointer_chains: list[list[int]],
        structure_value_offset: int,
        value_hex: str,
        signature_pattern: str | None = None,
        signature_offset_to_base: int = 0,
    ) -> PatchResult:
        address = self.resolve_light_address(
            module_name=module_name,
            pointer_chains=pointer_chains,
            structure_value_offset=structure_value_offset,
            signature_pattern=signature_pattern,
            signature_offset_to_base=signature_offset_to_base,
        )
        value = int(value_hex, 16)
        return self.write_byte(address, value)

    def resolve_light_pair_addresses(
        self,
        module_name: str,
        pointer_chains: list[list[int]],
        structure_value_offset: int = 0,
        signature_pattern: str | None = None,
        signature_offset_to_base: int = 0,
    ) -> tuple[int, int]:
        color_address = self.resolve_light_address(
            module_name=module_name,
            pointer_chains=pointer_chains,
            structure_value_offset=structure_value_offset,
            signature_pattern=signature_pattern,
            signature_offset_to_base=signature_offset_to_base,
        )
        intensity_address = color_address + 1
        try:
            self.read_byte(intensity_address)
        except Exception as exc:
            raise AddressResolveError(
                f"Resolved color address 0x{color_address:X}, but intensity byte 0x{intensity_address:X} is invalid."
            ) from exc
        return color_address, intensity_address

    def write_light_pair(self, color_address: int, color_value: int, intensity_value: int) -> LightPatchResult:
        return LightPatchResult(
            color=self.write_byte(color_address, color_value),
            intensity=self.write_byte(color_address + 1, intensity_value),
        )

    def apply_light_pair_by_resolver(
        self,
        module_name: str,
        pointer_chains: list[list[int]],
        color_value: int,
        intensity_value: int,
        structure_value_offset: int = 0,
        signature_pattern: str | None = None,
        signature_offset_to_base: int = 0,
    ) -> LightPatchResult:
        color_address, _intensity_address = self.resolve_light_pair_addresses(
            module_name=module_name,
            pointer_chains=pointer_chains,
            structure_value_offset=structure_value_offset,
            signature_pattern=signature_pattern,
            signature_offset_to_base=signature_offset_to_base,
        )
        return self.write_light_pair(color_address, color_value, intensity_value)
