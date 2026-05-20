from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON_WHEELS = ROOT / "vendor" / "python-wheels"
TESSERACT_VENDOR = ROOT / "vendor" / "tesseract"
SPEC_FILE = ROOT / "SystemMonitor.spec"
REQUIREMENTS_FILE = ROOT / "requirements.txt"
OUTPUT_EXE = ROOT / "dist" / "SystemMonitor" / "SystemMonitor.exe"

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
]


class BuildError(RuntimeError):
    """A build failure with a user-facing diagnostic."""


@dataclass(frozen=True)
class BuildOptions:
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

    return BuildOptions(
        clean=args.clean,
        install_deps=args.install_deps,
        upgrade_pip=args.upgrade_pip,
        open_dist=not args.no_open,
    )


def show_menu() -> BuildOptions:
    print()
    print("Select a build option:")
    print("  [1] Fast build")
    print("  [2] Clean build")
    print("  [3] Clean build + reinstall dependencies")
    print("  [4] Fast build, do not open dist folder")

    while True:
        choice = input("Enter choice: ").strip()
        if choice == "1":
            return BuildOptions()
        if choice == "2":
            return BuildOptions(clean=True)
        if choice == "3":
            return BuildOptions(clean=True, install_deps=True)
        if choice == "4":
            return BuildOptions(open_dist=False)
        print("Please enter 1, 2, 3, or 4.")


def run_build(options: BuildOptions) -> None:
    print("[1/6] Checking Python...")
    check_environment()

    print("[2/6] Checking for running SystemMonitor instances...")
    ensure_system_monitor_not_running()

    print("[3/6] Checking runtime and build dependencies...")
    manage_dependencies(options)

    print("[4/6] Cleaning previous build artifacts...")
    clean_directories(options.clean)

    print("[5/6] Preparing bundled Tesseract...")
    sync_tesseract()

    print("[6/6] Building executable with PyInstaller...")
    compile_app(options.clean)
    remove_stray_bootloader()

    print("Build complete.")
    print(f'Executable path: "{OUTPUT_EXE}"')

    if options.open_dist:
        open_output_folder()

    post_build_cleanup()


def check_environment() -> None:
    if shutil.which("py") is None:
        raise BuildError('Python launcher ("py") was not found. Install Python for Windows first.')

    arch = platform.architecture()[0]
    print(f"Using Python {platform.python_version()} {arch} at {sys.executable}")

    if sys.version_info[:2] != (3, 12) or arch != "64bit":
        raise BuildError(
            "This build requires 64-bit Python 3.12 because the bundled "
            "tesserocr/cysignals wheels are cp312-win_amd64. Install Python "
            "3.12 x64 from python.org, then rerun this script."
        )

    require_file(SPEC_FILE)
    require_file(REQUIREMENTS_FILE)


def ensure_system_monitor_not_running() -> None:
    result = run_subprocess(
        ["tasklist", "/FI", "IMAGENAME eq SystemMonitor.exe"],
        capture_output=True,
        check=False,
        action="checking running processes",
    )
    if result.returncode != 0:
        raise BuildError("Could not inspect running processes with tasklist.")

    if "SystemMonitor.exe" in result.stdout:
        raise BuildError(
            "SystemMonitor.exe is currently running. Close it before building "
            "so PyInstaller can replace dist\\SystemMonitor.exe."
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
    install_preferred_wheel("tesserocr", required=False)
    importlib.invalidate_caches()


def missing_modules() -> list[str]:
    return [module for module in REQUIRED_MODULES if importlib.util.find_spec(module) is None]


def install_preferred_wheel(package: str, *, required: bool) -> None:
    wheels = sorted(PYTHON_WHEELS.glob(f"{package}-*-cp312-cp312-win_amd64.whl"))
    if wheels:
        wheel = wheels[-1]
        print(f"Installing bundled {package} wheel:")
        print(f"  {wheel}")
        run_python_module(["pip", "install", "--upgrade", str(wheel)], f"installing {package} wheel")
        return

    print(f"WARNING: No bundled {package} cp312 wheel was found in {PYTHON_WHEELS}.")
    if required:
        print("         Falling back to pip...")
        run_python_module(["pip", "install", "--upgrade", package], f"installing {package} from pip")
    else:
        print(
            "         The build will continue, but OCR will fall back to pytesseract "
            f"unless {package} is installed manually."
        )


def clean_directories(clean_build: bool) -> None:
    if not clean_build:
        print("Reusing existing build caches for a faster incremental build.")
        return

    for directory in [ROOT / "build", ROOT / "dist", ROOT / "SystemMonitor.spec-build"]:
        remove_directory(directory)
    print("Clean build requested.")


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


def compile_app(clean_build: bool) -> None:
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise BuildError(
            "PyInstaller is not importable. Rerun with --install-deps, or install "
            "dependencies manually."
        ) from exc

    args = ["--noconfirm"]
    if clean_build:
        args.append("--clean")
    args.append(str(SPEC_FILE))

    try:
        PyInstaller.__main__.run(args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code != 0:
            raise BuildError(f"PyInstaller failed with exit code {code}.") from exc
    except Exception as exc:
        raise BuildError(f"PyInstaller failed: {exc}") from exc


def remove_stray_bootloader() -> None:
    stray_exe = ROOT / "dist" / "SystemMonitor.exe"
    if stray_exe.exists():
        print("Removing stray executable at dist\\SystemMonitor.exe...")
        remove_file(stray_exe)


def open_output_folder() -> None:
    if not OUTPUT_EXE.exists():
        return

    print("Launching output folder...")
    try:
        os.startfile(OUTPUT_EXE.parent)  # type: ignore[attr-defined]
    except OSError as exc:
        raise BuildError(f"Could not open output folder: {exc}") from exc


def post_build_cleanup() -> None:
    print("Cleaning unnecessary Tesseract artifacts...")
    remove_directory(TESSERACT_VENDOR / "tessdata" / "configs", missing_ok=True)
    remove_directory(TESSERACT_VENDOR / "tessdata" / "tessconfigs", missing_ok=True)

    doc_dir = TESSERACT_VENDOR / "doc"
    for filename in ["AUTHORS", "LICENSE", "README.md"]:
        remove_file(doc_dir / filename, missing_ok=True)


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
