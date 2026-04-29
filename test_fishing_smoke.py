"""Quick smoke test: verify fishing service works without needing the game running."""
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from systool.container import ServiceContainer

# 1. Create container (runtime created lazily on first access)
container = ServiceContainer()

# 2. Force runtime creation so we can set state before services touch it
_ = container.runtime
state = container.runtime.state

# 3. Override state with fishing prerequisites met
state.fish_rod_pos = (500, 500)       # pretend rod position recorded
state.fish_spots = [(400, 300), (600, 700)]  # two spots
state.fish_session_minutes = 10
state.fish_min_cap = 0

# 4. Access fishing_service directly — triggers lazy import of services.py
print("Accessing fishing_service (triggers lazy imports)...")
fs = container.fishing_service
print(f"  ✓ FishingService loaded: {type(fs).__name__}")

# 5. Call start() — this is the real test
print("\nCalling fishing_service.start()...")
try:
    fs.start()
    print("✓ start() succeeded (no crash)")
except Exception as e:
    print(f"✗ start() FAILED: {type(e).__name__}: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 6. Wait briefly for the worker thread to initialize
time.sleep(0.3)
print(f"fish_active = {state.fish_active}")
print("Done.")
