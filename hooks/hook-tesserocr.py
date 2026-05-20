"""PyInstaller hook for tesserocr.

tesserocr is a Cython extension that internally depends on:
  - tesserocr.cysignals.pyd    (Cython runtime, bundled inside tesserocr/cysignals/)
  - cysignals.pyd               (standalone cysignals, separate package)

PyInstaller's static analysis cannot detect C-level imports of .pyd
files (no .py stub exists), so we must explicitly bundle them as
binaries here.  Without this hook the frozen .exe crashes with:

    ImportError: No module named tesserocr.tesserocr
    ImportError: No module named cysignals.signals
"""

import importlib
import os
import sys

hiddenimports = []
binaries = []


def _collect_pyds(pkg_name, dest_dir=None):
    """Collect .pyd/.so files from a package's directory.

    Cython extensions have no .py stub, so PyInstaller cannot resolve
    them via the normal import graph.  We must:
      1. Add the module as a hidden import so PyInstaller's loader
         knows to look for it at runtime.
      2. Add the .pyd file to the binaries list so PyInstaller
         copies it into the build output.
    """
    try:
        mod = importlib.import_module(pkg_name)
    except (ImportError, ModuleNotFoundError):
        return
    if mod is None:
        return

    # Walk the entire package tree (packages can nest sub-dirs)
    def _walk(pkg_dir, pkg_dotted):
        try:
            entries = os.listdir(pkg_dir)
        except OSError:
            return
        for fname in entries:
            fpath = os.path.join(pkg_dir, fname)
            if fname.endswith((".pyd", ".so")):
                mod_name = fname.rsplit(".", 1)[0]
                hiddenimports.append(f"{pkg_dotted}.{mod_name}")
                dest = dest_dir or "."
                binaries.append((fpath, dest))
            elif os.path.isdir(fpath):
                # Recurse into sub-packages (e.g. tesserocr/cysignals/)
                _walk(fpath, f"{pkg_dotted}.{fname}")

    pkg_path = getattr(mod, "__path__", None)
    if not pkg_path:
        return
    _walk(pkg_path[0], pkg_name)


_collect_pyds("tesserocr")
_collect_pyds("cysignals")
