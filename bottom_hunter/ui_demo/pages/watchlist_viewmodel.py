"""PHASE 4-A — Watchlist page ViewModel (read-only display state).

Backend -> watchlist_contracts (DTO) -> WatchlistViewModel -> Watchlist.qml.

The view model holds nothing but display state: a QML-friendly list of rows,
a lifecycle status (loading / ready / empty / error), and notify signals. It
imports NO business module and never calls the watchlist repository. The DTO
is supplied by ``apply()``, fed from the read-only adapter in
``watchlist_contracts.py``.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_WATCHLIST, PageViewModel
from .watchlist_contracts import WatchlistDTO

# lifecycle states (mirrors OverviewState thought: INIT/LOADING/READY/EMPTY/ERROR)
LIFECYCLE_INIT = "INIT"
LIFECYCLE_LOADING = "LOADING"
LIFECYCLE_READY = "READY"
LIFECYCLE_EMPTY = "EMPTY"
LIFECYCLE_ERROR = "ERROR"


class WatchlistViewModel(PageViewModel):
    """Display state for the 自选 page (frozen WatchlistDTO contract)."""

    changed = Signal()
    lifecycleChanged = Signal()
    refreshRequested = Signal()
    chartRequested = Signal(str)
    importRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_WATCHLIST, "自选", parent)
        self._all_items: list[dict[str, Any]] = []
        self._items: list[dict[str, Any]] = []
        self._query = ""
        self._category = "all"
        self._crypto_count = 0
        self._global_equity_count = 0
        self._cn_equity_count = 0
        self._overlap_count = 0
        self._unresolved_industry_count = 0
        self._sector_count = 0
        self._lifecycle = LIFECYCLE_INIT
        self._loaded = False
        self._error = ""
        self._generated_at = ""

    # ---- data ----

    @Property("QVariantList", notify=changed)
    def items(self) -> list:  # noqa: N802
        return self._items

    @Property(int, notify=changed)
    def count(self) -> int:  # noqa: N802
        return len(self._items)

    @Property(int, notify=changed)
    def totalCount(self) -> int:  # noqa: N802
        return len(self._all_items)

    @Property(str, notify=changed)
    def query(self) -> str:
        return self._query

    @Property(str, notify=changed)
    def category(self) -> str:
        return self._category

    @Property(int, notify=changed)
    def cryptoCount(self) -> int:  # noqa: N802
        return self._crypto_count

    @Property(int, notify=changed)
    def globalEquityCount(self) -> int:  # noqa: N802
        return self._global_equity_count

    @Property(int, notify=changed)
    def cnEquityCount(self) -> int:  # noqa: N802
        return self._cn_equity_count

    @Property(int, notify=changed)
    def overlapCount(self) -> int:  # noqa: N802
        return self._overlap_count

    @Property(int, notify=changed)
    def unresolvedIndustryCount(self) -> int:  # noqa: N802
        return self._unresolved_industry_count

    @Property(int, notify=changed)
    def sectorCount(self) -> int:  # noqa: N802
        return self._sector_count

    @Property(str, notify=changed)
    def generatedAt(self) -> str:  # noqa: N802
        return self._generated_at

    # ---- lifecycle ----

    @Property(str, notify=lifecycleChanged)
    def lifecycle(self) -> str:  # noqa: N802
        return self._lifecycle

    @Property(bool, notify=changed)
    def loaded(self) -> bool:  # noqa: N802
        return self._loaded

    @Property(str, notify=changed)
    def error(self) -> str:  # noqa: N802
        return self._error

    # ---- DTO apply ----

    def apply(self, dto: WatchlistDTO) -> None:  # noqa: N802
        self._all_items = [item.as_dict() for item in dto.items]
        self._crypto_count = int(dto.crypto_count)
        self._global_equity_count = int(dto.global_equity_count)
        self._cn_equity_count = int(dto.cn_equity_count)
        self._overlap_count = int(dto.overlap_count)
        self._unresolved_industry_count = int(dto.unresolved_industry_count)
        self._sector_count = int(dto.sector_count)
        self._apply_filter()
        self._generated_at = str(dto.generated_at)
        self._loaded = True
        self._error = ""
        self._set_lifecycle(LIFECYCLE_READY if self._all_items else LIFECYCLE_EMPTY)
        self.changed.emit()

    def applyError(self, message: str) -> None:  # noqa: N802
        self._all_items = []
        self._items = []
        self._error = str(message)
        self._loaded = False
        self._set_lifecycle(LIFECYCLE_ERROR)
        self.changed.emit()

    def markLoading(self) -> None:  # noqa: N802
        self._set_lifecycle(LIFECYCLE_LOADING)

    def _set_lifecycle(self, value: str) -> None:
        if value != self._lifecycle:
            self._lifecycle = value
            self.lifecycleChanged.emit()

    # ---- refresh (read-only) ----

    @Slot()
    def refresh(self) -> None:  # noqa: N802
        self.markLoading()
        self.refreshRequested.emit()

    def _apply_filter(self) -> None:
        query = self._query.casefold()
        rows: list[dict[str, Any]] = []
        for item in self._all_items:
            if self._category != "all" and item.get("category") != self._category:
                continue
            haystack = " ".join(
                str(item.get(key) or "")
                for key in ("symbol", "name", "market", "industry", "source_text")
            ).casefold()
            if query and query not in haystack:
                continue
            rows.append(item)
        self._items = rows

    @Slot(str)
    def setQuery(self, value: str) -> None:  # noqa: N802
        value = str(value).strip()
        if value == self._query:
            return
        self._query = value
        self._apply_filter()
        self.changed.emit()

    @Slot(str)
    def setCategory(self, value: str) -> None:  # noqa: N802
        value = str(value)
        if value not in {"all", "crypto", "global_equity", "cn_equity"}:
            return
        if value == self._category:
            return
        self._category = value
        self._apply_filter()
        self.changed.emit()

    @Slot(int)
    def openChart(self, index: int) -> None:  # noqa: N802
        if 0 <= int(index) < len(self._items):
            canonical_id = str(self._items[int(index)].get("canonical_id") or "")
            if canonical_id:
                self.chartRequested.emit(canonical_id)

    @Slot()
    def openImport(self) -> None:  # noqa: N802
        self.importRequested.emit()
