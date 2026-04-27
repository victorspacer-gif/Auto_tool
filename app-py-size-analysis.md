# app.py Size Reduction Analysis Report

## Summary

File: ~/projects/Auto_tool/systool/app.py
Size: 2,586 lines / ~140 KB
Date: 2026-04-25

---

## Opportunities Identified (Total reducible: ~399 lines, ~15% reduction)

### Priority 1 - HP/MP/Cap Display Logic (~120 lines reducible)

Methods `_refresh_character_status_display` and `_refresh_variables_display` both contain nearly identical patterns for displaying HP, MP, and Cap values with source tags. The same logic appears twice:

```python
# Pattern repeated in BOTH methods:
hp_display = state.hp_value if state.hp_value is not None else state.char_status_hp
source_tag = f" [{state.hp_source}]" if state.hp_source == "pointer" ...
self.xxx_label.config(text=f"HP: {hp_display}...{source_tag}")
```

Fix: Extract a helper that takes the value, source, and label, reducing ~40 lines per method.

---

### Priority 2 - Settings Polling Loop (~80 lines reducible)

Lines 2159-2231 in `_poll_settings` have dozens of nearly identical patterns:
```python
state.xxx = get_ms("xxx_var", state.xxx)
state.yyy = max(0, get_int("yyy_var", state.yyy))
```

Fix: Use a declarative configuration list mapping UI var names to state attributes with validators. Reduces from ~80 lines of imperative code to ~30 lines of data-driven config.

---

### Priority 3 - Region Selection Handlers (~60 lines reducible)

Lines 1839-1867 have 5 nearly identical `select_*_region` methods:
- select_alarm_area()
- select_character_status_region()
- select_character_status_hp_region()
- select_character_status_mana_region()
- select_character_status_cap_region()

Each calls `_select_screen_region()` with only different title text and callback. Could be consolidated into a single parameterized method or a factory pattern.

---

### Priority 4 - Label Config Updates (~60 lines reducible)

Lines 2045-2064 and elsewhere: Multiple blocks that check `if self.xxx_label:` then call `.config()`. Pattern like:
```python
if self.pos_label:
    self.pos_label.config(text=f"Pos: {state.rclick_pos[0]}, ...")
if self.rod_label:
    self.rod_label.config(text=f"Rod: {...}")
# ... repeated for rune_hand, rune_storage, rune_blank, healer_char, healer_rune
```

Fix: Create a helper `_update_position_label(label, name, pos)` and loop over a config list. Reduces ~30 lines of repetitive label updates.

---

### Priority 5 - Pointer Auto-Attach (~45 lines reducible)

Lines 2080-2129: `_auto_attach_pointer_services` has three nearly identical blocks for HP, MP, and Cap services:
```python
if self.hp_service is not None:
    try:
        ok, msg = self.hp_service.attach()
        if ok and self.hp_service._hp_address is not None:
            self.runtime.ui.log(f"[HP] Auto-attached -> 0x{...}")
        else:
            self.runtime.ui.log(f"[HP] Auto-attach failed: {msg}")
    except Exception as exc:
        self.runtime.ui.log(f"[HP] Auto-attach exception: {exc}")
```

Fix: Loop over a list of `(service, label, attr_name)` tuples. Reduces from ~45 lines to ~12 lines.

---

### Priority 6 - Detach Logic (~24 lines reducible)

Lines 2448-2467: `on_close()` has four nearly identical try/except blocks for detaching services:
```python
try:
    self.light_service.detach()
except Exception: pass
try:
    if self.hp_service is not None:
        self.hp_service.detach()
except Exception: pass
# ... repeated for mp, cap
```

Fix: Single loop over service references with a helper. Reduces from ~24 lines to ~8 lines.

---

### Priority 7 - Import Consolidation (~10 lines reducible)

Lines 2087-2089 import three profile modules inside a method. Could move to top-level imports with `if` guards or consolidate into a single import statement.

---

## Priority Ranking Summary

| Priority | Area                  | Lines Saved | Effort   |
|----------|-----------------------|-------------|----------|
| 1        | HP/MP/Cap display     | ~120 lines  | Medium   |
| 2        | Settings polling loop | ~80 lines   | Medium   |
| 3        | Region selection      | ~60 lines   | Low      |
| 4        | Label config updates  | ~60 lines   | Low      |
| 5        | Pointer auto-attach   | ~45 lines   | Low      |
| 6        | Detach logic          | ~24 lines   | Low      |
| 7        | Import consolidation  | ~10 lines   | Trivial  |

Total reducible: ~399 lines (about 15% reduction)

## Recommended Approach

The biggest wins come from extracting helper methods and using data-driven patterns instead of imperative code.