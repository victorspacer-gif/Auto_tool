"""Application-wide constants for timing, polling intervals, and magic numbers."""

from __future__ import annotations

# ─── Polling & Sampling ──────────────────────────────────────────────
MIN_POLL_MS: int = 250          # Minimum char_status poll interval (ms)
LIGHT_FREEZE_MIN_INTERVAL_MS: int = 30  # Minimum light freeze loop delay (ms)
CHAR_STATUS_SAMPLE_DELAY_MS: float = 1.0  # Default sample delay between readings

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
RCCLICK_INTER_CLICK_MIN: float = 0.02   # Absolute minimum inter-click gap (s)
RCCLICK_INTER_CLICK_JITTER: tuple[float, float] = (-0.05, 0.08)  # Random jitter range

# ─── Hotkey Jobs ─────────────────────────────────────────────────────
HOTKEY_EXEC_MAX_WAIT: float = 0.45    # Max wait for cursor acquire in hotkey jobs

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

# ─── Fishing Service ────────────────────────────────────────────────
FISHING_BONUS_MULTIPLIER: float = 15.0   # Bonus minutes per session minute multiplier
FISHING_MIN_BONUS_SECS: int = 60         # Minimum bonus seconds

# ─── PauseController / ExecutionGate ────────────────────────────────
EXEC_WAIT_TIMEOUT_DEFAULT: float = 0.05    # Default wait timeout when max_wait is None
EXEC_WAIT_TIMEOUT_MIN: float = 0.01        # Absolute minimum wait timeout (s)
EXEC_WAIT_TIMEOUT_MAX: float = 0.05        # Absolute maximum wait timeout (s)

# ─── Pygame Audio ────────────────────────────────────────────────────
PYGAME_MIXER_FREQ: int = 44100    # Sample rate (Hz)
PYGAME_MIXER_FORMAT: int = -16    # Bit depth
PYGAME_MIXER_CHANNELS: int = 2    # Stereo
PYGAME_MIXER_BUFFER: int = 512    # Buffer size

# ─── UI / Layout ─────────────────────────────────────────────────────
UI_THRESHOLD_WIDTH: int = 1180    # Responsive column threshold (px)
