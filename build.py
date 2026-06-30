from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON_WHEELS = ROOT / "vendor" / "python-wheels"
TESSERACT_VENDOR = ROOT / "vendor" / "tesseract"
REQUIREMENTS_FILE = ROOT / "requirements.txt"
OCR_DIAG_JSON = ROOT / "build" / "ocr-diag.json"

# Build targets: (entry_point, spec_file, output_exe, display_name)
BUILD_TARGETS = {
    "tk": {
        "entry": "raw.py",
        "spec": ROOT / "SystemMonitor.spec",
        "output": ROOT / "dist" / "SystemMonitor" / "SystemMonitor.exe",
        "name": "SystemMonitor",
        "label": "Tkinter (original)",
    },
    "luxe": {
        "entry": "luxe.py",
        "spec": ROOT / "SystemMonitorLuxe.spec",
        "output": ROOT / "dist" / "SystemMonitorLuxe" / "SystemMonitorLuxe.exe",
        "name": "SystemMonitorLuxe",
        "label": "CustomTkinter (Luxe)",
    },
}

REQUIRED_MODULES = [
    "PyInstaller",
    "pynput",
    "win32api",
    "pystray",
    "PIL",
    "mss",
    "numpy",
    "pygame",
    "pyautogui",
    "pytesseract",
    "psutil",
    "pymem",
    "cv2",
    "cysignals",
    "tesserocr",
    "customtkinter",
]


class BuildError(RuntimeError):
    """A build failure with a user-facing diagnostic."""


@dataclass(frozen=True)
class BuildOptions:
    target: str = "tk"  # "tk" or "luxe" or "both"
    clean: bool = False
    install_deps: bool = False
    upgrade_pip: bool = False
    open_dist: bool = True


def main(argv: list[str] | None = None) -> int:
    os.chdir(ROOT)
    argv = list(sys.argv[1:] if argv is None else argv)

    try:
        options = show_menu() if not argv else parse_args(argv)
        run_build(options)
    except BuildError as exc:
        print(f"\nERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nBuild cancelled.")
        return 130

    return 0


def parse_args(argv: list[str]) -> BuildOptions:
    parser = argparse.ArgumentParser(
        description="Build SystemMonitor for Windows with PyInstaller.",
    )
    parser.add_argument(
        "--luxe",
        action="store_true",
        help="Build the Luxe (CustomTkinter) UI instead of the default Tkinter UI.",
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Build both Tkinter and Luxe UIs.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous build artifacts before building.",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Force dependency installation before building.",
    )
    parser.add_argument(
        "--upgrade-pip",
        action="store_true",
        help="Upgrade pip before installing dependencies.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the output folder after building.",
    )
    args = parser.parse_args(argv)

    target = "tk"
    if args.both:
        target = "both"
    elif args.luxe:
        target = "luxe"

    return BuildOptions(
        target=target,
        clean=args.clean,
        install_deps=args.install_deps,
        upgrade_pip=args.upgrade_pip,
        open_dist=not args.no_open,
    )


def show_menu() -> BuildOptions:
    print()
    print("Select a build option:")
    print("  [1] Fast build (Tkinter — original)")
    print("  [2] Clean build (Tkinter)")
    print("  [3] Clean build + reinstall deps (Tkinter)")
    print("  [4] Fast build (Luxe — CustomTkinter)")
    print("  [5] Clean build (Luxe)")
    print("  [6] Clean build + reinstall deps (Luxe)")
    print("  [7] Build BOTH Tkinter + Luxe")
    print("  [8] Build BOTH + reinstall deps")
    print("  [9] Fast build, do not open dist folder")

    while True:
        choice = input("Enter choice: ").strip()
        if choice == "1":
            return BuildOptions(target="tk")
        if choice == "2":
            return BuildOptions(target="tk", clean=True)
        if choice == "3":
            return BuildOptions(target="tk", clean=True, install_deps=True)
        if choice == "4":
            return BuildOptions(target="luxe")
        if choice == "5":
            return BuildOptions(target="luxe", clean=True)
        if choice == "6":
            return BuildOptions(target="luxe", clean=True, install_deps=True)
        if choice == "7":
            return BuildOptions(target="both")
        if choice == "8":
            return BuildOptions(target="both", clean=True, install_deps=True)
        if choice == "9":
            return BuildOptions(open_dist=False)
        print("Please enter 1-9.")


