"""Qt boundary for the separately deployed AI research assistant."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QObject,
    QProcess,
    QProcessEnvironment,
    QTimer,
    Signal,
    Slot,
)


def default_research_assistant_root() -> Path:
    configured = os.environ.get("BOTTOM_HUNTER_RESEARCH_ASSISTANT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "research_assistant"


class ResearchAssistantRuntime(QObject):
    """Own the local web-service process exposed by the desktop page."""

    changed = Signal()

    def __init__(
        self,
        root: str | Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._root = Path(root).expanduser().resolve() if root else default_research_assistant_root()
        self._runner = self._root / "run.py"
        self._available = self._runner.is_file()
        platform = os.environ.get("QT_QPA_PLATFORM", "").strip().casefold()
        auto_start_setting = os.environ.get("BOTTOM_HUNTER_RESEARCH_ASSISTANT_AUTOSTART", "1").strip().casefold()
        self._auto_start = (
            self._available
            and platform not in {"offscreen", "minimal", "minimalegl", "vnc", "linuxfb"}
            and auto_start_setting not in {"0", "false", "no", "off"}
        )
        self._state = "stopped" if self._available else "unavailable"
        self._status_text = "服务已停止" if self._available else "未找到投研助手模块"
        self._detail = (
            "进入页面后，主应用会启动服务并在界面内加载投研工作台。" if self._available else f"缺少文件：{self._runner}"
        )
        self._log_tail = ""
        self._stop_requested = False
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.started.connect(self._on_started)
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_process_error)

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(str, notify=changed)
    def statusText(self) -> str:  # noqa: N802
        return self._status_text

    @Property(str, notify=changed)
    def detail(self) -> str:
        return self._detail

    @Property(str, notify=changed)
    def logTail(self) -> str:  # noqa: N802
        return self._log_tail

    @Property(str, constant=True)
    def frontendUrl(self) -> str:  # noqa: N802
        return "http://127.0.0.1:5173"

    @Property(str, constant=True)
    def rootPath(self) -> str:  # noqa: N802
        return str(self._root)

    @Property(bool, notify=changed)
    def available(self) -> bool:
        return self._available

    @Property(bool, constant=True)
    def autoStart(self) -> bool:  # noqa: N802
        return self._auto_start

    @Property(bool, notify=changed)
    def canStart(self) -> bool:  # noqa: N802
        return self._available and self._state in {"stopped", "error"}

    @Property(bool, notify=changed)
    def canStop(self) -> bool:  # noqa: N802
        return self._state in {"starting", "running", "stopping"}

    @Property(bool, notify=changed)
    def ready(self) -> bool:
        return self._state == "running"

    def _set_state(self, state: str, status: str, detail: str | None = None) -> None:
        self._state = state
        self._status_text = status
        if detail is not None:
            self._detail = detail
        self.changed.emit()

    @Slot()
    def start(self) -> None:
        if not self.canStart:
            return
        self._stop_requested = False
        self._log_tail = ""
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUNBUFFERED", "1")
        self._process.setProcessEnvironment(environment)
        self._process.setWorkingDirectory(str(self._root))
        self._process.setProgram(sys.executable)
        self._process.setArguments([str(self._runner)])
        self._set_state("starting", "正在启动", "正在检查依赖并启动前后端服务…")
        self._process.start()

    @Slot()
    def stop(self) -> None:
        if self._process.state() == QProcess.ProcessState.NotRunning:
            if self._available:
                self._set_state("stopped", "服务已停止")
            return
        self._stop_requested = True
        self._set_state("stopping", "正在停止", "正在安全回收投研助手子进程…")
        self._process.terminate()
        QTimer.singleShot(5000, self._kill_if_running)

    def _on_started(self) -> None:
        self._set_state("starting", "正在启动", "服务进程已启动，正在等待健康检查…")

    def _read_output(self) -> None:
        chunk = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not chunk:
            return
        combined = (self._log_tail + chunk)[-4000:]
        self._log_tail = combined.strip()
        if "投研助手已就绪" in chunk or "投研助手已就绪" in combined:
            self._set_state(
                "running",
                "服务运行中",
                "FastAPI 与 React 已就绪，投研工作台已在当前页面内加载。",
            )
        else:
            self.changed.emit()

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        if self._stop_requested or exit_code == 0:
            self._set_state("stopped", "服务已停止", "投研助手子进程已回收。")
        else:
            detail = self._log_tail or f"服务进程退出（代码 {exit_code}）"
            self._set_state("error", "启动失败", detail)
        self._stop_requested = False

    def _on_process_error(self, _error: QProcess.ProcessError) -> None:
        if self._stop_requested:
            return
        detail = self._process.errorString() or "无法启动投研助手进程"
        self._set_state("error", "启动失败", detail)

    def _kill_if_running(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def shutdown(self) -> None:
        """Synchronously release child processes during application exit."""
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return
        self._stop_requested = True
        self._process.terminate()
        if not self._process.waitForFinished(5000):
            self._process.kill()
            self._process.waitForFinished(1000)


__all__ = ["ResearchAssistantRuntime", "default_research_assistant_root"]
