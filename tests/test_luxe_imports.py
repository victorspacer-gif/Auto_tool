"""Validate that the Luxe UI's module import chain works correctly.
Simulates the exact imports that happen when luxe.py starts up.
Also verifies the ServiceContainer creates all services without errors.
"""
import sys
import os

# Add the project root to sys.path (same as running python luxe.py)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

errors = []

def test_import(label: str, import_stmt: str):
    """Try an import and record any error."""
    try:
        exec(import_stmt)
        print(f"  ✅ {label}")
    except Exception as e:
        errors.append((label, str(e)))
        print(f"  ❌ {label}: {e}")

print("=" * 60)
print("  Luxe UI Import & Service Validation")
print("=" * 60)

# 1. Core runtime (shared with raw.py)
print("\n--- Core runtime ---")
test_import("systool.runtime", "from systool import runtime as _r; _ = _r.HAS_MSS; _ = _r.HAS_CV2; _ = _r.HAS_PYNPUT")

# 2. Service container
print("\n--- Service container ---")
test_import("systool.container", "from systool.container import ServiceContainer")

# 3. Config & models
print("\n--- Config & models ---")
test_import("systool.config", "from systool.config import ConfigSerializer")
test_import("systool.models", "from systool.models import HotkeyJob")

# 4. Character profiles
print("\n--- Character profiles ---")
test_import("systool.character_profiles", "from systool.character_profiles import build_identity")

# 5. Services (shared layer)
print("\n--- Services ---")
test_import("systool.services", "from systool.services import HotkeyService, HAS_LIGHT_MODULE")

# 6. Luxe tab modules
print("\n--- Luxe tab modules ---")
for tab_name in [
    "activity_control_tab", "character_status_tab", "config_tab",
    "fishing_tab", "hotkeys_tab", "light_control_tab",
    "screen_watch_tab", "variables_tab"
]:
    test_import(f"systool.ui.luxe_tabs.{tab_name}",
                f"from systool.ui.luxe_tabs import {tab_name}")

# 7. Luxe tabs package
print("\n--- Luxe tabs package ---")
test_import("systool.ui.luxe_tabs (all)", "from systool.ui.luxe_tabs import (ActivityControlTab, CharacterStatusTab, ConfigTab, FishingTab, HotkeysTab, LightControlTab, ScreenWatchTab, VariablesTab)")

# 8. Main app module
print("\n--- Main app module ---")
test_import("systool.app_luxe", "from systool.app_luxe import run")

# 9. Service container initialization (same as both UIs do at startup)
print("\n--- Service initialization ---")
try:
    from systool.container import ServiceContainer
    container = ServiceContainer()
    rt = container.runtime
    # Access each service to trigger lazy initialization
    svc_list = [
        "afk_service", "rclick_service", "alarm_service",
        "char_status_service", "fishing_service", "light_service",
        "hp_service", "mp_service", "cap_service", "food_service",
        "job_service", "runtime_timer_service",
    ]
    for name in svc_list:
        svc = getattr(container, name)
        print(f"  ✅ container.{name}")
    print(f"  All {len(svc_list)} services initialized.")
except Exception as e:
    errors.append(("ServiceContainer initialization", str(e)))
    print(f"  ❌ ServiceContainer: {e}")

print("\n" + "=" * 60)
if errors:
    print(f"\n❌ {len(errors)} ISSUE(S) FOUND:")
    for label, msg in errors:
        print(f"   • {label}: {msg}")
    print("\nThese will cause the Luxe UI to fail on startup.")
    sys.exit(1)
else:
    print("\n✅ ALL CHECKS PASSED — Luxe UI is safe to run.")
print("=" * 60)
