"""Entry point for the refactored SystemMonitor application."""

from __future__ import annotations

import argparse
import logging


def main() -> None:
    parser = argparse.ArgumentParser(description="SystemMonitor — MMORPG game helper")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug-level logging output",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    from systool.app import run
    run()


if __name__ == "__main__":
    main()
