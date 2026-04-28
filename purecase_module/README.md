# purecase_module

Python module for locating a PureCase or Sandboxie-Plus installation, creating/configuring boxes, and launching processes with `Start.exe`.

## Quick Example

```python
from pathlib import Path

from purecase_module.runtime import find_installation, launch_in_box

project_root = Path(__file__).resolve().parent
installation = find_installation(project_root=project_root)
if installation is None:
    raise RuntimeError("PureCase/Sandboxie not found.")

launch_in_box(
    installation,
    box_name="TargetBox01",
    executable=r"C:\path\to\app.exe",
    args=["--mode", "safe"],
)
```

## Main API

- `find_installation(...)` — Locate a PureCase or Sandboxie installation on disk.
- `ensure_box(...)` — Create a sandbox box if it doesn't exist.
- `configure_box(...)` — Write Sandboxie.ini settings for a box.
- `launch_in_box(...)` — Launch an executable inside a Sandboxie-Plus box.
- `list_box_pids(...)` — List running processes in a box.
- `terminate_box(...)` — Kill all processes in a box.

## Backends

Two isolation backends are supported:

1. **Job Object (built-in)** — Restricts clipboard, display settings, atom table; auto-kills children on close. No extra software needed.
2. **Sandboxie-Plus** — Kernel-driver level isolation with full file-system and registry redirection, hidden process list, network control. Requires Sandboxie-Plus installed (`sandboxie-plus.com`).

## Requirements

```bash
pip install pywin32
```

Sandboxie-Plus is optional but recommended for strongest isolation.
