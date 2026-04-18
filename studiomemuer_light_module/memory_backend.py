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
        except Exception as exc:
            raise MemoryWriteError(f"Failed to write byte at 0x{address:X}: {exc}") from exc

    @staticmethod
    def _find_pid_by_name(process_name: str) -> int | None:
        target = process_name.lower()
        for proc in psutil.process_iter(attrs=["name", "pid"]):
            name = proc.info.get("name")
            if name and target in name.lower():
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

    def resolve_pointer_chain(self, module_base: int, offsets: list[int]) -> int:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")
        if not offsets:
            raise AddressResolveError("Pointer chain is empty.")

        cursor = module_base + offsets[0]
        if len(offsets) == 1:
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
