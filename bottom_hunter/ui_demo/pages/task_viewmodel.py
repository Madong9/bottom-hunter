"""Presentation state and user intents for scan/backtest tasks."""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot


class TaskViewModel(QObject):
    changed = Signal()
    startScanRequested = Signal(str, bool, int)
    startBacktestRequested = Signal(str, str, bool, int)
    stopRequested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = "IDLE"
        self._kind = ""
        self._name = ""
        self._detail = "就绪"
        self._log = ""
        self._exit_code = 0

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._state in {"STARTING", "RUNNING", "STOPPING"}

    @Property(str, notify=changed)
    def kind(self) -> str:
        return self._kind

    @Property(str, notify=changed)
    def name(self) -> str:
        return self._name

    @Property(str, notify=changed)
    def detail(self) -> str:
        return self._detail

    @Property(str, notify=changed)
    def log(self) -> str:
        return self._log

    @Property(int, notify=changed)
    def exitCode(self) -> int:  # noqa: N802
        return self._exit_code

    @Slot(str, bool, int)
    def startScan(self, requested_date: str = "", offline: bool = False, workers: int = 4) -> None:  # noqa: N802
        if self.busy:
            return
        self._state = "STARTING"
        self._detail = "正在准备扫描…"
        self._log = ""
        self.changed.emit()
        self.startScanRequested.emit(str(requested_date), bool(offline), int(workers))

    @Slot(str, str, bool, int)
    def startBacktest(self, start: str, end: str, offline: bool = False, workers: int = 4) -> None:  # noqa: N802
        if self.busy:
            return
        self._state = "STARTING"
        self._detail = "正在准备回测…"
        self._log = ""
        self.changed.emit()
        self.startBacktestRequested.emit(str(start), str(end), bool(offline), int(workers))

    @Slot()
    def stop(self) -> None:
        if not self.busy:
            return
        self._state = "STOPPING"
        self._detail = "正在安全停止…"
        self.changed.emit()
        self.stopRequested.emit()

    @Slot(str, str)
    def markStarted(self, kind: str, name: str) -> None:  # noqa: N802
        self._kind = str(kind)
        self._name = str(name)
        self._state = "RUNNING"
        self._detail = f"{self._name} 正在运行"
        self.changed.emit()

    @Slot(str)
    def appendOutput(self, value: str) -> None:  # noqa: N802
        self._log = (self._log + str(value))[-30000:]
        self.changed.emit()

    @Slot(int, bool)
    def applyFinished(self, exit_code: int, cancelled: bool) -> None:  # noqa: N802
        self._exit_code = int(exit_code)
        if cancelled:
            self._state = "CANCELLED"
            self._detail = "任务已安全停止"
        elif exit_code == 0:
            self._state = "SUCCESS"
            self._detail = f"{self._name or '任务'} 已完成"
        else:
            self._state = "ERROR"
            self._detail = f"{self._name or '任务'} 失败 · 退出码 {exit_code}"
        self.changed.emit()

    @Slot(str)
    def applyError(self, message: str) -> None:  # noqa: N802
        self._state = "ERROR"
        self._detail = str(message) or "任务启动失败"
        self.changed.emit()


__all__ = ["TaskViewModel"]
