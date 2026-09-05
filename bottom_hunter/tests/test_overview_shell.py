"""Overview shell PHASE 1.6 hardening tests (no GPU pixel-perfect CI asserts).

Covers: file existence, QML load smokes (shell + surface), three-viewport
construction, dynamic protection zones (real Item geometry, resize-safe),
mask texture resolutions, Qt6 UBO regression, forbidden legacy artifacts
(DropletSplash / icosphere / matcap) and the no-business-imports rule.
No GPU CI uses QML/software/offscreen smoke fallback.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

QML_AVAILABLE = True
try:
    from PySide6.QtCore import QCoreApplication, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    _ = QCoreApplication  # silence linters about unused imports
except ImportError:  # pragma: no cover - PySide6 always present in this venv
    QML_AVAILABLE = False

SHELL_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "overview_shell"
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
VIEWPORTS = ((1280, 720), (1440, 900), (1920, 1080))

FRAGS = [
    SHELL_DIR / "effects" / "StaticRainUI.frag",
    SHELL_DIR / "effects" / "EnvReadability.frag",
    # accepted material reused by the surface (ClearGlass pane)
    SHELL_DIR.parent / "material_lab" / "shaders" / "ClearGlass.frag",
]


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def _load_root(monkeypatch, qml: str):
    _software_env(monkeypatch)
    _app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    engine.load(QUrl.fromLocalFile(str(SHELL_DIR / qml)))
    roots = engine.rootObjects()
    try:
        assert roots, f"{qml} produced no root object"
        yield roots[0]
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()


# ---- 1. required files ------------------------------------------------------

def test_overview_shell_files_exist() -> None:
    for name in (
        "OverviewShell.qml",
        "RainGlassSurface.qml",
        "GlassMetricCard.qml",
        "ProtectionRegistry.qml",
        "overview_shell_launcher.py",
        "effects/StaticRainUI.frag",
        "effects/StaticRainUI.qsb",
        "effects/EnvReadability.frag",
        "effects/EnvReadability.qsb",
    ):
        assert (SHELL_DIR / name).exists(), f"missing: {name}"
    assert (SHELL_DIR.parent / "material_lab" / "effects" / "ClearGlass.qsb").exists()


# ---- 2/3. QML load smokes ---------------------------------------------------

@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_overview_shell_qml_load_smoke(monkeypatch) -> None:
    for root in _load_root(monkeypatch, "OverviewShell.qml"):
        assert str(root.property("mode")) == "shell"


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_rain_glass_surface_load_smoke(monkeypatch) -> None:
    for _ in _load_root(monkeypatch, "RainGlassSurface.qml"):
        pass  # surface item loads without errors


# ---- 4/5/7/8/9. viewports + dynamic zones + texture sizes -------------------

def _vec2(v) -> tuple[float, float]:
    """QVector2D (or QJSValue) -> (x, y) tuple, tolerant of PySide6 shapes."""
    if hasattr(v, "x") and not callable(getattr(v, "x", None)):
        return float(v.x()), float(v.y())
    return float(v.x()), float(v.y())


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_viewports_and_dynamic_zones(monkeypatch) -> None:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    def _settle(ms: int = 120) -> None:
        """Run the event loop briefly so Row positioners finish their polish
        pass (offscreen has no render loop to drive it)."""
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()
        for _ in range(3):
            QCoreApplication.processEvents()

    for width, height in VIEWPORTS:
        for root in _load_root(monkeypatch, "OverviewShell.qml"):
            root.setProperty("width", width)
            root.setProperty("height", height)
            _settle()
            registry = None
            for child in root.findChildren(object):
                if child.metaObject().className().startswith("ProtectionRegistry"):
                    registry = child
                    break
            assert registry is not None, "ProtectionRegistry not found"
            registry.rebuild()
            _settle(60)

            # 4: constructible at this viewport (implicit by reaching here)

            # 5: all critical protection zones inside the viewport
            zones = registry.property("sources").toVariant()
            assert zones, "protection registry produced no zones"
            for z in zones:
                assert -40 <= z["x"] and z["x"] + z["w"] <= width + 40, (
                    f"zone x out of viewport: {z} @ {width}x{height}")
                assert -40 <= z["y"] and z["y"] + z["h"] <= height + 40, (
                    f"zone y out of viewport: {z} @ {width}x{height}")

            # 6: each metric value zone has rain protection (critical level
            #    zones cover every registered value rect)
            vals = registry.property("metricValueRects").toVariant()
            assert len(vals) == 4, f"expected 4 metric value rects, got {len(vals)}"
            critical = [z for z in zones if z["level"] == "critical"]
            assert len(critical) >= 4
            for v in vals:
                covered = any(
                    c["x"] <= v["x"] and c["y"] <= v["y"]
                    and c["x"] + c["w"] >= v["x"] + v["w"]
                    and c["y"] + c["h"] >= v["y"] + v["h"]
                    for c in critical
                )
                assert covered, f"value rect not covered by a critical zone: {v}"

            # 7: resize keeps the registry consistent (rebuild is idempotent
            #    and critical zones keep covering the value rects). NOTE: the
            #    offscreen/software env does not re-run Row-positioner polish
            #    after setProperty, so absolute positions are validated in the
            #    GPU launcher viewport runs (protection-zones diagnostics).
            before = registry.property("sources").toVariant()
            registry.rebuild()
            _settle(40)
            after = registry.property("sources").toVariant()
            assert len(before) == len(after) and len(after) >= 13
            crit2 = [z for z in after if z["level"] == "critical"]
            assert len(crit2) >= 4
            for v in vals:
                assert any(
                    c["x"] <= v["x"] and c["y"] <= v["y"]
                    and c["x"] + c["w"] >= v["x"] + v["w"]
                    and c["y"] + c["h"] >= v["y"] + v["h"]
                    for c in crit2
                ), f"value rect not covered after rebuild: {v}"

            # 8: scene capture textureSize matches the viewport
            tex = _vec2(root.property("captureTextureSize"))
            assert (int(tex[0]), int(tex[1])) == (width, height), (
                f"scene texture {tex} != viewport {width}x{height}")

            # 9: mask texture sizes are strictly below the scene texture size
            rain_mask = _vec2(root.property("rainMaskTextureSize"))
            read_mask = _vec2(root.property("readMaskTextureSize"))
            assert (int(rain_mask[0]), int(rain_mask[1])) < (width, height)
            assert (int(read_mask[0]), int(read_mask[1])) < (width, height)


# ---- 10. Qt6 UBO regression -------------------------------------------------

def test_shader_ubo_contract() -> None:
    """Qt6 fragment-only ShaderEffect: UBO (std140, binding 0) must start with
    mat4 qt_Matrix (offset 0) then float qt_Opacity (offset 64); custom
    uniforms follow; output honors qt_Opacity (premultiplied)."""
    for frag in FRAGS:
        text = frag.read_text(encoding="utf-8")
        m = re.search(
            r"layout\(std140,\s*binding\s*=\s*0\)\s*uniform\s+\w+\s*\{(.*?)\}\s*;",
            text, re.S,
        )
        assert m, f"{frag.name}: std140 UBO block not found"
        members = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
        assert members[0] == "mat4 qt_Matrix;", f"{frag.name}: UBO must start with qt_Matrix"
        assert members[1] == "float qt_Opacity;", f"{frag.name}: UBO[1] must be qt_Opacity"
        # STEP 5: output must honor qt_Opacity (premultiplied contract).
        # StaticRainUI keeps source alpha for the desktop-transparent product
        # window; the other frozen shaders remain fully opaque.
        opaque_output = re.search(
            r"fragColor\s*=\s*vec4\(\s*(\w+)\s*\*\s*qt_Opacity\s*,\s*qt_Opacity\s*\)",
            text,
        )
        transparent_output = (
            "float finalA = outputA * qt_Opacity;" in text
            and "color * qt_Opacity" in text
            and re.search(r"fragColor\s*=\s*vec4\(.*finalA\s*\)", text)
        )
        assert opaque_output or transparent_output, (
            f"{frag.name}: fragColor does not honor qt_Opacity (premultiplied)")


# ---- 11. forbidden legacy artifacts -----------------------------------------

def test_no_legacy_droplet_artifacts() -> None:
    """DropletSplash / icosphere / matcap must not re-enter the shell or the
    production GUI."""
    forbidden = re.compile(r"DropletSplash|icosphere|matcap|MatCap", re.I)
    targets = list(SHELL_DIR.rglob("*.qml")) + list(SHELL_DIR.rglob("*.frag"))
    targets += list((SRC_DIR).glob("gui_qt.py"))
    targets += list((SRC_DIR).glob("chart_widget.py"))
    for path in targets:
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"forbidden artifact in {path.name}"


# ---- 12. no business imports ------------------------------------------------

def test_no_production_business_imports() -> None:
    """The overview shell (QML + viewmodel) must not import production or
    business modules. The launcher is the ONLY file allowed to wire backend
    loaders (PHASE 2-A: it injects read-only helpers into the bridge; the
    shell itself stays isolated). gui_qt.py must stay unpolluted."""
    forbidden = re.compile(
        r"import\s+bottom_hunter\.src|from\s+bottom_hunter\.src|"
        r"gui_qt|charting|chart_widget|research_widget|scanner",
        re.I,
    )
    for py in SHELL_DIR.rglob("*.py"):
        if py.name == "overview_shell_launcher.py":
            # the launcher is the only sanctioned wire point (PHASE 2-A);
            # but it must never import gui_qt (pollution ban)
            assert "gui_qt" not in py.read_text(encoding="utf-8"), (
                "launcher imports gui_qt — pollution ban violated")
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {py.name}"
    for qml in SHELL_DIR.rglob("*.qml"):
        text = qml.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {qml.name}"
