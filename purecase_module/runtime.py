from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


LogCallback = Callable[[str], None]

_DEFAULT_SEARCH_PATHS = [
    Path(r"C:\Program Files\PureCase"),
    Path(r"C:\Program Files\Sandboxie-Plus"),
    Path(r"C:\Program Files\Sandboxie"),
    Path(r"C:\Program Files (x86)\PureCase"),
    Path(r"C:\Program Files (x86)\Sandboxie-Plus"),
    Path(r"C:\Program Files (x86)\Sandboxie"),
]

_PROJECT_PORTABLE_DIRS = [
    Path("Installer") / "PureCase_x64",
    Path("Installer") / "PureCase_a64",
    Path("Installer") / "PureCase_x86",
    Path("Installer") / "SbiePlus_x64",
    Path("Installer") / "SbiePlus_a64",
    Path("Installer") / "SbiePlus_x86",
]

_DEFAULT_HIDE_PROCESS_NAMES = [
    "purecase.exe",
    "purecase_launcher.exe",
    "sandboxie.exe",
    "sandboxierpcss.exe",
    "sandboxiecrypto.exe",
    "sandboxiedcom.exe",
    "start.exe",
    "sandman.exe",
    "sbiesvc.exe",
    "sbiesvc32.exe",
    "python.exe",
    "pythonw.exe",
]


@dataclass(frozen=True)
class PureCaseInstallation:
    root: Path
    start: Path
    ini: Path
    origin: str
    portable: bool = False

    @property
    def sbieini(self) -> Path:
        return self.root / "SbieIni.exe"


def sanitize_box_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", name or "")[:32]
    return clean or "PureCaseBox"


def find_installation(
    project_root: str | os.PathLike[str] | None = None,
    preferred_root: str | os.PathLike[str] | None = None,
    prefer_portable: bool = True,
) -> PureCaseInstallation | None:
    candidates: list[tuple[Path, str, bool]] = []

    if preferred_root:
        root = Path(preferred_root)
        candidates.append((root, "explicit", _has_portable_ini(root)))

    env_root = os.environ.get("PURECASE_ROOT") or os.environ.get("SANDBOXIE_ROOT")
    if env_root:
        root = Path(env_root)
        candidates.append((root, "environment", _has_portable_ini(root)))

    if project_root:
        root = Path(project_root)
        for rel_path in _PROJECT_PORTABLE_DIRS:
            candidates.append((root / rel_path, "project-portable", True))

    for path in _DEFAULT_SEARCH_PATHS:
        candidates.append((path, "installed", _has_portable_ini(path)))

    ordered = candidates if prefer_portable else sorted(candidates, key=lambda item: item[2])
    seen: set[Path] = set()

    for root, origin, portable in ordered:
        root = root.resolve(strict=False)
        if root in seen:
            continue
        seen.add(root)
        start = root / "Start.exe"
        ini = root / "Sandboxie.ini"
        if start.exists():
            return PureCaseInstallation(
                root=root,
                start=start,
                ini=ini,
                origin=origin,
                portable=portable,
            )
    return None


