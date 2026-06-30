"""Entry point for the Luxe (CustomTkinter) SystemMonitor interface."""

from __future__ import annotations

import argparse
import json
import logging


def main() -> None:
    parser = argparse.ArgumentParser(description="SystemMonitor Luxe — MMORPG game helper")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug-level logging output",
    )
    parser.add_argument(
        "--diagnose-ocr-env",
        metavar="OUTPUT_JSON",
        default="",
        help="Write OCR dependency diagnostics to a JSON file and exit",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    if args.diagnose_ocr_env:
        from systool import runtime

        engine_backend = ""
        engine_error = ""
        try:
            engine = runtime.create_ocr_engine("")
            engine_backend = getattr(engine, "backend", "")
        except Exception as exc:
            engine_error = str(exc)

        diagnostics = {
            "python": runtime.sys.version,
            "frozen": bool(getattr(runtime.sys, "frozen", False)),
            "meipass": str(getattr(runtime.sys, "_MEIPASS", "")),
            "has_mss": runtime.HAS_MSS,
            "mss_error": runtime.MSS_IMPORT_ERROR,
            "has_numpy": runtime.HAS_NUMPY,
            "numpy_error": runtime.NUMPY_IMPORT_ERROR,
            "has_cv2": runtime.HAS_CV2,
            "cv2_error": runtime.CV2_IMPORT_ERROR,
            "has_pytesseract": runtime.HAS_PYTESSERACT,
            "pytesseract_error": runtime.TESSERACT_IMPORT_ERROR,
            "has_tesserocr": runtime.HAS_TESSEROCR,
            "tesserocr_error": runtime.TESSEROCR_IMPORT_ERROR,
            "ocr_environment": runtime.describe_ocr_environment(),
            "tesseract_cmd": runtime.resolve_tesseract_cmd(""),
            "ocr_engine_backend": engine_backend,
            "ocr_engine_error": engine_error,
        }
        with open(args.diagnose_ocr_env, "w", encoding="utf-8") as handle:
            json.dump(diagnostics, handle, indent=2)
        return

    try:
        from systool.app_luxe import run
    except ImportError as exc:
        name = exc.name or ""
        if "customtkinter" in name:
            print("❌ SystemMonitor Luxe requires customtkinter.")
            print("   Install it with:  pip install customtkinter")
            print("   Or install all dependencies: pip install -r requirements.txt")
        else:
            print(f"❌ Failed to load Luxe UI: {exc}")
        return
    run()


if __name__ == "__main__":
    main()
