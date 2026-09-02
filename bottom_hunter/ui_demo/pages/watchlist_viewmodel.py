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
from .watchlist_contracts import WatchlistDTO, build_watchlist_dto

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

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_WATCHLIST, "自选", parent)
        self._items: list[dict[str, Any]] = []
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
        self._items = [item.as_dict() for item in dto.items]
        self._generated_at = str(dto.generated_at)
        self._loaded = True
        self._error = ""
        self._set_lifecycle(LIFECYCLE_READY if self._items else LIFECYCLE_EMPTY)
        self.changed.emit()

    def applyError(self, message: str) -> None:  # noqa: N802
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
        dto = build_watchlist_dto()
        if dto is None:
            self.applyError("暂无自选快照（尚未生成 watchlist 摘要）")
            return
        self.apply(dto)
