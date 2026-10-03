# Variables Tab — State Variable Reference

> This is the reference companion to the **State variables — detailed analysis** section in
> `README.md`. Both describe the same model; this file lists it field by field.

## Overview

The Variables tab shows the live character statistics that the services use for decision-making
(healing, alarms, fishing, rune crafting). All of them live on the shared `AppState`
(`systool/models.py`), which groups related fields into dataclasses (`AlarmState`, `CharStatusState`,
`FishingState`, `RuneState`, `HealerState`, `SandboxState`) while still exposing the flat attribute
names (`char_status_hp`, `fish_min_cap`, …) as properties.

Every stat has two channels:

1. **Pointer read (primary)** — `HpService` / `MpService` / `CapService` / `FoodService` walk a pointer
   chain in the game process and read a double.
2. **OCR read (fallback)** — `CharacterStatusService` screenshots the status window or individual
   fields and parses them with Tesseract.

`hp_source` / `mp_source` / `cap_source` / `food_source` always say which channel produced the value
that is currently displayed.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Memory sources                        │
│                                                              │
│  ┌────────────────────────┐   ┌────────────────────────────┐ │
│  │ PointerReader          │   │ CharacterStatusService     │ │
│  │ (primary)              │   │ (fallback / secondary)     │ │
│  │ pymem / driver / DBVM  │   │ mss + Tesseract            │ │
│  └────────────────────────┘   └────────────────────────────┘ │
│              ↓                            ↓                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  AppState (shared state)               │  │
│  │  hp_value   / char_status_hp    mp_value / …_mana      │  │
│  │  cap_value  / char_status_cap   food_value / …_food_*  │  │
│  └────────────────────────────────────────────────────────┘  │
│              ↓                            ↓                  │
│  ┌────────────────────────┐   ┌────────────────────────────┐ │
│  │ AlarmService           │   │ FishingService             │ │
│  │ AutoHealerService      │   │ RuneMakerService           │ │
│  │ RightClickService      │   │ HotkeyJobService           │ │
│  └────────────────────────┘   └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## Variable categories

### A. Primary stat values (pointer-backed)

| Variable | State field | Type | Source | Description |
|---|---|---|---|---|
| `hp_value` | `state.hp_value` | `int \| None` | pointer / OCR fallback | Current HP; falls back to `char_status_hp` |
| `mp_value` | `state.mp_value` | `int \| None` | pointer / OCR fallback | Current Mana; falls back to `char_status_mana` |
| `cap_value` | `state.cap_value` | `int \| None` | pointer / OCR fallback | Current Cap; falls back to `char_status_cap` |
| `food_value` | `state.food_value` | `int \| None` | pointer / OCR fallback | Food timer; falls back to `char_status_food_seconds` |

Implemented by `StatPointerService` subclasses in `systool/services/monitoring.py`, driven by
`PointerReader` (`systool/pointers/pointer_reader.py`) over the profiles in
`systool/pointers/profiles.py`.

**Pointer chains (current `main`):**

| Stat | Chains (module base → offsets) | Source table |
|---|---|---|
| HP | `+0x00A6DA60 → 0x4A0`, `+0x00A6DA6C → 0x4A0 → 0x11C` | `pointers_ct/HP Pointers.CT` |
| MP | `+0x00A6DA60 → 0x4F8`, `+0x00A6DA6C → 0x4F8 → 0x11C` | `pointers_ct/MP Pointers.CT` |
| Cap | `+0x00A6DA6C → 0x4B8 → 0x11C`, `+0x00A6DA60 → 0x4B8` | `pointers_ct/CAP Pointers.CT` |
| Food | `+0x00285388 → 0x69C → 0x3E8` (+`0x3BC`, +`0x3CC`) | `pointers_ct/Food_pointers.CT` |
| Light color | `+0x00A3E4C0 → 0xAC` (intensity = color + 1) | `pointers_ct/Light Pointers.CT` |

Chains are tried in order; the first one that resolves *and* probes successfully is cached for
`cache_ttl` seconds (default 60). `read_*` in `PointerReader` are the read entry points, and the
module base comes from Toolhelp rather than from pymem internals so the driver backends work too.

**Batch read:** `HpService._read_all_stats()` reads HP, MP, Cap and Food in one pass and writes
whichever value it obtained — pointer or promoted OCR — to `hp_value`, `mp_value`, `cap_value`,
`food_value`. The Variables tab calls it before refreshing the labels.

### B. Value validation and pointer invalidation

`StatPointerService._validate_pointer_value()` rejects a read when:

