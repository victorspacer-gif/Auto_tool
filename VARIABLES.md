# Variables Tab — State Variable Reference

## Overview

The Variables tab displays real-time character statistics read from the game process. These values are exposed through a shared `AppState` object that multiple services consume for decision-making (healing, alarms, fishing, rune crafting).

This document describes every variable displayed in the Variables table, its source, how it's computed, and which services consume it.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    Memory Sources                │
│                                                 │
│  ┌──────────────┐   ┌────────────────────────┐  │
│  │ Pointer Read │   │ Character Status OCR   │  │
│  │ (Primary)    │   │ (Fallback / Secondary) │  │
│  └──────────────┘   └────────────────────────┘  │
│         ↓                    ↓                   │
│  ┌─────────────────────────────────────────┐    │
│  │           AppState (Shared State)        │    │
│  │                                         │    │
│  │  hp_value / char_status_hp              │    │
│  │  mp_value / char_status_mana            │    │
│  │  cap_value / char_status_cap            │    │
│  └─────────────────────────────────────────┘    │
│         ↓                    ↓                   │
│  ┌──────────────┐   ┌────────────────────────┐  │
│  │ AlarmService │   │ FishService            │  │
│  │ HealerServ.  │   │ RuneService            │  │
│  │ RightClick   │   │ ...                    │  │
│  └──────────────┘   └────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## Variable Categories

### A. Primary Stat Values (Pointer-Based)

These are the main character stats read from memory pointers. They take precedence over OCR values when available.

| Variable | State Field | Type | Source | Description |
|----------|------------|------|--------|-------------|
| `hp_value` | `state.hp_value` | `int \| None` | Pointer (primary) / OCR (fallback) | Current character HP read from memory pointer at resolved address. Falls back to `char_status_hp` when pointer unavailable. |
| `mp_value` | `state.mp_value` | `float \| None` | Pointer (primary) / OCR (fallback) | Current character MP/Mana read from memory pointer. Falls back to `char_status_mana`. |
| `cap_value` | `state.cap_value` | `float \| None` | Pointer (primary) / OCR (fallback) | Current Cap value (capacity stat, separate from HP). Falls back to `char_status_cap`. |

**Pointer Resolution:**
- Base address: `0x00A783E0` (shared across all three stats)
- HP offset: `+ 0x4A0` → resolved via `HpService._resolve_hp_pointer()`
- MP offset: `+ 0x4F8` → resolved via `MpService._resolve_mp_pointer()`
- Cap offset: `+ 0x4B8` → resolved via `CapService._resolve_cap_pointer()`

**Batch Read Optimization:**
All three stats can be read in a single controller call via `HpService._read_all_stats()`. This reduces redundant module lookups and pointer chain resolution overhead.

---

### B. OCR-Derived Values (Fallback Source)

These values come from the Character Status OCR service, which reads character stats by taking screenshots of the game UI and running Tesseract OCR. They serve as fallback when pointers are unavailable or for additional data not exposed via memory pointers.

| Variable | State Field | Type | Description |
|----------|------------|------|-------------|
| `char_status_hp` | `state.char_status_hp` | `int \| None` | HP value extracted from OCR character status window. Used as fallback when pointer read fails. |
| `char_status_mana` | `state.char_status_mana` | `int \| None` | Mana/MP value extracted from OCR. Fallback for MP service. |
| `char_status_cap` | `state.char_status_cap` | `int \| None` | Cap value extracted from OCR. Fallback for Cap service. |
| `char_status_level` | `state.char_status_level` | `int \| None` | Character level extracted from OCR. Displayed in Variables tab. |
| `char_status_food_text` | `state.char_status_food_text` | `str` | Food buff text (e.g., "Ham", "Fish") extracted from OCR. |
| `char_status_food_seconds` | `state.char_status_food_seconds` | `int \| None` | Remaining seconds on food buff, parsed from OCR. Used by RightClickService to trigger burst clicks when food expires. |

