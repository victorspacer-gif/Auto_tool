# Studiomemuer Light Favorites Export

This package is an export-ready Python module set for Tkinter projects.

It provides:

- Process attach by executable name
- Byte patch writing at a known address
- Preset for the light-effect byte change (`0x07 -> 0x11`)
- Simple Tkinter UI to test and apply

## Files

- `memory_backend.py`: process/memory operations
- `light_profile.py`: configurable profile data
- `tk_light_tool.py`: Tkinter utility window
- `requirements.txt`: dependencies

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python tk_light_tool.py
```

## Integrate in another project

Copy this folder into your target app and import:

```python
from memory_backend import LightMemoryController
from light_profile import DEFAULT_PROFILE
```

Then call `controller.apply_light_value(...)` using your selected profile.
