"""Application-wide constants for timing, polling intervals, and magic numbers."""

from __future__ import annotations

# ─── Polling & Sampling ──────────────────────────────────────────────
LIGHT_FREEZE_MIN_INTERVAL_MS: int = 30  # Minimum light freeze loop delay (ms)
CHAR_STATUS_SAMPLE_DELAY_MS: float = 1.0  # Default sample delay between readings
APP_SETTINGS_POLL_INTERVAL_MS: int = 500  # UI settings sync poll interval (ms)
APP_STATS_POLL_INTERVAL_MS: int = 100  # Background stats polling interval (ms)
APP_TRAY_POLL_INTERVAL_MS: int = 500  # Tray state poll interval (ms)
APP_TRAY_BOOTSTRAP_DELAY_MS: int = 1000  # Initial tray poll delay (ms)

# ─── Alarm / Thresholds ──────────────────────────────────────────────
ALARM_COOLDOWN_DEFAULT: float = 5.0   # Default cooldown between alarm triggers (seconds)
ALARM_THRESHOLD_DEFAULT: float = 80.0  # Default HP/MP/Cap threshold (%)

# ─── AFK / Activity Monitor ──────────────────────────────────────────
AFK_MIN_MS_DEFAULT: int = 3000        # Default minimum AFK interval (ms)
AFK_MAX_MS_DEFAULT: int = 5000        # Default maximum AFK interval (ms)
AFK_EXEC_MAX_WAIT: float = 0.50       # Max wait for cursor acquire in AFK loop

# ─── Right-Click / RClick ────────────────────────────────────────────
RCCLICK_MIN_MS_DEFAULT: int = 100     # Default minimum rclick interval (ms)
RCCLICK_MAX_MS_DEFAULT: int = 200     # Default maximum rclick interval (ms)
RCCLICK_FOOD_BURST_INTERVAL_MIN_MS: int = 50   # Minimum burst interval (ms)
RCCLICK_CLICK_DELAY_MIN_MS: int = 100    # Minimum click delay (ms)
RCCLICK_WAIT_INTERRUPTIBLE: float = 1.0  # Wait between rclick iterations (seconds)
RCCLICK_QUEUE_WINDOW_MIN: float = 0.35    # Minimum queue window for food bursts (s)
RCCLICK_INTER_CLICK_MIN: float = 0.02   # Absolute minimum inter-click gap (s)
RCCLICK_INTER_CLICK_JITTER: tuple[float, float] = (-0.05, 0.08)  # Random jitter range

# ─── Hotkey Jobs ─────────────────────────────────────────────────────
HOTKEY_EXEC_MAX_WAIT: float = 0.45    # Max wait for cursor acquire in hotkey jobs
HOTKEY_FOCUS_RESTORE_DELAY: float = 0.05  # Delay after focus restore (s)
HOTKEY_KEY_TAP_HOLD: float = 0.03     # Key tap hold duration (s)

# ─── Healer Service ──────────────────────────────────────────────────
HEALER_WAIT_INTERRUPTIBLE_1: float = 0.15   # Initial wait (s)
HEALER_WAIT_INTERRUPTIBLE_2: float = 0.12   # Post-cast settle (s)
HEALER_WAIT_INTERRUPTIBLE_3: float = 0.2    # Mana check retry (s)
HEALER_EXEC_MAX_WAIT: float = 0.25          # Cursor acquire max wait (s)
HEALER_COOLDOWN_SHORT: float = 0.05         # Short cooldown after cast (s)
HEALER_COOLDOWN_LONG: float = 0.35          # Long cooldown between casts (s)
HEALER_MOUSE_MAX_WAIT: float = 0.35         # Mouse acquire max wait (s)
HEALER_COOLDOWN_AFTER_MOUSE: float = 0.08   # Cooldown after mouse action (s)

# ─── Rune Service ────────────────────────────────────────────────────
RUNE_WAIT_INTERRUPTIBLE: float = 1.0    # Wait between rune cycles (seconds)
RUNE_POST_CAST_SETTLE: float = 0.15     # Post-cast settle wait (s)
RUNE_QUEUE_WINDOW_BASE: float = 0.90    # Base queue window offset (s)
RUNE_QUEUE_WINDOW_BUFFER: float = 0.40  # Additional buffer for rune cycle (s)
RUNE_SPELL_HOLD_SECONDS: float = 0.04   # Spell tap hold duration (s)

# ─── Fishing Service ────────────────────────────────────────────────
FISHING_BONUS_MULTIPLIER: float = 15.0   # Bonus minutes per session minute multiplier
FISHING_MIN_BONUS_SECS: int = 60         # Minimum bonus seconds
FISHING_CHUNK_MIN: float = 0.25          # Min chunk sleep duration (s)
FISHING_CYCLE_WINDOW_BASE: float = 0.90  # Base cycle window offset (s)
FISHING_CYCLE_WINDOW_ADDITION: float = 1.20  # Additional cycle window (s)
FISHING_PAUSE_SHORT_MIN: float = 0.07    # Short pause min (s)
FISHING_PAUSE_SHORT_MAX: float = 0.17    # Short pause max (s)
FISHING_PAUSE_MEDIUM_MIN: float = 0.10   # Medium pause min (s)
FISHING_PAUSE_MEDIUM_MAX: float = 0.26   # Medium pause max (s)
FISHING_MOVE_BASE_DURATION: float = 0.25  # Base mouse move duration for fishing (s)
FISHING_MIN_MOVE_DURATION: float = 0.10   # Min mouse move duration for fishing (s)

