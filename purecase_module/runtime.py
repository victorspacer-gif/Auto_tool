from __future__ import annotations

import os
import re
import shlex
import subprocess
import ctypes
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:
    import win32api
    import win32con
    import win32process
    import win32security
    import win32job
    import pywintypes
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


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


def create_job_object() -> object | None:
    """
    Create a Windows Job Object for process isolation.
    Restricts clipboard, display settings, atoms, and exits with job closure.
    """
    if not WIN32_AVAILABLE:
        return None
    try:
        job = win32job.CreateJobObject(None, "SandboxJob")
        
        # UI restrictions (handles excluded for normal file/folder access)
        ui_info = win32job.QueryInformationJobObject(
            job, win32job.JobObjectBasicUIRestrictions
        )
        ui_info["UIRestrictionsClass"] = (
            win32job.JOB_OBJECT_UILIMIT_READCLIPBOARD |
            win32job.JOB_OBJECT_UILIMIT_WRITECLIPBOARD |
            win32job.JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS |
            win32job.JOB_OBJECT_UILIMIT_DISPLAYSETTINGS |
            win32job.JOB_OBJECT_UILIMIT_GLOBALATOMS |
            win32job.JOB_OBJECT_UILIMIT_EXITWINDOWS
        )
        win32job.SetInformationJobObject(
            job, win32job.JobObjectBasicUIRestrictions, ui_info
        )

        # Kill-on-job-close
        ext_info = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        ext_info["BasicLimitInformation"]["LimitFlags"] |= (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
            win32job.JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        )
        win32job.SetInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation, ext_info
        )
        return job
    except Exception:
        return None


def get_safer_token() -> object | None:
    """
    Produce a de-elevated token using Windows SAFER API (SaferComputeTokenFromLevel).
    Returns None if not available or pywin32 not installed.
    """
    if not WIN32_AVAILABLE:
        return None
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        SAFER_SCOPEID_USER = 1
        SAFER_LEVELID_NORMALUSER = 0x20000
        SAFER_LEVEL_OPEN = 1

        h_level = ctypes.c_void_p()
        if not advapi32.SaferCreateLevel(
            SAFER_SCOPEID_USER, SAFER_LEVELID_NORMALUSER,
            SAFER_LEVEL_OPEN, ctypes.byref(h_level), None
        ):
            return None

        raw_token = ctypes.wintypes.HANDLE()
        ok = advapi32.SaferComputeTokenFromLevel(
            h_level, None, ctypes.byref(raw_token), 0, None
        )
        advapi32.SaferCloseLevel(h_level)

        if not ok:
            return None

        # Duplicate raw token into PyHANDLE
        cur = win32api.GetCurrentProcess()
        py_token = win32api.DuplicateHandle(
            cur, raw_token.value, cur, 0, False,
            win32con.DUPLICATE_SAME_ACCESS
        )
        kernel32.CloseHandle(raw_token)
        return py_token
    except Exception:
        return None


def build_spoofed_env(extra_vars: dict | None = None) -> dict[str, str]:
    """
    Build environment dict with sandbox detection cues removed and plausible user profile.
    """
    env = os.environ.copy()
    
    # Remove debugging/profiling detection
    for key in [
        "_DEBUGGER_IS_PRESENT", "COR_ENABLE_PROFILING",
        "COR_PROFILER", "VSDEBUGGEE_PID", "VS_DEBUGGER",
        "COMPLUS_MDA", "__COMPAT_LAYER",
    ]:
        env.pop(key, None)

    # Spoof user profile
    if "USERPROFILE" not in env:
        env["USERPROFILE"] = r"C:\Users\User"
    if "HOMEPATH" not in env:
        env["HOMEPATH"] = r"\Users\User"
    if "USERNAME" not in env:
        env["USERNAME"] = "User"
    if "COMPUTERNAME" not in env:
        env["COMPUTERNAME"] = "DESKTOP-PC"

    env.setdefault("SystemRoot", r"C:\Windows")
    env.setdefault("windir", r"C:\Windows")

    if extra_vars:
        env.update(extra_vars)

    return env


