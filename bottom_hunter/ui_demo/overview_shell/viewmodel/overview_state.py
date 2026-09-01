"""PHASE 2-A — QObject ViewModel layer for the OverviewShell.

Architecture (production hardening, no business migration):

    Python / QtWidgets backend
            |
            v
    OverviewBridge (adapter: converts backend data — NO metric computation)
            |
            v
    OverviewState (QObject, display state only, notify signals)
            |
            v
    QML OverviewShell  (reads overviewState.* properties)

QML never imports Python business modules; business logic is untouched.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot


class OverviewState(QObject):
    """Display state only — no business computation.

    Exposed to QML as context property ``overviewState``. Every property has
    a notify signal so QML bindings update automatically.
    """

    opportunityCountChanged = Signal()
    dataHealthChanged = Signal()
    signalValidationChanged = Signal()
    portfolioValueChanged = Signal()
    reportDateChanged = Signal()
    hintChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # fallback defaults (no backend connected)
        self._opportunity_count = "--"
        self._opportunity_hint = "等待最新扫描"
        self._data_health = "--"
        self._data_health_hint = "行情完整度"
        self._signal_validation = "--"
        self._signal_validation_hint = "近30天5日持有胜率"
        self._portfolio_value = "1.0000"
        self._portfolio_hint = "三阶段框架净值"
        self._report_date = ""

    # ---- QML properties (READ + CONSTANT-less, with notify) ----------------

    @Property(str, notify=opportunityCountChanged)
    def opportunityCount(self) -> str:  # noqa: N802 (QML naming)
        return self._opportunity_count

    @Property(str, notify=opportunityCountChanged)
    def opportunityHint(self) -> str:  # noqa: N802
        return self._opportunity_hint

    @Property(str, notify=dataHealthChanged)
    def dataHealth(self) -> str:  # noqa: N802
        return self._data_health

    @Property(str, notify=dataHealthChanged)
    def dataHealthHint(self) -> str:  # noqa: N802
        return self._data_health_hint

    @Property(str, notify=signalValidationChanged)
    def signalValidation(self) -> str:  # noqa: N802
        return self._signal_validation

    @Property(str, notify=signalValidationChanged)
    def signalValidationHint(self) -> str:  # noqa: N802
        return self._signal_validation_hint

    @Property(str, notify=portfolioValueChanged)
    def portfolioValue(self) -> str:  # noqa: N802
        return self._portfolio_value

    @Property(str, notify=portfolioValueChanged)
    def portfolioHint(self) -> str:  # noqa: N802
        return self._portfolio_hint

    @Property(str, notify=reportDateChanged)
    def reportDate(self) -> str:  # noqa: N802
        return self._report_date

    # ---- setters (bridge-only; plain Python, no QML access) ----------------

    def setOpportunity(self, value: str, hint: str | None = None) -> None:  # noqa: N802
        if value != self._opportunity_count:
            self._opportunity_count = value
            self.opportunityCountChanged.emit()
        if hint is not None and hint != self._opportunity_hint:
            self._opportunity_hint = hint
            self.opportunityCountChanged.emit()

    def setDataHealth(self, value: str, hint: str | None = None) -> None:  # noqa: N802
        changed = value != self._data_health
        self._data_health = value
        if hint is not None:
            self._data_health_hint = hint
        if changed or hint is not None:
            self.dataHealthChanged.emit()

    def setSignalValidation(self, value: str, hint: str | None = None) -> None:  # noqa: N802
        if value != self._signal_validation:
            self._signal_validation = value
            self.signalValidationChanged.emit()
        if hint is not None and hint != self._signal_validation_hint:
            self._signal_validation_hint = hint
            self.signalValidationChanged.emit()

    def setPortfolio(self, value: str, hint: str | None = None) -> None:  # noqa: N802
        if value != self._portfolio_value:
            self._portfolio_value = value
            self.portfolioValueChanged.emit()
        if hint is not None and hint != self._portfolio_hint:
            self._portfolio_hint = hint
            self.portfolioValueChanged.emit()

    def setReportDate(self, value: str) -> None:  # noqa: N802
        if value != self._report_date:
            self._report_date = value
            self.reportDateChanged.emit()

    def resetToFallback(self) -> None:  # noqa: N802
        """Restore the no-backend defaults."""
        self.setOpportunity("--", "等待最新扫描")
        self.setDataHealth("--", "行情完整度")
        self.setSignalValidation("--", "近30天5日持有胜率")
        self.setPortfolio("1.0000", "三阶段框架净值")
        self.setReportDate("")


class OverviewBridge(QObject):
    """Adapter: backend data -> OverviewState (conversion only, no metrics).

    The bridge owns the data-fetching callables (injected; Phase 2-A wires
    them to the same read-only helpers the QtWidgets dashboard already uses,
    but the shell never imports business modules itself). No async system:
    initialization load + explicit refresh() only.
    """

    refreshed = Signal()

    def __init__(self, state: OverviewState, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = state
        # injected callables (each returns plain dicts / None); keeping them
        # injectable makes the bridge testable without a real database
        self._opportunity_loader = None   # () -> dict | None
        self._validation_loader = None    # () -> dict | None
        self._paper_loader = None         # () -> dict | None

    # ---- backend wiring (called by the host app, NOT by QML) ---------------

    def setOpportunityLoader(self, loader) -> None:  # noqa: N802
        self._opportunity_loader = loader

    def setValidationLoader(self, loader) -> None:  # noqa: N802
        self._validation_loader = loader

    def setPaperLoader(self, loader) -> None:  # noqa: N802
        self._paper_loader = loader

    # ---- QML-invokable ------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Manual refresh: pull once from the injected loaders and push the
        converted values into OverviewState. Missing loaders / None results
        keep the current values (fallback untouched)."""
        if self._opportunity_loader is not None:
            data = self._safe(self._opportunity_loader)
            if data is not None:
                self._state.setOpportunity(str(data.get("value", "--")), data.get("hint"))
                self._state.setReportDate(str(data.get("report_date", "")))
        if self._validation_loader is not None:
            data = self._safe(self._validation_loader)
            if data is not None:
                self._state.setSignalValidation(str(data.get("value", "--")), data.get("hint"))
        if self._paper_loader is not None:
            data = self._safe(self._paper_loader)
            if data is not None:
                self._state.setPortfolio(str(data.get("value", "1.0000")), data.get("hint"))
        self.refreshed.emit()

    @staticmethod
    def _safe(loader):
        try:
            return loader()
        except Exception:
            return None
