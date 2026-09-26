"""Acceptance checks for the merged AI research-assistant module."""

from __future__ import annotations

from pathlib import Path

from bottom_hunter.ui_demo.pages.research_assistant_runtime import (
    ResearchAssistantRuntime,
    default_research_assistant_root,
)

REPO = Path(__file__).resolve().parents[2]
ASSISTANT = REPO / "research_assistant"


def test_merged_research_assistant_contains_both_applications() -> None:
    assert (ASSISTANT / "run.py").is_file()
    assert (ASSISTANT / "backend" / "app" / "main.py").is_file()
    assert (ASSISTANT / "backend" / "tests" / "test_api.py").is_file()
    assert (ASSISTANT / "frontend" / "src" / "App.tsx").is_file()
    assert (ASSISTANT / "frontend" / "package-lock.json").is_file()
    assert (ASSISTANT / "docs" / "product_design.md").is_file()


def test_runtime_finds_merged_module_without_starting_processes() -> None:
    runtime = ResearchAssistantRuntime()
    assert default_research_assistant_root() == ASSISTANT
    assert runtime.available is True
    assert runtime.state == "stopped"
    assert runtime.canStart is True
    assert runtime.canStop is False
    assert runtime.ready is False
    assert runtime.frontendUrl == "http://127.0.0.1:5173"


def test_runtime_reports_missing_module(tmp_path: Path) -> None:
    runtime = ResearchAssistantRuntime(tmp_path / "missing")
    assert runtime.available is False
    assert runtime.state == "unavailable"
    assert runtime.canStart is False
    assert "run.py" in runtime.detail


def test_research_assistant_page_is_registered() -> None:
    from bottom_hunter.ui_demo.pages import PAGES

    assert ("research_assistant", "投研助手", "✦") in PAGES
    qml = (REPO / "bottom_hunter" / "ui_demo" / "pages" / "research_assistant" / "ResearchAssistant.qml").read_text(
        encoding="utf-8"
    )
    assert "researchAssistantVm" in qml
    assert "root.vm.start()" in qml
    assert "import QtWebEngine" in qml
    assert 'objectName: "researchAssistantWebView"' in qml
    assert "WebEngineView" in qml
    assert "Query Router + Stock Resolver + 五 Agent" in qml
    assert 'backgroundColor: "transparent"' in qml
    assert "zoomFactor: 1.10" in qml
    assert "viewingExternalPage || assistantWebView.canGoBack" in qml
    assert "assistantWebView.goBack()" in qml
    assert "assistantWebView.url = root.vm.frontendUrl" in qml
    assert "QDesktopServices" not in qml


def test_research_assistant_uses_bottom_hunter_glass_theme() -> None:
    styles = (ASSISTANT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")
    assert "Bottom Hunter Liquid Glass theme" in styles
    assert "--glass-fill:" in styles
    assert "--glass-edge:" in styles
    assert "backdrop-filter: var(--glass-blur)" in styles
    assert "html, body, #root, .app-shell, .main-panel" in styles


def test_research_assistant_frontend_exposes_seven_agent_workflow() -> None:
    timeline = (ASSISTANT / "frontend" / "src" / "components" / "ProcessTimeline.tsx").read_text(
        encoding="utf-8"
    )
    types = (ASSISTANT / "frontend" / "src" / "types" / "research.ts").read_text(
        encoding="utf-8"
    )
    assert 'title: "任务路由"' in timeline
    assert 'title: "证券识别"' in timeline
    assert 'title: "风险审核"' in timeline
    assert '"query_router"' in types
    assert '"stock_entity_resolver"' in types


def test_desktop_launcher_initializes_web_engine_before_the_application() -> None:
    launcher = (REPO / "bottom_hunter" / "ui_demo" / "pages" / "application_shell_launcher.py").read_text(
        encoding="utf-8"
    )
    assert "from PySide6.QtWebEngineQuick import QtWebEngineQuick" in launcher
    assert launcher.index("QtWebEngineQuick.initialize()") < launcher.index("app = QGuiApplication(arguments)")
