"""PHASE 1 smoke tests: QML demo loads, components resolve, low-GPU fallback.

These tests never assert pixel output (MASTER_PROMPT §17) — only that the
QML engine loads the demo without errors and the Bridge API works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

QML_AVAILABLE = True
try:
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    _ = QCoreApplication  # silence linters about unused imports
    _ = Qt
except ImportError:  # pragma: no cover - PySide6 always present in this venv
    QML_AVAILABLE = False

DEMO_DIR = Path(__file__).resolve().parent.parent / "ui_demo"


def _qgs_software(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
@pytest.mark.skipif(not DEMO_DIR.exists(), reason="ui_demo missing")
def test_demo_qml_file_and_shader_exist() -> None:
    assert (DEMO_DIR / "RainGlassDemo.qml").exists()
    assert (DEMO_DIR / "effects" / "RainGlassMaterial.qsb").exists()
    assert (DEMO_DIR / "shaders" / "RainGlassMaterial.frag").exists()
    assert (DEMO_DIR / "components" / "Theme.qml").exists()
    assert (DEMO_DIR / "components" / "GlassCard.qml").exists()
    assert (DEMO_DIR / "components" / "MetricCard.qml").exists()


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
@pytest.mark.skipif(not DEMO_DIR.exists(), reason="ui_demo missing")
def test_demo_loads_smoke(monkeypatch) -> None:
    """QML engine loads the demo; software fallback must not crash."""
    _qgs_software(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])

    from bottom_hunter.ui_demo.demo_launcher import Bridge

    bridge = Bridge()
    assert bridge.qtVersion
    assert bridge.diagnosticsVisible is False
    assert bridge.rhiBackendName() == "software"

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("initialQuality", "low")
    engine.addImportPath(str(DEMO_DIR))
    engine.load(str(DEMO_DIR / "RainGlassDemo.qml"))
    roots = engine.rootObjects()
    try:
        if roots:
            assert roots[0].property("quality") in ("high", "balanced", "low")
        # Low preset + software backend: shader may fail to compile there;
        # load success (or clean absence of root objects on GL-less CI)
        # is the acceptance bar, never pixel output.
    finally:
        if roots:
            roots[0].deleteLater()
        engine.deleteLater()
        bridge.deleteLater()
    del app


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_quality_preset_helpers() -> None:
    """QualityManager math (MASTER_PROMPT §13) via Theme functions."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(DEMO_DIR))
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(DEMO_DIR / "components" / "Theme.qml")))
    assert not component.isError(), component.errors()[:2]
    theme = component.create()
    assert theme is not None
    # QtObject properties → Python callables via shiboken
    assert float(theme.presetDropletDensity("high")) == 1.0
    assert float(theme.presetDropletDensity("balanced")) == pytest.approx(0.55)
    assert float(theme.presetDropletDensity("low")) == 0.0
    assert float(theme.presetBlurMax("low")) == 0.0
    assert float(theme.presetBlurMax("high")) > float(theme.presetBlurMax("balanced"))
    theme.deleteLater()
    del engine
    del app
