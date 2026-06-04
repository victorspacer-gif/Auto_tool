from __future__ import annotations

import argparse
from pathlib import Path
import struct


def main() -> int:
    parser = argparse.ArgumentParser(description="Print PE exports from studiomem_bridge.dll.")
    parser.add_argument(
        "dll",
        nargs="?",
        default=Path(__file__).resolve().parent / "build" / "Release" / "studiomem_bridge.dll",
        type=Path,
        help="Path to studiomem_bridge.dll.",
    )
    args = parser.parse_args()

    dll_path = args.dll.resolve()
    print(f"DLL path: {dll_path}")
    if not dll_path.exists():
        print("DLL does not exist.")
        return 1

    exports = pe_export_names(dll_path)
    if exports is None:
        print("Exports unavailable: file is not a readable PE DLL.")
        return 1

    for name in exports:
        print(name)

    print(f"\nsmem_resolve_process_cr3 exported: {'smem_resolve_process_cr3' in exports}")
    return 0 if "smem_resolve_process_cr3" in exports else 2


def pe_export_names(dll_path: Path) -> list[str] | None:
    try:
        data = dll_path.read_bytes()
        if len(data) < 0x100 or data[:2] != b"MZ":
            return None

        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_offset:pe_offset + 4] != b"PE\0\0":
            return None

        coff_offset = pe_offset + 4
        section_count = struct.unpack_from("<H", data, coff_offset + 2)[0]
        optional_size = struct.unpack_from("<H", data, coff_offset + 16)[0]
        optional_offset = coff_offset + 20
        magic = struct.unpack_from("<H", data, optional_offset)[0]
        data_directory_offset = optional_offset + (112 if magic == 0x20B else 96 if magic == 0x10B else 0)
        if data_directory_offset == optional_offset:
            return None

        export_rva, export_size = struct.unpack_from("<II", data, data_directory_offset)
        if export_rva == 0 or export_size == 0:
            return []

        sections = []
        section_offset = optional_offset + optional_size
        for index in range(section_count):
            offset = section_offset + index * 40
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
            sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer, raw_size))

        export_offset = rva_to_file_offset(export_rva, sections)
        if export_offset is None:
            return None

        number_of_names = struct.unpack_from("<I", data, export_offset + 24)[0]
        address_of_names = struct.unpack_from("<I", data, export_offset + 32)[0]
        names_offset = rva_to_file_offset(address_of_names, sections)
        if names_offset is None:
            return None

        names: list[str] = []
        for index in range(number_of_names):
            name_rva = struct.unpack_from("<I", data, names_offset + index * 4)[0]
            name_offset = rva_to_file_offset(name_rva, sections)
            if name_offset is None:
                continue
            end = data.find(b"\0", name_offset)
            if end == -1:
                continue
            names.append(data[name_offset:end].decode("ascii", errors="replace"))
        return sorted(names)
    except Exception:
        return None


def rva_to_file_offset(rva: int, sections: list[tuple[int, int, int, int]]) -> int | None:
    for virtual_address, virtual_size, raw_pointer, raw_size in sections:
        if virtual_address <= rva < virtual_address + virtual_size:
            offset = raw_pointer + (rva - virtual_address)
            return offset if offset < raw_pointer + raw_size else None
    return None


if __name__ == "__main__":
    raise SystemExit(main())
