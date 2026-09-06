"""Non-blocking QProcess controller for existing scan and backtest entry points."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, QProcess, QTimer, Signal, Slot

from .task_contracts import TaskCommandDTO


class TaskCommandPort(Protocol):
    def build_scan(self, requested_date: str, offline: bool, workers: int) -> TaskCommandDTO: ...

    def build_backtest(self, start: str, end: str, offline: bool, workers: int) -> TaskCommandDTO: ...


class TaskController(QObject):
    taskStarted = Signal(str, str)
    outputReceived = Signal(str)
    taskFinished = Signal(int, bool)
    taskFailed = Signal(str)
    busyChanged = Signal(bool)

    def __init__(self, port: TaskCommandPort, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._port = port
        self._process: QProcess | None = None
        self._operation = ""
        self._cancelled = False

    @property
    def operation(self) -> str:
        return self._operation

    @property
    def busy(self) -> bool:
        return self._process is not None

    @Slot(str, bool, int)
    def startScan(self, requested_date: str, offline: bool, workers: int) -> None:  # noqa: N802
        try:
            command = self._port.build_scan(str(requested_date), bool(offline), int(workers))
        except Exception as exc:  # command adapter boundary
            self.taskFailed.emit(str(exc))
            return
        self._start(command)

    @Slot(str, str, bool, int)
    def startBacktest(self, start: str, end: str, offline: bool, workers: int) -> None:  # noqa: N802
        try:
            command = self._port.build_backtest(str(start), str(end), bool(offline), int(workers))
        except Exception as exc:  # command adapter boundary
            self.taskFailed.emit(str(exc))
            return
        self._start(command)

    def _start(self, command: TaskCommandDTO) -> None:
        if self._process is not None:
            self.taskFailed.emit("已有扫描或回测正在运行。")
            return
        process = QProcess(self)
        process.setWorkingDirectory(command.cwd)
        process.setProgram(command.program)
        process.setArguments(list(command.arguments))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        self._process = process
        self._operation = command.kind
        self._cancelled = False
        self.busyChanged.emit(True)
        self.taskStarted.emit(command.kind, command.name)
        process.start()

    @Slot()
    def stop(self) -> None:
        if self._process is None:
            return
        self._cancelled = True
        self.outputReceived.emit("正在安全停止任务…\n")
        self._process.terminate()
        process = self._process

        def force_stop() -> None:
            if self._process is process and process.state() != QProcess.ProcessState.NotRunning:
                process.kill()

        QTimer.singleShot(3000, force_stop)

    @Slot()
    def _read_stdout(self) -> None:
        if self._process is not None:
            text = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
            if text:
                self.outputReceived.emit(text)

    @Slot()
    def _read_stderr(self) -> None:
        if self._process is not None:
            text = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
            if text:
                self.outputReceived.emit(text)

    @Slot(int, QProcess.ExitStatus)
    def _finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._read_stdout()
        self._read_stderr()
        cancelled = self._cancelled
        self._release_process()
        self.taskFinished.emit(int(exit_code), cancelled)

    @Slot(QProcess.ProcessError)
    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return
        message = self._process.errorString() if self._process is not None else "任务启动失败"
        self._release_process()
        self.taskFailed.emit(message)

    def _release_process(self) -> None:
        process = self._process
        self._process = None
        self._operation = ""
        self._cancelled = False
        self.busyChanged.emit(False)
        if process is not None:
            process.deleteLater()

    @Slot()
    def shutdown(self) -> None:
        process = self._process
        if process is None:
            return
        self._cancelled = True
        process.kill()
        process.waitForFinished(1000)


__all__ = ["TaskCommandPort", "TaskController"]
