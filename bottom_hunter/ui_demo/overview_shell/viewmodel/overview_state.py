"""PHASE 2-B — product-grade QObject ViewModel for the OverviewShell.

Architecture (no business migration, no async system):

    Python / QtWidgets backend (read-only helpers)
            |
            v
    OverviewBridge (adapter: converts backend data -> state transitions)
            |
            v
    OverviewState (QObject, display state only, notify signals)
            |
            v
    QML OverviewShell  (reads overviewState.* properties)

    OverviewRefreshController (refreshRequested signal only)
            |
            v  (host app connects its refresh trigger here)
    OverviewBridge.refresh()

QML never imports Python business modules; business logic is untouched.
"""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Property, QObject, Signal, Slot

# Lifecycle states
LIFECYCLE_INIT = "INIT"
LIFECYCLE_LOADING = "LOADING"
LIFECYCLE_READY = "READY"
LIFECYCLE_STALE = "STALE"
LIFECYCLE_ERROR = "ERROR"
LIFECYCLES = (LIFECYCLE_INIT, LIFECYCLE_LOADING, LIFECYCLE_READY,
              LIFECYCLE_STALE, LIFECYCLE_ERROR)

# data-health levels
HEALTH_OK = "OK"
HEALTH_WARNING = "WARNING"
HEALTH_ERROR = "ERROR"
HEALTH_UNKNOWN = "UNKNOWN"


