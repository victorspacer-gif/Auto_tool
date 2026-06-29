Place Windows wheels for the build Python here.

Supported build targets:
- Python `3.12` 64-bit (`cp312-cp312-win_amd64`)
- Python `3.14` 64-bit (`cp314-cp314-win_amd64`)

The build script (`build.py`) auto-selects the wheel matching the running
Python version by globbing for `{package}-*-{tag}-{tag}-win_amd64.whl`.

Bundled wheels (the build script will automatically find and install these):
- `tesserocr-*-{tag}-{tag}-win_amd64.whl`
- `cysignals-*-{tag}-{tag}-win_amd64.whl`

Recommended filenames for Python 3.12:
- `tesserocr-2.10.0-cp312-cp312-win_amd64.whl`
- `cysignals-1.12.6-cp312-cp312-win_amd64.whl`

Recommended filenames for Python 3.14:
- `tesserocr-2.10.0-cp314-cp314-win_amd64.whl`
- `cysignals-1.12.6-cp314-cp314-win_amd64.whl`

If a wheel is missing, the build script falls back to pip (requires internet).
For tesserocr (no Windows wheels on PyPI), the wheel must be placed here
or built from source.  cysignals 1.12.6+ provides cp314 wheels on PyPI and
can be downloaded automatically.
