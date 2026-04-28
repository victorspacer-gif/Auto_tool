"""Entry point for the refactored SystemMonitor application."""

from __future__ import annotations


def main() -> None:
    from systool.app import run
    run()


if __name__ == "__main__":
    main()
