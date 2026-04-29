"""Service package preserving the original public API."""

from .fishing import FishingService
from .healer import AutoHealerService
from .hotkeys import HotkeyJobService, HotkeyService
from .input_services import (
    AntiAfkService,
    HumanMouse,
    RightClickService,
    SafeKeyboardSession,
    WindowService,
)
from .monitoring import (
    HAS_LIGHT_MODULE,
    AlarmService,
    CapService,
    CharacterStatusService,
    HpService,
    LightControlService,
    MpService,
    StatPointerService,
)
from .position_capture import PositionCaptureService
from .runes import RuneMakerService

__all__ = [
    "HAS_LIGHT_MODULE",
    "AlarmService",
    "AntiAfkService",
    "AutoHealerService",
    "CapService",
    "CharacterStatusService",
    "FishingService",
    "HotkeyJobService",
    "HotkeyService",
    "HpService",
    "HumanMouse",
    "LightControlService",
    "MpService",
    "PositionCaptureService",
    "RightClickService",
    "RuneMakerService",
    "SafeKeyboardSession",
    "StatPointerService",
    "WindowService",
]
