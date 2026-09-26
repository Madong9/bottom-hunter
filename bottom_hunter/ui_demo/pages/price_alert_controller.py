"""Background intraday polling and CRUD coordinator for price-alert rules."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot


class _PollWorker(QObject):
    completed = Signal(object, object, object)

    def __init__(self, adapter) -> None:
        super().__init__()
        self._adapter = adapter

    @Slot()
    def run(self) -> None:
        try:
            snapshot, events = self._adapter.poll()
        except Exception as exc:
            self.completed.emit(None, [], exc)
        else:
            self.completed.emit(snapshot, events, None)


class PriceAlertController(QObject):
    snapshotChanged = Signal(object)
    alertTriggered = Signal(str)
    errorChanged = Signal(str)
    monitoringChanged = Signal(bool)

    def __init__(self, adapter, parent=None, interval_ms: int = 30_000) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._timer = QTimer(self)
        self._timer.setInterval(max(10_000, int(interval_ms)))
        self._timer.timeout.connect(self.poll)
        self._thread: QThread | None = None
        self._worker: _PollWorker | None = None
        self._monitoring = False

    @Slot()
    def start(self) -> None:
        if self._monitoring:
            return
        self._monitoring = True
        self.monitoringChanged.emit(True)
        self._timer.start()
        self._publish_snapshot(self._adapter.snapshot())
        self.poll()

    @Slot()
    def stop(self) -> None:
        if not self._monitoring:
            return
        self._monitoring = False
        self._timer.stop()
        self.monitoringChanged.emit(False)
        self._publish_snapshot(self._adapter.snapshot())

    @Slot(str, str, float)
    def addRule(self, canonical_id: str, condition: str, threshold: float) -> None:  # noqa: N802
        try:
            snapshot = self._adapter.add_rule(canonical_id, condition, threshold)
            self._publish_snapshot(snapshot)
            self.errorChanged.emit("")
            if self._monitoring:
                self.poll()
        except Exception as exc:
            self.errorChanged.emit(str(exc) or "无法创建预警")

    @Slot(str)
    def removeRule(self, rule_id: str) -> None:  # noqa: N802
        try:
            self._publish_snapshot(self._adapter.remove_rule(rule_id))
            self.errorChanged.emit("")
        except Exception as exc:
            self.errorChanged.emit(str(exc) or "无法删除预警")

    @Slot(str, bool)
    def setRuleEnabled(self, rule_id: str, enabled: bool) -> None:  # noqa: N802
        try:
            self._publish_snapshot(self._adapter.set_enabled(rule_id, enabled))
            self.errorChanged.emit("")
        except Exception as exc:
            self.errorChanged.emit(str(exc) or "无法更新预警")

    @Slot()
    def poll(self) -> None:
        if not self._monitoring or self._thread is not None:
            return
        snapshot = self._adapter.snapshot(monitoring=True)
        if not snapshot.rules:
            self._publish_snapshot(snapshot)
            return
        thread = QThread(self)
        worker = _PollWorker(self._adapter)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._completed)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object, object, object)
    def _completed(self, snapshot: object, events: object, error: Exception | None) -> None:
        if error is not None:
            self.errorChanged.emit(str(error) or "盘中预警刷新失败")
            return
        if snapshot is not None:
            self._publish_snapshot(snapshot)
            self.errorChanged.emit("")
        for event in events if isinstance(events, list) else []:
            self.alertTriggered.emit(str(event))

    @Slot()
    def _thread_finished(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread is not None:
            thread.deleteLater()

    def _publish_snapshot(self, snapshot: object) -> None:
        payload = snapshot.as_dict() if hasattr(snapshot, "as_dict") else snapshot
        if isinstance(payload, dict):
            payload = {**payload, "monitoring": self._monitoring}
            self.snapshotChanged.emit(payload)

    @Slot()
    def shutdown(self) -> None:
        self.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
