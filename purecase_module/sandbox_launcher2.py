"""
Sandbox Launcher
----------------
Two isolation backends:

  1. Job Object (built-in) — restricts clipboard, display settings, atom
     table; auto-kills children on close.  No extra software needed.

  2. Sandboxie-Plus — kernel-driver level isolation: full file-system and
     registry redirection, hidden process list, network control.
     Requires Sandboxie-Plus to be installed (sandboxie-plus.com).
     The launcher hides its own presence and Sandboxie infrastructure
     from the sandboxed process so detection-aware apps run normally.

Requirements:
    pip install pywin32
    Sandboxie-Plus (optional but recommended for strongest isolation)
"""

import os
import re
import sys
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import subprocess
import datetime

# --------------------------------------------------------------------------- #
#  Win32 helpers (pywin32 + ctypes)
# --------------------------------------------------------------------------- #
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



# --------------------------------------------------------------------------- #
#  Persistent config (saves last exe path between sessions)
# --------------------------------------------------------------------------- #
_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".sandbox_launcher.json")

def load_config():
    try:
        import json
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data: dict):
    try:
        import json
        existing = load_config()
        existing.update(data)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Sandboxie-Plus backend
# --------------------------------------------------------------------------- #
_SBIE_SEARCH_PATHS = [
    r"C:\Program Files\Sandboxie-Plus",
    r"C:\Program Files\Sandboxie",
    r"C:\Program Files (x86)\Sandboxie-Plus",
    r"C:\Program Files (x86)\Sandboxie",
]

# Sandboxie infrastructure + our launcher – hidden from the sandboxed app
_SBIE_PROCESS_NAMES = [
    "sandboxie.exe", "sandboxierpcss.exe", "sandboxiecrypto.exe",
    "sandboxiedcom.exe", "start.exe", "sandman.exe",
    "sbiesvc.exe", "sbiesvc32.exe",
    "sandbox_launcher.exe", "python.exe", "pythonw.exe",
]


def find_sandboxie():
    # Locate a Sandboxie-Plus installation.
    # Returns {'start': path, 'ini': path, 'root': path} or None.
    import winreg
    for key_path in [
        r"SOFTWARE\Sandboxie-Plus",
        r"SOFTWARE\Sandboxie",
        r"SOFTWARE\WOW6432Node\Sandboxie-Plus",
    ]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                install_dir, _ = winreg.QueryValueEx(k, "InstallPath")
                start = os.path.join(install_dir, "Start.exe")
                if os.path.isfile(start):
                    return {
                        "start": start,
                        "ini":   os.path.join(install_dir, "Sandboxie.ini"),
                        "root":  install_dir,
                    }
        except OSError:
            pass
    for d in _SBIE_SEARCH_PATHS:
        start = os.path.join(d, "Start.exe")
        if os.path.isfile(start):
            return {
                "start": start,
                "ini":   os.path.join(d, "Sandboxie.ini"),
                "root":  d,
            }
    return None


def _sbie_sanitise_box_name(name):
    # Sandboxie: letters+digits only, max 32 chars
    clean = re.sub(r"[^A-Za-z0-9]", "", name)[:32]
    return clean if clean else "LauncherBox"