class OverviewState(QObject):
    """Display state only — no business computation.

    Exposed to QML as context property ``overviewState``. Every property has
    a notify signal so QML bindings update automatically.
    """

    # ---- lifecycle ----------------------------------------------------------
    lifecycleChanged = Signal()
    lastSuccessfulUpdateChanged = Signal()
    lastErrorChanged = Signal()

    # ---- market status ------------------------------------------------------
    marketStatusChanged = Signal()
    marketStatusDetailChanged = Signal()

    # ---- scan status --------------------------------------------------------
    scanStatusChanged = Signal()
    scanStatusDetailChanged = Signal()

    # ---- opportunity --------------------------------------------------------
    opportunityCountChanged = Signal()
    opportunityHintChanged = Signal()
    opportunityUpdatedChanged = Signal()

    # ---- data health --------------------------------------------------------
    dataHealthChanged = Signal()

    # ---- validation ---------------------------------------------------------
    validationChanged = Signal()
    validationHintChanged = Signal()

    # ---- portfolio ----------------------------------------------------------
    portfolioValueChanged = Signal()
    portfolioHintChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # lifecycle
        self._lifecycle = LIFECYCLE_INIT
        self._last_successful_update = ""
        self._last_error = ""
        # market
        self._market_status = "--"
        self._market_status_detail = ""
        # scan
        self._scan_status = "--"
        self._scan_status_detail = "等待最新扫描"
        # opportunity
        self._opportunity_count = "--"
        self._opportunity_hint = "等待最新扫描"
        self._opportunity_updated = ""
        # data health
        self._data_health_level = HEALTH_UNKNOWN
        self._data_health_text = "--"
        # validation
        self._validation = "--"
        self._validation_hint = "近30天5日持有胜率"
        # portfolio
        self._portfolio_value = "1.0000"
        self._portfolio_hint = "三阶段框架净值"

    # ================= lifecycle =================

    @Property(str, notify=lifecycleChanged)
    def lifecycle(self) -> str:  # noqa: N802
        return self._lifecycle

    @Property(str, notify=lastSuccessfulUpdateChanged)
    def lastSuccessfulUpdate(self) -> str:  # noqa: N802
        return self._last_successful_update

    @Property(str, notify=lastErrorChanged)
    def lastError(self) -> str:  # noqa: N802
        return self._last_error

    # ================= market status =================

    @Property(str, notify=marketStatusChanged)
    def marketStatus(self) -> str:  # noqa: N802
        return self._market_status

    @Property(str, notify=marketStatusDetailChanged)
    def marketStatusDetail(self) -> str:  # noqa: N802
        return self._market_status_detail

    # ================= scan status =================

    @Property(str, notify=scanStatusChanged)
    def scanStatus(self) -> str:  # noqa: N802
        return self._scan_status

    @Property(str, notify=scanStatusDetailChanged)
    def scanStatusDetail(self) -> str:  # noqa: N802
        return self._scan_status_detail

    # ================= opportunity =================

    @Property(str, notify=opportunityCountChanged)
    def opportunityCount(self) -> str:  # noqa: N802
        return self._opportunity_count

    @Property(str, notify=opportunityHintChanged)
    def opportunityHint(self) -> str:  # noqa: N802
        return self._opportunity_hint

    @Property(str, notify=opportunityUpdatedChanged)
    def opportunityUpdated(self) -> str:  # noqa: N802
        return self._opportunity_updated

    # ================= data health =================

    @Property(str, notify=dataHealthChanged)
    def dataHealthLevel(self) -> str:  # noqa: N802
        return self._data_health_level

    @Property(str, notify=dataHealthChanged)
    def dataHealthText(self) -> str:  # noqa: N802
        return self._data_health_text

    # ================= validation =================

    @Property(str, notify=validationChanged)
    def validation(self) -> str:  # noqa: N802
        return self._validation

    @Property(str, notify=validationHintChanged)
    def validationHint(self) -> str:  # noqa: N802
        return self._validation_hint

    # ================= portfolio =================

    @Property(str, notify=portfolioValueChanged)
    def portfolioValue(self) -> str:  # noqa: N802
        return self._portfolio_value

    @Property(str, notify=portfolioHintChanged)
    def portfolioHint(self) -> str:  # noqa: N802
        return self._portfolio_hint

    # ================= state machine (bridge-only) =================

    def markLoading(self) -> None:  # noqa: N802
        self._set_lifecycle(LIFECYCLE_LOADING)

    def markReady(self) -> None:  # noqa: N802
        self._set_lifecycle(LIFECYCLE_READY)
        now = datetime.now().isoformat(timespec="seconds")
        if now != self._last_successful_update:
            self._last_successful_update = now
            self.lastSuccessfulUpdateChanged.emit()

    def markStale(self, error: str) -> None:  # noqa: N802
        # READY -> STALE: KEEP existing data, only update lifecycle + lastError
        self._set_lifecycle(LIFECYCLE_STALE)
        if error != self._last_error:
            self._last_error = error
            self.lastErrorChanged.emit()

    def markError(self, error: str) -> None:  # noqa: N802
        # first-load failure -> ERROR (data remains fallback)
        self._set_lifecycle(LIFECYCLE_ERROR)
        if error != self._last_error:
            self._last_error = error
            self.lastErrorChanged.emit()

    def _set_lifecycle(self, value: str) -> None:
        if value != self._lifecycle:
            self._lifecycle = value
            self.lifecycleChanged.emit()

    # ================= value setters (bridge-only) =================

    def setMarketStatus(self, value: str, detail: str | None = None) -> None:  # noqa: N802
        changed = value != self._market_status
        self._market_status = value
        if detail is not None:
            self._market_status_detail = detail
        if changed or detail is not None:
            self.marketStatusChanged.emit()

    def setScanStatus(self, value: str, detail: str | None = None) -> None:  # noqa: N802
        changed = value != self._scan_status
        self._scan_status = value
        if detail is not None:
            self._scan_status_detail = detail
        if changed or detail is not None:
            self.scanStatusChanged.emit()

    def setOpportunity(self, value: str, hint: str | None = None,  # noqa: N802
                       updated: str | None = None) -> None:
        changed = value != self._opportunity_count
        self._opportunity_count = value
        if hint is not None:
            self._opportunity_hint = hint
        if updated is not None:
            self._opportunity_updated = updated
        if changed:
            self.opportunityCountChanged.emit()
        if hint is not None:
            self.opportunityHintChanged.emit()
        if updated is not None:
            self.opportunityUpdatedChanged.emit()

    def setDataHealth(self, level: str, text: str) -> None:  # noqa: N802
        if level != self._data_health_level or text != self._data_health_text:
            self._data_health_level = level
            self._data_health_text = text
            self.dataHealthChanged.emit()

    def setValidation(self, value: str, hint: str | None = None) -> None:  # noqa: N802
        if value != self._validation:
            self._validation = value
            self.validationChanged.emit()
        if hint is not None and hint != self._validation_hint:
            self._validation_hint = hint
            self.validationHintChanged.emit()

    def setPortfolio(self, value: str, hint: str | None = None) -> None:  # noqa: N802
        if value != self._portfolio_value:
            self._portfolio_value = value
            self.portfolioValueChanged.emit()
        if hint is not None and hint != self._portfolio_hint:
            self._portfolio_hint = hint
            self.portfolioHintChanged.emit()

    def resetToFallback(self) -> None:  # noqa: N802
        """Restore the no-backend defaults (back to INIT)."""
        self.setOpportunity("--", "等待最新扫描", "")
        self.setDataHealth(HEALTH_UNKNOWN, "--")
        self.setValidation("--", "近30天5日持有胜率")
        self.setPortfolio("1.0000", "三阶段框架净值")
        self.setMarketStatus("--", "")
        self.setScanStatus("--", "等待最新扫描")
        self._set_lifecycle(LIFECYCLE_INIT)
        self._last_error = ""
        self.lastErrorChanged.emit()


