from __future__ import annotations

from dataclasses import dataclass
import ctypes as ct
from ctypes import wintypes
import os
from pathlib import Path
import re
import struct
import threading
from typing import Protocol

import psutil
import pymem


class ProcessNotFoundError(RuntimeError):
    pass


class MemoryReadError(RuntimeError):
    pass


class MemoryWriteError(RuntimeError):
    pass


class AddressResolveError(RuntimeError):
    pass


class DriverBridgeError(RuntimeError):
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


class MemoryBackend(Protocol):
    """Raw memory backend contract.

    Callers pass a process id plus target-process virtual addresses. Any driver,
    physical-address, CR3/DTB, or page-boundary details belong below this layer.
    """

    pid: int | None

    def attach(self, process_name: str) -> None:
        ...

    def detach(self) -> None:
        ...

    def get_module_base(self, module_substr: str) -> int:
        ...

    def read_bytes(self, address: int, size: int) -> bytes:
        ...

    def write_bytes(self, address: int, data: bytes) -> None:
        ...


class PymemBackend:
    """Memory backend backed by pymem's user-mode process handle."""

    def __init__(self) -> None:
        self.pm: pymem.Pymem | None = None
        self.pid: int | None = None

    def attach(self, process_name: str) -> None:
        pid = _find_pid_by_name(process_name)
        if pid is None:
            raise ProcessNotFoundError(f"Process not found: {process_name}")

        pm = pymem.Pymem()
        pm.open_process_from_id(pid)
        self.pm = pm
        self.pid = pid

    def detach(self) -> None:
        if self.pm is not None:
            self.pm.close_process()
        self.pm = None
        self.pid = None

    def get_module_base(self, module_substr: str) -> int:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")

        module_substr = module_substr.lower()
        modules = list(self.pm.list_modules())
        for module in modules:
            if module_substr in module.name.lower():
                return int(module.lpBaseOfDll)

        for module in modules:
            if module.name.lower().endswith(".exe"):
                return int(module.lpBaseOfDll)

        if modules:
            return int(modules[0].lpBaseOfDll)

        raise ProcessNotFoundError(f"Module not found: {module_substr}")

    def read_bytes(self, address: int, size: int) -> bytes:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")
        try:
            return self.pm.read_bytes(address, size)
        except Exception as exc:
            raise MemoryReadError(f"Failed to read {size} bytes at 0x{address:X}: {exc}") from exc

    def write_bytes(self, address: int, data: bytes) -> None:
        if self.pm is None:
            raise ProcessNotFoundError("Not attached to process.")
        try:
            self.pm.write_bytes(address, data, len(data))
        except Exception as exc:
            raise MemoryWriteError(f"Failed to write {len(data)} bytes at 0x{address:X}: {exc}") from exc


class SmemStatus:
    OK = 0
    NOT_INITIALIZED = 1
    DRIVER_UNAVAILABLE = 2
    PROCESS_NOT_FOUND = 3
    INVALID_ARGUMENT = 4
    INVALID_ADDRESS = 5
    PARTIAL_COPY = 6
    ACCESS_DENIED = 7
    INTERNAL = 100


