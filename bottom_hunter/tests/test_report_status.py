"""PHASE 3-C — page DTO adapter + view-model tests (Report / Status).

Verifies the read-only adapters build DTOs from the existing backend and the
view models apply them; the view-model layer never imports business directly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"


def test_report_viewmodel_defaults() -> None:
    from bottom_hunter.ui_demo.pages.report_status import ReportViewModel

    vm = ReportViewModel()
    assert vm.property("pageId") == "report"
    assert vm.property("reportDate") == "--"
    assert vm.property("loaded") is False


def test_report_viewmodel_apply() -> None:
    from bottom_hunter.ui_demo.pages.contracts import ReportDTO
    from bottom_hunter.ui_demo.pages.report_status import ReportViewModel

    vm = ReportViewModel()
    vm.apply(ReportDTO(report_date="2026-08-13", signal_count=5,
                       opportunity_count=27, sector_count=3, error_count=0))
    assert vm.property("reportDate") == "2026-08-13"
    assert vm.property("opportunityCount") == 27
    assert vm.property("loaded") is True


def test_report_adapter_reads_backend() -> None:
    """Adapter must not raise; returns None or a valid DTO."""
    from bottom_hunter.ui_demo.pages.contracts import ReportDTO, build_report_dto

    dto = build_report_dto()
    if dto is not None:
        assert isinstance(dto, ReportDTO)
        assert dto.report_date != "--"


def test_status_viewmodel_apply() -> None:
    from bottom_hunter.ui_demo.pages.contracts import StatusDTO
    from bottom_hunter.ui_demo.pages.report_status import StatusViewModel

    vm = StatusViewModel()
    dto = StatusDTO(items=(("Qt 桌面", True, "ok"), ("SQLite", False, "err")),
                    ok_count=1, total_count=2)
    vm.apply(dto)
    items = vm.property("items")
    assert len(items) == 2
    assert items[0]["name"] == "Qt 桌面"
    assert vm.property("okCount") == 1
    assert vm.property("totalCount") == 2
    assert vm.property("loaded") is True


def test_status_adapter_reads_backend() -> None:
    from bottom_hunter.ui_demo.pages.contracts import StatusDTO, build_status_dto

    dto = build_status_dto()
    assert isinstance(dto, StatusDTO)
    assert dto.total_count == len(dto.items)
    assert dto.ok_count <= dto.total_count


def test_viewmodel_layer_does_not_import_business() -> None:
    """report_status.py (viewmodel) must not reference backend modules; only
    contracts.py (the adapter boundary) may."""
    forbidden = re.compile(r"bottom_hunter\.src|from\s+bottom_hunter\.src", re.I)
    for name in ("report_status.py", "__init__.py", "routing.py"):
        text = (PAGES_DIR / name).read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {name}"
