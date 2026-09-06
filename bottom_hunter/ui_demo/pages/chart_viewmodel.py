"""Presentation state for the read-only QML K-line workspace."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_CHART, PageViewModel
from .chart_contracts import ChartAssetDTO, ChartDrawingDTO, ChartDTO

TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "60m", "4h", "1d", "1w", "1M"})


class ChartViewModel(PageViewModel):
    changed = Signal()
    lifecycleChanged = Signal()
    loadRequested = Signal(str, str, int)
    drawingsLoadRequested = Signal(str, str)
    drawingsSaveRequested = Signal(str, str, object)
    drawingsChanged = Signal()

    def __init__(self, assets: tuple[ChartAssetDTO, ...] = (), parent=None) -> None:
        super().__init__(PAGE_CHART, "K线", parent)
        self._assets = tuple(assets)
        self._asset_rows = [asset.as_dict() for asset in self._assets]
        self._selected_index = 0
        self._timeframe = "1d"
        self._limit = 160
        self._bars: list[dict[str, Any]] = []
        self._provider = ""
        self._updated_at = ""
        self._note = ""
        self._error = ""
        self._annotations: list[dict[str, str | float]] = []
        self._lifecycle = "INIT" if self._assets else "EMPTY"

    @Property("QVariantList", notify=changed)
    def assets(self) -> list[dict[str, Any]]:
        return self._asset_rows

    @Property(int, notify=changed)
    def selectedIndex(self) -> int:  # noqa: N802
        return self._selected_index

    @Property(str, notify=changed)
    def selectedCanonicalId(self) -> str:  # noqa: N802
        asset = self._selected_asset()
        return asset.canonical_id if asset else ""

    @Property(str, notify=changed)
    def selectedMarket(self) -> str:  # noqa: N802
        asset = self._selected_asset()
        return asset.market if asset else ""

    @Property(str, notify=changed)
    def timeframe(self) -> str:
        return self._timeframe

    @Property(int, notify=changed)
    def limit(self) -> int:
        return self._limit

    @Property("QVariantList", notify=changed)
    def bars(self) -> list[dict[str, Any]]:
        return self._bars

    @Property(int, notify=changed)
    def barCount(self) -> int:  # noqa: N802
        return len(self._bars)

    @Property(str, notify=changed)
    def provider(self) -> str:
        return self._provider

    @Property(str, notify=changed)
    def updatedAt(self) -> str:  # noqa: N802
        return self._updated_at

    @Property(str, notify=changed)
    def note(self) -> str:
        return self._note

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(str, notify=lifecycleChanged)
    def lifecycle(self) -> str:
        return self._lifecycle

    @Property(bool, notify=changed)
    def available(self) -> bool:
        return bool(self._assets)

    @Property("QVariantList", notify=drawingsChanged)
    def annotations(self) -> list[dict[str, str | float]]:
        return [dict(item) for item in self._annotations]

    def _selected_asset(self) -> ChartAssetDTO | None:
        if 0 <= self._selected_index < len(self._assets):
            return self._assets[self._selected_index]
        return None

    @Slot(object)
    def replaceAssets(self, assets: object) -> None:  # noqa: N802
        values = tuple(item for item in assets if isinstance(item, ChartAssetDTO))
        previous_id = self.selectedCanonicalId
        self._assets = values
        self._asset_rows = [asset.as_dict() for asset in values]
        self._selected_index = next(
            (index for index, asset in enumerate(values) if asset.canonical_id == previous_id),
            0,
        )
        if not values:
            self._bars = []
            self._annotations = []
            self._set_lifecycle("EMPTY")
            self.drawingsChanged.emit()
        self.changed.emit()

    def _set_lifecycle(self, lifecycle: str) -> None:
        if lifecycle != self._lifecycle:
            self._lifecycle = lifecycle
            self.lifecycleChanged.emit()

    @Slot()
    def activate(self) -> None:
        if not self._assets:
            self._set_lifecycle("EMPTY")
            return
        if not self._bars and self._lifecycle != "LOADING":
            self.refresh()

    @Slot()
    def refresh(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            self._set_lifecycle("EMPTY")
            return
        self.loadRequested.emit(asset.canonical_id, self._timeframe, self._limit)

    def _load_drawings(self) -> None:
        asset = self._selected_asset()
        if asset is not None:
            self.drawingsLoadRequested.emit(asset.canonical_id, self._timeframe)

    @Slot()
    def requestDrawings(self) -> None:  # noqa: N802
        self._load_drawings()

    @Slot(int)
    def selectAsset(self, index: int) -> None:  # noqa: N802
        if not 0 <= int(index) < len(self._assets) or int(index) == self._selected_index:
            return
        self._selected_index = int(index)
        self._bars = []
        self._annotations = []
        self._error = ""
        self._set_lifecycle("INIT")
        self.changed.emit()
        self.drawingsChanged.emit()
        self._load_drawings()
        self.refresh()

    @Slot(str)
    def selectCanonicalId(self, canonical_id: str) -> None:  # noqa: N802
        requested = str(canonical_id)
        for index, asset in enumerate(self._assets):
            if asset.canonical_id != requested:
                continue
            if index == self._selected_index:
                self.activate()
            else:
                self.selectAsset(index)
            return

    @Slot(str)
    def selectTimeframe(self, timeframe: str) -> None:  # noqa: N802
        if timeframe not in TIMEFRAMES or timeframe == self._timeframe:
            return
        self._timeframe = timeframe
        self._bars = []
        self._annotations = []
        self._error = ""
        self._set_lifecycle("INIT")
        self.changed.emit()
        self.drawingsChanged.emit()
        self._load_drawings()
        self.refresh()

    @Slot(int)
    def setLimit(self, limit: int) -> None:  # noqa: N802
        normalized = max(30, min(int(limit), 500))
        if normalized == self._limit:
            return
        self._limit = normalized
        self.changed.emit()
        self.refresh()

    @Slot(str, str)
    def markLoading(self, canonical_id: str, timeframe: str) -> None:  # noqa: N802
        if canonical_id != self.selectedCanonicalId or timeframe != self._timeframe:
            return
        self._error = ""
        self._set_lifecycle("LOADING")
        self.changed.emit()

    @Slot(object)
    def apply(self, dto: ChartDTO) -> None:
        if dto.canonical_id != self.selectedCanonicalId or dto.timeframe != self._timeframe:
            return
        self._bars = [bar.as_dict() for bar in dto.bars]
        self._provider = dto.provider
        self._updated_at = dto.updated_at
        self._note = dto.note
        self._error = ""
        self._set_lifecycle("READY" if self._bars else "EMPTY")
        self.changed.emit()

    @Slot(str)
    def applyError(self, message: str) -> None:  # noqa: N802
        self._error = str(message) or "行情加载失败"
        self._set_lifecycle("ERROR")
        self.changed.emit()

    @Slot(str, str, str)
    def applyLoadError(self, canonical_id: str, timeframe: str, message: str) -> None:  # noqa: N802
        if canonical_id != self.selectedCanonicalId or timeframe != self._timeframe:
            return
        self.applyError(message)

    @Slot(object)
    def saveAnnotations(self, annotations: object) -> None:  # noqa: N802
        asset = self._selected_asset()
        if asset is None:
            return
        self.drawingsSaveRequested.emit(asset.canonical_id, self._timeframe, annotations)

    @Slot(object)
    def applyDrawings(self, dto: ChartDrawingDTO) -> None:  # noqa: N802
        if dto.canonical_id != self.selectedCanonicalId or dto.timeframe != self._timeframe:
            return
        self._annotations = dto.as_list()
        self.drawingsChanged.emit()
