"""Safe placeholder contract for the intentionally unmigrated chart page."""

from __future__ import annotations

from PySide6.QtCore import Property

from . import PAGE_CHART, PageViewModel


class ChartPlaceholderViewModel(PageViewModel):
    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_CHART, "K线", parent)

    @Property(str, constant=True)
    def lifecycle(self) -> str:
        return "PLACEHOLDER"

    @Property(bool, constant=True)
    def available(self) -> bool:
        return False

    @Property(str, constant=True)
    def message(self) -> str:
        return "K线与画线能力仍由现有安全模块承载，尚未迁移到 QML。"
