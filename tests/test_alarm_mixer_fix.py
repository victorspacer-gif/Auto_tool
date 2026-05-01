"""Verify _quit_pygame_mixer does NOT call mixer.quit(), preserving Windows
DirectSound/WASAPI backend reliability across alarms.

Bug: the old code called pygame.mixer.quit() after each alarm playback,
which broke re-initialization on Windows — subsequent alarms would fail
with "pygame mixer failed to initialize" and no sound played.

Fix: _quit_pygame_mixer only calls music.stop(), leaving the mixer
initialized for the application lifetime.
"""

import sys


def test_alarm_mixer_lifecycle_no_quit():
    """End-to-end test of alarm playback lifecycle with mock pygame.

    Verifies:
      1. First alarm triggers pre_init + mixer.init
      2. _quit_pygame_mixer calls music.stop() but NOT mixer.quit()
      3. Second alarm skips re-init (pre_init/init not called again)

    Note: This test relies on the pygame mock injected by conftest.py.
    The mock is shared across all tests, so we use it directly without
    trying to replace sys.modules['pygame'].
    """
    from systool import runtime as rt_module
    _init_pygame_mixer = rt_module._init_pygame_mixer
    _quit_pygame_mixer = rt_module._quit_pygame_mixer

    # Get the pygame mock that conftest.py injected into sys.modules
    mock_pygame = sys.modules['pygame']

    # === First alarm: lazy init should fire ===
    _init_pygame_mixer()
    assert mock_pygame.mixer.pre_init.called, (
        "pre_init must be called on first alarm"
    )
    assert mock_pygame.mixer.init.called, (
        "mixer.init must be called on first alarm"
    )

    # === Quit after playback: stop only, no quit() ===
    _quit_pygame_mixer()
    mock_pygame.mixer.music.stop.assert_called_once()
    assert not mock_pygame.mixer.quit.called, (
        "pygame.mixer.quit() must NOT be called; "
        "it breaks Windows audio backend re-init"
    )

    # === Second alarm: should skip re-init since flag stays True ===
    mock_pygame.reset_mock()
    _init_pygame_mixer()

    assert not mock_pygame.mixer.pre_init.called, (
        "pre_init must NOT be called on second alarm"
    )
    assert not mock_pygame.mixer.init.called, (
        "mixer.init must NOT be called on second alarm"
    )