class DriverBridgeBackend:
    """ctypes wrapper for studiomem_bridge.dll.

    Python owns all buffers. The DLL only receives caller-provided memory and
    returns byte counts/status codes; it never allocates memory for Python.
    """

    def __init__(self, dll_path: str | os.PathLike[str] | None = None) -> None:
        self.pid: int | None = None
        self._dll_path = Path(dll_path) if dll_path is not None else _default_bridge_path()
        self._dll = ct.WinDLL(str(self._dll_path))
        self._bind_exports()

    def _bind_exports(self) -> None:
        u32 = ct.c_uint32
        u64 = ct.c_uint64

        self._dll.smem_initialize.argtypes = []
        self._dll.smem_initialize.restype = ct.c_int

        self._dll.smem_shutdown.argtypes = []
        self._dll.smem_shutdown.restype = ct.c_int

        self._dll.smem_attach_process.argtypes = [ct.c_wchar_p, ct.POINTER(u32)]
        self._dll.smem_attach_process.restype = ct.c_int

        self._dll.smem_open_process.argtypes = [u32]
        self._dll.smem_open_process.restype = ct.c_int

        self._dll.smem_close_process.argtypes = []
        self._dll.smem_close_process.restype = ct.c_int

        self._dll.smem_get_module_base.argtypes = [
            u32,
            ct.c_wchar_p,
            ct.POINTER(u64),
            ct.POINTER(u64),
        ]
        self._dll.smem_get_module_base.restype = ct.c_int

        self._dll.smem_read_virtual.argtypes = [
            u32,
            u64,
            ct.c_void_p,
            u64,
            ct.POINTER(u64),
        ]
        self._dll.smem_read_virtual.restype = ct.c_int

        self._dll.smem_write_virtual.argtypes = [
            u32,
            u64,
            ct.c_void_p,
            u64,
            ct.POINTER(u64),
        ]
        self._dll.smem_write_virtual.restype = ct.c_int

        self._dll.smem_last_error.argtypes = [ct.c_wchar_p, u32]
        self._dll.smem_last_error.restype = ct.c_int

    def attach(self, process_name: str) -> None:
        self._check(self._dll.smem_initialize(), "driver bridge initialization")

        pid = ct.c_uint32()
        status = self._dll.smem_attach_process(process_name, ct.byref(pid))
        if status == SmemStatus.PROCESS_NOT_FOUND:
            raise ProcessNotFoundError(f"Process not found: {process_name}")
        self._check(status, f"attach to {process_name}")
        self.pid = int(pid.value)

    def detach(self) -> None:
        try:
            self._check(self._dll.smem_close_process(), "close driver bridge process")
            self._check(self._dll.smem_shutdown(), "driver bridge shutdown")
        finally:
            self.pid = None

    def get_module_base(self, module_substr: str) -> int:
        if self.pid is None:
            raise ProcessNotFoundError("Not attached to process.")

        base = ct.c_uint64()
        size = ct.c_uint64()
        status = self._dll.smem_get_module_base(
            self.pid,
            module_substr,
            ct.byref(base),
            ct.byref(size),
        )
        if status == SmemStatus.PROCESS_NOT_FOUND:
            raise ProcessNotFoundError(f"Module not found: {module_substr}")
        self._check(status, f"module lookup {module_substr}")
        return int(base.value)

    def read_bytes(self, address: int, size: int) -> bytes:
        if self.pid is None:
            raise ProcessNotFoundError("Not attached to process.")
        if size <= 0:
            raise ValueError("Read size must be positive.")

        buffer = ct.create_string_buffer(size)
        bytes_read = ct.c_uint64()
        status = self._dll.smem_read_virtual(
            self.pid,
            ct.c_uint64(address),
            ct.cast(buffer, ct.c_void_p),
            ct.c_uint64(size),
            ct.byref(bytes_read),
        )
        if status == SmemStatus.PARTIAL_COPY or bytes_read.value != size:
            raise MemoryReadError(
                f"Partial read at 0x{address:X}: {bytes_read.value}/{size} bytes"
            )
        self._check(status, f"read 0x{address:X}")
        return bytes(buffer.raw)

    def write_bytes(self, address: int, data: bytes) -> None:
        if self.pid is None:
            raise ProcessNotFoundError("Not attached to process.")
        if not data:
            raise ValueError("Write buffer must not be empty.")

        buffer = ct.create_string_buffer(data, len(data))
        bytes_written = ct.c_uint64()
        status = self._dll.smem_write_virtual(
            self.pid,
            ct.c_uint64(address),
            ct.cast(buffer, ct.c_void_p),
            ct.c_uint64(len(data)),
            ct.byref(bytes_written),
        )
        if status == SmemStatus.PARTIAL_COPY or bytes_written.value != len(data):
            raise MemoryWriteError(
                f"Partial write at 0x{address:X}: {bytes_written.value}/{len(data)} bytes"
            )
        self._check(status, f"write 0x{address:X}", memory_error=MemoryWriteError)

    def _check(
        self,
        status: int,
        operation: str,
        memory_error: type[RuntimeError] = MemoryReadError,
    ) -> None:
        if status == SmemStatus.OK:
            return

        message = self._last_error_message()
        if status == SmemStatus.PROCESS_NOT_FOUND:
            raise ProcessNotFoundError(f"{operation} failed: {message}")
        if status in (SmemStatus.INVALID_ADDRESS, SmemStatus.PARTIAL_COPY):
            raise memory_error(f"{operation} failed [{status}]: {message}")
        if status == SmemStatus.ACCESS_DENIED:
            raise PermissionError(f"{operation} failed [{status}]: {message}")
        raise DriverBridgeError(f"{operation} failed [{status}]: {message}")

    def _last_error_message(self) -> str:
        buffer = ct.create_unicode_buffer(512)
        try:
            self._dll.smem_last_error(buffer, len(buffer))
        except Exception:
            return "No bridge error message available."
        return buffer.value or "No bridge error message available."


