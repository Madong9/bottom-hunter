"""Background worker for the experimental strategy research page."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _StrategyWorker(QObject):
    completed = Signal(object, object)

    def __init__(self, project_dir: str, state_dir: str) -> None:
        super().__init__()
        self._project_dir = project_dir
        self._state_dir = state_dir

    @Slot()
    def run(self) -> None:
        try:
            from .strategy_adapter import run_local_strategy_research

            result = run_local_strategy_research(self._project_dir, self._state_dir)
        except Exception as exc:
            self.completed.emit(None, exc)
        else:
            self.completed.emit(result, None)


class StrategyController(QObject):
    started = Signal()
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, project_dir: str, state_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._project_dir = project_dir
        self._state_dir = state_dir
        self._thread: QThread | None = None
        self._worker: _StrategyWorker | None = None

    @Slot()
    def run(self) -> None:
        if self._thread is not None:
            return
        thread = QThread(self)
        worker = _StrategyWorker(self._project_dir, self._state_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._completed)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        self.started.emit()
        thread.start()

    @Slot(object, object)
    def _completed(self, result: object, error: Exception | None) -> None:
        if error is not None:
            self.failed.emit(str(error) or "策略研究失败")
        elif isinstance(result, dict):
            self.succeeded.emit(result)
        else:
            self.failed.emit("策略研究返回了无效结果")

    @Slot()
    def _thread_finished(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        self.finished.emit()
        if thread is not None:
            thread.deleteLater()

    @Slot()
    def shutdown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