def run_build(options: BuildOptions) -> None:
    targets_to_build = []
    if options.target == "both":
        targets_to_build = ["tk", "luxe"]
    else:
        targets_to_build = [options.target]

    for target_key in targets_to_build:
        target = BUILD_TARGETS[target_key]
        print(f"\n{'='*60}")
        print(f"  Building: {target['label']}  ({target['entry']})")
        print(f"{'='*60}\n")

        _do_build(options, target)

        if len(targets_to_build) > 1:
            print(f"\n  ✅ {target['label']} built successfully.\n")


def _do_build(options: BuildOptions, target: dict) -> None:
    spec = target["spec"]
    output = target["output"]
    name = target["name"]

    print("[1/6] Checking Python...")
    check_environment()

    print("[2/6] Checking for running instances...")
    ensure_process_not_running(name)

    print("[3/6] Checking runtime and build dependencies...")
    manage_dependencies(options)

    print(f"[4/6] Cleaning previous build artifacts for {name}...")
    _clean_named_directories(options.clean, name)

    print("[5/6] Preparing bundled Tesseract...")
    sync_tesseract()

    print(f"[6/6] Building executable with PyInstaller ({spec.name})...")
    compile_app(options.clean, spec, name)
    remove_stray_bootloader(name)

    print("[7/7] Validating OCR bundle...")
    validate_ocr_bundle(output)

    print(f"Build complete — {name}.")
    print(f'Executable path: "{output}"')

    if options.open_dist:
        open_output_folder(output)

    post_build_cleanup()


def check_environment() -> None:
    if shutil.which("py") is None:
        raise BuildError('Python launcher ("py") was not found. Install Python for Windows first.')

    arch = platform.architecture()[0]
    print(f"Using Python {platform.python_version()} {arch} at {sys.executable}")

    if sys.version_info[:2] not in ((3, 12), (3, 14)) or arch != "64bit":
        py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
        raise BuildError(
            f"This build requires 64-bit Python 3.12 or 3.14 (detected {py_tag} "
            f"{arch}) because the bundled tesserocr/cysignals wheels are "
            f"cp312-win_amd64 and cp314-win_amd64. Install Python 3.12 or "
            f"3.14 x64 from python.org, then rerun this script."
        )

    require_file(REQUIREMENTS_FILE)


def ensure_process_not_running(name: str) -> None:
    result = run_subprocess(
        ["tasklist", "/FI", f"IMAGENAME eq {name}.exe"],
        capture_output=True,
        check=False,
        action="checking running processes",
    )
    if result.returncode != 0:
        raise BuildError("Could not inspect running processes with tasklist.")

    if f"{name}.exe" in result.stdout:
        raise BuildError(
            f"{name}.exe is currently running. Close it before building "
            f"so PyInstaller can replace dist\\{name}\\{name}.exe."
        )


def manage_dependencies(options: BuildOptions) -> None:
    missing = missing_modules()

    if missing and not options.install_deps:
        print("Missing modules: " + ", ".join(missing))
    elif not missing and not options.install_deps:
        print("Dependencies already installed.")
        return

    if options.upgrade_pip:
        print("Upgrading pip...")
        run_python_module(["pip", "install", "--upgrade", "pip"], "upgrading pip")

    print("Installing missing dependencies...")
    run_python_module(
        [
            "pip",
            "install",
            "--upgrade",
            "--find-links",
            str(PYTHON_WHEELS),
            "--prefer-binary",
            "--only-binary=tesserocr,cysignals",
            "-r",
            str(REQUIREMENTS_FILE),
            "pyinstaller",
            "pyinstaller-hooks-contrib",
        ],
        "installing dependencies",
    )

    install_preferred_wheel("cysignals", required=True)
    install_preferred_wheel("tesserocr", required=True)
    importlib.invalidate_caches()


