"""Dependency-injection container for SystemMonitor services.

Provides a single ``ServiceContainer`` that owns all service instances.
The UI layer (app.py) only depends on the container interface, not on
concrete service classes — making it trivial to swap implementations,
mock in tests, or add new features without touching the GUI code.

Usage::

    from .container import ServiceContainer

    class SystemMonitorApp:
        def __init__(self):
            self.container = ServiceContainer()   # production wiring
            # In tests:  self.container = ServiceContainer(mock=True)

    container.py is imported by app.py; services.py and runtime.py are
    imported transitively through the container.
"""

from __future__ import annotations


class ServiceContainer:
    """Central factory / DI container for all SystemMonitor services.

    Services are created lazily on first access so that tests can inject
    mocks *before* any service is instantiated.  All services share a
    single ``AppRuntime`` instance (also managed by the container).
    """

    # ------------------------------------------------------------------
    # Public API — every attribute is a lazy property
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self._runtime = None  # set once; never changes
        # Cache for lazy construction
        self._cache: dict[str, object] = {}

    @property
    def runtime(self):
        """The shared AppRuntime instance (created on first access)."""
        if self._runtime is None:
            from .runtime import AppRuntime
            self._runtime = AppRuntime()
        return self._runtime

    # -- Service properties ------------------------------------------------

    @property
    def position_capture(self):
        from .services import PositionCaptureService
        return self._lazy("position_capture", PositionCaptureService, (self.runtime,))

    @property
    def afk_service(self):
        from .services import AntiAfkService
        return self._lazy("afk_service", AntiAfkService, (self.runtime,))

    @property
    def rclick_service(self):
        from .services import RightClickService
        return self._lazy("rclick_service", RightClickService, (self.runtime,))

    @property
    def alarm_service(self):
        from .services import AlarmService
        return self._lazy("alarm_service", AlarmService, (self.runtime,))

    @property
    def char_status_service(self):
        from .services import CharacterStatusService
        return self._lazy("char_status_service", CharacterStatusService, (self.runtime,))

    @property
    def fishing_service(self):
        from .services import FishingService
        return self._lazy("fishing_service", FishingService, (self.runtime,))

    @property
    def healer_service(self):
        from .services import AutoHealerService
        return self._lazy("healer_service", AutoHealerService, (self.runtime,))

    @property
    def light_service(self):
        from .services import LightControlService
        return self._lazy("light_service", LightControlService, (self.runtime,))

    @property
    def rune_service(self):
        from .services import RuneMakerService
        return self._lazy("rune_service", RuneMakerService, (self.runtime,))

    @property
    def job_service(self):
        from .services import HotkeyJobService
        return self._lazy("job_service", HotkeyJobService, (self.runtime,))

    # -- Internal helpers --------------------------------------------------

    def _lazy(self, key: str, cls, args: tuple) -> object:
        if key not in self._cache:
            self._cache[key] = cls(*args)
        return self._cache[key]

    # -- Testing / mocking -------------------------------------------------

    def register(self, name: str, instance: object) -> None:
        """Inject a pre-built (mocked or custom) service.

        Example for tests::

            container.register("afk_service", Mock())
        """
        self._cache[name] = instance
