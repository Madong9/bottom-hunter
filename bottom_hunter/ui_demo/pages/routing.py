"""PHASE 3-A — native Qt/QML navigation state (no third-party framework).

NavigationController owns routing state only: the list of pages, the current
page id, and a navigate() slot. It holds no business logic and no page data.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from . import PAGE_OVERVIEW, PAGES


class NavigationController(QObject):
    """Routing state: current page id + page list (frozen order)."""

    currentPageChanged = Signal()
    pagesChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_page = PAGE_OVERVIEW
        self._pages = list(PAGES)

    @Property(str, notify=currentPageChanged)
    def currentPage(self) -> str:  # noqa: N802
        return self._current_page

    @Property("QVariantList", notify=pagesChanged)
    def pages(self) -> list:  # noqa: N802
        return [
            {"id": pid, "title": title, "glyph": glyph}
            for pid, title, glyph in self._pages
        ]

    @Slot(str)
    def navigate(self, page_id: str) -> None:  # noqa: N802
        """Switch the current page (no-op for unknown ids)."""
        valid = {pid for pid, _t, _g in self._pages}
        if page_id not in valid:
            return
        if page_id != self._current_page:
            self._current_page = page_id
            self.currentPageChanged.emit()

    @Slot(str)
    def navigateByTitle(self, title: str) -> None:  # noqa: N802
        for pid, t, _g in self._pages:
            if t == title:
                self.navigate(pid)
                return
