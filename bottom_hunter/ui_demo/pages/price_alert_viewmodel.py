"""QML presentation state for custom intraday price alerts."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_STRATEGY, PageViewModel


class PriceAlertViewModel(PageViewModel):
    changed = Signal()
    addRequested = Signal(str, str, float)
    removeRequested = Signal(str)
    setEnabledRequested = Signal(str, bool)
    alertTriggered = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_STRATEGY, "盘中预警", parent)
        self._assets: list[dict[str, Any]] = []
        self._rules: list[dict[str, Any]] = []
        self._monitoring = False
        self._error = ""
        self._last_alert = ""

    @Property("QVariantList", notify=changed)
    def assets(self) -> list[dict[str, Any]]:
        return self._assets

    @Property("QVariantList", notify=changed)
    def rules(self) -> list[dict[str, Any]]:
        return self._rules

    @Property(bool, notify=changed)
    def monitoring(self) -> bool:
        return self._monitoring

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(str, notify=changed)
    def lastAlert(self) -> str:  # noqa: N802
        return self._last_alert

    @Slot(object)
    def applySnapshot(self, snapshot: object) -> None:  # noqa: N802
        if hasattr(snapshot, "as_dict"):
            payload = snapshot.as_dict()
        elif isinstance(snapshot, dict):
            payload = snapshot
        else:
            return
        self._assets = list(payload.get("assets") or [])
        self._rules = []
        labels = {
            "price_above": "价格 ≥",
            "price_below": "价格 ≤",
            "change_above": "涨幅 ≥",
            "change_below": "涨幅 ≤",
        }
        for raw in payload.get("rules") or []:
            item = dict(raw)
            item["condition_label"] = labels.get(item.get("condition"), item.get("condition", ""))
            item["threshold_label"] = (
                f"{float(item.get('threshold') or 0):g}%"
                if str(item.get("condition", "")).startswith("change_")
                else f"{float(item.get('threshold') or 0):g}"
            )
            self._rules.append(item)
        self._monitoring = bool(payload.get("monitoring", self._monitoring))
        self._error = ""
        self.changed.emit()

    @Slot(str)
    def applyError(self, message: str) -> None:  # noqa: N802
        self._error = str(message)
        self.changed.emit()

    @Slot(str)
    def announce(self, message: str) -> None:
        self._last_alert = str(message)
        self.changed.emit()
        self.alertTriggered.emit(self._last_alert)

    @Slot(str, str, float)
    def addRule(self, canonical_id: str, condition: str, threshold: float) -> None:  # noqa: N802
        self.addRequested.emit(str(canonical_id), str(condition), float(threshold))

    @Slot(str)
    def removeRule(self, rule_id: str) -> None:  # noqa: N802
        self.removeRequested.emit(str(rule_id))

    @Slot(str, bool)
    def setRuleEnabled(self, rule_id: str, enabled: bool) -> None:  # noqa: N802
        self.setEnabledRequested.emit(str(rule_id), bool(enabled))
