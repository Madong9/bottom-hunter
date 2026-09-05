"""Final product architecture and frozen-boundary audit."""

from __future__ import annotations

import importlib
import inspect
import os
import re
import subprocess
from dataclasses import is_dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PACKAGE = REPO / "bottom_hunter"
UI = PACKAGE / "ui_demo"
PAGES = UI / "pages"
PHASE5_BASE = os.environ.get("BH_PHASE5_BASE", "39379b0")
DESKTOP_ALPHA_SHADER = {
    "bottom_hunter/ui_demo/overview_shell/effects/StaticRainUI.frag",
    "bottom_hunter/ui_demo/overview_shell/effects/StaticRainUI.qsb",
}

DTO_MODULES = (
    "bottom_hunter.ui_demo.overview_shell.contracts",
    "bottom_hunter.ui_demo.pages.contracts",
    "bottom_hunter.ui_demo.pages.watchlist_contracts",
    "bottom_hunter.ui_demo.pages.research_contracts",
    "bottom_hunter.ui_demo.pages.import_contracts",
    "bottom_hunter.ui_demo.pages.status_contracts",
)

SANCTIONED_BACKEND_ADAPTERS = {
    UI / "overview_shell" / "overview_shell_launcher.py",
    PAGES / "contracts.py",
    PAGES / "import_backend_adapter.py",
    PAGES / "import_preview_adapter.py",
    PAGES / "overview_adapter.py",
    PAGES / "status_adapter.py",
}


def test_all_product_routes_have_page_loader_and_qml() -> None:
    shell = (PAGES / "ApplicationShell.qml").read_text(encoding="utf-8")
    for page_id, relative in {
        "overview": "overview/Overview.qml",
        "watchlist": "watchlist/Watchlist.qml",
        "research": "research/Research.qml",
        "report": "report/Report.qml",
        "import": "import/Import.qml",
        "status": "status/Status.qml",
        "chart": "chart/Chart.qml",
    }.items():
        assert (PAGES / relative).is_file()
        assert f'objectName: "{page_id}PageLoader"' in shell
        assert relative in shell


def test_qml_has_no_backend_or_storage_access() -> None:
    forbidden = re.compile(
        r"bottom_hunter|AccountWatchlistRepository|StateStore|sqlite3|"
        r"import_file\s*\(|add_manual_asset\s*\(|scanner\.py|backtest\.py",
        re.I,
    )
    for path in UI.rglob("*.qml"):
        assert not forbidden.search(path.read_text(encoding="utf-8", errors="ignore")), path


def test_viewmodels_have_no_business_or_database_imports() -> None:
    candidates = list(PAGES.glob("*viewmodel.py")) + [
        PAGES / "report_status.py",
        UI / "overview_shell" / "viewmodel" / "overview_state.py",
    ]
    forbidden = re.compile(
        r"bottom_hunter\.src|AccountWatchlistRepository|StateStore|ResearchStore|"
        r"sqlite3|from\s+.+scanner|from\s+.+backtest",
        re.I,
    )
    for path in candidates:
        assert not forbidden.search(path.read_text(encoding="utf-8", errors="ignore")), path


def test_all_dto_types_are_frozen_dataclasses_without_qt() -> None:
    for module_name in DTO_MODULES:
        module = importlib.import_module(module_name)
        source = inspect.getsource(module)
        assert "PySide6" not in source and "QObject" not in source
        dto_types = [
            value
            for name, value in vars(module).items()
            if name.endswith("DTO") and inspect.isclass(value) and value.__module__ == module_name
        ]
        assert dto_types, module_name
        for dto_type in dto_types:
            assert is_dataclass(dto_type), dto_type
            assert dto_type.__dataclass_params__.frozen is True, dto_type


def test_backend_imports_exist_only_in_sanctioned_adapters() -> None:
    pattern = re.compile(r"from\s+bottom_hunter\.src|import\s+bottom_hunter\.src")
    for path in UI.rglob("*.py"):
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            assert path in SANCTIONED_BACKEND_ADAPTERS, path


def test_import_controller_and_ui_are_isolated() -> None:
    controller = (PAGES / "import_controller.py").read_text(encoding="utf-8")
    viewmodel = (PAGES / "import_viewmodel.py").read_text(encoding="utf-8")
    qml = (PAGES / "import" / "Import.qml").read_text(encoding="utf-8")
    forbidden = re.compile(r"bottom_hunter\.src|AccountWatchlistRepository|sqlite3|StateStore")
    assert not forbidden.search(controller)
    assert not forbidden.search(viewmodel)
    assert not forbidden.search(qml)
    assert "QThread" in controller
    assert "QThread" not in viewmodel


def test_phase5_does_not_modify_frozen_backend_or_visual_files() -> None:
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    result = subprocess.run(
        ["git", "diff", "--name-only", PHASE5_BASE, "--"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip("PHASE 5 base commit is unavailable")
    changed = set(result.stdout.splitlines())
    frozen = {
        "bottom_hunter/src/gui_qt.py",
        "bottom_hunter/src/scanner.py",
        "bottom_hunter/src/backtest.py",
    }
    assert not changed.intersection(frozen)
    changed_shaders = {path for path in changed if path.endswith((".frag", ".qsb"))}
    assert changed_shaders <= DESKTOP_ALPHA_SHADER
    assert not any(path.startswith("bottom_hunter/src/") and "chart" in path.casefold() for path in changed)
