from __future__ import annotations

import argparse

from systool.pointers.memory_backend import DbvmBridgeBackend, LightMemoryController


def parse_int(value: str) -> int:
    return int(value.strip(), 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise the Studiomemuer DBVM bridge.")
    parser.add_argument("--process", default="miracle_gl.exe", help="Target process name used for attach/module lookup.")
    parser.add_argument("--cr3", help="Explicit target process CR3/DTB. If omitted, DBK auto-resolution is tried before STUDIOMEM_DBVM_CR3.")
    parser.add_argument("--read-physical", type=parse_int, help="Physical address to read.")
    parser.add_argument("--write-physical", type=parse_int, help="Physical address to write.")
    parser.add_argument("--read-virtual", type=parse_int, help="Target-process virtual address to read through CR3.")
    parser.add_argument("--write-virtual", type=parse_int, help="Target-process virtual address to write through CR3.")
    parser.add_argument("--data", default="", help="Hex bytes for write operations, e.g. D7 08.")
    parser.add_argument("--size", type=int, default=16, help="Read size in bytes.")
    args = parser.parse_args()

    backend = DbvmBridgeBackend(cr3=args.cr3)
    controller = LightMemoryController(args.process, backend=backend)
    controller.attach()
    print(f"Attached to {args.process} with DBVM version 0x{backend.version:X} and CR3 0x{backend.cr3:X}")

    if args.read_physical is not None:
        data = backend.read_physical(args.read_physical, args.size)
        print(f"physical[0x{args.read_physical:X}] = {data.hex(' ')}")

    if args.write_physical is not None:
        payload = bytes.fromhex(args.data)
        backend.write_physical(args.write_physical, payload)
        print(f"wrote {len(payload)} bytes to physical 0x{args.write_physical:X}")

    if args.read_virtual is not None:
        data = backend.read_bytes(args.read_virtual, args.size)
        print(f"virtual[0x{args.read_virtual:X}] = {data.hex(' ')}")

    if args.write_virtual is not None:
        payload = bytes.fromhex(args.data)
        backend.write_bytes(args.write_virtual, payload)
        print(f"wrote {len(payload)} bytes to virtual 0x{args.write_virtual:X}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