class OverviewRefreshController(QObject):
    """Unified refresh trigger — `refreshRequested` signal ONLY.

    Owns no business logic, computes nothing, and never modifies state
    directly. The host app connects `refreshRequested` to the bridge's
    refresh slot (future signal/event-bus integration point).
    """

    refreshRequested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @Slot()
    def requestRefresh(self) -> None:  # noqa: N802
        self.refreshRequested.emit()


class OverviewBridge(QObject):
    """Adapter: backend data -> OverviewState transitions.

    Owns the injected loaders; converts their results into state updates and
    drives the lifecycle state machine. No metric computation. Exceptions
    are captured into `lastError` — never raised into QML.

    State machine:
      INIT --refresh()--> LOADING
        -- all success --> READY
        -- first failure --> ERROR (fallback data)
      READY -- refresh failure --> STALE (OLD DATA PRESERVED, no "--" flicker)
      STALE -- refresh success --> READY
    """

    refreshed = Signal()

    def __init__(self, state: OverviewState, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._opportunity_loader = None
        self._market_loader = None
        self._health_loader = None
        self._validation_loader = None
        self._paper_loader = None

    # ---- backend wiring (host app only, NOT QML) ---------------------------

    def setOpportunityLoader(self, loader) -> None:  # noqa: N802
        self._opportunity_loader = loader

    def setMarketLoader(self, loader) -> None:  # noqa: N802
        self._market_loader = loader

    def setHealthLoader(self, loader) -> None:  # noqa: N802
        self._health_loader = loader

    def setValidationLoader(self, loader) -> None:  # noqa: N802
        self._validation_loader = loader

    def setPaperLoader(self, loader) -> None:  # noqa: N802
        self._paper_loader = loader

    # ---- refresh (QML-invokable) -------------------------------------------

    @Slot()
    def refresh(self) -> None:
        had_data = self._state.lifecycle in (LIFECYCLE_READY, LIFECYCLE_STALE)
        self._state.markLoading()

        errors: list[str] = []

        # opportunity
        if self._opportunity_loader is not None:
            data = self._safe(self._opportunity_loader, errors, "今日机会")
            if data is not None:
                self._state.setOpportunity(
                    str(data.get("value", "--")), data.get("hint"),
                    data.get("report_date", ""))
                self._state.setScanStatus("就绪", f"报告 {data.get('report_date', '--')}")

        # market
        if self._market_loader is not None:
            data = self._safe(self._market_loader, errors, "市场状态")
            if data is not None:
                self._state.setMarketStatus(str(data.get("value", "--")), data.get("detail"))

        # data health
        if self._health_loader is not None:
            data = self._safe(self._health_loader, errors, "数据健康")
            if data is not None:
                self._state.setDataHealth(
                    str(data.get("level", HEALTH_OK)),
                    str(data.get("text", "--")))

        # validation
        if self._validation_loader is not None:
            data = self._safe(self._validation_loader, errors, "信号验证")
            if data is not None:
                self._state.setValidation(str(data.get("value", "--")), data.get("hint"))

        # portfolio
        if self._paper_loader is not None:
            data = self._safe(self._paper_loader, errors, "模拟组合")
            if data is not None:
                self._state.setPortfolio(str(data.get("value", "1.0000")), data.get("hint"))

        if errors:
            if had_data:
                self._state.markStale("; ".join(errors))
            else:
                self._state.markError("; ".join(errors))
        else:
            self._state.markReady()

        self.refreshed.emit()

    @staticmethod
    def _safe(loader, errors: list[str], label: str):
        try:
            return loader()
        except Exception as exc:  # capture, never raise into QML
            errors.append(f"{label}: {exc}")
            return None