**OCR Configuration:**
- Region: `char_status_region`, `char_status_hp_region`, `char_status_mana_region`, `char_status_cap_region` — screen coordinates for OCR capture
- Poll interval: `char_status_poll_ms` (default 800ms)
- Samples: `char_status_samples` (default 3), with median aggregation

---

### C. Derived Statistics

These are computed from raw values and used for monitoring, alarms, and decision-making.

| Variable | State Field | Type | Computation | Description |
|----------|------------|------|-------------|-------------|
| `char_status_hp_peak` | `state.char_status_hp_peak` | `int` | `max(hp_value)` over time | Peak HP observed. Used by AlarmService to calculate HP percentage thresholds. |
| `char_status_hp_regen_per_min` | `state.char_status_hp_regen_per_min` | `float` | Computed from HP history (180s window) | HP regeneration rate per minute. Tracks positive delta over time. |
| `char_status_mana_regen_per_min` | `state.char_status_mana_regen_per_min` | `float` | Computed from Mana history (180s window) | Mana regeneration rate per minute. |

**Regen Rate Algorithm:**
```python
# Maintains a rolling 180-second history of value changes
# Only counts positive deltas (gains), ignores losses
# Rate = total_gained / elapsed_minutes
```

---

### D. Source Metadata

These track the provenance and reliability of each stat source.

| Variable | State Field | Type | Values | Description |
|----------|------------|------|--------|-------------|
| `hp_source` | `state.hp_source` | `str` | `"pointer"` / `"ocr"` | Source tag for HP value display. Shows whether pointer or OCR is active. |
| `mp_source` | `state.mp_source` | `str` | `"pointer"` / `"ocr"` / `"none"` | Source tag for MP value display. |
| `cap_source` | `state.cap_source` | `str` | `"pointer"` / `"ocr"` / `"none"` | Source tag for Cap value display. |

---

### E. Pointer Addresses (Hex Display)

These show the resolved memory addresses used for pointer reads, displayed in hex format.

| Variable | State Field | Type | Description |
|----------|------------|------|-------------|
| `hp_pointer_address_hex` | `state.hp_pointer_address_hex` | `str` | Hex string of resolved HP pointer address (e.g., `"22B9EE60"`) |
| `mp_pointer_address_hex` | `state.mp_pointer_address_hex` | `str` | Hex string of resolved MP pointer address |
| `cap_pointer_address_hex` | `state.cap_pointer_address_hex` | `str` | Hex string of resolved Cap pointer address |

**Internal (for batch reads):**
- `_mp_resolved_addr`: Raw integer address for MP, stored by MpService.attach()
- `_cap_resolved_addr`: Raw integer address for Cap, stored by CapService.attach()

---

### F. Read Statistics & Health Monitoring

These track the health and performance of the OCR character status reader.

| Variable | State Field | Type | Description |
|----------|------------|------|-------------|
| `char_status_reads` | `state.char_status_reads` | `int` | Total successful OCR reads since service started |
| `char_status_failures` | `state.char_status_failures` | `int` | Total failed OCR attempts (exceptions, no digits recognized) |
| `char_status_last_seen` | `state.char_status_last_seen` | `float \| None` | Unix timestamp of last successful OCR read |
| `char_status_last_error` | `state.char_status_last_error` | `str` | Last error message from OCR service (empty string if no error) |

---

## Service Consumption Map

Shows which services consume each variable and how they use it:

### HpService / MpService / CapService
```python
# Primary read path
HpService.get_hp() → state.hp_value          # pointer read or OCR fallback
MpService.get_mp()  → state.mp_value         # pointer read or OCR fallback
CapService.get_cap() → state.cap_value       # pointer read or OCR fallback

# Batch read (optimized)
HpService._read_all_stats() → (hp_val, mp_val, cap_val)
```

### AlarmService
```python
# Uses HP values to trigger alarms when HP drops below threshold
state.alarm_hp_percent  # alarm percentage threshold
state.char_status_hp_peak  # peak HP for ratio calculation: (current / peak) * 100
state.hp_value           # current HP value
state.char_status_hp     # fallback OCR HP if pointer unavailable
```

