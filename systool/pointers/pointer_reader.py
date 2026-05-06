"""Centralized pointer reader used by all stat-related modules."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .memory_backend import AddressResolveError, LightMemoryController
from .profiles import DEFAULT_LIGHT_PROFILE, STAT_PROFILES, LightPointerProfile, StatPointerProfile


@dataclass
class CachedPointer:
    address: int
    resolved_at: float


class PointerReader:
    """Shared pointer resolver/reader for HP, MP, Cap, Food, and Light."""

    def __init__(self, controller: LightMemoryController, cache_ttl: float = 60.0) -> None:
        self.controller = controller
        self.cache_ttl = cache_ttl
        self._cache: dict[str, CachedPointer] = {}

    def clear_cache(self, stat_name: str | None = None) -> None:
        if stat_name is None:
            self._cache.clear()
            return
        self._cache.pop(stat_name, None)

    def resolve_address(self, stat_name: str, refresh: bool = False) -> int:
        profile = self._get_stat_profile(stat_name)
        cached = self._cache.get(stat_name)
        if not refresh and cached and (time.time() - cached.resolved_at) < self.cache_ttl:
            return cached.address

        module_base = self.controller.get_module_base(profile.module_name)
        read_probe = self._get_read_callable(profile.read_method)
        last_error: Exception | None = None

        for chain in profile.pointer_chains:
            try:
                base_candidate = self.controller.resolve_pointer_chain(module_base, list(chain))
                address = base_candidate + profile.structure_value_offset
                read_probe(address)
                self._cache[stat_name] = CachedPointer(address=address, resolved_at=time.time())
                return address
            except Exception as exc:
                last_error = exc

        raise AddressResolveError(
            f"Unable to resolve {stat_name} pointer."
        ) from last_error

    def resolve_light_address(self, refresh: bool = False) -> int:
        cached = self._cache.get("light")
        if not refresh and cached and (time.time() - cached.resolved_at) < self.cache_ttl:
            return cached.address

        profile = DEFAULT_LIGHT_PROFILE
        address = self.controller.resolve_light_address(
            module_name=profile.module_name,
            pointer_chains=[list(chain) for chain in profile.pointer_chains],
            structure_value_offset=profile.structure_value_offset,
            signature_pattern=profile.signature_pattern,
            signature_offset_to_base=profile.signature_offset_to_base,
        )
        self._cache["light"] = CachedPointer(address=address, resolved_at=time.time())
        return address

    def resolve_light_pair_addresses(self, refresh: bool = False) -> tuple[int, int]:
        color_address = self.resolve_light_address(refresh=refresh)
        intensity_address = color_address + 1
        self.controller.read_byte(intensity_address)
        return color_address, intensity_address

    def get_profile(self, stat_name: str) -> StatPointerProfile:
        return self._get_stat_profile(stat_name)

    def get_light_profile(self) -> LightPointerProfile:
        return DEFAULT_LIGHT_PROFILE

    def read_hp(self) -> int:
        return int(self._read_stat("hp"))

    def read_mp(self) -> float:
        return float(self._read_stat("mp"))

    def read_cap(self) -> float:
        return float(self._read_stat("cap"))

    def read_food(self) -> int:
        return int(self._read_stat("food"))

    def read_light(self) -> int:
        address = self.resolve_light_address()
        return int(self.controller.read_byte(address))

    def _read_stat(self, stat_name: str) -> Any:
        profile = self._get_stat_profile(stat_name)
        address = self.resolve_address(stat_name)
        reader = self._get_read_callable(profile.read_method)
        return reader(address)

    def _get_stat_profile(self, stat_name: str) -> StatPointerProfile:
        try:
            return STAT_PROFILES[stat_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported stat pointer: {stat_name}") from exc

    def _get_read_callable(self, read_method: str):
        if read_method == "read_byte":
            return self.controller.read_byte
        if read_method == "read_double":
            return self.controller.read_double
        raise ValueError(f"Unsupported read method: {read_method}")