def launch_with_job_object(
    executable: str | os.PathLike[str],
    *,
    args: str | Sequence[str] | None = None,
    drop_admin: bool = False,
    spoof_env: bool = True,
    cwd: str | os.PathLike[str] | None = None,
    extra_env: dict[str, str] | None = None,
    log_callback: LogCallback | None = None,
) -> subprocess.Popen:
    """
    Launch executable inside a Job Object sandbox.
    
    Parameters
    ----------
    executable  : Full path to the executable.
    args        : Command-line arguments (str or sequence).
    drop_admin  : Strip administrator privileges from child token.
    spoof_env   : Use spoofed environment dict.
    cwd         : Working directory (defaults to executable directory).
    extra_env   : Additional environment variables to inject.
    log_callback: Callable for logging.
    """
    env = build_spoofed_env(extra_env) if spoof_env else os.environ.copy()
    
    cmd = [str(executable)]
    cmd.extend(_normalize_args(args))
    
    _log(log_callback, f"[{_ts()}] Command  : {' '.join(cmd)}")
    _log(log_callback, f"[{_ts()}] Drop admin: {drop_admin}")

    if not WIN32_AVAILABLE:
        _log(log_callback, f"[{_ts()}] WARNING: pywin32 not found – launching without Job Object.")
        return subprocess.Popen(
            cmd,
            env=env,
            cwd=str(cwd) if cwd else str(Path(executable).parent),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    job = create_job_object()
    start_flags = (
        win32process.CREATE_SUSPENDED |
        win32process.CREATE_NEW_PROCESS_GROUP
    )

    env_dict = dict(env)
    cwd_str = str(cwd) if cwd else str(Path(executable).parent)
    cmdline = " ".join(cmd)

    try:
        if drop_admin:
            _log(log_callback, f"[{_ts()}] Token    : computing SAFER de-elevated token")
            token_handle = get_safer_token()
            if not token_handle:
                _log(log_callback, f"[{_ts()}] Token    : failed, proceeding without de-elevation")
                si = win32process.STARTUPINFO()
                si.dwFlags = win32process.STARTF_USESHOWWINDOW
                si.wShowWindow = win32con.SW_SHOWNORMAL
                hProcess, hThread, pid, tid = win32process.CreateProcess(
                    str(executable), cmdline, None, None, False,
                    start_flags, env_dict, cwd_str, si,
                )
            else:
                si = win32process.STARTUPINFO()
                si.dwFlags = win32process.STARTF_USESHOWWINDOW
                si.wShowWindow = win32con.SW_SHOWNORMAL
                hProcess, hThread, pid, tid = win32process.CreateProcessAsUser(
                    token_handle, str(executable), cmdline, None, None, False,
                    start_flags, env_dict, cwd_str, si,
                )
                del token_handle
        else:
            si = win32process.STARTUPINFO()
            si.dwFlags = win32process.STARTF_USESHOWWINDOW
            si.wShowWindow = win32con.SW_SHOWNORMAL
            hProcess, hThread, pid, tid = win32process.CreateProcess(
                str(executable), cmdline, None, None, False,
                start_flags, env_dict, cwd_str, si,
            )

        _log(log_callback, f"[{_ts()}] PID      : {pid}")

        if job:
            win32job.AssignProcessToJobObject(job, hProcess)
            _log(log_callback, f"[{_ts()}] Job object assigned.")

        win32process.ResumeThread(hThread)
        _log(log_callback, f"[{_ts()}] Process resumed – sandbox active.")

        proc = _Win32ProcWrapper(hProcess, pid, job)
    except Exception as exc:
        _log(log_callback, f"[{_ts()}] Launch failed: {exc}")
        raise

    _log(log_callback, f"[{_ts()}] Launch complete.")
    return proc


class _Win32ProcWrapper:
    """Thin wrapper so Win32 process handles behave like subprocess.Popen."""

    def __init__(self, hProcess: int, pid: int, job: object | None) -> None:
        self._hProcess = hProcess
        self.pid = pid
        self._job = job

    def wait(self) -> int:
        if WIN32_AVAILABLE:
            try:
                import win32event
                win32event.WaitForSingleObject(self._hProcess, win32event.INFINITE)
            except Exception:
                pass
        return 0

    def poll(self) -> int | None:
        if not WIN32_AVAILABLE:
            return None
        try:
            import win32event
            rc = win32event.WaitForSingleObject(self._hProcess, 0)
            return None if rc == win32event.WAIT_TIMEOUT else 0
        except Exception:
            return None

    def terminate(self) -> None:
        """Kill process and all children in Job Object, with taskkill fallback."""
        if self._job:
            try:
                win32job.TerminateJobObject(self._job, 1)
            except Exception:
                pass
        try:
            win32api.TerminateProcess(self._hProcess, 1)
        except Exception:
            pass
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.pid)],
                capture_output=True, timeout=5
            )
        except Exception:
            pass


def _ts() -> str:
    """Return current time as HH:MM:SS."""
    return datetime.datetime.now().strftime("%H:%M:%S")


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