# ─── Input Services / Mouse ────────────────────────────────────────
INPUT_MOUSE_DURATION_MIN: float = 0.12    # Min mouse move duration (s)
INPUT_MOUSE_DURATION_MAX: float = 0.55    # Max mouse move duration (s)
INPUT_CONTROL_SCALE_RANGE: tuple[float, float] = (-35, 35)  # Curve offset range for HumanMouse
INPUT_MOUSE_SPEED_DIVISOR_MIN: int = 900  # Min speed divisor for distance calc
INPUT_MOUSE_SPEED_DIVISOR_MAX: int = 1500 # Max speed divisor for distance calc
INPUT_FAKE_JITTER_RANGE: tuple[float, float] = (-0.9, 0.9)  # Fake mouse jitter ±
INPUT_PRESS_DELAY_MIN: float = 0.06       # Min press delay (s)
INPUT_PRESS_DELAY_MAX: float = 0.14       # Max press delay (s)
INPUT_HOLD_DELAY_MIN: float = 0.05        # Min hold delay (s)
INPUT_HOLD_DELAY_MAX: float = 0.10        # Max hold delay (s)
INPUT_SETTLE_DELAY_MIN: float = 0.04      # Min settle delay (s)
INPUT_SETTLE_DELAY_MAX: float = 0.09      # Max settle delay (s)
INPUT_POST_CLICK_SLEEP: float = 0.08      # Post-click sleep (s)
INPUT_RCCLICK_PAUSE_1: float = 0.04       # RClick pause tier 1 (s)
INPUT_RCCLICK_PAUSE_2: float = 0.03       # RClick pause tier 2 (s)
INPUT_RCCLICK_PAUSE_3: float = 0.02       # RClick pause tier 3 (s)
INPUT_RCCLICK_MAX_WAIT: float = 0.80          # Max wait for rclick queue (s)
INPUT_QUEUE_WINDOW: float = 0.80          # Queue window duration (s)
AFK_CTRL_HOLD_MIN: float = 0.04           # Ctrl hold min (s)
AFK_CTRL_HOLD_MAX: float = 0.08           # Ctrl hold max (s)
AFK_DIR_PRESS_MIN: float = 0.03           # Direction key press min (s)
AFK_DIR_PRESS_MAX: float = 0.06           # Direction key press max (s)
AFK_DIR_RELEASE_MIN: float = 0.02         # Release pause min (s)
AFK_DIR_RELEASE_MAX: float = 0.04         # Release pause max (s)
RIGHT_CLICK_FOOD_BURST_COOLDOWN: float = 1.5  # Cooldown after a food burst (s)

# ─── Healer Service ────────────────────────────────────────────────
HEALER_CAST_HOLD_SECONDS: float = 0.03    # Spell tap hold duration (s)
HEALER_COOLDOWN_AFTER_TAP: float = 0.05   # Cooldown after spell tap (s)
HEALER_MOVE_BASE_DURATION: float = 0.20   # Base mouse move duration divisor
HEALER_MIN_MOVE_DURATION: float = 0.05    # Min mouse move duration (s)
HEALER_POST_ACTION_SLEEP: float = 0.04    # Sleep after move/tap action (s)
HEALER_MAX_COOLDOWN_BASE: float = 0.45    # Max cooldown base before rune delay (s)
HEALER_MIN_WAIT_TIMEOUT: float = 0.1      # Minimum wait timeout for healer actions (s)

# ─── Monitoring / Alarm Service ────────────────────────────────────
MONITOR_POLL_SLEEP: float = 0.1           # Poll loop sleep interval (s)
MONITOR_ERROR_RETRY_SLEEP: float = 0.5    # Error retry sleep interval (s)
FISHING_AUTO_RESTART_DELAY: float = 1.0   # Delay before restarting fishing (s)

# ─── PauseController / ExecutionGate ────────────────────────────────
EXEC_WAIT_TIMEOUT_DEFAULT: float = 0.05    # Default wait timeout when max_wait is None
EXEC_WAIT_TIMEOUT_MIN: float = 0.01        # Absolute minimum wait timeout (s)
EXEC_WAIT_TIMEOUT_MAX: float = 0.05        # Absolute maximum wait timeout (s)
PAUSE_CONTROLLER_SLEEP_INTERVAL: float = 0.01  # Poll interval while paused/waiting (s)

# ─── Pygame Audio ────────────────────────────────────────────────────
PYGAME_MIXER_FREQ: int = 44100    # Sample rate (Hz)
PYGAME_MIXER_FORMAT: int = -16    # Bit depth
PYGAME_MIXER_CHANNELS: int = 2    # Stereo
PYGAME_MIXER_BUFFER: int = 512    # Buffer size
PYGAME_DEFAULT_VOLUME: float = 1.0  # Default alarm playback volume

# ─── Alarm Sound ──────────────────────────────────────────────────────
ALARM_SOUND_FILENAME: str = "brazil-alarm.mp3"  # Bundled default alarm sound (in systool/services/)

# ─── UI / Layout ─────────────────────────────────────────────────────
UI_THRESHOLD_WIDTH: int = 1180    # Responsive column threshold (px)
APP_WINDOW_MIN_WIDTH: int = 960   # Main window minimum width
APP_WINDOW_MIN_HEIGHT: int = 720  # Main window minimum height
