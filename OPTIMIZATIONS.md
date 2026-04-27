# Optimization Backlog — SystemMonitor (Auto_tool)

Generated: 2026-04-25

---

## Implemented

### ✅ Batch Memory Reads for Stats (#4)
Batch HP, MP, Cap reads into a single pointer resolution call since they share base address `0x00A783E0`.

---

## Pending (ordered by priority/impact)

### #1 — Cache Resolved Pointer Addresses with TTL
Every call to `get_hp()`, `get_mp()`, `get_cap()` potentially re-resolves pointer chains. After initial resolution, resolved addresses remain valid until process restart or game update. Add TTL-based caching:

```python
self._resolved_address = None
self._address_cache_time = time.time()
CACHE_TTL = 60.0  # seconds

def _resolve_pointer(self):
    if (self._resolved_address is not None 
        and time.time() - self._address_cache_time < CACHE_TTL):
        return self._resolved_address
```

**Impact:** Reduces repeated module base lookups and pointer chain walking on every stat read.

---

### #2 — Reduce Settings Polling Overhead
`_poll_settings()` runs every 500ms and reads ALL ~40+ UI variables even when nothing changed. Options:
- Use dirty-flag pattern to track which vars actually changed
- Increase polling interval from 500ms to 1000ms (settings rarely change during gameplay)

**Impact:** ~50% reduction in UI variable reads, less lock contention on `settings_lock`.

---

### #5 — Reduce Fast Poll Loop Frequency  
`_fast_poll_loop` runs every 20ms (50x/sec) triggering memory reads via `_refresh_variables_display()`. For game stat display this is overkill:

```python
# Change from 20ms to 100-200ms
self.root.after(100, self._fast_poll_loop)  # 10x/sec instead of 50x/sec
```

**Impact:** 75% reduction in memory read operations and UI updates. Game stats don't change fast enough to need 50fps polling.

---

### #6 — Execution Gate Timeout Optimization  
`ExecutionGate.acquire()` with `max_wait=0.50` for AFK creates potential blocking. Consider reducing timeout or using non-blocking try-acquire:

```python
if not self.runtime.execution.try_acquire(module_id="afk"):
    continue  # Non-blocking, immediate retry next iteration
```

**Impact:** Reduces thread blocking latency when multiple services compete.

---

### #7 — Precompute Random Ranges from Milliseconds to Seconds
Multiple services call `random.randint(min_ms, max_ms) / 1000.0` every loop iteration. Store pre-converted values:

```python
# Store as afk_min_s / afk_max_s in AppState
```

**Impact:** Minor but eliminates repeated division operations in hot loops.

---

### #8 — OCR Result Caching with TTL
OCR character status reads are expensive (screenshot + tesseract processing). No caching between polls:

```python
_ocr_cache = {}
_ocr_ttl = 0.5  # seconds

def get_char_status(self):
    now = time.time()
    if 'hp' in _ocr_cache and now - _ocr_cache['time'] < _ocr_ttl:
        return _ocr_cache['values']
```

**Impact:** Significant CPU savings when OCR runs at high frequency.

---

## Priority Ranking by Impact
1. Batch memory reads (#4) ✅ — biggest single improvement for pointer-based stats  
2. Reduce fast poll frequency (#5) — immediate 75% reduction in read operations
3. Cache resolved pointers (#1) — eliminates redundant chain resolution
4. Settings polling optimization (#2) — reduces lock contention
5. OCR caching (#8) — significant CPU savings during character status monitoring
