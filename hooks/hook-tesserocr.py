"""PyInstaller hook for tesserocr.

tesserocr is a Cython extension that internally depends on:
  - tesserocr.cysignals.pyd    (Cython runtime, bundled inside tesserocr/)
  - cysignals.pyd               (standalone cysignals, separate package)

PyInstaller's static analysis cannot detect the C-level import of
``tesserocr.cysignals`` inside ``tesserocr.pyd``, so we must explicitly
bundle it here.  Without this hook the frozen .exe crashes with:

    ImportError: No module named tesserocr.cysignals
"""

import importlib
import os

hiddenimports = []

def _collect_pyds(pkg_name):
    """Collect .pyd/.so files from a package's directory."""
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
    for fname in os.listdir(pkg_dir):
        if fname.endswith((".pyd", ".so")):
            mod_name = fname.rsplit(".", 1)[0]
            hiddenimports.append(f"{pkg_name}.{mod_name}")

_collect_pyds("tesserocr")
_collect_pyds("cysignals")
