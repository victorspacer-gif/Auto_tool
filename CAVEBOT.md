# 🤖 CaveBot — Automated Hunting System

The CaveBot is a fully automated hunting assistant adapted from the [TibiaAuto12](https://github.com/MuriloChianfa/TibiaAuto12) project. It walks waypoint paths, attacks monsters, and loots corpses — all configurable through the SystemMonitor GUI.

## Architecture

Three co-operating services run as background threads:

```
┌─────────────────────────────────────────────────────────┐
│                    CaveBotService                        │
│  Waypoint orchestrator — walks a scripted path, then    │
│  waits while companions handle attack + loot             │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐  ┌──────────────────────────┐  │
│  │   ChaseTargetService  │  │    AutoLooterService     │  │
│  │  Continuous monster   │  │  Background corpse       │  │
│  │  targeting scanner    │  │  looting                 │  │
│  └──────────────────────┘  └──────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                    InputRouter                           │
│  Routes all input through:                               │
│    • "hardware" mode — physical mouse/keyboard (pynput)  │
│    • "direct" mode — Win32 SendMessage to game window    │
└─────────────────────────────────────────────────────────┘
```

All three share the same `ExecutionGate`/`MouseGate` for coordinated input access, and respect the global `PauseController`.

## Workflow

### 1. Create a Script

1. Go to the **CaveBot** tab
2. Type a script name in the **Script** field, click **+ New**
3. Select a **Mark** type (e.g. CheckMark, Star, Skull — these are visual labels for your waypoints)
4. Select a **Type**: Walk / Rope / Shovel (future actions)
5. Move your character to the desired in-game position
6. Click **+ Add WP** — the current mouse cursor position is recorded as the waypoint coordinate
7. Repeat steps 3–6 for each waypoint in your path

The script is stored as a JSON file in `scripts/<name>.json`:

```json
[
  {"mark": "Star", "x": 500, "y": 300, "type": 1, "status": false},
  {"mark": "Cross", "x": 620, "y": 280, "type": 1, "status": true},
  {"mark": "Skull", "x": 750, "y": 350, "type": 1, "status": false}
]
```

The waypoint with `"status": true` is the current active waypoint.

### 2. Configure Monsters

**Chase Target** section (right column):

1. Enter monster names in **M1–M4** fields
2. Set the **Key** used to target (default: `f1`)
3. Set **Interval (ms)** — how often to re-target (default: 300ms)
4. Toggle **Follow mode** — periodically clicks on the character to re-engage follow
5. Click **🎯 Record X** to capture the battle list X-coordinate (moves mouse to the battle list side, then press F12)

### 3. Configure Looting

**Auto Looter** section (right column):

1. Add SQM positions around your character using **+ Add Pos**
2. Or click **⬇ Copy from CaveBot** to reuse the CaveBot's SQM positions
3. Set **Delay** range (min–max ms between loot cycles)
4. Toggle the looter on with **▶ Start Looter**, or keep it off for manual looting

### 4. Set Input Mode

**Input Mode** panel (right column, top):

| Mode | Cursor Moves? | Window Needs Focus? | Best For |
|---|---|---|---|
| **Hardware** (default) | Yes | Yes | Typical use with game in foreground |
| **Direct** | No | No | Background hunting while you do other work |

For **Direct mode**: enter your game window's title fragment (e.g. "Miracle") and click **Detect**. The HWND is auto-found and stored.

### 5. Start Hunting

1. Ensure your minimap region is configured (Map Region under config)
2. Set **Stand (s)** — seconds to pause at each waypoint
3. Configure toggles: **Walk**, **Loot**, **Debug**, **Follow**
4. Click **▶ Start CaveBot**

The CaveBot will:
- Auto-start ChaseTarget and AutoLooter if they're configured
- Walk through each waypoint in sequence
- At each stop: let ChaseTarget attack nearby monsters, then loot corpses
- Loop back to the first waypoint when all are done

### Stopping

- Click **⏹ Stop CaveBot** — stops all three services
- Press **HOME** key — stops **everything** (all jobs + cavebot + companions)
- Press **F5** — global pause/resume

## Configuration Reference

### CaveBot State (`cavebot_state.py`)

| Field | Default | Description |
|---|---|---|
| `script_name` | `""` | Active script name (without .json) |
| `stand_seconds` | `1` | Seconds to stand at each waypoint |
| `walking_enabled` | `true` | Walk between waypoints (camping when off) |
| `walk_for_debug` | `false` | Arrow-key refresh after each walk step |
| `follow_mode` | `true` | Click character to re-engage follow |
| `monsters_to_attack` | `[]` | List of monster names to attack |
| `battle_list_x` | `0` | X-coordinate of the battle list |
| `sqm_positions` | `[]` | Screen coordinates for looting |
| `map_region` | `null` | Minimap area (left, top, width, height) |
| `looting_enabled` | `true` | Auto-loot at each waypoint |
| `skill_key` | `"f1"` | Key to press for targeting |
| `attack_mode` | `"normal"` | Attack stance (normal/full attack/balance/full defence) |
| `suspend_after` | `5` | Seconds before suspending when can't attack |
| `monsters_range` | `3` | Attack attempts per waypoint |

### ChaseTarget State

| Field | Default | Description |
|---|---|---|
| `monster_names` | `[]` | Monster names to cycle through |
| `attack_key` | `"f1"` | Key pressed to target the nearest monster |
| `scan_interval_ms` | `300` | Milliseconds between targeting attempts |
| `follow_mode` | `true` | Click follow when character goes idle |
| `battle_list_x` | `0` | X-coordinate for battle list clicks |

### AutoLooter State

| Field | Default | Description |
|---|---|---|
| `sqm_positions` | `[]` | Screen coordinates to right-click for loot |
| `loot_delay_min_ms` | `200` | Minimum ms between loot cycles |
| `loot_delay_max_ms` | `500` | Maximum ms between loot cycles |
| `jitter` | `3` | Random pixel offset ± when clicking SQM |

### Input Mode

| Field | Default | Description |
|---|---|---|
| `input_mode` | `"hardware"` | `"hardware"` or `"direct"` |
| `game_window_title` | `""` | Title fragment for detecting the game window |
| `game_hwnd` | `null` | Explicit window handle (overrides title search) |

## Script Format

Scripts are JSON arrays of waypoint objects:

```json
{
  "mark":   "<mark-name>",      // Visual label (Star, Cross, Skull, etc.)
  "x":      <int>,              // Screen X coordinate for minimap click
  "y":      <int>,              // Screen Y coordinate for minimap click
  "type":   <1|2|3>,            // 1=Walk, 2=Rope, 3=Shovel
  "status": <bool|string>       // true=active, false=inactive, "NotConfigured"=unused
}
```

## Waypoint Mark Types

20 mark types matching TibiaAuto12:

| # | Mark | # | Mark | # | Mark | # | Mark |
|---|---|---|---|---|---|---|---|
| 1 | CheckMark | 6 | Church | 11 | Lock | 16 | ArrowDown |
| 2 | QuestionMark | 7 | Mouth | 12 | Bag | 17 | ArrowRight |
| 3 | ExclimationMark | 8 | Shovel | 13 | Skull | 18 | ArrowLeft |
| 4 | Star | 9 | Sword | 14 | Money | 19 | Above |
| 5 | Cross | 10 | Flag | 15 | ArrowUp | 20 | Bellow |

## Direct Input Mode Details

When `input_mode` is set to `"direct"`, the InputRouter uses Win32 API calls:

```python
# No cursor movement — events go straight to the window's message queue
win32api.SendMessage(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
win32api.SendMessage(hwnd, WM_LBUTTONUP, MK_LBUTTON, lparam)
win32api.SendMessage(hwnd, WM_KEYDOWN, VK_F1, 0)
```

**HWND resolution order:**
1. Explicit `game_hwnd` value (if set)
2. Exact title match via `win32gui.FindWindow(None, title)`
3. Partial title match via `win32gui.EnumWindows()` + substring search

## Companion Auto-Start

When CaveBot starts, it automatically starts ChaseTarget and AutoLooter if:

- **ChaseTarget**: `monster_names` is non-empty AND `battle_list_x > 0`
- **AutoLooter**: `sqm_positions` is non-empty

Both companions stop automatically when CaveBot stops.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Map region not configured" | Missing minimap area | Configure a map region in options |
| "No chase-target monsters configured" | Empty monster list | Add monster names in Chase Target panel |
| "Battle list X not configured" | Missing X coordinate | Click "Record X" and click on battle list |
| "No SQM positions configured" | Empty loot positions | Add SQM spots via position capture |
| "Script has no configured waypoints" | Script is a stub | Open the script, add waypoints, click Load |
| "direct input: no target HWND" | Can't find game window | Enter window title in Input Mode panel, click Detect |
| Chase target not attacking | Wrong battle list X | Re-record battle list X with the correct position |
| Character not walking | Wrong map region | Record the minimap area accurately |
| Looting too slow/fast | Delay config | Adjust min/max delay in Auto Looter panel |

## Development Notes

Based on TibiaAuto12 model:
- **CaveBotController** → `CaveBotService._worker()` — the waypoint walk loop
- **Scanners** → `ChaseTargetService` — continuous monster targeting
- **AutoLooter** → `AutoLooterService` — corpse looting
- **Hotkey/Press** → `InputRouter` — dual-mode input abstraction
- **MarksConf** → Waypoint mark names stored in `cavebot_tab.py`
