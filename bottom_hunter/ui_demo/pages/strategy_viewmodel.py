"""Presentation state for the standalone factor and strategy research page."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_STRATEGY, PageViewModel


class StrategyViewModel(PageViewModel):
    changed = Signal()
    runRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_STRATEGY, "因子策略", parent)
        self._lifecycle = "READY"
        self._running = False
        self._error = ""
        self._result: dict[str, Any] = {}

    @Property(str, notify=changed)
    def lifecycle(self) -> str:
        return self._lifecycle

    @Property(bool, notify=changed)
    def running(self) -> bool:
        return self._running

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property("QVariantMap", notify=changed)
    def result(self) -> dict[str, Any]:
        return self._result

    @Slot()
    def runResearch(self) -> None:  # noqa: N802
        if self._running:
            return
        self._error = ""
        self._running = True
        self._lifecycle = "RUNNING"
        self.changed.emit()
        self.runRequested.emit()

    @Slot(object)
    def apply(self, payload: object) -> None:
        self._result = dict(payload) if isinstance(payload, dict) else {}
        self._error = ""
        self._running = False
        self._lifecycle = "READY"
        self.changed.emit()

    @Slot(str)
    def applyError(self, message: str) -> None:  # noqa: N802
        self._error = str(message)
        self._running = False
        self._lifecycle = "ERROR"
        self.changed.emit()
