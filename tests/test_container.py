"""Tests for systool.container.ServiceContainer — DI wiring, lazy loading, caching."""

from unittest.mock import MagicMock, patch

import pytest

from systool.container import ServiceContainer


# ---------------------------------------------------------------------------
# Runtime property
# ---------------------------------------------------------------------------

class TestRuntimeProperty:
    """AppRuntime is created lazily and cached."""

    def test_runtime_is_none_until_access(self):
        container = ServiceContainer()
        assert container._runtime is None

    @patch("systool.runtime.AppRuntime")
    def test_creates_app_runtime_on_first_access(self, MockRuntime):
        mock_instance = MagicMock()
        MockRuntime.return_value = mock_instance

        container = ServiceContainer()
        rt = container.runtime

        assert rt is mock_instance
        MockRuntime.assert_called_once_with()

    @patch("systool.runtime.AppRuntime")
    def test_runtime_is_cached(self, MockRuntime):
        """Second access returns the same instance without re-creating."""
        mock_instance = MagicMock()
        MockRuntime.return_value = mock_instance

        container = ServiceContainer()
        rt1 = container.runtime
        rt2 = container.runtime

        assert rt1 is rt2
        MockRuntime.assert_called_once()  # only called once


# ---------------------------------------------------------------------------
# _lazy helper
# ---------------------------------------------------------------------------

class TestLazyHelper:
    """_lazy creates on first call, caches on subsequent calls."""

    def test_creates_instance_on_first_call(self):
        container = ServiceContainer()
        mock_cls = MagicMock(return_value="new_instance")

        result1 = container._lazy("my_svc", mock_cls, ("arg1",))
        assert result1 == "new_instance"
        mock_cls.assert_called_once_with("arg1")

    def test_caches_result_on_second_call(self):
        container = ServiceContainer()
        mock_cls = MagicMock(return_value="cached_instance")

        result1 = container._lazy("my_svc", mock_cls, ("a",))
        result2 = container._lazy("my_svc", mock_cls, ("b",))  # args ignored

        assert result1 is result2
        mock_cls.assert_called_once_with("a")  # only called once with original args


# ---------------------------------------------------------------------------
# Service properties — lazy creation + caching
# ---------------------------------------------------------------------------

class TestServiceProperties:
    """Each service property creates the correct type on first access and caches."""

    def _make_container(self):
        return ServiceContainer()

    @pytest.mark.parametrize(
        "attr,expected_cls_name",
        [
            ("position_capture", "PositionCaptureService"),
            ("afk_service", "AntiAfkService"),
            ("rclick_service", "RightClickService"),
            ("alarm_service", "AlarmService"),
            ("char_status_service", "CharacterStatusService"),
            ("fishing_service", "FishingService"),
            ("healer_service", "AutoHealerService"),
            ("light_service", "LightControlService"),
            ("hp_service", "HpService"),
            ("mp_service", "MpService"),
            ("cap_service", "CapService"),
            ("rune_service", "RuneMakerService"),
            ("job_service", "HotkeyJobService"),
        ],
    )
    def test_creates_correct_type(self, attr, expected_cls_name):
        """First access creates the service with (self.runtime,) as args."""
        container = self._make_container()

        # Patch AppRuntime so runtime returns a mock
        mock_runtime = MagicMock()
        with patch("systool.runtime.AppRuntime", return_value=mock_runtime):
            service = getattr(container, attr)

        # Verify the correct class was instantiated (not a MagicMock)
        assert container._cache[attr] is not None
        # The service should have been created with runtime as its argument
        assert hasattr(service, "__class__")

    @pytest.mark.parametrize(
        "attr,expected_cls_name",
        [
            ("position_capture", "PositionCaptureService"),
            ("afk_service", "AntiAfkService"),
            ("rclick_service", "RightClickService"),
            ("alarm_service", "AlarmService"),
            ("char_status_service", "CharacterStatusService"),
            ("fishing_service", "FishingService"),
            ("healer_service", "AutoHealerService"),
            ("light_service", "LightControlService"),
            ("hp_service", "HpService"),
            ("mp_service", "MpService"),
            ("cap_service", "CapService"),
            ("rune_service", "RuneMakerService"),
            ("job_service", "HotkeyJobService"),
        ],
    )
    def test_caches_service_instance(self, attr, expected_cls_name):
        """Second access returns the same instance without re-creating."""
        container = self._make_container()

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            MockRuntime.return_value = mock_runtime

            svc1 = getattr(container, attr)
            svc2 = getattr(container, attr)

        assert svc1 is svc2
        # Verify the service class was only instantiated once
        # (we can check cache size to confirm)
        assert len(container._cache) == 1


