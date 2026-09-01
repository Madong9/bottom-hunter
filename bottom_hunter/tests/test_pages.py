"""PHASE 3 / 3-A — page framework + routing tests.

Covers: PageViewModel base, NavigationController routing (valid/invalid
navigate, signal), placeholder view models for all 7 pages, QML
ApplicationShell load smoke, and business isolation.
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
except ImportError:  # pragma: no cover - PySide6 always present in this venv
    QML_AVAILABLE = False

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"
SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def _controller():
    from bottom_hunter.ui_demo.pages import NavigationController

    return NavigationController()


# ---- page registry / view models --------------------------------------------

def test_pages_registry_has_seven_pages() -> None:
    from bottom_hunter.ui_demo.pages import PAGES

    ids = [pid for pid, _t, _g in PAGES]
    assert ids == ["overview", "watchlist", "research", "report",
                   "import", "status", "chart"]
    titles = [t for _pid, t, _g in PAGES]
    assert titles == ["总览", "自选", "研究", "报告", "导入", "状态", "K线"]


def test_placeholder_viewmodels_built() -> None:
    from bottom_hunter.ui_demo.pages import build_page_viewmodels

    vms = build_page_viewmodels()
    assert len(vms) == 7
    vm = vms["research"]
    assert vm.property("pageId") == "research"
    assert vm.property("title") == "研究"
    assert vm.property("active") is False
    vm.setActive(True)
    assert vm.property("active") is True


# ---- navigation routing -----------------------------------------------------

def test_navigation_default_current() -> None:
    c = _controller()
    assert c.property("currentPage") == "overview"


def test_navigation_valid_and_invalid() -> None:
    c = _controller()
    c.navigate("status")
    assert c.property("currentPage") == "status"
    # invalid id -> no-op, current unchanged
    c.navigate("does-not-exist")
    assert c.property("currentPage") == "status"


def test_navigation_by_title() -> None:
    c = _controller()
    c.navigateByTitle("报告")
    assert c.property("currentPage") == "report"


def test_navigation_signal() -> None:
    c = _controller()
    seen = []
    c.currentPageChanged.connect(lambda: seen.append(c.property("currentPage")))
    c.navigate("chart")
    c.navigate("overview")
    assert seen == ["chart", "overview"]


def test_navigation_pages_list() -> None:
    c = _controller()
    pages = c.property("pages")
    assert len(pages) == 7
    assert pages[0]["id"] == "overview"
    assert pages[0]["glyph"] == "⌂"


# ---- QML shell smoke --------------------------------------------------------

@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_application_shell_loads(monkeypatch) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = _controller()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("navController", controller)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "ApplicationShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "ApplicationShell.qml produced no root object"
        controller.navigate("report")
        QCoreApplication.processEvents()
        assert controller.property("currentPage") == "report"
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


# ---- business isolation -----------------------------------------------------

def test_pages_do_not_import_business_modules() -> None:
    forbidden = re.compile(r"bottom_hunter\.src|from\s+bottom_hunter\.src|scanner", re.I)
    for py in PAGES_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {py.name}"
    for qml in PAGES_DIR.rglob("*.qml"):
        text = qml.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {qml.name}"
