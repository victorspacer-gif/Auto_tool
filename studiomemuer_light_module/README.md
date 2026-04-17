# Studiomemuer Light Favorites Export

This package is an export-ready Python module set for Tkinter projects.

It provides:

- Process attach by executable name
- Dynamic address resolution (pointer chains + signature fallback)
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

## Resolver strategy

1. Try each CE-style chain in `pointer_chains` using `module_base + offsets`.
2. If all chains fail, scan memory for `signature_pattern` (AOB format, `??` wildcards).
3. Compute final value address as:
   - `base = signature_match + signature_offset_to_base`
   - `target = base + structure_value_offset` (for `mov [eax+0xAD], cl`, use `0xAD`)

## Pointer helper

Generate pointer-chain scaffolding from your saved CE addresslist snapshots:

```bash
python studiomemuer_light_module/pointer_chain_helper.py --study-dir Pointer_study --value-offset 0xAD
```

If you prefer `python -m ...`, install deps first (`pip install -r requirements.txt`) so package imports succeed.

This writes `studiomemuer_light_module/pointer_chain_candidates.json` with:
- parsed absolute addresses per run
- derived structure-base candidates (`address - 0xAD`)
- a `LightProfile` snippet template for `pointer_chains`
