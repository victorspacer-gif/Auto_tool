# Auto_tool Test Coverage — Remaining Work

## Status

- **Total existing tests:** 153 passed, 6 skipped (across 7 files)
- **Newly added:** `tests/test_container.py` — 40 tests covering DI container
- **Coverage gap:** ~4,182 lines of service/UI code with zero or partial test coverage

---

## Priority 1 — High Impact / Low Effort (Core Logic)

### 1.1 `systool/runtime.py` (394 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| R1 | `AppRuntime.__init__()` | Default state: `_config`, `_state`, `_listeners`, `_optional_deps` initialized correctly |
| R2 | `AppRuntime.load_config(cfg)` | Loads config dict, updates `_config`, triggers listeners |
| R3 | `AppRuntime.save_config()` | Serializes current config back to dict format |
| R4 | `AppRuntime.add_listener(name, callback)` | Registers listener, verifies it's called on state change |
| R5 | `AppRuntime.remove_listener(name)` | Removes listener, subsequent changes don't call it |
| R6 | `_detect_optional_deps()` | Correctly identifies available optional modules (psutil, etc.) |
| R7 | State persistence across config load/save cycles | Round-trip: save → reload → compare |

**Why first:** Runtime is the state hub. If this is broken, every service silently fails.

---

### 1.2 `systool/config.py` (368 lines) — partial coverage exists

| # | Test Target | What to Verify |
|---|-------------|----------------|
| C1 | `ConfigSerializer.to_json()` | Serializes all fields including nested dicts |
| C2 | `ConfigSerializer.load_file(path)` with missing file | Raises appropriate error (FileNotFoundError) |
| C3 | `ConfigSerializer.load_file(path)` with malformed JSON | Raises ValueError / json.JSONDecodeError |
| C4 | Legacy field migration — old config format → new format | Backward compatibility for renamed fields |
| C5 | Default values when optional keys are missing | Config doesn't crash on partial data |

**Why:** You already have round-trip tests. Add error-path coverage to prevent silent failures in production.

---

## Priority 2 — Core Services (Business Logic)

### 2.1 `systool/services/fishing.py` (229 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| F1 | `FishingService.cast_rod()` | Validates state before casting, calls correct runtime method |
| F2 | `FishingService.reel_in()` | Handles success/failure paths, updates UI via runtime |
| F3 | `FishingService._manage_spots()` | Adds/removes spots based on availability logic |
| F4 | State transitions: idle → fishing → reeling → done | Full lifecycle without touching UI |

**Why:** Fishing is the most complex extracted service. 229 lines of domain logic with only lock tests.

---

### 2.2 `systool/services/healer.py` (176 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| H1 | `AutoHealerService.check_and_heal()` | Reads HP from runtime, decides when to heal |
| H2 | Threshold logic — heals only below configured % | Boundary: exactly at threshold, just above, just below |
| H3 | Cooldown handling between heals | Doesn't spam heal commands |
| H4 | Integration with HpService (reads correct pointer) | Verifies it calls `runtime.hp_service` not a stale value |

---

### 2.3 `systool/services/runes.py` (174 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| Rn1 | `RuneMakerService.cast_rune_sequence()` | Correct spell order, handles failures mid-sequence |
| Rn2 | Rune spot management — creates/uses spots | Verifies position capture integration |
| Rn3 | Cooldown between rune casts | Doesn't cast faster than game allows |

---

### 2.4 `systool/services/hotkeys.py` (223 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| HK1 | `HotkeyJobService.add_job(job)` | Validates job, adds to internal list |
| HK2 | `HotkeyJobService.remove_job(key)` | Removes by key, verifies it's gone |
| HK3 | `HotkeyService.register_hotkey()` | Binds key combo, stores in registry |
| HK4 | Duplicate hotkey detection — same key twice | Raises error or warns |

---

## Priority 3 — Input Services (Complex, Hard to Test)

### 2.5 `systool/services/input_services.py` (541 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| I1 | `AntiAfkService.check_and_move()` | Detects idle state, triggers movement |
| I2 | `RightClickService.right_click_at()` | Validates coordinates before clicking |
| I3 | `WindowService` window focus management | Verifies win32 calls (mocked) are correct |

