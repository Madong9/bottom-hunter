"""PHASE 5 composition root for the seven-page QML product shell."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Slot

from .chart_adapter import DRAWINGS_PATH, ChartDrawingAdapter, ChartReadAdapter
from .chart_contracts import ChartAssetDTO
from .chart_controller import ChartController, ChartReadPort
from .chart_viewmodel import ChartViewModel
from .contracts import ReportDTO, build_report_dto
from .import_backend_adapter import ProductionImportFlow, build_production_import_flow
from .import_runtime_adapter import RealRuntimeActivityPort, RuntimeStatusDTO
from .overview_adapter import build_overview_dto
from .report_status import ReportViewModel
from .research_adapter import build_research_dto
from .research_contracts import ResearchDTO
from .research_viewmodel import ResearchViewModel
from .routing import NavigationController
from .status_adapter import build_status_dto
from .status_contracts import StatusDTO
from .status_viewmodel import StatusViewModel
from .task_adapter import TaskCommandAdapter
from .task_controller import TaskController
from .task_viewmodel import TaskViewModel
from .watchlist_contracts import WatchlistDTO, build_watchlist_dto
from .watchlist_viewmodel import WatchlistViewModel


class _TaskRuntimeStatusProvider:
    def __init__(self, controller: TaskController) -> None:
        self._controller = controller

    def snapshot(self) -> RuntimeStatusDTO:
        return RuntimeStatusDTO(
            scanner_running=self._controller.operation == "scan",
            backtest_running=self._controller.operation == "backtest",
        )


class ProductCoordinator(QObject):
    """Coordinate presentation intents without exposing backend objects to QML."""

    def __init__(
        self,
        navigation: NavigationController,
        chart_view_model: ChartViewModel,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._navigation = navigation
        self._chart_view_model = chart_view_model

    @Slot(str)
    def openChart(self, canonical_id: str) -> None:  # noqa: N802
        self._chart_view_model.selectCanonicalId(canonical_id)
        self._navigation.navigate("chart")

    @Slot()
    def openImport(self) -> None:  # noqa: N802
        self._navigation.navigate("import")


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
    task_view_model: TaskViewModel
    task_controller: TaskController
    chart_view_model: ChartViewModel
    chart_controller: ChartController
    chart_drawing_adapter: ChartDrawingAdapter
    coordinator: ProductCoordinator

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
            "taskVm": self.task_view_model,
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
    chart_port: ChartReadPort | None = None,
    chart_assets: tuple[ChartAssetDTO, ...] | None = None,
    chart_drawing_adapter: ChartDrawingAdapter | None = None,
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
    task_vm = TaskViewModel()
    _load_read_only(watchlist_vm, watchlist_provider, WatchlistDTO())
    _load_read_only(research_vm, research_provider, ResearchDTO())
    _load_read_only(report_vm, report_provider, ReportDTO())
    _load_read_only(status_vm, status_provider, StatusDTO())

    task_controller = TaskController(TaskCommandAdapter())
    task_vm.startScanRequested.connect(task_controller.startScan)
    task_vm.startBacktestRequested.connect(task_controller.startBacktest)
    task_vm.stopRequested.connect(task_controller.stop)
    task_controller.taskStarted.connect(task_vm.markStarted)
    task_controller.outputReceived.connect(task_vm.appendOutput)
    task_controller.taskFinished.connect(task_vm.applyFinished)
    task_controller.taskFailed.connect(task_vm.applyError)
    runtime_activity = RealRuntimeActivityPort(
        runtime_status_provider or _TaskRuntimeStatusProvider(task_controller)
    )
    import_flow = build_production_import_flow(
        runtime_activity,
        project_dir,
        state_dir=state_dir,
        config_dir=config_dir,
    )
    resolved_chart_port = chart_port or ChartReadAdapter()
    resolved_chart_assets = (
        tuple(chart_assets)
        if chart_assets is not None
        else tuple(getattr(resolved_chart_port, "assets", ()))
    )
    chart_vm = ChartViewModel(resolved_chart_assets)
    chart_controller = ChartController(resolved_chart_port)
    chart_vm.loadRequested.connect(chart_controller.request)
    chart_controller.loadStarted.connect(chart_vm.markLoading)
    chart_controller.loadSucceeded.connect(chart_vm.apply)
    chart_controller.loadFailed.connect(chart_vm.applyLoadError)
    drawing_path = Path(state_dir) / "chart_drawings.json" if state_dir else None
    drawing_adapter = chart_drawing_adapter or ChartDrawingAdapter(drawing_path or DRAWINGS_PATH)
    chart_vm.drawingsLoadRequested.connect(
        lambda canonical_id, timeframe: chart_vm.applyDrawings(
            drawing_adapter.load(canonical_id, timeframe)
        )
    )
    chart_vm.drawingsSaveRequested.connect(
        lambda canonical_id, timeframe, annotations: chart_vm.applyDrawings(
            drawing_adapter.save(canonical_id, timeframe, annotations)
        )
    )
    chart_vm.requestDrawings()
    coordinator = ProductCoordinator(navigation, chart_vm)
    watchlist_vm.chartRequested.connect(coordinator.openChart)
    watchlist_vm.importRequested.connect(coordinator.openImport)
    watchlist_vm.refreshRequested.connect(
        lambda: _load_read_only(watchlist_vm, watchlist_provider, WatchlistDTO())
    )
    research_vm.refreshRequested.connect(
        lambda: _load_read_only(research_vm, research_provider, ResearchDTO())
    )
    report_vm.refreshRequested.connect(
        lambda: _load_read_only(report_vm, report_provider, ReportDTO())
    )
    status_vm.refreshRequested.connect(
        lambda: _load_read_only(status_vm, status_provider, StatusDTO())
    )

    def refresh_after_task(exit_code: int, cancelled: bool) -> None:
        if exit_code != 0 or cancelled:
            return
        overview_bridge.refresh()
        _load_read_only(watchlist_vm, watchlist_provider, WatchlistDTO())
        _load_read_only(research_vm, research_provider, ResearchDTO())
        _load_read_only(report_vm, report_provider, ReportDTO())
        _load_read_only(status_vm, status_provider, StatusDTO())
        refresh_chart_assets()

    task_controller.taskFinished.connect(refresh_after_task)

    def refresh_after_import(*_args: object) -> None:
        _load_read_only(watchlist_vm, watchlist_provider, WatchlistDTO())
        _load_read_only(status_vm, status_provider, StatusDTO())
        import_flow.view_model.applyMaintenanceResult(
            import_flow.maintenance_controller.initial_status()
        )
        refresh_chart_assets()

    def refresh_chart_assets() -> None:
        refresh = getattr(resolved_chart_port, "refresh_assets", None)
        if callable(refresh):
            chart_vm.replaceAssets(refresh())

    import_flow.controller.resultReady.connect(refresh_after_import)
    import_flow.view_model.maintenanceCompleted.connect(refresh_after_import)
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
        task_view_model=task_vm,
        task_controller=task_controller,
        chart_view_model=chart_vm,
        chart_controller=chart_controller,
        chart_drawing_adapter=drawing_adapter,
        coordinator=coordinator,
    )