def configure_sandbox_box(sbie_root, box_name, log_callback=None):
    # Configure the box via SbieIni.exe (preferred) or direct ini edit.
    # Always sets Enabled=y so Start.exe recognises the box.
    def log(m):
        if log_callback:
            log_callback(m)

    sbieini    = os.path.join(sbie_root, "SbieIni.exe")
    hide_names = ",".join(_SBIE_PROCESS_NAMES)
    settings   = [
        ("Enabled",             "y"),
        ("HideOtherBoxes",      "y"),
        ("HideSandboxieWindow", "y"),
        ("HideProcessName",     hide_names),
        # Drop Administrators/Power Users from token inside the box
        ("DropAdminRights",     "y"),
        # Spoof IsUserAnAdmin/IsElevated so apps don't refuse to start
        ("FakeAdminRights",     "y"),
        ("CopyLimitKb",         "524288"),
    ]

    if os.path.isfile(sbieini):
        for key, val in settings:
            try:
                r = subprocess.run(
                    [sbieini, "set", box_name, key, val],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode != 0:
                    log("[" + _ts() + "] SbieIni warn [" + key + "]: " + r.stderr.strip())
            except Exception as ex:
                log("[" + _ts() + "] SbieIni error: " + str(ex))
        log("[" + _ts() + "] Sandboxie: box [" + box_name + "] configured via SbieIni.exe")
    else:
        ini_path = os.path.join(sbie_root, "Sandboxie.ini")
        try:
            with open(ini_path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except FileNotFoundError:
            lines = []
        hdr = "[" + box_name + "]"
        sec_s = sec_e = -1
        in_s  = False
        for i, line in enumerate(lines):
            s = line.strip()
            if s == hdr:
                in_s = True; sec_s = i
            elif in_s and s.startswith("[") and s.endswith("]"):
                sec_e = i; break
        if in_s and sec_e == -1:
            sec_e = len(lines)
        if sec_s == -1:
            new_lines = ["\n", hdr + "\n"] + [k + "=" + v + "\n" for k, v in settings]
            lines.extend(new_lines)
        else:
            existing = {l.split("=")[0].strip().lower() for l in lines[sec_s:sec_e] if "=" in l}
            inserts  = [k + "=" + v + "\n" for k, v in settings if k.lower() not in existing]
            if inserts:
                lines[sec_e:sec_e] = inserts
        try:
            with open(ini_path, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            log("[" + _ts() + "] Sandboxie: box [" + box_name + "] written to ini directly")
        except PermissionError:
            log("[" + _ts() + "] Sandboxie: WARNING - run launcher as admin to configure box")


def launch_via_sandboxie(sbie, box_name, exe_path, args="", drop_admin=False, log_callback=None):
    # Launch exe_path inside a Sandboxie-Plus box via Start.exe.
    # Sanitises box name, configures it, reloads Sandboxie, then launches.
    def log(m):
        if log_callback:
            log_callback(m)

    box_name = _sbie_sanitise_box_name(box_name)
    log("[" + _ts() + "] Sandboxie: box name = " + box_name)

    configure_sandbox_box(sbie["root"], box_name, log_callback)

    # Reload so the Sandboxie driver sees the new/updated box definition
    try:
        subprocess.run([sbie["start"], "/reload"], capture_output=True, timeout=8)
        log("[" + _ts() + "] Sandboxie: config reloaded")
    except Exception:
        pass

    # Build the Start.exe command.
    # Only /box: and /drop_rights are used here — they are the safest flags
    # confirmed to work across all Sandboxie-Plus versions.  Extra flags like
    # /nosbiectrl and /silent vary between builds and cause "invalid parameter"
    # errors on some installations.
    # /fake_admin makes the app's elevation/admin checks return true
    # without actually granting real admin rights on the host
    cmd = [sbie["start"], "/box:" + box_name, "/fake_admin"]
    if drop_admin:
        cmd.append("/drop_rights")
    cmd.append(exe_path)
    if args.strip():
        cmd.extend(args.split())

    log("[" + _ts() + "] Sandboxie: command = " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=os.path.dirname(exe_path) or None,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    log("[" + _ts() + "] Sandboxie: Start.exe PID = " + str(proc.pid))
    return proc


def get_safer_token():
    """
    Produce a de-elevated PyHANDLE using the Windows SAFER API.
    SaferComputeTokenFromLevel is the same mechanism UAC uses internally and
    needs no special privileges.

    Strategy:
      1. SaferCreateLevel(NORMALUSER) + SaferComputeTokenFromLevel via ctypes
         to get a raw restricted token handle.
      2. DuplicateHandle that raw handle into a proper pywin32 PyHANDLE using
         win32api.DuplicateHandle so CreateProcessAsUser accepts it.

    Returns a pywin32 PyHANDLE.
    """
    if not WIN32_AVAILABLE:
        return None

    import ctypes, ctypes.wintypes as wt
    import pywintypes

    advapi32  = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32  = ctypes.WinDLL("kernel32",  use_last_error=True)

    SAFER_SCOPEID_USER       = 1
    SAFER_LEVELID_NORMALUSER = 0x20000
    SAFER_LEVEL_OPEN         = 1

    # ── Step 1: obtain raw restricted token via SAFER API ─────────────────
    h_level = ctypes.c_void_p()
    if not advapi32.SaferCreateLevel(
            SAFER_SCOPEID_USER, SAFER_LEVELID_NORMALUSER,
            SAFER_LEVEL_OPEN, ctypes.byref(h_level), None):
        raise ctypes.WinError(ctypes.get_last_error())

    raw_token = wt.HANDLE()
    ok = advapi32.SaferComputeTokenFromLevel(
        h_level, None, ctypes.byref(raw_token), 0, None)
    advapi32.SaferCloseLevel(h_level)

    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())

    # ── Step 2: duplicate the raw ctypes HANDLE into a pywin32 PyHANDLE ──
    # win32api.DuplicateHandle returns a PyHANDLE natively.
    cur = win32api.GetCurrentProcess()
    py_token = win32api.DuplicateHandle(
        cur,                          # source process
        raw_token.value,              # handle to duplicate (int is fine here)
        cur,                          # target process
        0,                            # desired access (0 = same as source)
        False,                        # not inheritable
        win32con.DUPLICATE_SAME_ACCESS
    )
    kernel32.CloseHandle(raw_token)   # release the raw ctypes copy
    return py_token                   # PyHANDLE – ready for CreateProcessAsUser




def create_job_object():
    """
    Create a Windows Job Object.
    NOTE: JOB_OBJECT_UILIMIT_HANDLES is intentionally excluded – it blocks
    child processes from accessing inherited handles (e.g. file system,
    AppData folder creation) and causes apps to crash on first launch.
    """
    if not WIN32_AVAILABLE:
        return None
    job = win32job.CreateJobObject(None, "SandboxJob")

    # --- UI restrictions (handles excluded to allow normal file/folder access) ---
    ui_info = win32job.QueryInformationJobObject(
        job, win32job.JobObjectBasicUIRestrictions
    )
    ui_info["UIRestrictionsClass"] = (
        win32job.JOB_OBJECT_UILIMIT_READCLIPBOARD    |
        win32job.JOB_OBJECT_UILIMIT_WRITECLIPBOARD   |
        win32job.JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS |
        win32job.JOB_OBJECT_UILIMIT_DISPLAYSETTINGS  |
        win32job.JOB_OBJECT_UILIMIT_GLOBALATOMS      |
        win32job.JOB_OBJECT_UILIMIT_EXITWINDOWS
    )
    win32job.SetInformationJobObject(
        job, win32job.JobObjectBasicUIRestrictions, ui_info
    )

    # --- Kill-on-job-close (cleans up child when launcher exits) ---
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


def build_spoofed_env(extra_vars: dict | None = None) -> dict:
    """
    Return an environment dict that looks like a typical Windows user session.
    Sensitive debugging / test flags are removed or overridden.
    """
    env = os.environ.copy()

    # Remove common sandbox-detection cues
    for key in [
        "_DEBUGGER_IS_PRESENT", "COR_ENABLE_PROFILING",
        "COR_PROFILER", "VSDEBUGGEE_PID", "VS_DEBUGGER",
        "COMPLUS_MDA", "__COMPAT_LAYER",
    ]:
        env.pop(key, None)

    # Ensure the app sees a plausible home-user profile path
    if "USERPROFILE" not in env:
        env["USERPROFILE"] = r"C:\Users\User"
    if "HOMEPATH" not in env:
        env["HOMEPATH"] = r"\Users\User"
    if "USERNAME" not in env:
        env["USERNAME"] = "User"
    if "COMPUTERNAME" not in env:
        env["COMPUTERNAME"] = "DESKTOP-PC"

    # Standard Windows paths – keep whatever the host already has
    env.setdefault("SystemRoot", r"C:\Windows")
    env.setdefault("windir",     r"C:\Windows")

    if extra_vars:
        env.update(extra_vars)

    return env


def launch_sandboxed(
    exe_path: str,
    args: str = "",
    drop_admin: bool = False,
    extra_env: dict | None = None,
    log_callback=None,
) -> subprocess.Popen:
    """
    Launch *exe_path* inside a Job Object sandbox.

    Parameters
    ----------
    exe_path    : Full path to the executable.
    args        : Additional command-line arguments (space-separated string).
    drop_admin  : Strip administrator privileges from the child token.
    extra_env   : Extra environment variables to inject / override.
    log_callback: Callable(str) for live log output; called from a thread.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    env = build_spoofed_env(extra_env)

    cmd = [exe_path] + ([a for a in args.split() if a] if args.strip() else [])
    log(f"[{_ts()}] Command  : {' '.join(cmd)}")
    log(f"[{_ts()}] Drop admin: {drop_admin}")

    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    if WIN32_AVAILABLE:
        import ctypes as _ct

        # Pre-create the AppData folder structure the app expects so it
        # does not crash when trying to write on first launch.
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            for folder in [
                os.path.join(appdata, "Miracle 7.4"),
                os.path.join(appdata, "Miracle 7.4", "MiracleV2"),
            ]:
                os.makedirs(folder, exist_ok=True)
                log(f"[{_ts()}] AppData  : ensured {folder}")

        job = create_job_object()

        start_flags = (
            win32process.CREATE_SUSPENDED |
            win32process.CREATE_NEW_PROCESS_GROUP
        )

        env_dict = dict(env)
        cwd      = os.path.dirname(exe_path) or None
        cmdline  = " ".join(cmd)

        if drop_admin:
            log(f"[{_ts()}] Token    : computing SAFER de-elevated token")
            token_handle = get_safer_token()
            # token_handle is a pywin32 PyHANDLE – no manual CloseHandle needed
            si2 = win32process.STARTUPINFO()
            si2.dwFlags     = win32process.STARTF_USESHOWWINDOW
            si2.wShowWindow = win32con.SW_SHOWNORMAL
            hProcess, hThread, pid, tid = win32process.CreateProcessAsUser(
                token_handle,
                exe_path, cmdline,
                None, None, False,
                start_flags,
                env_dict, cwd, si2,
            )
            del token_handle  # release PyHANDLE now that process is created
        else:
            si = win32process.STARTUPINFO()
            si.dwFlags     = win32process.STARTF_USESHOWWINDOW
            si.wShowWindow = win32con.SW_SHOWNORMAL
            hProcess, hThread, pid, tid = win32process.CreateProcess(
                exe_path, cmdline,
                None, None, False,
                start_flags,
                env_dict, cwd, si,
            )

        log(f"[{_ts()}] PID      : {pid}")

        if job:
            win32job.AssignProcessToJobObject(job, hProcess)
            log(f"[{_ts()}] Job object assigned.")

        win32process.ResumeThread(hThread)
        log(f"[{_ts()}] Process resumed – sandbox active.")

        proc = _Win32ProcWrapper(hProcess, pid, job)
    else:
        # Fallback – plain subprocess (no Job Object / token magic)
        log(f"[{_ts()}] WARNING: pywin32 not found – launching without Job Object.")
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=os.path.dirname(exe_path) or None,
            creationflags=creation_flags,
        )
        log(f"[{_ts()}] PID      : {proc.pid}")

    log(f"[{_ts()}] Launch complete.")
    return proc


def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S")


class _Win32ProcWrapper:
    """Thin wrapper so Win32 process handles behave like subprocess.Popen."""
    def __init__(self, hProcess, pid, job):
        self._hProcess = hProcess
        self.pid = pid
        self._job = job   # keep ref so job isn't GC'd while process lives

    def wait(self):
        import win32event
        win32event.WaitForSingleObject(self._hProcess, win32event.INFINITE)

    def poll(self):
        import win32event
        rc = win32event.WaitForSingleObject(self._hProcess, 0)
        return None if rc == win32event.WAIT_TIMEOUT else 0

    def terminate(self):
        """
        Kill every process in the Job Object first (covers all children),
        then ensure the root handle is dead too.
        Falls back to taskkill /F /T as a last resort.
        """
        if self._job:
            try:
                win32job.TerminateJobObject(self._job, 1)
            except Exception:
                pass
        # Always attempt root handle too in case it escaped the job
        try:
            win32api.TerminateProcess(self._hProcess, 1)
        except Exception:
            pass
        # Nuclear fallback: taskkill kills the whole process tree
        try:
            import subprocess as _sp
            _sp.run(["taskkill", "/F", "/T", "/PID", str(self.pid)],
                    capture_output=True)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#  GUI
# --------------------------------------------------------------------------- #
class SandboxLauncherApp(tk.Tk):
    DARK_BG   = "#1e1e2e"
    PANEL_BG  = "#2a2a3e"
    ACCENT    = "#7aa2f7"
    ACCENT2   = "#bb9af7"
    FG        = "#cdd6f4"
    MUTED     = "#6c7086"
    SUCCESS   = "#a6e3a1"
    WARNING   = "#f9e2af"
    ERROR     = "#f38ba8"
    FONT_MONO = ("Consolas", 9)
    FONT_UI   = ("Segoe UI", 10)
    FONT_H    = ("Segoe UI Semibold", 11)

    def __init__(self):
        super().__init__()
        self.title("Sandbox Launcher")
        self.configure(bg=self.DARK_BG)
        self.resizable(True, True)
        self.minsize(700, 660)
        self._proc = None
        self._sbie = find_sandboxie()   # None if not installed
        self._build_ui()
        self._center()
        # Restore last session values
        cfg = load_config()
        if cfg.get("last_exe"):
            self.exe_var.set(cfg["last_exe"])
        if cfg.get("last_args"):
            self.args_var.set(cfg["last_args"])
        if cfg.get("last_box"):
            self.sbie_box_var.set(cfg["last_box"])

    # ------------------------------------------------------------------ build
    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=self.PANEL_BG, pady=10)
        top.pack(fill="x")
        tk.Label(
            top, text="⬡  SANDBOX LAUNCHER", bg=self.PANEL_BG,
            fg=self.ACCENT, font=("Segoe UI Semibold", 14), padx=16
        ).pack(side="left")
        if not WIN32_AVAILABLE:
            tk.Label(
                top, text="⚠  pywin32 not installed – limited mode",
                bg=self.PANEL_BG, fg=self.WARNING,
                font=self.FONT_UI, padx=12
            ).pack(side="right")

        # ── Main body ────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=self.DARK_BG, padx=18, pady=14)
        body.pack(fill="both", expand=True)

        # Executable path
        self._section(body, "Executable")
        path_row = tk.Frame(body, bg=self.DARK_BG)
        path_row.pack(fill="x", pady=(4, 10))
        self.exe_var = tk.StringVar()
        exe_entry = tk.Entry(
            path_row, textvariable=self.exe_var,
            bg=self.PANEL_BG, fg=self.FG, insertbackground=self.FG,
            relief="flat", font=self.FONT_UI, bd=0
        )
        exe_entry.pack(side="left", fill="x", expand=True,
                       ipady=6, padx=(0, 8))
        self._btn(path_row, "Browse…", self._browse).pack(side="left")

        # Arguments
        self._section(body, "Arguments  (optional)")
        self.args_var = tk.StringVar()
        tk.Entry(
            body, textvariable=self.args_var,
            bg=self.PANEL_BG, fg=self.FG, insertbackground=self.FG,
            relief="flat", font=self.FONT_UI, bd=0
        ).pack(fill="x", ipady=6, pady=(4, 10))

        # Extra env vars
        self._section(body, "Extra environment variables  (KEY=VALUE, one per line)")
        self.env_text = tk.Text(
            body, bg=self.PANEL_BG, fg=self.FG, insertbackground=self.FG,
            relief="flat", font=self.FONT_MONO, height=4, bd=0
        )
        self.env_text.pack(fill="x", pady=(4, 10))

        # Backend selector
        self._section(body, "Isolation backend")
        be_frame = tk.Frame(body, bg=self.DARK_BG)
        be_frame.pack(fill="x", pady=(4, 8))

        self.backend_var = tk.StringVar(value="jobobj")
        sbie_available = self._sbie is not None
        sbie_label = (
            "Sandboxie-Plus  (kernel-driver isolation – recommended)"
            if sbie_available else
            "Sandboxie-Plus  (not installed – download from sandboxie-plus.com)"
        )
        rb_job = tk.Radiobutton(
            be_frame, text="Job Object  (built-in, no extra software)",
            variable=self.backend_var, value="jobobj",
            bg=self.DARK_BG, fg=self.FG, selectcolor=self.PANEL_BG,
            activebackground=self.DARK_BG, activeforeground=self.ACCENT,
            font=self.FONT_UI, command=self._on_backend_change,
        )
        rb_job.pack(anchor="w", pady=1)
        rb_sbie = tk.Radiobutton(
            be_frame, text=sbie_label,
            variable=self.backend_var, value="sandboxie",
            bg=self.DARK_BG, fg=self.ACCENT if sbie_available else self.MUTED,
            selectcolor=self.PANEL_BG,
            activebackground=self.DARK_BG, activeforeground=self.ACCENT,
            font=self.FONT_UI, state="normal" if sbie_available else "disabled",
            command=self._on_backend_change,
        )
        rb_sbie.pack(anchor="w", pady=1)

        # Sandboxie box name (shown only when Sandboxie backend selected)
        self._sbie_box_frame = tk.Frame(body, bg=self.DARK_BG)
        self._sbie_box_frame.pack(fill="x", pady=(0, 6))
        tk.Label(
            self._sbie_box_frame, text="Box name:",
            bg=self.DARK_BG, fg=self.MUTED, font=self.FONT_UI
        ).pack(side="left", padx=(16, 6))
        self.sbie_box_var = tk.StringVar(value="LauncherBox")
        tk.Entry(
            self._sbie_box_frame, textvariable=self.sbie_box_var,
            bg=self.PANEL_BG, fg=self.FG, insertbackground=self.FG,
            relief="flat", font=self.FONT_UI, bd=0, width=28,
        ).pack(side="left", ipady=4)
        self._sbie_box_frame.pack_forget()   # hidden until sbie selected
        tk.Label(self._sbie_box_frame, text="(letters+digits only, max 32 chars)", bg=self.DARK_BG, fg=self.MUTED, font=("Segoe UI", 8)).pack(side="left", padx=(6,0))

        if sbie_available:
            sbie_path = self._sbie["root"]
            tk.Label(
                be_frame,
                text="  ✓ found: " + sbie_path,
                bg=self.DARK_BG, fg=self.SUCCESS, font=("Segoe UI", 8),
            ).pack(anchor="w", padx=(22, 0))

        # Options
        self._section(body, "Options")
        opts = tk.Frame(body, bg=self.DARK_BG)
        opts.pack(fill="x", pady=(4, 12))

        self.drop_admin_var = tk.BooleanVar(value=False)
        self._checkbox(
            opts,
            "Force run without administrative privileges  "
            "(strips admin token – app cannot elevate)",
            self.drop_admin_var,
        ).pack(anchor="w", pady=2)

        self.spoof_env_var = tk.BooleanVar(value=True)
        self._checkbox(
            opts,
            "Spoof environment  "
            "(remove sandbox fingerprints, inject standard Windows variables)",
            self.spoof_env_var,
        ).pack(anchor="w", pady=2)

        self.job_var = tk.BooleanVar(value=True)
        self._checkbox(
            opts,
            "Wrap in Job Object  "
            "(restricts clipboard, display settings, atom table; auto-kills on close)",
            self.job_var,
        ).pack(anchor="w", pady=2)

        # Launch / Kill buttons
        btn_row = tk.Frame(body, bg=self.DARK_BG)
        btn_row.pack(fill="x", pady=(4, 8))
        self.launch_btn = self._btn(btn_row, "▶  Launch", self._launch,
                                     bg=self.ACCENT, fg=self.DARK_BG)
        self.launch_btn.pack(side="left", padx=(0, 8))
        self.kill_btn = self._btn(btn_row, "■  Terminate", self._kill,
                                   bg=self.ERROR, fg=self.DARK_BG,
                                   state="disabled")
        self.kill_btn.pack(side="left")

        # Log
        self._section(body, "Log")
        self.log_box = scrolledtext.ScrolledText(
            body, bg="#11111b", fg=self.FG,
            font=self.FONT_MONO, relief="flat", height=10,
            state="disabled", bd=0
        )
        self.log_box.pack(fill="both", expand=True, pady=(4, 0))
        self.log_box.tag_config("ok",   foreground=self.SUCCESS)
        self.log_box.tag_config("warn", foreground=self.WARNING)
        self.log_box.tag_config("err",  foreground=self.ERROR)

    # ---------------------------------------------------------------- helpers
    def _section(self, parent, text):
        f = tk.Frame(parent, bg=self.DARK_BG)
        f.pack(fill="x", pady=(6, 0))
        tk.Label(f, text=text, bg=self.DARK_BG, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Frame(f, bg=self.MUTED, height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=2
        )

    def _btn(self, parent, text, cmd, bg=None, fg=None, **kw):
        b = tk.Button(
            parent, text=text, command=cmd,
            bg=bg or self.PANEL_BG,
            fg=fg or self.ACCENT,
            activebackground=self.ACCENT,
            activeforeground=self.DARK_BG,
            relief="flat", font=self.FONT_UI,
            padx=12, pady=5, cursor="hand2",
            **kw
        )
        return b

    def _checkbox(self, parent, text, var):
        return tk.Checkbutton(
            parent, text=text, variable=var,
            bg=self.DARK_BG, fg=self.FG,
            selectcolor=self.PANEL_BG,
            activebackground=self.DARK_BG,
            activeforeground=self.ACCENT,
            font=self.FONT_UI,
        )

    def _center(self):
        self.update_idletasks()
        w, h = 700, 620
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ----------------------------------------------------------------- events
    def _on_backend_change(self):
        if self.backend_var.get() == "sandboxie":
            self._sbie_box_frame.pack(fill="x", pady=(0, 6))
        else:
            self._sbie_box_frame.pack_forget()

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select executable",
            filetypes=[("Executables", "*.exe *.bat *.cmd"),
                       ("All files", "*.*")]
        )
        if path:
            self.exe_var.set(path.replace("/", "\\"))

    def _launch(self):
        exe = self.exe_var.get().strip()
        if not exe:
            messagebox.showwarning("No executable", "Please select an executable first.")
            return
        if not os.path.isfile(exe):
            messagebox.showerror("File not found", f"Cannot find:\n{exe}")
            return

        self.launch_btn.config(state="disabled")
        self.kill_btn.config(state="normal")
        self._log(f"[{_ts()}] ── Launching ──────────────────────────", tag="ok")
        # Persist this session's values
        save_config({
            "last_exe":  exe,
            "last_args": self.args_var.get(),
            "last_box":  self.sbie_box_var.get(),
        })

        extra_env = {}
        for line in self.env_text.get("1.0", "end").splitlines():
            line = line.strip()
            if "=" in line and line:
                k, _, v = line.partition("=")
                extra_env[k.strip()] = v.strip()

        use_sbie   = (self.backend_var.get() == "sandboxie" and self._sbie)
        box_name   = self.sbie_box_var.get().strip() or "SandboxLauncherBox"
        drop_admin = self.drop_admin_var.get()

        def worker():
            try:
                if use_sbie:
                    self._log("[" + _ts() + "] Backend  : Sandboxie-Plus", tag="ok")
                    proc = launch_via_sandboxie(
                        sbie       = self._sbie,
                        box_name   = box_name,
                        exe_path   = exe,
                        args       = self.args_var.get(),
                        drop_admin = drop_admin,
                        log_callback = self._log,
                    )
                else:
                    self._log("[" + _ts() + "] Backend  : Job Object (built-in)", tag="ok")
                    proc = launch_sandboxed(
                        exe_path   = exe,
                        args       = self.args_var.get(),
                        drop_admin = drop_admin,
                        extra_env  = extra_env if self.spoof_env_var.get() else None,
                        log_callback = self._log,
                    )
                self._proc = proc
                root_pid = proc.pid
                self._log(f"[{_ts()}] ── Monitoring ─────────────────────────", tag="ok")

                # ── For Sandboxie backend, give Start.exe a moment to hand
                #    off the process to the driver, then find the real PIDs ──
                if use_sbie:
                    import time as _time
                    _time.sleep(1.5)
                    # Poll real sandboxed PIDs via Start.exe /listpids
                    def _get_sbie_pids(sbie_info, bname):
                        try:
                            r = subprocess.run(
                                [sbie_info["start"], "/box:" + bname, "/listpids"],
                                capture_output=True, text=True, timeout=8
                            )
                            pids = []
                            for line in r.stdout.splitlines():
                                line = line.strip()
                                if line.isdigit():
                                    pids.append(int(line))
                            return pids[1:] if len(pids) > 1 else pids  # first line is count
                        except Exception:
                            return []
                    sbie_info_ref = self._sbie
                    box_name_ref  = _sbie_sanitise_box_name(box_name)
                    sbie_pids = _get_sbie_pids(sbie_info_ref, box_name_ref)
                    if sbie_pids:
                        root_pid = sbie_pids[0]
                        self._log(f"[{_ts()}] Sandboxie: tracking {len(sbie_pids)} boxed PID(s): {sbie_pids}", tag="ok")
                    else:
                        self._log(f"[{_ts()}] Sandboxie: no PIDs yet in box – will retry in monitor loop", tag="warn")

                # ── rich process monitor ──────────────────────────────────────
                import ctypes, ctypes.wintypes as wt
                k32 = ctypes.WinDLL("kernel32", use_last_error=True)

                PROCESS_QUERY_INFORMATION = 0x0400
                PROCESS_VM_READ           = 0x0010
                TH32CS_SNAPPROCESS        = 0x00000002
                STILL_ACTIVE              = 259

                class PROCESSENTRY32(ctypes.Structure):
                    _fields_ = [
                        ("dwSize",              wt.DWORD),
                        ("cntUsage",            wt.DWORD),
                        ("th32ProcessID",       wt.DWORD),
                        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
                        ("th32ModuleID",        wt.DWORD),
                        ("cntThreads",          wt.DWORD),
                        ("th32ParentProcessID", wt.DWORD),
                        ("pcPriClassBase",      ctypes.c_long),
                        ("dwFlags",             wt.DWORD),
                        ("szExeFile",           ctypes.c_char * 260),
                    ]

                def snapshot_children(parent_pid):
                    """Return {pid: name} for all direct children of parent_pid."""
                    h = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
                    if h == ctypes.c_void_p(-1).value:
                        return {}
                    children = {}
                    pe = PROCESSENTRY32()
                    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
                    if k32.Process32First(h, ctypes.byref(pe)):
                        while True:
                            if pe.th32ParentProcessID == parent_pid:
                                children[pe.th32ProcessID] = pe.szExeFile.decode(errors="replace")
                            if not k32.Process32Next(h, ctypes.byref(pe)):
                                break
                    k32.CloseHandle(h)
                    return children

                def get_exit_code(pid):
                    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                    if not h:
                        return None
                    code = wt.DWORD()
                    k32.GetExitCodeProcess(h, ctypes.byref(code))
                    k32.CloseHandle(h)
                    return code.value

                known_children = {}   # pid -> name
                poll_interval  = 0.5  # seconds

                import time, win32event

                while True:
                    time.sleep(poll_interval)

                    # ── check root process ────────────────────────────────────
                    root_rc = get_exit_code(root_pid)
                    root_alive = (root_rc == STILL_ACTIVE)

                    if not root_alive and root_rc is not None:
                        self._log(
                            f"[{_ts()}] Root PID {root_pid} exited  "
                            f"(exit code {root_rc} / 0x{root_rc:08X})",
                            tag="warn"
                        )
                        # describe common codes
                        hints = {
                            0:          "clean exit",
                            1:          "generic error",
                            3:          "updater/self-restart code",
                            0xC0000005: "access violation (crash)",
                            0xC000013A: "Ctrl+C / terminated",
                            0xC0000142: "DLL init failed",
                            0xC0000034: "object name not found",
                        }
                        if root_rc in hints:
                            self._log(f"[{_ts()}]   → {hints[root_rc]}", tag="warn")

                    # ── scan for new child processes ──────────────────────────
                    current_children = snapshot_children(root_pid)
                    for cpid, cname in current_children.items():
                        if cpid not in known_children:
                            self._log(
                                f"[{_ts()}] Child spawned  PID {cpid}  [{cname}]",
                                tag="ok"
                            )
                            known_children[cpid] = cname

                    # check children that were seen before
                    for cpid, cname in list(known_children.items()):
                        if cpid not in current_children:
                            crc = get_exit_code(cpid)
                            self._log(
                                f"[{_ts()}] Child exited   PID {cpid}  [{cname}]  "
                                f"code {crc} / 0x{(crc or 0):08X}",
                                tag="warn"
                            )
                            del known_children[cpid]

                    # ── decide whether session is truly dead ──────────────────
                    if not root_alive and not current_children and not known_children:
                        self._log(
                            f"[{_ts()}] ── Session ended – no root or children alive ──",
                            tag="warn"
                        )
                        break

                    # if root died but children are still running, keep watching
                    if not root_alive and (current_children or known_children):
                        self._log(
                            f"[{_ts()}] Root exited but {len(current_children or known_children)} "
                            f"child(ren) still running – continuing to monitor…",
                            tag="ok"
                        )

                    # ── Sandboxie: also check boxed PIDs directly ─────────────
                    if use_sbie:
                        live_sbie = _get_sbie_pids(sbie_info_ref, box_name_ref)
                        if live_sbie and not root_alive and not current_children and not known_children:
                            # Start.exe exited but box still has processes – stay alive
                            self._log(
                                f"[{_ts()}] Sandboxie: {len(live_sbie)} process(es) still running in box: {live_sbie}",
                                tag="ok"
                            )
                            root_pid  = live_sbie[0]
                            # Re-open the handle for the new root PID so exit detection works
                            import win32event
                            try:
                                import win32api as _wa
                                hProcess = _wa.OpenProcess(0x0400, False, root_pid)
                                proc._hProcess = hProcess
                            except Exception:
                                pass
                            known_children = {}  # reset – we're tracking fresh PIDs now
                            continue

            except Exception as e:
                self._log(f"[{_ts()}] ERROR: {e}", tag="err")
            finally:
                self.after(0, self._reset_buttons)

        threading.Thread(target=worker, daemon=True).start()

    def _kill(self):
        # For Sandboxie backend, use Start.exe /terminate to kill the whole box
        if self.backend_var.get() == "sandboxie" and self._sbie:
            box = _sbie_sanitise_box_name(self.sbie_box_var.get())
            try:
                subprocess.run(
                    [self._sbie["start"], "/box:" + box, "/terminate"],
                    capture_output=True, timeout=8
                )
                self._log(f"[{_ts()}] Sandboxie: box '{box}' terminated.", tag="warn")
            except Exception as e:
                self._log(f"[{_ts()}] Sandboxie terminate error: {e}", tag="err")
        elif self._proc:
            try:
                self._proc.terminate()
                self._log(f"[{_ts()}] Process terminated by user.", tag="warn")
            except Exception as e:
                self._log(f"[{_ts()}] Could not terminate: {e}", tag="err")
        self._reset_buttons()

    def _reset_buttons(self):
        self.launch_btn.config(state="normal")
        self.kill_btn.config(state="disabled")
        self._proc = None

    def _log(self, msg, tag=None):
        def _append():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n", tag or "")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _append)


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    if sys.platform != "win32":
        print("This tool targets Windows. On other platforms only the GUI "
              "and plain subprocess fallback are available.")
    app = SandboxLauncherApp()
    app.mainloop()