def configure_box(
    installation: PureCaseInstallation,
    box_name: str,
    *,
    hide_process_names: Iterable[str] | None = None,
    extra_settings: dict[str, str] | None = None,
    log_callback: LogCallback | None = None,
) -> str:
    box_name = sanitize_box_name(box_name)
    settings = {
        "Enabled": "y",
        "HideOtherBoxes": "y",
        "HideSandboxieWindow": "y",
        "HideProcessName": ",".join(_merge_hide_names(hide_process_names)),
        "DropAdminRights": "y",
        "FakeAdminRights": "y",
        "CopyLimitKb": "524288",
    }
    if extra_settings:
        settings.update(extra_settings)

    if installation.sbieini.exists():
        for key, value in settings.items():
            result = subprocess.run(
                [str(installation.sbieini), "set", box_name, key, value],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                _log(
                    log_callback,
                    f"SbieIni warning [{key}]: {result.stderr.strip() or result.stdout.strip()}",
                )
        _log(log_callback, f"PureCase box [{box_name}] configured via SbieIni.exe")
        return box_name

    _write_ini_section(installation.ini, box_name, settings)
    _log(log_callback, f"PureCase box [{box_name}] written directly to {installation.ini}")
    return box_name


def reload_configuration(
    installation: PureCaseInstallation,
    *,
    log_callback: LogCallback | None = None,
) -> None:
    subprocess.run([str(installation.start), "/reload"], capture_output=True, timeout=8)
    _log(log_callback, "PureCase configuration reloaded")


def ensure_box(
    installation: PureCaseInstallation,
    box_name: str,
    *,
    reload: bool = True,
    hide_process_names: Iterable[str] | None = None,
    extra_settings: dict[str, str] | None = None,
    log_callback: LogCallback | None = None,
) -> str:
    box_name = configure_box(
        installation,
        box_name,
        hide_process_names=hide_process_names,
        extra_settings=extra_settings,
        log_callback=log_callback,
    )
    if reload:
        reload_configuration(installation, log_callback=log_callback)
    return box_name


def build_start_command(
    installation: PureCaseInstallation,
    box_name: str,
    executable: str | os.PathLike[str],
    *,
    args: str | Sequence[str] | None = None,
    drop_admin: bool = False,
    fake_admin: bool = True,
) -> list[str]:
    cmd = [str(installation.start), f"/box:{sanitize_box_name(box_name)}"]
    if fake_admin:
        cmd.append("/fake_admin")
    if drop_admin:
        cmd.append("/drop_rights")
    cmd.append(str(executable))
    cmd.extend(_normalize_args(args))
    return cmd


def launch_in_box(
    installation: PureCaseInstallation,
    box_name: str,
    executable: str | os.PathLike[str],
    *,
    args: str | Sequence[str] | None = None,
    drop_admin: bool = False,
    fake_admin: bool = True,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
    ensure: bool = True,
    log_callback: LogCallback | None = None,
) -> subprocess.Popen:
    if ensure:
        box_name = ensure_box(installation, box_name, log_callback=log_callback)
    command = build_start_command(
        installation,
        box_name,
        executable,
        args=args,
        drop_admin=drop_admin,
        fake_admin=fake_admin,
    )
    _log(log_callback, "PureCase command = " + " ".join(command))
    return subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else str(Path(executable).parent),
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def list_box_pids(
    installation: PureCaseInstallation,
    box_name: str,
) -> list[int]:
    result = subprocess.run(
        [str(installation.start), f"/box:{sanitize_box_name(box_name)}", "/listpids"],
        capture_output=True,
        text=True,
        timeout=8,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if value.isdigit():
            pids.append(int(value))
    return pids[1:] if len(pids) > 1 else pids


def terminate_box(
    installation: PureCaseInstallation,
    box_name: str,
    *,
    log_callback: LogCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(installation.start), f"/box:{sanitize_box_name(box_name)}", "/terminate"],
        capture_output=True,
        text=True,
        timeout=8,
    )
    _log(log_callback, f"PureCase box [{sanitize_box_name(box_name)}] terminated")
    return result


def _normalize_args(args: str | Sequence[str] | None) -> list[str]:
    if args is None:
        return []
    if isinstance(args, str):
        return shlex.split(args, posix=False)
    return [str(arg) for arg in args]


def _merge_hide_names(extra_names: Iterable[str] | None) -> list[str]:
    names = list(_DEFAULT_HIDE_PROCESS_NAMES)
    if extra_names:
        names.extend(str(name).strip() for name in extra_names if str(name).strip())
    seen: set[str] = set()
    merged: list[str] = []
    for name in names:
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(name)
    return merged


def _write_ini_section(path: Path, section: str, values: dict[str, str]) -> None:
    lines: list[str]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except FileNotFoundError:
        lines = []

    header = f"[{section}]"
    start_index = -1
    end_index = len(lines)

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == header:
            start_index = index
            continue
        if start_index != -1 and stripped.startswith("[") and stripped.endswith("]"):
            end_index = index
            break

    if start_index == -1:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.extend(["\n", header + "\n"])
        lines.extend(f"{key}={value}\n" for key, value in values.items())
        path.write_text("".join(lines), encoding="utf-8")
        return

    existing: dict[str, int] = {}
    for index in range(start_index + 1, end_index):
        line = lines[index]
        if "=" not in line:
            continue
        key = line.split("=", 1)[0].strip().lower()
        existing[key] = index

    for key, value in values.items():
        existing_index = existing.get(key.lower())
        rendered = f"{key}={value}\n"
        if existing_index is None:
            lines.insert(end_index, rendered)
            end_index += 1
        else:
            lines[existing_index] = rendered

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def _has_portable_ini(path: Path) -> bool:
    return (path / "Sandboxie.ini").exists() or (path / "PureCase.ini").exists()


def _log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)
