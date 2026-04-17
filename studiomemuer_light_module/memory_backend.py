from __future__ import annotations

from dataclasses import dataclass
import re

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


class LightMemoryController:
    def __init__(self, process_name: str) -> None:
        self.process_name = process_name
        self.pm: pymem.Pymem | None = None

    # -------------------------
    # PROCESS ATTACH / DETACH
    # -------------------------
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

    # -------------------------
    # MEMORY PRIMITIVES
    # -------------------------
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
        except Exception as exc:
            raise MemoryWriteError(f"Failed to write byte at 0x{address:X}: {exc}") from exc

    # -------------------------
    # PROCESS / MODULE HELPERS
    # -------------------------
    @staticmethod
    def _find_pid_by_name(process_name: str) -> int | None:
        target = process_name.lower()

        for proc in psutil.process_iter(attrs=["name", "pid"]):
            name = proc.info.get("name")
            if name and target in name.lower():  # ✅ partial match fix
                return int(proc.info["pid"])

        return None

    def get_module_base(self, module_substr: str) -> int:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")

        module_substr = module_substr.lower()

        for module in self.pm.list_modules():
            if module_substr in module.name.lower():
                return module.lpBaseOfDll

        raise ProcessNotFoundError(f"Module not found: {module_substr}")

    # -------------------------
    # POINTER / SIGNATURE RESOLUTION
    # -------------------------
    def resolve_pointer_chain(self, module_base: int, offsets: list[int]) -> int:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")
        if not offsets:
            raise AddressResolveError("Pointer chain is empty.")

        addr = module_base + offsets[0]

        for offset in offsets[1:-1]:
            addr = self.pm.read_int(addr)
            addr += offset

        if len(offsets) == 1:
            return addr

        addr = self.pm.read_int(addr)
        return addr + offsets[-1]

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
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")

        module_base = self.get_module_base(module_name)

        # 1) Preferred strategy: stable pointer chains (module base + CE offsets)
        for chain in pointer_chains:
            try:
                candidate = self.resolve_pointer_chain(module_base, chain)
                self.pm.read_uchar(candidate)
                return candidate
            except (MemoryReadError, OSError, ValueError, AddressResolveError):
                continue
            except Exception:
                continue

        # 2) Fallback strategy: structure signature scan + known value offset.
        if signature_pattern:
            signature_addr = self.scan_signature_address(signature_pattern)
            if signature_addr is not None:
                base_addr = signature_addr + signature_offset_to_base
                candidate = base_addr + structure_value_offset
                try:
                    self.pm.read_uchar(candidate)
                    return candidate
                except Exception as exc:
                    raise AddressResolveError(
                        f"Signature found but computed light address is invalid: 0x{candidate:X}"
                    ) from exc

        raise AddressResolveError(
            "Unable to resolve light address. Add a valid pointer chain or adjust signature pattern."
        )

    def apply_light_value(
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

    # -------------------------
    # DEBUGGING
    # -------------------------
    def debug_resolve_pointer_chain(self, module_name: str, offsets: list[int]) -> int:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")

        base = self.get_module_base(module_name)

        print(f"[DEBUG] Module base: 0x{base:X}")
        print(f"[DEBUG] Pointer chain: {[hex(x) for x in offsets]}")

        final = self.resolve_pointer_chain(base, offsets)
        print(f"[DEBUG] Final address: 0x{final:X}")

        return final