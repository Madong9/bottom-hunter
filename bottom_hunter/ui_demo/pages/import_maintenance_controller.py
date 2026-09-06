"""Asynchronous controller for explicit watchlist maintenance commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .import_contracts import ImportMaintenanceCommandDTO, ImportMaintenanceResultDTO


class ImportMaintenancePort(Protocol):
    def execute(self, command: ImportMaintenanceCommandDTO) -> ImportMaintenanceResultDTO: ...

    def source_statuses(self) -> ImportMaintenanceResultDTO: ...


class _MaintenanceWorker(QObject):
    completed = Signal(object, object)

    def __init__(self, port: ImportMaintenancePort, command: ImportMaintenanceCommandDTO) -> None:
        super().__init__()
        self._port = port
        self._command = command

    @Slot()
    def run(self) -> None:
        try:
            result = self._port.execute(self._command)
        except Exception as exc:  # command boundary
            self.completed.emit(None, exc)
        else:
            self.completed.emit(result, None)


class ImportMaintenanceController(QObject):
    stateChanged = Signal(str)
    resultReady = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        port: ImportMaintenancePort,
        parent: QObject | None = None,
        *,
        activity: object | None = None,
        busy_check: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._port = port
        self._thread: QThread | None = None
        self._worker: _MaintenanceWorker | None = None
        self._activity = activity
        self._busy_check = busy_check or (lambda: False)

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def initial_status(self) -> ImportMaintenanceResultDTO:
        return self._port.source_statuses()

    def _start(self, command: ImportMaintenanceCommandDTO) -> None:
        if self.busy:
            self.failed.emit("已有自选维护任务正在执行。")
            return
        operation = ""
        if self._activity is not None:
            operation = str(self._activity.active_operation() or "")
        if operation or self._busy_check():
            self.failed.emit(f"请等待{operation or '导入任务'}完成后重试。")
            return
        thread = QThread(self)
        worker = _MaintenanceWorker(self._port, command)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._complete)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self.stateChanged.emit("RUNNING")
        thread.start()

    @Slot(str, str, str, str, str)
    def addManual(
        self, source: str, symbol: str, name: str, market: str, industry: str
    ) -> None:  # noqa: N802
        if not str(symbol).strip() and not str(name).strip():
            self.failed.emit("请输入股票名称或交易代码。")
            return
        self._start(
            ImportMaintenanceCommandDTO(
                action="add_manual",
                source=str(source),
                symbol=str(symbol).strip(),
                name=str(name).strip(),
                market=str(market).strip(),
                industry=str(industry).strip(),
            )
        )

    @Slot(str)
    def clearSource(self, source: str) -> None:  # noqa: N802
        self._start(ImportMaintenanceCommandDTO(action="clear_source", source=str(source)))

    @Slot()
    def refreshLinked(self) -> None:  # noqa: N802
        self._start(ImportMaintenanceCommandDTO(action="refresh_linked"))

    @Slot(object, object)
    def _complete(self, result: object, error: object) -> None:
        if error is not None:
            self.stateChanged.emit("ERROR")
            self.failed.emit(str(error) or "自选维护失败。")
            return
        self.stateChanged.emit("SUCCESS")
        self.resultReady.emit(result)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