**Note:** These depend heavily on Windows-specific APIs. Mock `pywin32`, `pynput`, and `pyautogui`.

---

## Priority 4 — UI Tabs (Hardest to Test)

### 2.6 `systool/ui/tabs/character_status_tab.py` (244 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| CT1 | Tab initialization — creates all widgets | Verifies Tkinter widget creation |
| CT2 | `_update_hp_mp()` reads from services and updates labels | Data flow: service → runtime → UI label |
| CT3 | Button callbacks trigger correct service methods | Click "Start" → calls `fishing_service.cast_rod()` |

---

### 2.7 `systool/ui/tabs/fishing_tab.py` (329 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| FT1 | Spot management UI — add/remove spots | Widget state changes match service calls |
| FT2 | Casting button → triggers `fishing_service.cast_rod()` | Event handler wiring |
| FT3 | Status label updates during fishing cycle | Real-time UI feedback |

---

### 2.8 `systool/ui/tabs/healer_tab.py` (137 lines) + `rune_tab.py` (190 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| HT1 / RT1 | Threshold sliders → update config via runtime | Slider value → `_config["heal_threshold"]` |
| HT2 / RT2 | Enable/disable toggles → service start/stop | Toggle state → `service.start()` / `service.stop()` |

---

## Priority 5 — Monitoring Services (Already Partially Covered)

### 2.9 `systool/services/monitoring.py` (1,068 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| M1 | `StatPointerService._read_pointer()` | Mock memory read, verify correct address + format parsing |
| M2 | `HpService` / `MpService` / `CapService` inheritance | Each reads from correct pointer offset |
| M3 | `AlarmService` trigger logic — fires when value crosses threshold | Boundary testing for alarm activation/deactivation |
| M4 | `CharacterStatusService` character data aggregation | Combines HP, MP, Cap into status dict |

**Note:** 1,068 lines is the largest module. Focus on pointer reading and alarm logic first.

---

## Priority 6 — Position Capture (Small but Critical)

### 2.10 `systool/services/position_capture.py` (49 lines)

| # | Test Target | What to Verify |
|---|-------------|----------------|
| PC1 | `PositionCaptureService.capture()` | Takes screenshot, returns coordinates |
| PC2 | `PositionCaptureService.reset()` | Clears cached position |
| PC3 | Integration with mss library (mocked) | Verifies correct region + format calls |

---

## Effort Estimates

| Priority | Module | Est. Tests | Est. Hours |
|----------|--------|-----------|------------|
| P1 | runtime.py | 7 tests | ~2h |
| P1 | config.py (edge cases) | 5 tests | ~1h |
| P2 | fishing.py | 4 tests | ~3h |
| P2 | healer.py | 4 tests | ~2h |
| P2 | runes.py | 3 tests | ~2h |
| P2 | hotkeys.py | 4 tests | ~2h |
| P3 | input_services.py | 3 tests | ~3h |
| P4 | UI tabs (all) | 8+ tests | ~6h |
| P5 | monitoring.py | 4 tests | ~3h |
| P6 | position_capture.py | 3 tests | ~1h |
| **Total** | | **~42-47 tests** | **~24-26h** |

---

## Suggested Order of Execution

1. **runtime.py** — foundational, small module, high impact
2. **config.py edge cases** — quick wins, complements existing round-trip tests
3. **fishing.py + healer.py** — most-used services, complex logic
4. **runes.py + hotkeys.py** — similar patterns to fishing/healer
5. **input_services.py** — hardest due to Windows deps, mock everything
6. **UI tabs** — test event handlers and data flow, not Tkinter internals
7. **monitoring.py** — pointer reading is the critical path
8. **position_capture.py** — small but needed by rune/fishing services

---

## Notes & Constraints

- All tests run on Linux (Fedora 43) — Windows APIs must be mocked
- `conftest.py` already mocks: tkinter, pywin32, psutil
- UI tab tests should focus on **event handler wiring** and **data flow**, not widget rendering
- Service tests should verify **behavior** (what methods are called with what args), not internal state
- Use `unittest.mock.MagicMock` for all external dependencies (mss, pytesseract, pyautogui)
