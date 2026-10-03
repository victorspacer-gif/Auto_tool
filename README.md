# SystemMonitor (Auto_tool)

SystemMonitor is a Windows desktop automation and monitoring utility built with Python and Tkinter.
It combines configurable hotkey automation, pixel/OCR monitoring, direct process-memory reads of
character stats, per-character profile autosave, and an optional sandbox launcher for the game
client — all inside one GUI.

The application targets the `miracle_gl.exe` / `miracle_dx*.exe` game client, but the OCR channel,
hotkey jobs and input services work against any window.

## Current Features

- **Activity Control**
  Hotkey-based repeating jobs (`HotkeyJobService`), activity monitor movement (AFK), and right-click
  monitoring with `timer` / `food` modes.
- **Rune Session**
  Automated rune-making loop (hand → storage → blank positions) with cycle delay variation, mana
  gating and mouse timing controls.
- **Auto Healer**
  Healing by spell hotkey or by rune-on-character flow using watched HP values, with a minimum mana
  requirement.
- **Light Control**
  Reads and patches the client's light color/intensity bytes through the pointer list, with a freeze
  thread, custom byte values, and restore of the original pair.
- **Screen Watch**
  Pixel-change alerts, low-HP alerts driven by the watched HP value, battle detection over a
  configured region, taskbar flashing, system sounds and an optional battle-logout popup.
- **Character Status**
  OCR watcher for `Level`, `Hit Points`, `Mana`, `Cap`, and `Food` with median aggregation and
  HP/Mana regeneration tracking.
- **Variables**
  Live view of Level / HP / Cap / MP / Food plus the active source (`pointer` or `ocr`), the resolved
  pointer addresses, regeneration rates, read counters and last update time.
- **Fishing Session**
  Rod/spot automation with cast and wait timing, spot rotation, session timing, capacity stop
  thresholds and optional auto-restart keyed on the food timer.
- **Hotkeys**
  Rebindable global hotkeys for pause, stop-all and feature toggles.
- **Config**
  Save/load of the complete app state in JSON, plus automatic per-character profile autosave.

## Stat pipeline: pointer-first, OCR fallback

Every stat (HP, MP, Cap, Food) has two sources:

1. **Pointer read (primary)** — a pointer chain is resolved in the game process and the value is read
   as a double. Resolved addresses are cached for 60 s, so the three client stats that share a base
   module address are read in a single resolution pass.
2. **OCR read (fallback)** — the Character Status watcher screenshots the selected window or fields,
   runs Tesseract, and writes the parsed numbers into `state.char_status_*`.

