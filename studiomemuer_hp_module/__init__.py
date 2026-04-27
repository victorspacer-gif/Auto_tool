"""HP pointer module — re-exports HP profile and the shared memory backend from the light module."""

from .hp_profile import DEFAULT_HP_PROFILE, HPProfile
from studiomemuer_light_module.memory_backend import (
    AddressResolveError,
    LightMemoryController as MemoryBackend,
    MemoryWriteError,
    ProcessNotFoundError,
)

__all__ = [
    "DEFAULT_HP_PROFILE",
    "HPProfile",
    "AddressResolveError",
    "MemoryWriteError",
    "ProcessNotFoundError",
]
