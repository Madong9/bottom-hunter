"""PHASE 3 — page migration framework (base ViewModel + registry).

Architecture (Qt backend + QML presentation):

    Existing backend (read-only helpers)
            |
            v  (per-page adapters, later PHASE 3-C)
    PageDTO (per-page frozen contract, later)
            |
            v
    PageViewModel (base class here; per-page subclasses)
            |
            v
    QML page root

Nothing here imports business modules; pages are empty shells at this stage.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal

# Page identifiers (stable routing keys)
PAGE_OVERVIEW = "overview"
PAGE_WATCHLIST = "watchlist"
PAGE_RESEARCH = "research"
PAGE_REPORT = "report"
PAGE_IMPORT = "import"
PAGE_STATUS = "status"
PAGE_CHART = "chart"

PAGES = (
    (PAGE_OVERVIEW, "总览", "⌂"),
    (PAGE_WATCHLIST, "自选", "◆"),
    (PAGE_RESEARCH, "研究", "◎"),
    (PAGE_REPORT, "报告", "▤"),
    (PAGE_IMPORT, "导入", "✚"),
    (PAGE_STATUS, "状态", "◐"),
    (PAGE_CHART, "K线", "↗"),
)


class PageViewModel(QObject):
    """Base for all page view models.

    Exposes the minimal routing contract to QML. Subclasses add per-page
    display properties + a DTO provider in later phases. No business logic.
    """

    titleChanged = Signal()
    activeChanged = Signal()

    def __init__(self, page_id: str, title: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._page_id = page_id
        self._title = title
        self._active = False

    @Property(str, constant=True)
    def pageId(self) -> str:  # noqa: N802
        return self._page_id

    @Property(str, notify=titleChanged)
    def title(self) -> str:  # noqa: N802
        return self._title

    @Property(bool, notify=activeChanged)
    def active(self) -> bool:  # noqa: N802
        return self._active

    def setActive(self, value: bool) -> None:  # noqa: N802
        if value != self._active:
            self._active = value
            self.activeChanged.emit()


class PlaceholderViewModel(PageViewModel):
    """Empty page view model: no data, just the page identity/title.

    Used by all seven pages until their DTO/view model is built in
    PHASE 3-C. QML renders "«title» module ready".
    """

    def __init__(self, page_id: str, title: str, parent: QObject | None = None) -> None:
        super().__init__(page_id, title, parent)


def build_page_viewmodels(parent: QObject | None = None) -> dict[str, PageViewModel]:
    """Construct the seven placeholder view models (one per page)."""
    return {
        page_id: PlaceholderViewModel(page_id, title, parent)
        for page_id, title, _glyph in PAGES
    }


from .routing import NavigationController  # noqa: E402

__all__ = [
    "NavigationController",
    "PAGES",
    "PAGE_OVERVIEW",
    "PAGE_WATCHLIST",
    "PAGE_RESEARCH",
    "PAGE_REPORT",
    "PAGE_IMPORT",
    "PAGE_STATUS",
    "PAGE_CHART",
    "PageViewModel",
    "PlaceholderViewModel",
    "build_page_viewmodels",
]