class DbvmBridgeBackend:
    """DBVM-level backend using VMCall plus target-process CR3.

    Explicit CR3 configuration wins. Otherwise attach resolves PID-to-CR3
    through the Studiomemuer DBK device when available, with
    STUDIOMEM_DBVM_CR3 retained as a fallback.
    """

    def __init__(
        self,
        dll_path: str | os.PathLike[str] | None = None,
        cr3: int | str | None = None,
    ) -> None:
        self.pid: int | None = None
        self.cr3 = _parse_int(cr3)
        self._env_cr3 = _parse_int(os.environ.get("STUDIOMEM_DBVM_CR3"))
        self._driver_initialized = False
        self.version: int | None = None
        self._dll_path = Path(dll_path) if dll_path is not None else _default_bridge_path()
        self._dll = ct.WinDLL(str(self._dll_path))
        self._bind_exports()

    def _bind_exports(self) -> None:
        u32 = ct.c_uint32
        u64 = ct.c_uint64

        self._dll.smem_initialize.argtypes = []
        self._dll.smem_initialize.restype = ct.c_int

        self._dll.smem_shutdown.argtypes = []
        self._dll.smem_shutdown.restype = ct.c_int

        self._dll.smem_resolve_process_cr3.argtypes = [u32, ct.POINTER(u64)]
        self._dll.smem_resolve_process_cr3.restype = ct.c_int

        self._dll.smem_dbvm_initialize.argtypes = []
        self._dll.smem_dbvm_initialize.restype = ct.c_int

        self._dll.smem_dbvm_get_version.argtypes = [ct.POINTER(u32)]
        self._dll.smem_dbvm_get_version.restype = ct.c_int

        self._dll.smem_dbvm_read_physical.argtypes = [
            u64,
            ct.c_void_p,
            u64,
            ct.POINTER(u64),
        ]
        self._dll.smem_dbvm_read_physical.restype = ct.c_int

        self._dll.smem_dbvm_write_physical.argtypes = [
            u64,
            ct.c_void_p,
            u64,
            ct.POINTER(u64),
        ]
        self._dll.smem_dbvm_write_physical.restype = ct.c_int

        self._dll.smem_dbvm_read_virtual.argtypes = [
            u64,
            u64,
            ct.c_void_p,
            u64,
            ct.POINTER(u64),
        ]
        self._dll.smem_dbvm_read_virtual.restype = ct.c_int

        self._dll.smem_dbvm_write_virtual.argtypes = [
            u64,
            u64,
            ct.c_void_p,
            u64,
            ct.POINTER(u64),
        ]
        self._dll.smem_dbvm_write_virtual.restype = ct.c_int

        self._dll.smem_last_error.argtypes = [ct.c_wchar_p, u32]
        self._dll.smem_last_error.restype = ct.c_int

    def attach(self, process_name: str) -> None:
        pid = _find_pid_by_name(process_name)
        if pid is None:
            raise ProcessNotFoundError(f"Process not found: {process_name}")
        if self.cr3 is None or self.cr3 == 0:
            self.cr3 = self._resolve_process_cr3_with_fallback(pid)

        self._check(self._dll.smem_dbvm_initialize(), "DBVM initialization")
        version = ct.c_uint32()
        self._check(self._dll.smem_dbvm_get_version(ct.byref(version)), "DBVM version query")
        self.version = int(version.value)
        self.pid = pid

    def detach(self) -> None:
        if self._driver_initialized:
            try:
                self._check(self._dll.smem_shutdown(), "driver bridge shutdown")
            finally:
                self._driver_initialized = False
        self.pid = None

    def get_module_base(self, module_substr: str) -> int:
        if self.pid is None:
            raise ProcessNotFoundError("Not attached to process.")
        return _get_module_base_toolhelp(self.pid, module_substr)

    def read_bytes(self, address: int, size: int) -> bytes:
        if self.pid is None:
            raise ProcessNotFoundError("Not attached to process.")
        if self.cr3 is None or self.cr3 == 0:
            raise DriverBridgeError("DBVM CR3 is not configured.")
        if size <= 0:
            raise ValueError("Read size must be positive.")

        buffer = ct.create_string_buffer(size)
        bytes_read = ct.c_uint64()
        status = self._dll.smem_dbvm_read_virtual(
            ct.c_uint64(self.cr3),
            ct.c_uint64(address),
            ct.cast(buffer, ct.c_void_p),
            ct.c_uint64(size),
            ct.byref(bytes_read),
        )
        if status == SmemStatus.PARTIAL_COPY or bytes_read.value != size:
            raise MemoryReadError(
                f"DBVM partial virtual read at 0x{address:X}: {bytes_read.value}/{size} bytes"
            )
        self._check(status, f"DBVM virtual read 0x{address:X}")
        return bytes(buffer.raw)

    def write_bytes(self, address: int, data: bytes) -> None:
        if self.pid is None:
            raise ProcessNotFoundError("Not attached to process.")
        if self.cr3 is None or self.cr3 == 0:
            raise DriverBridgeError("DBVM CR3 is not configured.")
        if not data:
            raise ValueError("Write buffer must not be empty.")

        buffer = ct.create_string_buffer(data, len(data))
        bytes_written = ct.c_uint64()
        status = self._dll.smem_dbvm_write_virtual(
            ct.c_uint64(self.cr3),
            ct.c_uint64(address),
            ct.cast(buffer, ct.c_void_p),
            ct.c_uint64(len(data)),
            ct.byref(bytes_written),
        )
        if status == SmemStatus.PARTIAL_COPY or bytes_written.value != len(data):
            raise MemoryWriteError(
                f"DBVM partial virtual write at 0x{address:X}: {bytes_written.value}/{len(data)} bytes"
            )
        self._check(status, f"DBVM virtual write 0x{address:X}", memory_error=MemoryWriteError)

    def read_physical(self, physical_address: int, size: int) -> bytes:
        if size <= 0:
            raise ValueError("Read size must be positive.")
        buffer = ct.create_string_buffer(size)
        bytes_read = ct.c_uint64()
        status = self._dll.smem_dbvm_read_physical(
            ct.c_uint64(physical_address),
            ct.cast(buffer, ct.c_void_p),
            ct.c_uint64(size),
            ct.byref(bytes_read),
        )
        if status == SmemStatus.PARTIAL_COPY or bytes_read.value != size:
            raise MemoryReadError(
                f"DBVM partial physical read at 0x{physical_address:X}: {bytes_read.value}/{size} bytes"
            )
        self._check(status, f"DBVM physical read 0x{physical_address:X}")
        return bytes(buffer.raw)

    def write_physical(self, physical_address: int, data: bytes) -> None:
        if not data:
            raise ValueError("Write buffer must not be empty.")
        buffer = ct.create_string_buffer(data, len(data))
        bytes_written = ct.c_uint64()
        status = self._dll.smem_dbvm_write_physical(
            ct.c_uint64(physical_address),
            ct.cast(buffer, ct.c_void_p),
            ct.c_uint64(len(data)),
            ct.byref(bytes_written),
        )
        if status == SmemStatus.PARTIAL_COPY or bytes_written.value != len(data):
            raise MemoryWriteError(
                f"DBVM partial physical write at 0x{physical_address:X}: {bytes_written.value}/{len(data)} bytes"
            )
        self._check(status, f"DBVM physical write 0x{physical_address:X}", memory_error=MemoryWriteError)

    def _resolve_process_cr3_with_fallback(self, pid: int) -> int:
        auto_error: str | None = None

        try:
            self._check(self._dll.smem_initialize(), "driver bridge initialization for CR3 resolution")
            self._driver_initialized = True

            cr3 = ct.c_uint64()
            self._check(
                self._dll.smem_resolve_process_cr3(ct.c_uint32(pid), ct.byref(cr3)),
                f"resolve CR3 for PID {pid}",
            )
            if cr3.value:
                return int(cr3.value)
        except Exception as exc:
            auto_error = str(exc)

        if self._env_cr3:
            return self._env_cr3

        message = (
            f"DBVM backend could not resolve CR3 automatically for PID {pid}."
        )
        if auto_error:
            message += f" Automatic resolution failed: {auto_error}."
        message += (
            " Set STUDIOMEM_DBVM_CR3 or pass --cr3, for example "
            "$env:STUDIOMEM_DBVM_CR3='0x12345000'."
        )
        raise DriverBridgeError(message)

    def _check(
        self,
        status: int,
        operation: str,
        memory_error: type[RuntimeError] = MemoryReadError,
    ) -> None:
        if status == SmemStatus.OK:
            return
        message = self._last_error_message()
        if status in (SmemStatus.INVALID_ADDRESS, SmemStatus.PARTIAL_COPY):
            raise memory_error(f"{operation} failed [{status}]: {message}")
        if status == SmemStatus.ACCESS_DENIED:
            raise PermissionError(f"{operation} failed [{status}]: {message}")
        raise DriverBridgeError(f"{operation} failed [{status}]: {message}")

    def _last_error_message(self) -> str:
        buffer = ct.create_unicode_buffer(512)
        try:
            self._dll.smem_last_error(buffer, len(buffer))
        except Exception:
            return "No bridge error message available."
        return buffer.value or "No bridge error message available."