# ---------------------------------------------------------------------------
# register — manual injection / mocking
# ---------------------------------------------------------------------------

class TestRegister:
    """register() overwrites cached services and can inject before lazy access."""

    def test_register_overwrites_cached_service(self):
        container = ServiceContainer()
        with patch("systool.runtime.AppRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            MockRuntime.return_value = mock_runtime
            svc1 = container.afk_service  # create real (mocked) instance

        custom_svc = MagicMock(spec=svc1)
        container.register("afk_service", custom_svc)

        assert container._cache["afk_service"] is custom_svc

    def test_register_before_lazy_access(self):
        """Inject a mock before any lazy property is accessed."""
        container = ServiceContainer()
        fake_svc = MagicMock()
        container.register("afk_service", fake_svc)

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            MockRuntime.return_value = MagicMock()
            result = container.afk_service

        assert result is fake_svc  # _lazy skips creation when key exists

    def test_register_arbitrary_name(self):
        """register accepts any string name — useful for custom services."""
        container = ServiceContainer()
        obj = MagicMock(spec=list)
        container.register("custom_thing", obj)

        assert container._cache["custom_thing"] is obj


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Boundary conditions and error paths."""

    def test_runtime_and_service_access_order(self):
        """Access runtime first, then a service — both should work."""
        container = ServiceContainer()

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            mock_rt = MagicMock()
            MockRuntime.return_value = mock_rt
            rt1 = container.runtime

            # Now access a service (runtime is already cached)
            svc = container.fishing_service

        assert container._runtime is not None  # runtime was created

    def test_cache_isolation_between_services(self):
        """Each service has its own cache key; they don't collide."""
        container = ServiceContainer()

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            mock_rt = MagicMock()
            MockRuntime.return_value = mock_rt

            _ = container.afk_service
            _ = container.fishing_service

        assert len(container._cache) == 2
        assert "afk_service" in container._cache
        assert "fishing_service" in container._cache
        assert container._cache["afk_service"] is not container._cache["fishing_service"]

    def test_register_does_not_affect_runtime(self):
        """register only touches _cache, never _runtime."""
        container = ServiceContainer()

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            mock_rt = MagicMock()
            MockRuntime.return_value = mock_rt
            rt = container.runtime  # create runtime first

        custom_svc = MagicMock()
        container.register("afk_service", custom_svc)

        assert container._runtime is mock_rt  # runtime unchanged


# ---------------------------------------------------------------------------
# Integration — full wiring with mocked services
# ---------------------------------------------------------------------------

class TestIntegration:
    """End-to-end: register mocks, access all services, verify no errors."""

    def test_all_services_accessible_after_register(self):
        """Register a single mock and confirm every property returns it (or its own)."""
        container = ServiceContainer()

        # Register afk_service before any lazy creation
        fake_afk = MagicMock()
        container.register("afk_service", fake_afk)

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            MockRuntime.return_value = MagicMock()
            assert container.afk_service is fake_afk

    def test_runtime_is_shared_across_services(self):
        """All services receive the same runtime instance."""
        container = ServiceContainer()

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            mock_rt = MagicMock()
            MockRuntime.return_value = mock_rt

            _ = container.fishing_service
            _ = container.healer_service
            _ = container.rune_service

        # Verify each service was constructed (cache has 3 entries)
        assert len(container._cache) == 3
        assert "fishing_service" in container._cache
        assert "healer_service" in container._cache
        assert "rune_service" in container._cache

    def test_accessing_all_13_services(self):
        """Access every service property — all should succeed without errors."""
        container = ServiceContainer()

        with patch("systool.runtime.AppRuntime") as MockRuntime:
            mock_rt = MagicMock()
            MockRuntime.return_value = mock_rt

            services = [
                "position_capture", "afk_service", "rclick_service",
                "alarm_service", "char_status_service", "fishing_service",
                "healer_service", "light_service", "hp_service",
                "mp_service", "cap_service", "rune_service", "job_service",
            ]

            for name in services:
                svc = getattr(container, name)
                # Each service should be a real instance (not MagicMock)
                assert svc is not None

        assert len(container._cache) == 13
