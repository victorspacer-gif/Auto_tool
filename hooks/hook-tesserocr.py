"""PyInstaller hook for tesserocr.

tesserocr is a Cython extension that internally depends on:
  - tesserocr.tesserocr.cp312-win_amd64.pyd  (Cython extension)
  - tesserocr/cysignals/signals.cp312-win_amd64.pyd  (Cython runtime)
  - cysignals/signals.cp312-win_amd64.pyd  (standalone cysignals)

PyInstaller's static analysis cannot detect C-level imports of .pyd
files (no .py stub exists) and will warn about hidden imports it
can't resolve from the .pyd PE import tables.  This hook explicitly
bundles the .pyd binaries and their DLL dependencies so the frozen
.exe works at runtime.

Without this hook the frozen .exe crashes with:

    ImportError: No module named tesserocr.tesserocr
    ImportError: No module named cysignals.signals
"""

import importlib
import os
import sys
from pathlib import Path

# Use packaging.tags to build the interpreter tag, since
# sysconfig.get_python_tag() was removed in Python 3.12.
from packaging import tags as _tags
import sysconfig

hiddenimports = []
binaries = []

# Build platform-tagged suffix that PyInstaller's binary scanner
# extracts from .pyd PE import tables (e.g. "cp312-win_amd64").
# packaging.tags.interpreter_name()  → "cp" (for CPython)
# packaging.tags.interpreter_version() → "312" (for 3.12)
# sysconfig.get_platform() returns "win-amd64" (dash), but .pyd
# filenames use "win_amd64" (underscore), so we normalise.
_platform_tag = f"{_tags.interpreter_name()}{_tags.interpreter_version()}-{sysconfig.get_platform().replace('-', '_')}"

# Also collect native DLLs from tesseract install directory
# These include: libtesseract*.dll, liblept*.dll, and their dependencies
_tesseract_vendor = Path(__file__).resolve().parent.parent / "vendor" / "tesseract"
if _tesseract_vendor.exists():
    for dll in _tesseract_vendor.glob("*.dll"):
        binaries.append((str(dll), "tesseract"))


def _collect_package(pkg_name):
    """Collect .pyd/.so/.dll files from a package's directory tree.

    Cython extensions have no .py stub, so PyInstaller cannot resolve
    them via the normal import graph.  We must:
      1. Add the module as a hidden import (name WITHOUT platform tag)
         AND with the platform-tagged name so PyInstaller's binary
         scanner matches the PE import table entries.
      2. Add every .pyd/.so/.dll to the binaries list so PyInstaller
         copies it into the build output, in the correct subdirectory.
    """
    try:
        mod = importlib.import_module(pkg_name)
    except (ImportError, ModuleNotFoundError):
        return
    if mod is None:
        return

    pkg_path = getattr(mod, "__path__", None)
    if not pkg_path:
        return
    pkg_dir = pkg_path[0]

    def _walk(directory, dotted_name):
        """Recursively walk the package directory tree."""
        try:
            entries = os.listdir(directory)
        except OSError:
            return
        for fname in sorted(entries):
            fpath = os.path.join(directory, fname)
            if fname.endswith((".pyd", ".so")):
                # Strip platform tag for the base module name.
                # e.g. tesserocr.cp312-win_amd64.pyd -> tesserocr
                mod_name = fname.rsplit(".", 1)[0]
                tag_suffix = f".{_platform_tag}"
                if mod_name.endswith(tag_suffix):
                    mod_name = mod_name[: -len(tag_suffix)]
                base_name = f"{dotted_name}.{mod_name}"

                hiddenimports.append(base_name)

                # Destination is the package directory with dots
                # replaced by slashes (PyInstaller normalises).
                dest = dotted_name.replace(".", "/")
                binaries.append((fpath, dest))
            elif fname.endswith(".dll"):
                dest = dotted_name.replace(".", "/")
                binaries.append((fpath, dest))
            elif os.path.isdir(fpath):
                _walk(fpath, f"{dotted_name}.{fname}")

    _walk(pkg_dir, pkg_name)


_collect_package("tesserocr")
_collect_package("cysignals")