- the value is not a finite number, is negative, or is fractional for an integer stat,
- it exceeds the hard maximum (`1_000_000` for HP/MP/Cap),
- it is more than `3 ×` the last observed peak (`char_status_hp_peak`),
- it differs from the OCR value by more than `max(500, 5 × OCR value)`,
- after normalisation it is `<= 0`.

Rejection calls `_invalidate_pointer()`, which sets the sticky flag (`_hp_pointer_invalid`,
`_mp_pointer_invalid`, `_cap_pointer_invalid`), clears the resolved address and hex field, flips the
source tag to `ocr`, and logs `"<STAT> pointer invalidated: <reason>. Falling back to OCR."`.
The address cache is also rebuilt whenever its 60 s TTL expires.

### C. OCR-derived values (fallback source)

| Variable | State field | Type | Description |
|---|---|---|---|
| `char_status_hp` | `state.char_status_hp` | `int \| None` | HP parsed from the status window |
| `char_status_mana` | `state.char_status_mana` | `int \| None` | Mana parsed from the status window |
| `char_status_cap` | `state.char_status_cap` | `int \| None` | Cap parsed from the status window |
| `char_status_level` | `state.char_status_level` | `int \| None` | Character level |
| `char_status_food_seconds` | `state.char_status_food_seconds` | `int \| None` | Remaining food-buff seconds |
| `char_status_food_text` | `state.char_status_food_text` | `str` | Food-buff text (e.g. `Ham`, `Fish`) |

**OCR configuration:** `char_status_region`, `char_status_hp_region`, `char_status_mana_region`,
`char_status_cap_region`; poll interval `char_status_poll_ms` (default 800 ms); `char_status_samples`
(default 3) with `char_status_sample_delay_ms` (default 100 ms); optional `char_status_tesseract_path`.

Samples are aggregated with the **median** for numeric fields and the **most common value** for
`char_status_food_text`.

### D. Derived statistics

| Variable | State field | Computation |
|---|---|---|
| `char_status_hp_peak` | `state.char_status_hp_peak` | Running maximum of the OCR HP value |
| `char_status_hp_regen_per_min` | `state.char_status_hp_regen_per_min` | Positive HP deltas over a rolling 180 s window ÷ elapsed minutes |
| `char_status_mana_regen_per_min` | `state.char_status_mana_regen_per_min` | Same, for mana |

Regen history only records *changes*, is trimmed to 180 s, and ignores losses, so the number is a
regeneration rate rather than a net change rate.

### E. Source metadata

| Variable | State field | Values |
|---|---|---|
| `hp_source` | `state.hp_source` | `pointer` / `ocr` (default `ocr`) |
| `mp_source` | `state.mp_source` | `pointer` / `ocr` / `none` |
| `cap_source` | `state.cap_source` | `pointer` / `ocr` / `none` |
| `food_source` | `state.food_source` | `pointer` / `ocr` |

### F. Pointer addresses (hex display)

| Variable | State field | Description |
|---|---|---|
| `hp_pointer_address_hex` | `state.hp_pointer_address_hex` | Resolved HP address, hex without prefix |
| `mp_pointer_address_hex` | `state.mp_pointer_address_hex` | Resolved MP address |
| `cap_pointer_address_hex` | `state.cap_pointer_address_hex` | Resolved Cap address |
| `food_pointer_address_hex` | `state.food_pointer_address_hex` | Resolved Food address |

**Internal (used by the batched read and the UI):**

- `_mp_resolved_addr`, `_cap_resolved_addr`, `_food_resolved_addr` — raw integer addresses
- `_prev_ocr_hp`, `_prev_ocr_mp`, `_prev_ocr_cap` — previous OCR values for change detection

### G. Read statistics and health monitoring

| Variable | State field | Type | Description |
|---|---|---|---|
| `char_status_reads` | `state.char_status_reads` | `int` | Successful OCR reads since start |
| `char_status_failures` | `state.char_status_failures` | `int` | Failed OCR attempts |
| `char_status_last_seen` | `state.char_status_last_seen` | `float \| None` | Timestamp of the last successful read |
| `char_status_last_error` | `state.char_status_last_error` | `str` | Last OCR error message |

---

## Service consumption map

### HpService / MpService / CapService / FoodService

```python
HpService.get_hp()    -> state.hp_value     # pointer read or OCR fallback
MpService.get_mp()    -> state.mp_value     # pointer read or OCR fallback
CapService.get_cap()  -> state.cap_value    # pointer read or OCR fallback
FoodService.get_food() -> state.food_value  # pointer read or OCR fallback

HpService._read_all_stats() -> (hp_val, mp_val, cap_val)   # batched, also stores food
```

### AlarmService

