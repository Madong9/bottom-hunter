"""PHASE 5 composition root for the seven-page QML product shell."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .chart_viewmodel import ChartPlaceholderViewModel
from .contracts import ReportDTO, build_report_dto
from .import_backend_adapter import ProductionImportFlow, build_production_import_flow
from .import_runtime_adapter import RealRuntimeActivityPort, RuntimeStatusDTO
from .overview_adapter import build_overview_dto
from .report_status import ReportViewModel
from .research_contracts import ResearchDTO, build_research_dto
from .research_viewmodel import ResearchViewModel
from .routing import NavigationController
from .status_adapter import build_status_dto
from .status_contracts import StatusDTO
from .status_viewmodel import StatusViewModel
from .watchlist_contracts import WatchlistDTO, build_watchlist_dto
from .watchlist_viewmodel import WatchlistViewModel


class _IdleRuntimeStatusProvider:
    def snapshot(self) -> RuntimeStatusDTO:
        return RuntimeStatusDTO()


@dataclass
class ProductFlow:
    navigation: NavigationController
    overview_state: object
    overview_bridge: object
    overview_refresh_controller: object
    watchlist_view_model: WatchlistViewModel
    research_view_model: ResearchViewModel
    report_view_model: ReportViewModel
    import_flow: ProductionImportFlow
    status_view_model: StatusViewModel
    chart_view_model: ChartPlaceholderViewModel

    def context_properties(self) -> dict[str, object]:
        return {
            "navController": self.navigation,
            "overviewState": self.overview_state,
            "overviewBridge": self.overview_bridge,
            "overviewRefreshController": self.overview_refresh_controller,
            "watchlistVm": self.watchlist_view_model,
            "researchVm": self.research_view_model,
            "reportVm": self.report_view_model,
            "importVm": self.import_flow.view_model,
            "statusVm": self.status_view_model,
            "chartVm": self.chart_view_model,
        }

    def install_context(self, engine: object) -> None:
        context = engine.rootContext()
        for name, value in self.context_properties().items():
            context.setContextProperty(name, value)


def _load_read_only(view_model: object, provider: Callable[[], object | None], empty_dto: object) -> None:
    view_model.markLoading()
    try:
        dto = provider()
    except Exception as exc:  # product boundary: never raise snapshot failures into QML
        view_model.applyError(str(exc) or "读取快照失败")
        return
    view_model.apply(dto or empty_dto)


def build_production_flow(
    project_dir: str | None = None,
    *,
    state_dir: str | None = None,
    config_dir: str | None = None,
    runtime_status_provider: object | None = None,
    overview_provider: Callable[[], object | None] = build_overview_dto,
    watchlist_provider: Callable[[], WatchlistDTO | None] = build_watchlist_dto,
    research_provider: Callable[[], ResearchDTO | None] = build_research_dto,
    report_provider: Callable[[], ReportDTO | None] = build_report_dto,
    status_provider: Callable[[], StatusDTO] = build_status_dto,
) -> ProductFlow:
    """Build adapters, DTO providers, ViewModels and QML context objects."""

    from bottom_hunter.ui_demo.overview_shell.viewmodel import (
        OverviewBridge,
        OverviewRefreshController,
        OverviewState,
    )

    navigation = NavigationController()
    overview_state = OverviewState()
    overview_bridge = OverviewBridge(overview_state)
    overview_refresh_controller = OverviewRefreshController()
    overview_bridge.setDtoProvider(overview_provider)
    overview_refresh_controller.refreshRequested.connect(overview_bridge.refresh)
    overview_bridge.refresh()

    watchlist_vm = WatchlistViewModel()
    research_vm = ResearchViewModel()
    report_vm = ReportViewModel()
    status_vm = StatusViewModel()
    _load_read_only(watchlist_vm, watchlist_provider, WatchlistDTO())
    _load_read_only(research_vm, research_provider, ResearchDTO())
    _load_read_only(report_vm, report_provider, ReportDTO())
    _load_read_only(status_vm, status_provider, StatusDTO())

    runtime_activity = RealRuntimeActivityPort(runtime_status_provider or _IdleRuntimeStatusProvider())
    import_flow = build_production_import_flow(
        runtime_activity,
        project_dir,
        state_dir=state_dir,
        config_dir=config_dir,
    )
    return ProductFlow(
        navigation=navigation,
        overview_state=overview_state,
        overview_bridge=overview_bridge,
        overview_refresh_controller=overview_refresh_controller,
        watchlist_view_model=watchlist_vm,
        research_view_model=research_vm,
        report_view_model=report_vm,
        import_flow=import_flow,
        status_view_model=status_vm,
        chart_view_model=ChartPlaceholderViewModel(),
    )
