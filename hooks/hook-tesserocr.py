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
import sysconfig

hiddenimports = []
binaries = []

# Build platform-tagged suffix that PyInstaller's binary scanner
# extracts from .pyd PE import tables (e.g. "cp312-win_amd64").
# sysconfig.get_platform() returns "win-amd64" (dash), but .pyd
# filenames use "win_amd64" (underscore), so we normalise.
_platform_tag = f"{sysconfig.get_python_tag()}-{sysconfig.get_platform().replace('-', '_')}"


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
            if fname.endswith((".pyd", ".so", ".dll")):
                # Strip platform tag for the base module name.
                # e.g. tesserocr.cp312-win_amd64.pyd -> tesserocr
                mod_name = fname.rsplit(".", 1)[0]
                base_name = f"{dotted_name}.{mod_name}"
                tagged_name = f"{base_name}.{_platform_tag}"

                # Add BOTH names so PyInstaller's binary scanner
                # (which reads PE import tables with the tagged name)
                # can resolve them.
                hiddenimports.append(base_name)
                hiddenimports.append(tagged_name)

                # Destination is the package directory with dots
                # replaced by slashes (PyInstaller normalises).
                dest = dotted_name.replace(".", "/")
                binaries.append((fpath, dest))
            elif os.path.isdir(fpath):
                _walk(fpath, f"{dotted_name}.{fname}")

    _walk(pkg_dir, pkg_name)


_collect_package("tesserocr")
_collect_package("cysignals")