```python
state.alarm.threshold          # pixel-change ratio threshold
state.alarm.battle_threshold   # battle-region change ratio
state.alarm_hp_percent         # low-HP alarm percentage
state.alarm_hp_value           # low-HP alarm absolute value
state.alarm.mp_value           # mp alarm threshold
state.alarm.cap_value          # cap alarm threshold
state.hp_value                 # current HP
state.char_status_hp_peak      # peak for the percentage calculation
```

### FishingService

```python
state.fish_min_cap                      # stop/abort below this Cap
state.cap_value                         # pointer Cap (primary)
state.char_status_cap                   # OCR Cap fallback
state.fish_auto_restart_food_min_secs   # restart when food drops below this
state.char_status_food_seconds          # OCR food timer
```

### RuneMakerService

```python
state.rune_min_mana   # cast only at/above this mana
state.rune_max_mana   # cast only at/below this mana
state.mp_value        # pointer mana (primary)
state.char_status_mana  # OCR fallback
```

### AutoHealerService

```python
state.healer_use_percent  # percentage vs absolute threshold
state.healer_hp_percent   # heal below this percentage
state.healer_hp_value     # heal below this absolute value
state.healer_min_mana     # require this much mana before healing
state.hp_value            # current HP
state.char_status_hp      # OCR fallback
```

### RightClickService

```python
state.rclick_require_food        # check food before right-clicking
state.rclick_food_min_minutes    # keep food above this many minutes
state.char_status_food_seconds   # OCR food timer
state.food_value                 # pointer food timer (primary)
```

### HotkeyJobService

```python
job.min_mana / job.max_mana   # per-job mana window
state.mp_value                # pointer mana
state.char_status_mana        # OCR fallback
```

---

## Data flow

```
StatPointerService.attach()
  -> LightMemoryController(backend from state.light_memory_backend)
  -> PointerReader(controller, cache_ttl=60 s)
  -> resolve_pointer() for the stat profile  ->  state.<stat>_pointer_address_hex
  -> read + validate                         ->  state.<stat>_value / <stat>_source = "pointer"
       (on validation failure: _<stat>_pointer_invalid = True, source = "ocr")

CharacterStatusService._worker()
  -> mss capture (full window and/or per-field regions)
  -> TesseractOCREngine (tesserocr preferred, pytesseract fallback)
  -> median / mode aggregation
  -> state.char_status_hp / mana / cap / level / food_seconds / food_text
  -> regen + peak update
```

---

## UI refresh cycle

`VariablesTab.refresh_display()` (`systool/ui/tabs/variables_tab.py`):

1. calls `HpService._read_all_stats()` when available, otherwise `get_hp()`, `get_mp()`, `get_cap()`
   and `get_food()` individually,
2. renders each value together with its source tag (`pointer` / `ocr` / `none`),
3. renders the resolved pointer address for HP, MP, Cap and Food,
4. renders regen rates, read/miss counters, HP peak and the last update timestamp.

The tab also drives the periodic refresh from `SystemMonitorApp` (settings poll every 500 ms, stats
poll every 100 ms).

---

## File locations (current `main`)

| Component | File |
|---|---|
| State models (`AppState` + grouped states) | `systool/models.py` |
| Defaults and clamp bounds | `systool/config.py` |
| Pointer profiles (chains, read method) | `systool/pointers/profiles.py` |
| Pointer resolution + read entry points | `systool/pointers/pointer_reader.py` |
| Memory backends | `systool/pointers/memory_backend.py` |
| Chain ranking helper | `systool/pointers/pointer_chain_ranker.py` |
| Stat services + light + alarm + OCR | `systool/services/monitoring.py` |
| Variables tab UI | `systool/ui/tabs/variables_tab.py` |
| Services container | `systool/container.py` |
| Runtime state, gates, OCR engine | `systool/runtime.py` |

---

## Notes for future updates

When adding a variable:

1. add the field to the right grouped dataclass in `models.py` (and a property alias if the flat name
   is already used elsewhere),
2. add its default and clamp bounds to `config.py`, and include it in `ConfigSerializer.to_dict()` /
   `apply_loaded()` if it should persist,
3. have the populating service write it under `runtime.settings_lock`,
4. display it in `systool/ui/tabs/variables_tab.py`,
5. document which services consume it here,
6. if it shares a base address with HP/MP/Cap/Food, extend `_read_all_stats()` instead of adding a new
   resolution pass.

When adding a consumer service:

1. read state under `runtime.settings_lock`,
2. prefer the pointer value (`hp_value`, `mp_value`, `cap_value`, `food_value`),
3. fall back to `char_status_*` when the pointer value is `None`,
4. handle `None` explicitly — the OCR channel can be empty while no window is selected.
