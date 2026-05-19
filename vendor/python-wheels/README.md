Place the Windows `tesserocr` wheel for the build Python here.

Expected build target:
- Python `3.12`
- Windows `64-bit`

The build script will automatically look for:
- `tesserocr-*-cp312-cp312-win_amd64.whl`

Recommended filename:
- `tesserocr-2.10.0-cp312-cp312-win_amd64.whl`

If this wheel is present, `build_windows.bat` will install it automatically,
along with `cysignals`, before running PyInstaller.
