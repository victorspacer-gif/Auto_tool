# studiomem bridge

This directory builds `studiomem_bridge.dll`, the stable C ABI consumed by
`systool.pointers.memory_backend.DriverBridgeBackend`.

The local portable app is branded `Studiomemuer` / `Studiomemuer 7.5.1`.
Its binary still embeds the CE DBK device defaults `CEDRIVER73`,
`DBKProcList60`, `DBKThreadList60`, and `driver64.dat`, so the bridge opens
`\\.\CEDRIVER73` by default.

The exported DLL surface intentionally accepts only:

- process id
- target-process virtual address
- caller-owned byte buffers
- caller-owned byte-count outputs

All DBK/DBVM-specific work belongs in `driver_adapter.cpp`:

- opening/validating the already-loaded driver
- resolving process context/CR3/DTB if required
- translating target virtual addresses as required by the driver
- issuing the actual read/write requests

`studiomem_bridge.cpp` handles argument validation, status normalization,
module lookup, error text, and page-boundary splitting before invoking the
adapter's page-contained chunk functions.

Build with a Visual Studio x64 developer prompt:

```powershell
cmake -S bridge -B bridge\build -A x64
cmake --build bridge\build --config Release
```

Copy or package the resulting DLL as:

```text
systool\pointers\studiomem_bridge.dll
```

The PyInstaller spec also collects `bridge\build\Release\studiomem_bridge.dll`
when it exists.

If a fork changes the DBK symbolic link name, set:

```powershell
$env:STUDIOMEM_DBK_DEVICE='\\.\YourDeviceName'
```

## DBVM Backend

The DBVM path is separate from the DBK driver path. It does not open
`\\.\CEDRIVER73` for memory I/O. Instead, the bridge issues VMCall/VMMCall operations for:

- DBVM version detection
- physical memory read/write
- CR3-based x64 virtual-to-physical page walking
- virtual memory read/write after translation

Start DBVM in Studiomemuer first. During attach, the Python backend discovers
the target PID and asks the already-loaded DBK driver for that process CR3 via
Cheat Engine's `IOCTL_CE_GETCR3`. An explicit `--cr3` value still wins, and
`STUDIOMEM_DBVM_CR3` remains a fallback when automatic DBK resolution is not
available:

```powershell
$env:STUDIOMEM_DBVM_CR3='0x12345000'
```

In the Light Control tab, choose backend `dbvm`. The Python backend will use
the automatically resolved CR3 for all target-process virtual reads/writes.

Example direct exercise:

```powershell
python examples\dbvm_bridge_usage.py --process miracle_gl.exe --read-virtual 0x7ff600001000 --size 16
python examples\dbvm_bridge_usage.py --process miracle_gl.exe --cr3 0x12345000 --read-virtual 0x7ff600001000 --size 16
python examples\dbvm_bridge_usage.py --process miracle_gl.exe --cr3 0x12345000 --read-physical 0x100000 --size 16
```

Module base lookup still uses Windows Toolhelp snapshots; memory reads/writes
themselves use DBVM. Automatic CR3 discovery depends on the DBK device being
loaded and reachable through `STUDIOMEM_DBK_DEVICE` or the default
`\\.\CEDRIVER73`.