### FishService
```python
# Uses Cap values to determine fishing session conditions
state.fish_min_cap       # minimum Cap required before starting fish session
state.char_status_cap    # current Cap from OCR for comparison
state.cap_value          # current Cap from pointer (primary)
```

### RuneService
```python
# Uses Mana values to determine rune crafting eligibility
state.rune_min_mana      # minimum mana required before casting runes
state.char_status_mana   # current mana from OCR
state.mp_value           # current mana from pointer (primary)
```

### HealerService
```python
# Uses HP/MP values for healing decisions
state.healer_hp_percent  # heal when HP drops below this percentage
state.healer_hp_value    # heal when HP drops below this absolute value
state.hp_value           # current HP to check against thresholds
state.char_status_hp     # fallback OCR HP
```

### RightClickService
```python
# Uses food status for burst click timing
state.rclick_require_food  # whether to check food before right-clicking
state.char_status_food_seconds  # remaining food buff seconds
state.rclick_food_min_secs      # minimum food seconds before triggering burst
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Memory Services                          │
│                                                              │
│  HpService.attach() → resolve pointer → state.hp_value      │
│  MpService.attach() → resolve pointer → state.mp_value      │
│  CapService.attach()→ resolve pointer → state.cap_value     │
│                                                              │
│  CharacterStatusService._worker():                          │
│    screenshot → OCR → median aggregation →                  │
│    state.char_status_hp/mana/cap/level/food                 │
│    state.char_status_hp_regen_per_min                       │
│    state.char_status_mana_regen_per_min                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    AppState (Shared)                         │
│                                                              │
│  Primary values:  hp_value, mp_value, cap_value             │
│  Fallback values: char_status_hp/mana/cap                   │
│  Derived stats:   regen rates, peak HP                      │
│  Metadata:        source tags, pointer addresses            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    Consumer Services                         │
│                                                              │
│  AlarmService     → monitors HP % and triggers alarms       │
│  FishService      → checks Cap before fishing               │
│  RuneService      → checks Mana before rune crafting        │
│  HealerService    → heals when HP drops below threshold     │
│  RightClickServ.  → burst clicks when food expires          │
└─────────────────────────────────────────────────────────────┘
```

---

## UI Refresh Cycle

The `_refresh_variables_display()` method in `app.py` is called periodically to update the Variables tab:

1. **Batch memory read** — calls `HpService._read_all_stats()` to get HP/MP/Cap from pointers
2. **Fallback individual reads** — if batch fails, calls `get_hp()`, `get_mp()`, `get_cap()` separately
3. **Update UI labels** — displays values with source tags and pointer addresses
4. **Show regen stats** — displays regeneration rates computed from OCR history

---

## File Locations

| Component | File | Location |
|-----------|------|----------|
| State model definition | `systool/models.py` | Lines 30-211 (AppState class) |
| HP service | `systool/services.py` | HpService class (~line 450+) |
| MP service | `systool/services.py` | MpService class (~line 632+) |
| Cap service | `systool/services.py` | CapService class (~line 761+) |
| Character Status OCR | `systool/services.py` | CharacterStatusService class (~line 1240+) |
| UI refresh logic | `systool/app.py` | `_refresh_variables_display()` (~line 2326) |

---

## Notes for Future Updates

When adding new variables or modifying existing ones:

1. **Add state fields to AppState** in `models.py` with proper type hints and default values
2. **Update the service that populates the value** — ensure it writes under `settings_lock`
3. **Update `_refresh_variables_display()`** in `app.py` to display the new variable
4. **Document consumption** — note which services read this variable and how they use it
5. **Consider batch reads** — if the new stat shares a base address with HP/MP/Cap, add it to `_read_all_stats()`

When adding new consumer services:
1. Read values under `settings_lock` to avoid race conditions
2. Use primary pointer values first (`hp_value`, `mp_value`, `cap_value`)
3. Fall back to OCR values (`char_status_*`) when pointer is None
4. Handle `None` gracefully — don't assume values are always available