def missing_modules() -> list[str]:
    return [module for module in REQUIRED_MODULES if importlib.util.find_spec(module) is None]


def _py_ver_tag() -> str:
    """Return the CPython version tag for wheel filenames, e.g. 'cp312'."""
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def install_preferred_wheel(package: str, *, required: bool) -> None:
    tag = _py_ver_tag()
    pattern = f"{package}-*-{tag}-{tag}-win_amd64.whl"
    wheels = sorted(PYTHON_WHEELS.glob(pattern))
    if wheels:
        wheel = wheels[-1]
        print(f"Installing bundled {package} wheel:")
        print(f"  {wheel}")
        run_python_module(["pip", "install", "--upgrade", str(wheel)], f"installing {package} wheel")
        return

    print(f"WARNING: No bundled {package} {tag} wheel was found in {PYTHON_WHEELS}.")
    if required:
        print("         Falling back to pip...")
        run_python_module(["pip", "install", "--upgrade", package], f"installing {package} from pip")
    else:
        print(
            "         The build will continue, but OCR will fall back to pytesseract "
            f"unless {package} is installed manually."
        )


def _clean_named_directories(clean_build: bool, name: str) -> None:
    if not clean_build:
        print("Reusing existing build caches for a faster incremental build.")
        return

    build_dir = ROOT / "build" / name
    dist_dir = ROOT / "dist" / name
    spec_build = ROOT / f"{name}.spec-build"
    remove_directory(build_dir, missing_ok=True)
    remove_directory(dist_dir, missing_ok=True)
    remove_directory(spec_build, missing_ok=True)
    print(f"Cleaned build artifacts for {name}.")


def sync_tesseract() -> None:
    source = find_tesseract_source()
    if source is None:
        raise BuildError(
            "Tesseract was not found in a standard install location. Install "
            "Tesseract on the build machine first, or copy it into "
            "vendor\\tesseract manually."
        )

    remove_directory(TESSERACT_VENDOR)
    copy_directory(source, TESSERACT_VENDOR)


def find_tesseract_source() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Tesseract-OCR",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Tesseract-OCR",
    ]

    for candidate in candidates:
        if (candidate / "tesseract.exe").exists():
            return candidate
    return None


def compile_app(clean_build: bool, spec: Path, name: str) -> None:
    args = ["--noconfirm"]
    if clean_build:
        args.append("--clean")
    args.append(str(spec))

    print(f"  PyInstaller args: {' '.join(args)}")
    try:
        # Use subprocess instead of direct import to capture full output
        result = run_subprocess(
            [sys.executable, "-m", "PyInstaller", *args],
            action=f"building {name} executable",
            capture_output=False,
            check=False,
        )
    except BuildError as exc:
        raise BuildError(f"PyInstaller failed: {exc}") from exc

    if result.returncode != 0:
        error_text = result.stderr.strip() if result.stderr.strip() else "(no stderr — check output above)"
        raise BuildError(
            f"PyInstaller failed with exit code {result.returncode} for {name}.\n"
            f"  Spec: {spec}\n"
            f"  Error: {error_text}"
        )
    print(f"  PyInstaller finished successfully for {name}.")


def remove_stray_bootloader(name: str) -> None:
    stray_exe = ROOT / "dist" / f"{name}.exe"
    if stray_exe.exists():
        print(f"Removing stray executable at dist\\{name}.exe...")
        remove_file(stray_exe)