`hp_source` / `mp_source` / `cap_source` / `food_source` record which channel produced the number that
is currently on screen, and each stat falls back to OCR automatically when the pointer fails, is
invalidated by validation, or the client is restarted. See
[State variables — detailed analysis](#state-variables--detailed-analysis) for the full model.

## State variables — detailed analysis

This section documents the variables the app actually reads, derives and consumes on the current
`main` tree. It is the entry point to `VARIABLES.md`, which contains the same model in reference form.

### 1. Live stat channels

Each channel is implemented by a subclass of `StatPointerService`
(`systool/services/monitoring.py`) and is registered in `ServiceContainer`.

| Channel | Value field | Source field | Address field | OCR fallback field | Pointer profile | Read method |
|---|---|---|---|---|---|---|
| HP | `hp_value` | `hp_source` | `hp_pointer_address_hex` | `char_status_hp` | `DEFAULT_HP_PROFILE` | `read_double` |
| MP (Mana) | `mp_value` | `mp_source` | `mp_pointer_address_hex` | `char_status_mana` | `DEFAULT_MP_PROFILE` | `read_double` |
| Cap | `cap_value` | `cap_source` | `cap_pointer_address_hex` | `char_status_cap` | `DEFAULT_CAP_PROFILE` | `read_double` |
| Food | `food_value` | `food_source` | `food_pointer_address_hex` | `char_status_food_seconds` | `DEFAULT_FOOD_PROFILE` | `read_double` |

Service classes: `HpService`, `MpService`, `CapService`, `FoodService`; all of them inherit
`attach()`, `detach()`, the 60 s address cache, the validation rules and the OCR fallback from
`StatPointerService`. `HpService._read_all_stats()` is the batch entry point used by the Variables tab
and by the background poller.

In addition to the stat channels, `LightControlService` reads and writes the light **color/intensity
byte pair** (`light_last_color_address_hex`, `light_last_intensity_address_hex`,
`light_original_color_value`, `light_original_intensity_value`) using `DEFAULT_LIGHT_PROFILE`.

### 2. Pointer chains on `main`

Chains live in `systool/pointers/profiles.py` and are imported from the Cheat Engine tables in
`pointers_ct/`. Candidate chains are tried in order; the first one that resolves *and* reads
successfully wins, and the resolved absolute address is cached.

| Stat | Chains (module base → offsets) | Source table |
|---|---|---|
| HP | `+0x00A6DA60 → 0x4A0`, `+0x00A6DA6C → 0x4A0 → 0x11C` | `pointers_ct/HP Pointers.CT` |
| MP | `+0x00A6DA60 → 0x4F8`, `+0x00A6DA6C → 0x4F8 → 0x11C` | `pointers_ct/MP Pointers.CT` |
| Cap | `+0x00A6DA6C → 0x4B8 → 0x11C`, `+0x00A6DA60 → 0x4B8` | `pointers_ct/CAP Pointers.CT` |
| Food | `+0x00285388 → 0x69C → 0x3E8`, `… → 0x3BC`, `… → 0x3CC` | `pointers_ct/Food_pointers.CT` |
| Light color | `+0x00A3E4C0 → 0xAC` (intensity = color address + 1) | `pointers_ct/Light Pointers.CT` |

`PointerReader.resolve_address()` resolves through the module base reported by Toolhelp and stores
`CachedPointer(address, resolved_at)` per stat; `cache_ttl` defaults to 60 s and can be forced with
`refresh=True`. `PointerReader.read_hp/read_mp/read_cap/read_food/read_light` are the only read entry
points, and `resolve_light_pair_addresses()` returns the adjacent color/intensity pair.

Light profile defaults: `color_enabled_value = 215`, `default_intensity_value = 8`,
`boosted_intensity_value = 11`.

### 3. Validation and pointer invalidation

A pointer value is rejected — and the channel is immediately switched back to OCR — when any of
these hold (`StatPointerService._validate_pointer_value`):

| Rule | Threshold |
|---|---|
| Non-numeric, boolean, `NaN`/`inf` | rejected |
| Negative | rejected |
| Fractional when an integer stat is expected (`require_integer_value`) | rejected |
| Above the hard maximum | `1,000,000` for HP / MP / Cap |
| Above peak tolerance | `> 3 ×` the last observed peak (`char_status_hp_peak`) |
| Inconsistent with the OCR fallback | delta `> max(500, 5 × OCR value)` |
| Zero or negative after normalisation | value dropped to `None` |

On rejection `_invalidate_pointer()` sets `_hp_pointer_invalid` / `_mp_pointer_invalid` /
`_cap_pointer_invalid`, clears the resolved address and the hex state field, sets the source tag back
to `"ocr"`, and writes a warning to the UI log. Invalidation is sticky until the next `attach()`.

`_read_all_stats()` writes whatever it has — pointer value or promoted OCR value — into
`hp_value` / `mp_value` / `cap_value` / `food_value`, so downstream consumers (healer, runes, fishing,
alarm, right-click) always see a number instead of `None` when a client update breaks the chains.

### 4. OCR channel variables

Written by `CharacterStatusService` (`systool/services/monitoring.py`) through `TesseractOCREngine`:

| Variable | Meaning |
|---|---|
| `char_status_level` | Character level parsed from the status window |
| `char_status_hp` | HP parsed from the status window (pointer fallback) |
| `char_status_mana` | Mana parsed from the status window (pointer fallback) |
| `char_status_cap` | Cap parsed from the status window (pointer fallback) |
| `char_status_food_seconds` / `char_status_food_text` | Remaining food-buff seconds and the buff text |
| `char_status_region`, `char_status_hp_region`, `char_status_mana_region`, `char_status_cap_region` | Capture regions (full window and/or per-field) |
| `char_status_poll_ms` | Poll interval, default `800` ms |
| `char_status_samples`, `char_status_sample_delay_ms` | Sample count (default 3) and delay (default 100 ms) |
| `char_status_tesseract_path` | Optional explicit `tesseract.exe` |

Aggregation over the samples uses the **median** for numeric fields (`level`, `hp`, `mana`, `cap`,
`food_seconds`) and the **most common value** for `food_text`.

### 5. Derived variables

| Variable | Formula |
|---|---|
| `char_status_hp_peak` | Running maximum of the OCR HP value |
| `char_status_hp_regen_per_min` | Sum of positive HP deltas over a rolling 180 s window ÷ elapsed minutes |
| `char_status_mana_regen_per_min` | Same formula for mana |

Regen history records a sample only when the value actually changes, is trimmed to a 180 s window, and
ignores losses — so it measures regeneration, not net change.

### 6. Source metadata and health counters

| Variable | Type | Values / meaning |
|---|---|---|
| `hp_source`, `mp_source`, `cap_source` | `str` | `pointer` \| `ocr` \| `none` |
| `food_source` | `str` | `pointer` \| `ocr` |
| `hp_pointer_address_hex`, `mp_pointer_address_hex`, `cap_pointer_address_hex`, `food_pointer_address_hex` | `str` | Resolved absolute address in hex (`-` when unresolved) |
| `char_status_reads` / `char_status_failures` | `int` | Successful reads / failed OCR attempts |
| `char_status_last_seen` | `float \| None` | Timestamp of the last successful OCR read |
| `char_status_last_error` | `str` | Last OCR error message |
| `_hp_pointer_invalid`, `_mp_pointer_invalid`, `_cap_pointer_invalid` | `bool` | Sticky invalidation flags |
| `_mp_resolved_addr`, `_cap_resolved_addr`, `_food_resolved_addr` | `int \| None` | Raw resolved addresses for the batched read |

### 7. Threshold variables and their consumers

| Consumer | Variables it reads |
|---|---|
| `AutoHealerService` | `healer_mode`, `healer_spell_key`, `healer_use_percent`, `healer_hp_percent`, `healer_hp_value`, `healer_min_mana`, `healer_max_mana`, `healer_character_pos`, `healer_rune_pos`, `healer_mouse_speed`, `healer_rune_delay_ms` + live HP/Mana |
| `AlarmService` | `alarm_hp_percent`, `alarm_hp_value`, `alarm_mp_value`, `alarm_cap_value`, `alarm_threshold`, `alarm_cooldown`, `alarm_region`, `alarm_battle_enabled`, `alarm_battle_threshold`, `alarm_battle_region`, `alarm_flash_window`, `alarm_system_sound`, `alarm_auto_pause`, `alarm_mp3` + live HP and `char_status_hp_peak` |
| `FishingService` | `fish_min_cap`, `fish_session_minutes`, `fish_auto_restart_enabled`, `fish_auto_restart_food_min_secs` + live Cap and `char_status_food_seconds` |
| `RuneMakerService` | `rune_min_mana`, `rune_max_mana`, `rune_available_blank_runes`, `rune_cycle_delay_ms`, `rune_cycle_delay_variation_ms` + live Mana |
| `RightClickService` | `rclick_mode`, `rclick_require_food`, `rclick_food_min_minutes`, `rclick_food_burst_count*`, `rclick_food_burst_interval_ms` + `char_status_food_seconds` |
| `HotkeyJobService` | `min_mana` / `max_mana` per job + live Mana |
| `LightControlService` | `light_process_name`, `light_memory_backend`, `light_freeze_*`, `light_custom_*`, `light_direct_address_hex` |

### 8. Persistence model

- `ConfigSerializer.to_dict()` flattens the grouped state dataclasses (`AlarmState`,
  `CharStatusState`, `FishingState`, `RuneState`, `HealerState`, `SandboxState`) into dot-notation keys
  (`fishing.cast_min_ms`, `healer.hp_percent`, …) and merges the special fields
  (`hotkey_bindings`, `jobs`, `fish_spots`).
- `apply_loaded()` accepts both the dot-notation keys and the legacy flat keys (`alarm_mp3`,
  `sandbox_backend`, `rclick_food_min_secs`, …), and clamps every value against the bounds declared in
  `systool/config.py` (for example `healer.hp_percent` ∈ 1…100, `light_*` bytes ∈ 0…255,
  `fishing.session_minutes` ∈ 1…40).
- Character profiles are saved through the same serializer with `exclude_keys` — the light settings
  (`light_*`, `light_memory_backend`, `light_direct_address_hex`) and `alarm.flash_window` are treated
  as machine-wide and deliberately **not** stored per character.
- Profile files land in `Documents\aututu\autosave_<normalized_character>.json` (schema version 1,
  `__meta__` block with process name, window title, character name and OCR regions in both absolute and
  window-relative form). They are written every 120 s (`AUTOSAVE_INTERVAL_MS`) while attached, and on
  load the OCR regions are re-mapped onto the current window rectangle before use.

### 9. Known gaps in the variable model

- `CapService.state_peak_attr` points at `char_status_cap_peak`, but `CharStatusState` only declares
  `hp_peak`. The consequence is twofold: `CapService.get_cap_peak()` (currently uncalled) would raise
  `AttributeError`, and Cap never gets the `> 3 × peak` validation rule that HP has.
- `_mp_resolved_addr`, `_cap_resolved_addr` and `_food_resolved_addr` are set dynamically with
  `setattr` rather than declared on the dataclass; they are safe today, but they are invisible to
  type checkers and to the serializer's field list.

## Project Structure

```text
Auto_tool/
|-- raw.py                       # entry point (argparse: --debug, --diagnose-ocr-env)
|-- README.md
|-- VARIABLES.md                 # state-variable reference (see the analysis above)
|-- requirements.txt
|-- SystemMonitor.spec           # PyInstaller spec (Tesseract data + bridge DLL + hidden imports)
|-- build.bat                    # checks Python 3.12 64-bit, then calls build.py
|-- build.py                     # dependency install, tesserocr wheel, PyInstaller build
|-- pytest.ini
|-- magic_number_tool.py         # scan/export/edit constants + magic numbers
|-- magic_number_report.json
|-- app-py-size-analysis.md      # refactor/size reports
|-- app-refactoring-analysis.md
|-- code_agent.py                # standalone code-template generator experiment
|-- test_fishing_smoke.py
|-- bridge/                      # C++ source for studiomem_bridge.dll (DBK/DBVM adapters)
|-- chat-transcripts/
|-- examples/
|   `-- dbvm_bridge_usage.py
|-- hooks/                       # PyInstaller hooks (jaraco, tesserocr)
|-- runtime_hooks/
|-- pointers_ct/                 # Cheat Engine tables: HP, MP, CAP, Food, Light
|-- purecase_module/              # Sandboxie / Job Object launcher
|-- vendor/
|   |-- python-wheels/            # e.g. tesserocr wheel installed by build.py
|   `-- tesseract/                # bundled Tesseract used by the packaged build
|-- tests/                        # pytest suite + todo-list.md
`-- systool/
    |-- __init__.py
    |-- app.py                    # Tkinter shell, tab wiring, hotkey dispatch, poll loops
    |-- character_profiles.py     # identity, autosave profiles, OCR-region remapping
    |-- config.py                 # defaults, clamp bounds, ConfigSerializer
    |-- constants.py              # timing/polling/magic-number constants
    |-- container.py              # ServiceContainer (DI)
    |-- models.py                 # grouped state dataclasses + AppState
    |-- runtime.py                # AppRuntime, gates, UINotifier, OCR engine
    |-- theme.py
    |-- pointers/
    |   |-- memory_backend.py     # PymemBackend, DriverBridgeBackend, DbvmBridgeBackend
    |   |-- pointer_reader.py     # cached resolver + read_* entry points
    |   |-- pointer_chain_ranker.py
    |   |-- profiles.py           # stat + light pointer profiles
    |   |-- studiomem_bridge.dll
    |   `-- tk_light_tool.py
    |-- services/
    |   |-- fishing.py            |
    |   |-- healer.py             |
    |   |-- hotkeys.py            |   feature services, re-exported by
    |   |-- input_services.py     |   systool/services/__init__.py to keep the
    |   |-- monitoring.py         |   original import surface
    |   |-- position_capture.py   |
    |   |-- runes.py              |
    |   |-- runtime_timer.py      |
    |   `-- brazil-alarm.mp3      # bundled default alarm sound
    `-- ui/
        |-- __init__.py
        `-- tabs/                 # one module per tab (activity, rune, healer, light,
                                  # screen watch, character status, variables, fishing,
                                  # hotkeys, config)
```

## File Overview

- `raw.py`
  Entry point. Parses `--debug` (verbose logging) and `--diagnose-ocr-env <file>` (writes an OCR
  dependency report and exits), then calls `systool.app.run()`.
- `systool/app.py`
  `SystemMonitorApp`: notebook and tab construction, widget wiring, hotkey dispatch, the 500 ms
  settings poll, the 100 ms stats poll, tray integration, character profile autosave and attach flow.
- `systool/container.py`
  `ServiceContainer` — lazy DI container that owns every service instance and the single `AppRuntime`;
  tests inject mocks through `register()`.
- `systool/models.py`
  Grouped state dataclasses (`AlarmState`, `CharStatusState`, `FishingState`, `RuneState`,
  `HealerState`, `SandboxState`) plus `AppState` and `HotkeyJob`. Flat attribute names
  (`char_status_hp`, `fish_min_cap`, …) remain available as properties over the groups.
- `systool/runtime.py`
  `AppRuntime` (state, locks, per-feature stop events), `PauseController`, `ExecutionGate` /
  `MouseGate`, `UINotifier` (all UI writes marshalled through `root.after`), `TesseractOCREngine`,
  Tesseract discovery (`resolve_tesseract_cmd`, `configure_tesseract_runtime`, `create_ocr_engine`).
- `systool/config.py`
  Defaults and clamp bounds for every user-facing number, plus `ConfigSerializer`
  (`to_dict` / `save_json` / `load_file` / `apply_loaded`) with legacy-key migration.
- `systool/constants.py`
  Timing, polling, mouse/input, audio and UI layout constants used by the services.
- `systool/character_profiles.py`
  Character identity from the window title, `Documents\aututu` autosave profiles, OCR-region metadata
  and remapping, window/process lookup helpers.
- `systool/pointers/`
  Memory access layer: backend protocol + pymem/Studiomemuer-driver/DBVM implementations,
  `LightMemoryController`, `PointerReader` (60 s cache), pointer profiles and the chain ranker.
- `systool/services/`
  Automation features: hotkey jobs and global hotkeys, AFK, right-click, alarm, character status,
  HP/MP/Cap/Food, light control, fishing, healer, runes, position capture, runtime timer, plus the
  shared `HumanMouse`, `SafeKeyboardSession` and `WindowService` helpers.
- `systool/ui/tabs/`
  One class per tab; each tab owns its widgets and reads/writes through the runtime and services.
- `purecase_module/`
  Optional launcher that starts the game client inside a Sandboxie box or a Windows Job Object with a
  restricted (Safer) token and a spoofed environment.
- `bridge/`
  C++ sources and CMake project for `studiomem_bridge.dll`, the stable C ABI used by
  `DriverBridgeBackend` for driver-level memory access.
- `magic_number_tool.py`
  CLI/Tk tool that scans `systool/config.py` and `systool/constants.py` for magic numbers, exports
  `magic_number_report.json` and edits constants through the GUI.
- `SystemMonitor.spec` / `build.bat` / `build.py`
  Packaging: PyInstaller spec (Tesseract data, `studiomem_bridge.dll`, hidden imports for the pointer
  package, OCR backends and `purecase_module`) driven by a Python build script.

## Requirements

Python 3.12 64-bit is required to build the executable; running from source works on newer 3.x
interpreters when the wheel set below is importable on Windows.

Runtime packages (`requirements.txt`):

```text
pynput
pywin32
pystray
pillow
mss
numpy>=2
pygame-ce>=2.5.7
pyautogui
opencv-python>=4.13.0.92
pytesseract
tesserocr
psutil
pymem
```

Notes:

- `pywin32` and the global input hooks make this a Windows-only application.
- `psutil` + `pymem` back the pointer channel; without them the stat channels run in OCR-only mode.
- `tesserocr` and `pytesseract` are both optional at import time — the first one that imports is used
  (tesserocr preferred).
- The build script additionally installs `pyinstaller` and `cysignals`, and installs a
  `tesserocr-*-cp312-cp312-win_amd64.whl` from `vendor/python-wheels` when present.

## Run Locally

From the project folder:

```bash
python raw.py
```

Useful flags:

```bash
python raw.py --debug
python raw.py --diagnose-ocr-env ocr-report.json
```

## OCR Stack

`create_ocr_engine()` resolves a Tesseract installation in this order:

1. an explicit `tesseract.exe` path entered in the Character Status tab,
2. `tesseract\tesseract.exe` next to the frozen executable (`sys._MEIPASS`),
3. `vendor\tesseract\tesseract.exe` in the project,
4. `tesseract` on `PATH`,
5. `%ProgramFiles%`, `%ProgramFiles(x86)%` or `%LocalAppData%\Tesseract-OCR`.

`TesseractOCREngine` then prefers persistent **tesserocr** instances (one `PyTessBaseAPI` per thread,
reused across reads) and falls back to **pytesseract** when tesserocr is unavailable, returning text
plus a confidence value in both cases. The chosen backend is reported by
`describe_ocr_environment()` and by `--diagnose-ocr-env`.

## Pointer / Memory Backends

`LightMemoryController` takes a backend, selected from `state.light_memory_backend`:

| Value | Backend | Notes |
|---|---|---|
| `pymem` | `PymemBackend` | Default; user-mode `ReadProcessMemory` / writes via pymem |
| `studiomemuer` / `driver` | `DriverBridgeBackend` | Uses `studiomem_bridge.dll` over `\\.\CEDRIVER73` |
| anything else | `DbvmBridgeBackend` | DBVM-level access through the same bridge ABI |

All backends go through the same lock-protected controller, so stat reads, light patches and pointer
resolution cannot interleave badly. `pointers_ct/*.CT` are the Cheat Engine tables the profiles were
imported from, and `systool/pointers/pointer_chain_ranker.py` can score live candidate chains against
expected values/signatures when a client update moves the structures.

## Character Profiles and Configuration

- Manual save/load through the Config tab writes the full flattened state as JSON.
- While attached, the app derives the character name from the game window title, loads
  `Documents\aututu\autosave_<name>.json` when one exists (re-mapping saved OCR regions onto the
  current window size), and rewrites it every 120 s.
- Machine-wide settings (light control, `alarm.flash_window`) are excluded from character profiles on
  purpose.

## Sandbox Launcher

`purecase_module` can start the configured executable inside:

- a **Sandboxie** box (`find_installation`, `ensure_box`, `configure_box`, `reload_configuration`,
  `launch_in_box`), or
- a **Windows Job Object** with a Safer token and an optionally spoofed environment
  (`create_job_object`, `get_safer_token`, `build_spoofed_env`, `launch_with_job_object`).

The active backend is chosen in the UI and stored as `sandbox.backend` (`jobobj` or `sandboxie`).
The module is optional: the app runs normally when it cannot be imported.

## Build a Windows EXE

Build on Windows with Python 3.12 64-bit installed and the `py` launcher available.

### Automatic build

```powershell
.\build.bat
```

`build.bat` verifies the interpreter and then runs `build.py`, which:

1. installs/updates the runtime packages from `requirements.txt`,
2. installs the `tesserocr` wheel from `vendor\python-wheels` when present,
3. cleans previous build artefacts,
4. copies a local Tesseract installation into `vendor\tesseract`,
5. runs PyInstaller with `SystemMonitor.spec`.

Expected output:

```text
dist\SystemMonitor\SystemMonitor.exe
```

Important:

- The build machine should have Tesseract installed in a standard location such as
  `C:\Program Files\Tesseract-OCR` so it can be bundled; end users then need no separate install.
- The spec also bundles `systool\pointers\studiomem_bridge.dll` (from the repo or
  `bridge\build\Release`) and declares hidden imports for `systool.pointers.*`, `purecase_module`,
  `pytesseract`, `tesserocr`, `cysignals`, `mss.windows` and the `win32*` modules.

### Manual build from the spec

```powershell
py -3.12-64 -m pip install -r requirements.txt pyinstaller cysignals
py -3.12-64 -m PyInstaller --noconfirm --clean SystemMonitor.spec
```

## Tests

```bash
python -m pytest
```

`pytest.ini` points at `tests/` and registers a `slow` marker. The suite covers the DI container,
config serialization and legacy keys, models/state properties, the FIFO execution gate, fishing locks,
mana thresholds, the memory backend and light backend selection, character profiles, runtime helpers
and service behaviour; `tests/conftest.py` mocks tkinter, pywin32 and psutil so the suite can run
without a game client or a Windows session. `tests/todo-list.md` tracks the remaining coverage plan.

## Troubleshooting

### OCR features are not working

- Run `python raw.py --diagnose-ocr-env ocr-report.json` and read the report: it lists mss, numpy,
  OpenCV, pytesseract, tesserocr availability and which backend the engine picked.
- Confirm Tesseract is installed (or bundled) and, if needed, set the path in the Character Status tab.
- Point the watcher at a clear stats window, or select the HP/Mana/Cap fields individually.

### A stat shows `-` or keeps flipping to `ocr`

The pointer chain failed or was invalidated (validation rules in section 3 above). Check the UI log for
`<STAT> pointer invalidated: …`, verify the game client version, and re-import the chains from the
matching `pointers_ct/*.CT` table.

### The EXE says a dependency is missing

Build with `build.bat` so the spec's hidden imports, Tesseract data and the bridge DLL are included.

### Runtime behaviour differs between Python and the EXE

Test with `python raw.py` in the same Windows environment used for packaging before blaming the build.

### Some features do not work on macOS/Linux

That is expected — the app depends on Win32 APIs (window enumeration, input hooks, process memory)
and on Windows-only packages.

## Entry Point

```python
from systool.app import run

if __name__ == "__main__":
    run()
```

`raw.py` is the supported entry point because it also handles `--debug` and `--diagnose-ocr-env`.

## Next Steps

- Add the test coverage listed in `tests/todo-list.md` (fishing/healer/runes/hotkeys behaviour, UI tab
  event wiring, monitoring pointer paths).
- Declare `cap_peak` on `CharStatusState` (or drop `CapService.get_cap_peak`) so Cap gets the same peak
  validation as HP.
- Improve OCR tuning for additional UI variants and window scales.
- Add an installer instead of a raw executable build.