class LightMemoryController:
    """Thread-safe typed memory controller for Windows processes."""

    def __init__(self, process_name: str, backend: MemoryBackend | None = None) -> None:
        self.process_name = process_name
        self.backend: MemoryBackend = backend or PymemBackend()
        self._lock = threading.RLock()

    @property
    def pid(self) -> int | None:
        return self.backend.pid

    def attach(self) -> None:
        with self._lock:
            self.backend.attach(self.process_name)

    def detach(self) -> None:
        with self._lock:
            self.backend.detach()

    def read_byte(self, address: int) -> int:
        with self._lock:
            return self.backend.read_bytes(address, 1)[0]

    def write_byte(self, address: int, value: int) -> PatchResult:
        if not 0 <= value <= 0xFF:
            raise ValueError(f"Byte value out of range: {value}")

        with self._lock:
            try:
                old_value = self.read_byte(address)
                self.backend.write_bytes(address, bytes([value]))
                return PatchResult(address=address, old_value=old_value, new_value=value)
            except Exception as exc:
                if isinstance(exc, MemoryWriteError):
                    raise
                raise MemoryWriteError(f"Failed to write byte at 0x{address:X}: {exc}") from exc

    def read_double(self, address: int) -> float:
        with self._lock:
            return struct.unpack("<d", self.backend.read_bytes(address, 8))[0]

    def write_double(self, address: int, value: float) -> PatchResult:
        with self._lock:
            try:
                old_value = self.read_double(address)
                self.backend.write_bytes(address, struct.pack("<d", value))
                return PatchResult(address=address, old_value=int(old_value), new_value=int(value))
            except Exception as exc:
                if isinstance(exc, MemoryWriteError):
                    raise
                raise MemoryWriteError(f"Failed to write double at 0x{address:X}: {exc}") from exc

    def read_pointer(self, address: int) -> int:
        with self._lock:
            return struct.unpack("<Q", self.backend.read_bytes(address, 8))[0]

    def get_module_base(self, module_substr: str) -> int:
        with self._lock:
            return self.backend.get_module_base(module_substr)

    def resolve_pointer_chain(self, module_base: int, offsets: list[int]) -> int:
        with self._lock:
            if not offsets:
                raise AddressResolveError("Pointer chain is empty.")

            cursor = module_base + offsets[0]
            if len(offsets) == 1:
                return cursor

            for offset in offsets[1:]:
                cursor = self.read_pointer(cursor) + offset

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
        raise AddressResolveError(
            "Signature scanning requires a backend module-region iterator. "
            "Pointer chains remain supported for both pymem and driver backends."
        )

    def resolve_light_address(
        self,
        module_name: str,
        pointer_chains: list[list[int]],
        structure_value_offset: int,
        signature_pattern: str | None = None,
        signature_offset_to_base: int = 0,
    ) -> int:
        with self._lock:
            module_base = self.get_module_base(module_name)

            for chain in pointer_chains:
                try:
                    base_candidate = self.resolve_pointer_chain(module_base, chain)
                    target_candidate = base_candidate + structure_value_offset
                    self.read_byte(target_candidate)
                    return target_candidate
                except Exception:
                    continue

            if signature_pattern:
                signature_addr = self.scan_signature_address(signature_pattern)
                if signature_addr is not None:
                    base_addr = signature_addr + signature_offset_to_base
                    target = base_addr + structure_value_offset
                    try:
                        self.read_byte(target)
                        return target
                    except Exception as exc:
                        raise AddressResolveError(
                            f"Signature found but computed target is invalid: 0x{target:X}"
                        ) from exc

            raise AddressResolveError("Unable to resolve light address from pointer chains/signature.")

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