def open_output_folder(output_exe: Path) -> None:
    if not output_exe.exists():
        return

    print("Launching output folder...")
    try:
        os.startfile(output_exe.parent)  # type: ignore[attr-defined]
    except OSError as exc:
        raise BuildError(f"Could not open output folder: {exc}") from exc


def post_build_cleanup() -> None:
    print("Cleaning unnecessary Tesseract artifacts...")
    remove_directory(TESSERACT_VENDOR / "tessdata" / "configs", missing_ok=True)
    remove_directory(TESSERACT_VENDOR / "tessdata" / "tessconfigs", missing_ok=True)

    doc_dir = TESSERACT_VENDOR / "doc"
    for filename in ["AUTHORS", "LICENSE", "README.md"]:
        remove_file(doc_dir / filename, missing_ok=True)


def validate_ocr_bundle(output_exe: Path) -> None:
    """Run the frozen .exe's OCR diagnostics and confirm tesserocr is bundled.

    This catches silent failures where the .exe falls back to pytesseract
    because tesserocr's .pyd or native DLLs were not bundled correctly.
    """
    if not output_exe.exists():
        raise BuildError(f"Cannot validate OCR: {output_exe} was not found.")

    diag_path = str(OCR_DIAG_JSON)
    result = run_subprocess(
        [str(output_exe), "--diagnose-ocr-env", diag_path],
        action="running OCR diagnostics on built executable",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise BuildError(
            f"OCR diagnostics failed (exit code {result.returncode}).\n"
            f"  {stderr if stderr else 'No stderr output.'}"
        )

    try:
        with open(OCR_DIAG_JSON, encoding="utf-8") as handle:
            diag = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"Could not read OCR diagnostics JSON: {exc}")

    if not diag.get("has_tesserocr"):
        error = diag.get("tesserocr_error", "unknown error")
        fallback = diag.get("ocr_engine_backend", "none")
        print(f"  WARNING: tesserocr is NOT available in the bundle ({error}).")
        print(f"  OCR will use the fallback backend: {fallback}")
        print(f"  Full diagnostics: {json.dumps(diag, indent=2)}")
    else:
        print(f"  tesserocr=ready  |  backend={diag.get('ocr_engine_backend', '?')}  "
              f"|  tesseract_cmd={diag.get('tesseract_cmd', '?')}")

    # Clean up diagnostics file
    try:
        OCR_DIAG_JSON.unlink(missing_ok=True)
    except OSError:
        pass


def require_file(path: Path) -> None:
    if not path.exists():
        raise BuildError(f"Required file is missing: {path}")


def run_python_module(args: list[str], action: str) -> subprocess.CompletedProcess[str]:
    return run_subprocess([sys.executable, "-m", *args], action=action)


def run_subprocess(
    args: list[str],
    *,
    action: str,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=capture_output,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BuildError(f"Command not found while {action}: {args[0]}") from exc
    except OSError as exc:
        raise BuildError(f"Could not run command while {action}: {exc}") from exc

    if check and result.returncode != 0:
        detail = ""
        if result.stderr:
            detail = f"\n{result.stderr.strip()}"
        raise BuildError(f"Command failed while {action}: {' '.join(args)}{detail}")

    return result


def remove_directory(path: Path, *, missing_ok: bool = True) -> None:
    if not path.exists():
        if missing_ok:
            return
        raise BuildError(f"Directory does not exist: {path}")

    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise BuildError(f"Could not remove directory {path}: {exc}") from exc


def copy_directory(source: Path, destination: Path) -> None:
    try:
        shutil.copytree(source, destination)
    except OSError as exc:
        raise BuildError(f"Could not copy {source} to {destination}: {exc}") from exc


def remove_file(path: Path, *, missing_ok: bool = True) -> None:
    if not path.exists():
        if missing_ok:
            return
        raise BuildError(f"File does not exist: {path}")

    try:
        path.unlink()
    except OSError as exc:
        raise BuildError(f"Could not remove file {path}: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
