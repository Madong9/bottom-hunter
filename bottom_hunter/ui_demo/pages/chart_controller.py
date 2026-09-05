"""Asynchronous coordinator for the read-only chart adapter."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .chart_contracts import ChartDTO


class ChartReadPort(Protocol):
    def fetch(self, canonical_id: str, timeframe: str, limit: int) -> ChartDTO: ...


class _ChartWorker(QObject):
    completed = Signal(object, object)

    def __init__(self, port: ChartReadPort, request: tuple[str, str, int]) -> None:
        super().__init__()
        self._port = port
        self._request = request

    @Slot()
    def run(self) -> None:
        try:
            result = self._port.fetch(*self._request)
        except Exception as exc:
            self.completed.emit(None, exc)
        else:
            self.completed.emit(result, None)


class ChartController(QObject):
    """Keep network and backend work off the QML/UI thread."""

    loadStarted = Signal(str, str)
    loadSucceeded = Signal(object)
    loadFailed = Signal(str, str, str)
    busyChanged = Signal(bool)

    def __init__(self, port: ChartReadPort, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._port = port
        self._thread: QThread | None = None
        self._worker: _ChartWorker | None = None
        self._active: tuple[str, str, int] | None = None
        self._pending: tuple[str, str, int] | None = None

    @Slot(str, str, int)
    def request(self, canonical_id: str, timeframe: str, limit: int) -> None:
        request = (str(canonical_id), str(timeframe), max(30, min(int(limit), 500)))
        if self._thread is not None:
            self._pending = request
            return
        self._start(request)

    def _start(self, request: tuple[str, str, int]) -> None:
        thread = QThread(self)
        worker = _ChartWorker(self._port, request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._completed)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        self._active = request
        self.busyChanged.emit(True)
        self.loadStarted.emit(request[0], request[1])
        thread.start()

    @Slot(object, object)
    def _completed(self, dto: object, error: Exception | None) -> None:
        canonical_id, timeframe, _limit = self._active or ("", "", 0)
        if error is not None:
            self.loadFailed.emit(canonical_id, timeframe, str(error) or "行情读取失败")
        elif isinstance(dto, ChartDTO):
            self.loadSucceeded.emit(dto)
        else:
            self.loadFailed.emit(canonical_id, timeframe, "行情适配器返回了无效结果。")

    @Slot()
    def _thread_finished(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        self._active = None
        pending = self._pending
        self._pending = None
        if pending is None:
            self.busyChanged.emit(False)
        else:
            self._start(pending)
        if thread is not None:
            thread.deleteLater()
