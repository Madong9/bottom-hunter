# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir recipe used by AppImage and Debian packaging."""

from pathlib import Path
import sysconfig

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PACKAGE_DIR = Path(SPEC).resolve().parent.parent
REPOSITORY_DIR = PACKAGE_DIR.parent


def resource_files(root: Path, destination: str, suffixes: set[str]) -> list[tuple[str, str]]:
    values = []
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix in suffixes or path.name == "qmldir"):
            relative_parent = path.relative_to(root).parent
            values.append((str(path), str(Path(destination) / relative_parent)))
    return values


datas = resource_files(
    PACKAGE_DIR / "ui_demo",
    "bottom_hunter/ui_demo",
    {".qml", ".qsb"},
)
for relative in (
    "config/thresholds.yaml",
    "config/research.yaml",
    "config/notify.example.yaml",
    "data/fundamentals.csv",
    "data/research_import_template.csv",
    "packaging/defaults/watchlist.yaml",
    "packaging/defaults/industry_overrides.yaml",
):
    source = PACKAGE_DIR / relative
    datas.append((str(source), str(Path("bottom_hunter") / Path(relative).parent)))

datas += collect_data_files("exchange_calendars")
hiddenimports = collect_submodules("exchange_calendars") + [
    "PySide6.QtQuickControls2",
    "matplotlib.backends.backend_agg",
]

# A venv created from Conda may compile extension modules against newer Expat
# and OpenSSL builds than the host distribution. PyInstaller's generic resolver
# can otherwise select incompatible `/lib` copies, producing missing symbols at
# runtime even though the Python environment itself works correctly.
python_libdir = Path(sysconfig.get_config_var("LIBDIR") or "")
binaries = [
    (str(library), ".")
    for name in ("libexpat.so.1", "libssl.so.3", "libcrypto.so.3")
    if (library := python_libdir / name).is_file()
]

a = Analysis(
    [str(PACKAGE_DIR / "packaging" / "frozen_entry.py")],
    pathex=[str(REPOSITORY_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BottomHunter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BottomHunter",
)