def _find_pid_by_name(process_name: str) -> int | None:
    target = process_name.lower()
    for proc in psutil.process_iter(attrs=["name", "pid"]):
        name = proc.info.get("name")
        if name and target in name.lower():
            return int(proc.info["pid"])
    return None


def _parse_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text, 0)


class _MODULEENTRY32W(ct.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ct.POINTER(ct.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * 256),
        ("szExePath", wintypes.WCHAR * 260),
    ]


def _get_module_base_toolhelp(pid: int, module_substr: str) -> int:
    kernel32 = ct.WinDLL("kernel32", use_last_error=True)
    snapshot_flags = 0x00000008 | 0x00000010  # TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
    invalid_handle = wintypes.HANDLE(-1).value

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ct.POINTER(_MODULEENTRY32W)]
    kernel32.Module32FirstW.restype = wintypes.BOOL
    kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ct.POINTER(_MODULEENTRY32W)]
    kernel32.Module32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(snapshot_flags, pid)
    if snapshot == invalid_handle:
        raise ProcessNotFoundError(f"Unable to snapshot modules for PID {pid}: {ct.get_last_error()}")

    target = module_substr.lower()
    fallback: int | None = None
    entry = _MODULEENTRY32W()
    entry.dwSize = ct.sizeof(entry)
    try:
        ok = bool(kernel32.Module32FirstW(snapshot, ct.byref(entry)))
        while ok:
            name = str(entry.szModule)
            path = str(entry.szExePath)
            base = ct.cast(entry.modBaseAddr, ct.c_void_p).value or 0
            if fallback is None and name.lower().endswith(".exe"):
                fallback = int(base)
            if target in name.lower() or target in path.lower():
                return int(base)
            ok = bool(kernel32.Module32NextW(snapshot, ct.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)

    if fallback is not None:
        return fallback
    raise ProcessNotFoundError(f"Module not found: {module_substr}")


def _default_bridge_path() -> Path:
    local = Path(__file__).with_name("studiomem_bridge.dll")
    if local.exists():
        return local

    root = Path(__file__).resolve().parents[2]
    return root / "bridge" / "build" / "Release" / "studiomem_bridge.dll"
