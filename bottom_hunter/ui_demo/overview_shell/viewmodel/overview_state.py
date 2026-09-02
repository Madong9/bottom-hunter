"""PHASE 2-C — product-grade QObject ViewModel for the OverviewShell.

Architecture (DTO contract frozen; no business migration, no async system):

    Python / QtWidgets backend (read-only helpers)
            |
            v  (host app builds the DTO via loader adapters)
    OverviewDTO  (contracts/ — pure data, no business, no Qt)
            |
            v
    OverviewBridge (DTO -> state transitions + lifecycle)
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

from datetime import datetime

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..contracts import HEALTH_UNKNOWN

# Lifecycle states
LIFECYCLE_INIT = "INIT"
LIFECYCLE_LOADING = "LOADING"
LIFECYCLE_READY = "READY"
LIFECYCLE_STALE = "STALE"
LIFECYCLE_ERROR = "ERROR"
LIFECYCLES = (LIFECYCLE_INIT, LIFECYCLE_LOADING, LIFECYCLE_READY,
              LIFECYCLE_STALE, LIFECYCLE_ERROR)


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

    # ================= DTO contract (PHASE 2-C) =================

    def apply(self, dto) -> None:  # noqa: N802
        """Apply an OverviewDTO — one DTO == one atomic state update.

        Accepts an OverviewDTO instance OR a plain mapping with the same
        shape (tests/builders may construct dicts). Never imports business
        code; only maps the frozen contract onto display properties.
        """
        market = getattr(dto, "market", dto.get("market", {})) if hasattr(dto, "get") else dto.market
        scan = getattr(dto, "scan", dto.get("scan", {})) if hasattr(dto, "get") else dto.scan
        opportunity = (
            getattr(dto, "opportunity", dto.get("opportunity", {}))
            if hasattr(dto, "get")
            else dto.opportunity
        )
        health = getattr(dto, "health", dto.get("health", {})) if hasattr(dto, "get") else dto.health
        validation = getattr(dto, "validation", dto.get("validation", {})) if hasattr(dto, "get") else dto.validation
        portfolio = getattr(dto, "portfolio", dto.get("portfolio", {})) if hasattr(dto, "get") else dto.portfolio

        if isinstance(opportunity, dict):
            self.setOpportunity(
                str(opportunity.get("count", "--")),
                opportunity.get("hint"),
                opportunity.get("updated", ""))
        else:
            self.setOpportunity(str(opportunity.count), opportunity.hint, opportunity.updated)

        if isinstance(health, dict):
            self.setDataHealth(str(health.get("level", HEALTH_UNKNOWN)), str(health.get("text", "--")))
        else:
            self.setDataHealth(str(health.level), str(health.text))

        if isinstance(validation, dict):
            self.setValidation(str(validation.get("value", "--")), validation.get("hint"))
        else:
            self.setValidation(str(validation.value), validation.hint)

        if isinstance(portfolio, dict):
            self.setPortfolio(str(portfolio.get("value", "1.0000")), portfolio.get("hint"))
        else:
            self.setPortfolio(str(portfolio.value), portfolio.hint)

        if isinstance(market, dict):
            self.setMarketStatus(str(market.get("status", "--")), market.get("detail"))
        else:
            self.setMarketStatus(str(market.status), market.detail)

        if isinstance(scan, dict):
            self.setScanStatus(str(scan.get("status", "--")), scan.get("detail", "等待最新扫描"))
        else:
            self.setScanStatus(str(scan.status), scan.detail)


class OverviewBridge(QObject):
    """Adapter: Backend -> OverviewDTO -> OverviewState transitions.

    PHASE 2-C: the bridge now depends on a SINGLE DTO provider callable
    (``setDtorovider`` -> ``() -> OverviewDTO``) instead of per-field backend
    loaders. It holds no backend detail: the host app builds the DTO (via
    loader adapters) and the bridge only maps DTO -> state + lifecycle.

    State machine:
      INIT --refresh()--> LOADING
        -- success --> READY
        -- first failure --> ERROR (fallback data)
      READY -- refresh failure --> STALE (OLD DATA PRESERVED, no "--" flicker)
      STALE -- refresh success --> READY
    """

    refreshed = Signal()

    def __init__(self, state: OverviewState, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._dto_provider = None   # () -> OverviewDTO | dict | None

    # ---- data contract wiring (host app only, NOT QML) ---------------------

    def setDtoProvider(self, provider) -> None:  # noqa: N802
        """Provider: callable returning an OverviewDTO (or dict) or None."""
        self._dto_provider = provider

    # ---- refresh (QML-invokable) -------------------------------------------

    @Slot()
    def refresh(self) -> None:
        had_data = self._state.lifecycle in (LIFECYCLE_READY, LIFECYCLE_STALE)
        self._state.markLoading()

        if self._dto_provider is None:
            self._state.markError("no DTO provider wired")
            self.refreshed.emit()
            return

        error = ""
        try:
            dto = self._dto_provider()
        except Exception as exc:  # capture, never raise into QML
            dto = None
            error = str(exc)

        if dto is None:
            if had_data:
                self._state.markStale(error or "backend returned no data")
            else:
                self._state.markError(error or "backend returned no data")
        else:
            self._state.apply(dto)
            self._state.markReady()

        self.refreshed.emit()


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
