"""CrystalGlassMaterialLab tests (no pixel/visual assertions, per §17/§18).

Covers: file existence, shader hygiene (no reversed smoothstep, Qt6 ShaderEffect
UBO contract, droplet diameter quota), QML load smoke under software RHI, and
launcher CLI parsing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

QML_AVAILABLE = True
try:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
except ImportError:  # pragma: no cover - PySide6 always present in this venv
    QML_AVAILABLE = False

LAB_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "material_lab"

FRAGS = [LAB_DIR / "shaders" / "StaticRain.frag", LAB_DIR / "shaders" / "ClearGlass.frag"]
QSBS = [LAB_DIR / "effects" / "StaticRain.qsb", LAB_DIR / "effects" / "ClearGlass.qsb"]


def test_material_lab_files_exist() -> None:
    assert (LAB_DIR / "MaterialLab.qml").exists()
    assert (LAB_DIR / "material_lab_launcher.py").exists()
    for frag in FRAGS:
        assert frag.exists(), f"missing shader source: {frag}"
    for qsb in QSBS:
        assert qsb.exists(), f"missing compiled shader: {qsb}"


def test_no_reversed_smoothstep() -> None:
    """smoothstep(edge0, edge1, x) with literal edge0 > edge1 is UB and banned."""
    pat = re.compile(r"smoothstep\(\s*([0-9]+(?:\.[0-9]+)?)\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*[,)]")
    for frag in FRAGS:
        text = frag.read_text(encoding="utf-8")
        for m in pat.finditer(text):
            e0, e1 = float(m.group(1)), float(m.group(2))
            assert e0 < e1, (
                f"{frag.name}: reversed smoothstep edges {e0} > {e1} at {m.group(0)!r}"
            )


def test_shader_ubo_contract() -> None:
    """Qt6 fragment-only ShaderEffect: UBO (std140, binding 0) must start with
    mat4 qt_Matrix (offset 0) then float qt_Opacity (offset 64); custom uniforms
    follow. Violating this silently breaks rendering (buffer layout mismatch)."""
    for frag in FRAGS:
        text = frag.read_text(encoding="utf-8")
        m = re.search(
            r"layout\(std140,\s*binding\s*=\s*0\)\s*uniform\s+\w+\s*\{(.*?)\}\s*;",
            text,
            re.S,
        )
        assert m, f"{frag.name}: std140 UBO block not found"
        members = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
        assert members[0] == "mat4 qt_Matrix;", f"{frag.name}: UBO must start with qt_Matrix"
        assert members[1] == "float qt_Opacity;", f"{frag.name}: UBO[1] must be qt_Opacity"
        assert "_pad" not in text, f"{frag.name}: unnamed pad members break property mapping"


def test_static_rain_diameter_quota() -> None:
    """Droplet diameters must stay within quota; absolute max 30px never exceeded."""
    text = (LAB_DIR / "shaders" / "StaticRain.frag").read_text(encoding="utf-8")
    dmin = re.search(r"const float D_MIN\[4\]\s*=\s*float\[4\]\(([^)]*)\);", text)
    dmax = re.search(r"const float D_MAX\[4\]\s*=\s*float\[4\]\(([^)]*)\);", text)
    assert dmin and dmax, "D_MIN/D_MAX quota constants not found"
    dmin = [float(x) for x in dmin.group(1).replace(",", " ").split()]
    dmax = [float(x) for x in dmax.group(1).replace(",", " ").split()]
    assert dmin == [1.5, 4.0, 8.0, 15.0], f"unexpected D_MIN {dmin}"
    assert dmax == [4.0, 8.0, 15.0, 25.0], f"unexpected D_MAX {dmax}"
    assert max(dmax) <= 30.0, "absolute diameter cap (30px) exceeded"
    for lo, hi in zip(dmin, dmax):
        assert lo < hi, "diameter range invalid"


def test_qml_loads_smoke(monkeypatch) -> None:
    """QML engine loads the lab scene under software RHI; no pixel assertions."""
    if not QML_AVAILABLE:
        pytest.skip("PySide6 QtQuick unavailable")
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    from PySide6.QtCore import QUrl

    engine.load(QUrl.fromLocalFile(str(LAB_DIR / "MaterialLab.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "MaterialLab.qml produced no root object"
        assert str(roots[0].property("mode")) == "background"
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


def test_launcher_cli() -> None:
    from bottom_hunter.ui_demo.material_lab.material_lab_launcher import (
        HEIGHT,
        WIDTH,
        MODES,
        _select_modes,
        parse_args,
    )

    args = parse_args([])
    assert not args.debug_droplets
    assert not args.run
    assert not args.software
    assert args.modes is None
    assert args.out.endswith("shots")
    assert (WIDTH, HEIGHT) == (1440, 900)
    names = [f for _, f in MODES]
    assert names == [
        "background_only.png",
        "clear_glass_no_rain.png",
        "clear_glass_with_static_rain.png",
        "debug_droplets.png",
        "refraction_calibration.png",
        "final_material_rain.png",
        "debug_droplets_final.png",
        "refraction_calibration_final.png",
    ]
    assert _select_modes(None) == list(MODES)
    assert _select_modes("rain,calibration") == [
        ("rain", "clear_glass_with_static_rain.png"),
        ("calibration", "refraction_calibration.png"),
    ]
    import pytest

    with pytest.raises(SystemExit):
        _select_modes("bogus")
    args = parse_args(["--out", "/tmp/x", "--debug-droplets", "--software"])
    assert args.out == "/tmp/x"
    assert args.debug_droplets is True
    assert args.software is True
    args = parse_args(["--run", "--debug-droplets"])
    assert args.run is True
    assert args.debug_droplets is True
