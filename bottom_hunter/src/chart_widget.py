from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from matplotlib import rcParams
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from PySide6.QtCore import QObject, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .charting import (
    ChartAnnotationStore,
    ChartResult,
    MarketChartService,
    TIMEFRAME_LABELS,
    calculate_chart_indicators,
)


rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans CJK JP", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False

OVERLAY_INDICATORS = (
    ("MA 均线", "ma"),
    ("EMA 指数均线", "ema"),
    ("BOLL 布林带", "boll"),
    ("关闭主图指标", "none"),
)
PANEL_INDICATORS = (
    ("MACD", "macd"),
    ("RSI(14)", "rsi"),
    ("KDJ(9,3,3)", "kdj"),
    ("ATR(14)", "atr"),
    ("关闭副图指标", "none"),
)
BINANCE_LIVE_INTERVALS = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "60m": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
    "1M": "1M",
}
OKX_LIVE_CHANNELS = {
    "1m": "candle1m",
    "5m": "candle5m",
    "15m": "candle15m",
    "30m": "candle30m",
    "60m": "candle1H",
    "4h": "candle4H",
    "1d": "candle1Dutc",
    "1w": "candle1Wutc",
    "1M": "candle1Mutc",
}


def parse_live_candle(provider: str, message: str) -> dict[str, Any] | None:
    """Parse one official Binance/OKX WebSocket candlestick message."""

    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return None
    if provider == "binance":
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            payload = payload["data"]
        candle = payload.get("k") if isinstance(payload, dict) else None
        if not isinstance(candle, dict):
            return None
        values = {
            "timestamp": candle.get("t"),
            "open": candle.get("o"),
            "high": candle.get("h"),
            "low": candle.get("l"),
            "close": candle.get("c"),
            "volume": candle.get("v"),
            "closed": bool(candle.get("x")),
        }
    elif provider == "okx":
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
            return None
        row = rows[0]
        if len(row) < 6:
            return None
        values = {
            "timestamp": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
            "closed": len(row) > 8 and str(row[8]) == "1",
        }
    else:
        return None
    try:
        timestamp = pd.to_datetime(int(values["timestamp"]), unit="ms", utc=True).tz_localize(
            None
        )
        numbers = {
            key: float(values[key]) for key in ("open", "high", "low", "close", "volume")
        }
    except (TypeError, ValueError, OverflowError):
        return None
    if min(numbers["open"], numbers["high"], numbers["low"], numbers["close"]) <= 0:
        return None
    if numbers["high"] < numbers["low"] or numbers["volume"] < 0:
        return None
    return {"date": timestamp, **numbers, "closed": values["closed"]}


def merge_live_candle(result: ChartResult, candle: Mapping[str, Any], limit: int) -> ChartResult:
    """Replace or append the current candle while retaining the requested history window."""

    bars = result.bars.copy()
    timestamp = pd.Timestamp(candle["date"])
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)
    bars.loc[timestamp, ["open", "high", "low", "close", "volume"]] = [
        candle[column] for column in ("open", "high", "low", "close", "volume")
    ]
    bars = bars.sort_index().loc[lambda frame: ~frame.index.duplicated(keep="last")].tail(limit)
    provider = "币安 WebSocket" if result.provider.startswith("币安") else "欧易 WebSocket"
    cadence = "约 2 秒" if provider.startswith("币安") else "最快 1 秒"
    return ChartResult(
        canonical_id=result.canonical_id,
        symbol=result.symbol,
        name=result.name,
        timeframe=result.timeframe,
        bars=bars,
        provider=provider,
        updated_at=datetime.now(timezone.utc),
        note=f"交易所实时推送 · 当前未收盘 K 线{cadence}更新",
    )


class ChartDataWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    finished = Signal()

    def __init__(
        self,
        service: MarketChartService,
        asset: Mapping[str, Any],
        timeframe: str,
        limit: int,
    ) -> None:
        super().__init__()
        self.service = service
        self.asset = dict(asset)
        self.timeframe = timeframe
        self.limit = limit

    @Slot()
    def run(self) -> None:
        canonical_id = str(self.asset.get("canonical_id") or self.asset.get("symbol") or "")
        try:
            result = self.service.fetch(self.asset, self.timeframe, self.limit)
        except Exception as exc:
            self.failed.emit(canonical_id, self.timeframe, str(exc))
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


class ChartWorkspace(QWidget):
    MIN_VISIBLE_CANDLES = 12

    def __init__(
        self,
        annotation_path: str | Path,
        *,
        service: MarketChartService | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("ContentPage")
        self.service = service or MarketChartService()
        self.annotation_store = ChartAnnotationStore(annotation_path)
        self.assets: list[dict[str, Any]] = []
        self.current_result: ChartResult | None = None
        self.annotations: list[dict[str, Any]] = []
        self._thread: QThread | None = None
        self._worker: ChartDataWorker | None = None
        self._pending_request: tuple[dict[str, Any], str, int] | None = None
        self._draw_mode = ""
        self._draft_point: tuple[str, float] | None = None
        self.price_axis = None
        self.volume_axis = None
        self.indicator_axis = None
        self._indicator_values = pd.DataFrame()
        self._active_overlay_columns: tuple[str, ...] = ()
        self._crosshair_vertical = None
        self._crosshair_horizontal = None
        self._view_xlim: tuple[float, float] | None = None
        self._live_provider = ""
        self._live_expected: tuple[str, str] | None = None
        self._live_subscription: dict[str, str] = {}
        self._live_retry_count = 0
        self._live_failed_provider = ""
        self._live_socket = QWebSocket()
        self._live_socket.connected.connect(self._live_connected)
        self._live_socket.disconnected.connect(self._live_disconnected)
        self._live_socket.textMessageReceived.connect(self._live_message_received)
        self._live_socket.errorOccurred.connect(self._live_socket_error)
        self._live_reconnect_timer = QTimer(self)
        self._live_reconnect_timer.setSingleShot(True)
        self._live_reconnect_timer.timeout.connect(self._configure_live_stream)
        self._live_ping_timer = QTimer(self)
        self._live_ping_timer.setInterval(20_000)
        self._live_ping_timer.timeout.connect(self._send_live_ping)

        self._build_ui()
        self.canvas.mpl_connect("button_press_event", self._chart_clicked)
        self.canvas.mpl_connect("motion_notify_event", self._chart_hovered)
        self.canvas.mpl_connect("scroll_event", self._chart_scrolled)
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(30_000)
        self.auto_refresh_timer.timeout.connect(self.refresh_chart)
        self.auto_refresh_timer.start()
        self._render_empty("请从左侧或自选列表选择一个标的")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("实时 K 线与画线分析")
        title.setProperty("role", "pageTitle")
        self.subtitle = QLabel("加密货币支持 WebSocket 实时 K 线；股票按行情权限刷新")
        self.subtitle.setProperty("role", "pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.loading = QProgressBar()
        self.loading.setRange(0, 0)
        self.loading.setFixedWidth(110)
        self.loading.setVisible(False)
        header.addWidget(self.loading)
        layout.addLayout(header)

        controls = QFrame()
        controls.setObjectName("InnerPanel")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(12, 9, 12, 9)
        controls_layout.setSpacing(7)
        self.asset_combo = QComboBox()
        self.asset_combo.setMinimumWidth(235)
        self.asset_combo.setMaxVisibleItems(18)
        self.asset_combo.currentIndexChanged.connect(self._selection_changed)
        self.timeframe_combo = QComboBox()
        for value, label in TIMEFRAME_LABELS.items():
            self.timeframe_combo.addItem(label, value)
        self.timeframe_combo.setCurrentIndex(list(TIMEFRAME_LABELS).index("1d"))
        self.timeframe_combo.currentIndexChanged.connect(self._timeframe_changed)
        self.limit_combo = QComboBox()
        for value in (80, 120, 250, 300):
            self.limit_combo.addItem(f"{value} 根", value)
        self.limit_combo.setCurrentIndex(2)
        self.limit_combo.currentIndexChanged.connect(self._limit_changed)
        self.auto_refresh = QCheckBox("自动刷新")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.toggled.connect(self._auto_refresh_toggled)
        self.live_badge = QLabel("● 等待行情")
        self.live_badge.setProperty("chip", True)
        self.live_badge.setProperty("tone", "warning")
        self.refresh_button = QPushButton("刷新行情")
        self.refresh_button.setProperty("kind", "primary")
        self.refresh_button.clicked.connect(self.refresh_chart)
        controls_layout.addWidget(QLabel("标的"))
        controls_layout.addWidget(self.asset_combo, 1)
        controls_layout.addWidget(QLabel("周期"))
        controls_layout.addWidget(self.timeframe_combo)
        controls_layout.addWidget(QLabel("显示"))
        controls_layout.addWidget(self.limit_combo)
        controls_layout.addWidget(self.live_badge)
        controls_layout.addWidget(self.auto_refresh)
        controls_layout.addWidget(self.refresh_button)
        layout.addWidget(controls)

        indicators = QFrame()
        indicators.setObjectName("InnerPanel")
        indicator_layout = QHBoxLayout(indicators)
        indicator_layout.setContentsMargins(12, 7, 12, 7)
        indicator_layout.setSpacing(7)
        self.overlay_combo = QComboBox()
        for label, value in OVERLAY_INDICATORS:
            self.overlay_combo.addItem(label, value)
        self.overlay_combo.setToolTip("叠加在价格 K 线上的趋势指标")
        self.overlay_combo.currentIndexChanged.connect(self._indicator_changed)
        self.panel_combo = QComboBox()
        for label, value in PANEL_INDICATORS:
            self.panel_combo.addItem(label, value)
        self.panel_combo.setToolTip("显示在成交量下方的独立技术指标")
        self.panel_combo.currentIndexChanged.connect(self._indicator_changed)
        indicator_hint = QLabel("指标按当前 K 线周期计算，切换时不重新请求行情")
        indicator_hint.setProperty("role", "muted")
        indicator_layout.addWidget(QLabel("主图指标"))
        indicator_layout.addWidget(self.overlay_combo)
        indicator_layout.addSpacing(8)
        indicator_layout.addWidget(QLabel("副图指标"))
        indicator_layout.addWidget(self.panel_combo)
        indicator_layout.addWidget(indicator_hint, 1)
        layout.addWidget(indicators)

        drawing = QFrame()
        drawing.setObjectName("InnerPanel")
        drawing_layout = QHBoxLayout(drawing)
        drawing_layout.setContentsMargins(12, 7, 12, 7)
        drawing_layout.setSpacing(7)
        self.trend_button = QPushButton("趋势线")
        self.trend_button.clicked.connect(lambda: self._set_draw_mode("trend"))
        self.horizontal_button = QPushButton("水平线")
        self.horizontal_button.clicked.connect(lambda: self._set_draw_mode("horizontal"))
        undo_button = QPushButton("撤销")
        undo_button.clicked.connect(self.undo_annotation)
        clear_button = QPushButton("清空画线")
        clear_button.setProperty("kind", "danger")
        clear_button.clicked.connect(self.clear_annotations)
        self.draw_hint = QLabel("Ctrl + 鼠标滚轮调整可见K线数量；画线会自动保存")
        self.draw_hint.setProperty("role", "muted")
        drawing_layout.addWidget(self.trend_button)
        drawing_layout.addWidget(self.horizontal_button)
        drawing_layout.addWidget(undo_button)
        drawing_layout.addWidget(clear_button)
        drawing_layout.addWidget(self.draw_hint, 1)
        layout.addWidget(drawing)

        chart_frame = QFrame()
        chart_frame.setObjectName("Card")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(7, 7, 7, 7)
        chart_layout.setSpacing(2)
        self.figure = Figure(figsize=(11, 7), dpi=100, facecolor="#ffffff")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(470)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setIconSize(self.toolbar.iconSize() * 0.85)
        chart_layout.addWidget(self.toolbar)
        chart_layout.addWidget(self.canvas, 1)
        layout.addWidget(chart_frame, 1)

        footer = QHBoxLayout()
        self.ohlc_label = QLabel("O --  H --  L --  C --")
        self.ohlc_label.setProperty("role", "muted")
        self.status_label = QLabel("尚未加载行情")
        self.status_label.setProperty("role", "muted")
        footer.addWidget(self.ohlc_label)
        footer.addStretch(1)
        footer.addWidget(self.status_label)
        layout.addLayout(footer)

    @property
    def is_loading(self) -> bool:
        return self._thread is not None

    def set_assets(self, assets: list[Mapping[str, Any]]) -> None:
        normalized = [dict(item) for item in assets]
        signature = [str(item.get("canonical_id")) for item in normalized]
        if signature == [str(item.get("canonical_id")) for item in self.assets]:
            self.assets = normalized
            return
        selected_id = self.current_asset_id()
        self.assets = normalized
        self.asset_combo.blockSignals(True)
        self.asset_combo.clear()
        for asset in self.assets:
            name = str(asset.get("name") or asset.get("symbol") or "--")
            symbol = str(asset.get("symbol") or "--")
            market = str(asset.get("market") or "--")
            self.asset_combo.addItem(f"{name} · {symbol} · {market}", asset)
        selected_index = next(
            (
                index
                for index, asset in enumerate(self.assets)
                if str(asset.get("canonical_id")) == selected_id
            ),
            0,
        )
        if self.assets:
            self.asset_combo.setCurrentIndex(selected_index)
        self.asset_combo.blockSignals(False)

    def current_asset(self) -> dict[str, Any] | None:
        value = self.asset_combo.currentData(Qt.ItemDataRole.UserRole)
        return dict(value) if isinstance(value, dict) else None

    def current_asset_id(self) -> str:
        asset = self.current_asset()
        return str((asset or {}).get("canonical_id") or "")

    def select_asset(self, asset: Mapping[str, Any]) -> None:
        canonical_id = str(asset.get("canonical_id") or "")
        index = next(
            (
                row
                for row in range(self.asset_combo.count())
                if str((self.asset_combo.itemData(row) or {}).get("canonical_id") or "")
                == canonical_id
            ),
            -1,
        )
        if index >= 0:
            changed = index != self.asset_combo.currentIndex()
            self.asset_combo.setCurrentIndex(index)
            if not changed:
                self.refresh_chart()

    def ensure_loaded(self) -> None:
        if self.current_result is None and self.asset_combo.count():
            self.refresh_chart()

    def _selection_changed(self, _index: int) -> None:
        self._stop_live_stream()
        self._live_retry_count = 0
        self._live_failed_provider = ""
        self.current_result = None
        self._view_xlim = None
        self.refresh_chart()

    def _timeframe_changed(self, _index: int) -> None:
        self._stop_live_stream()
        self._live_retry_count = 0
        self._live_failed_provider = ""
        self.current_result = None
        self._view_xlim = None
        self._draw_mode = ""
        self._draft_point = None
        self.refresh_chart()

    def _limit_changed(self, _index: int) -> None:
        self._view_xlim = None
        self.refresh_chart()

    def _indicator_changed(self, _index: int) -> None:
        if self.current_result is not None:
            self._render_chart()

    def _set_live_badge(self, text: str, tone: str) -> None:
        self.live_badge.setText(text)
        self.live_badge.setProperty("tone", tone)
        self.live_badge.style().unpolish(self.live_badge)
        self.live_badge.style().polish(self.live_badge)

    def _auto_refresh_toggled(self, checked: bool) -> None:
        if checked:
            self._live_retry_count = 0
            self._live_failed_provider = ""
            self._configure_live_stream()
            self.refresh_chart()
        else:
            self._stop_live_stream()
            self._set_live_badge("● 自动刷新已关闭", "warning")

    def _stop_live_stream(self, *, reset_badge: bool = True) -> None:
        self._live_expected = None
        self._live_provider = ""
        self._live_subscription = {}
        self._live_reconnect_timer.stop()
        self._live_ping_timer.stop()
        self._live_socket.abort()
        if reset_badge and hasattr(self, "live_badge"):
            self._set_live_badge("● 等待行情", "warning")

    def _configure_live_stream(self) -> None:
        self._stop_live_stream(reset_badge=False)
        asset = self.current_asset()
        result = self.current_result
        if not self.auto_refresh.isChecked():
            self._set_live_badge("● 自动刷新已关闭", "warning")
            return
        if not asset or result is None:
            self._set_live_badge("● 等待行情", "warning")
            return
        is_crypto = str(asset.get("category") or "") == "crypto" or str(
            asset.get("market") or ""
        ) == "CRYPTO"
        if not is_crypto:
            if result.provider.startswith("长桥"):
                self.auto_refresh_timer.setInterval(5_000)
                self._set_live_badge("● 长桥 5 秒刷新", "idle")
                self.subtitle.setText(f"{result.note} · 当前 K 线每 5 秒刷新")
            else:
                self.auto_refresh_timer.setInterval(15_000)
                self._set_live_badge("● 公共行情 15 秒刷新", "warning")
                self.subtitle.setText(f"{result.note} · 公共股票行情可能延迟")
            return

        timeframe = result.timeframe
        source_symbols = dict(asset.get("source_symbols") or {})
        if result.provider.startswith("币安") and source_symbols.get("binance"):
            symbol = re.sub(r"[^A-Z0-9]", "", str(source_symbols["binance"]).upper())
            interval = BINANCE_LIVE_INTERVALS[timeframe]
            url = f"wss://data-stream.binance.vision/ws/{symbol.lower()}@kline_{interval}"
            self._live_provider = "binance"
        elif result.provider.startswith("欧易"):
            symbol = str(source_symbols.get("okx") or asset.get("symbol") or "").upper()
            symbol = symbol.replace("/", "-").replace("_", "-")
            if "-" not in symbol:
                for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
                    if symbol.endswith(quote) and len(symbol) > len(quote):
                        symbol = symbol[: -len(quote)] + "-" + quote
                        break
            channel = OKX_LIVE_CHANNELS[timeframe]
            url = "wss://ws.okx.com:8443/ws/v5/business"
            self._live_provider = "okx"
            self._live_subscription = {"channel": channel, "instId": symbol}
        else:
            self.auto_refresh_timer.setInterval(10_000)
            self._set_live_badge("● 加密行情 10 秒刷新", "warning")
            return
        if (
            self._live_failed_provider == self._live_provider
            and self._live_retry_count >= 3
        ):
            self.auto_refresh_timer.setInterval(5_000)
            self._set_live_badge("● 实时不可用 · 5 秒刷新", "warning")
            self.subtitle.setText(f"{result.note} · WebSocket 不可用，已自动改为 5 秒刷新")
            return
        self.auto_refresh_timer.setInterval(60_000)
        self._live_expected = (result.canonical_id, timeframe)
        self._set_live_badge("● 实时连接中…", "warning")
        self._live_socket.open(QUrl(url))

    @Slot()
    def _live_connected(self) -> None:
        if self._live_expected is None:
            self._live_socket.abort()
            return
        if self._live_provider == "okx":
            request = {
                "id": "bottom-hunter-live",
                "op": "subscribe",
                "args": [self._live_subscription],
            }
            self._live_socket.sendTextMessage(json.dumps(request, separators=(",", ":")))
            self._live_ping_timer.start()
        label = "币安" if self._live_provider == "binance" else "欧易"
        self._set_live_badge(f"● {label}实时", "idle")

    @Slot(str)
    def _live_message_received(self, message: str) -> None:
        if message == "pong" or self._live_expected is None or self.current_result is None:
            return
        expected = (self.current_asset_id(), str(self.timeframe_combo.currentData() or ""))
        if expected != self._live_expected:
            return
        candle = parse_live_candle(self._live_provider, message)
        if candle is None:
            return
        self._live_retry_count = 0
        self._live_failed_provider = ""
        limit = int(self.limit_combo.currentData() or 250)
        self.current_result = merge_live_candle(self.current_result, candle, limit)
        self._render_chart()
        local_time = self.current_result.updated_at.astimezone().strftime("%H:%M:%S")
        state = "已收盘" if candle.get("closed") else "更新中"
        self.status_label.setText(
            f"{self.current_result.provider} · {state} · 实时更新于 {local_time}"
        )
        self.subtitle.setText(self.current_result.note)

    @Slot()
    def _live_disconnected(self) -> None:
        self._live_ping_timer.stop()
        if self._live_expected is not None and self.auto_refresh.isChecked():
            self._live_failed_provider = self._live_provider
            self._live_retry_count += 1
            if self._live_retry_count >= 3:
                self._live_expected = None
                self.auto_refresh_timer.setInterval(5_000)
                self._set_live_badge("● 实时不可用 · 5 秒刷新", "warning")
                self.subtitle.setText("WebSocket 连续连接失败，已自动改为 5 秒刷新")
                return
            self._set_live_badge("● 实时重连中…", "warning")
            self._live_reconnect_timer.start(3_000)

    @Slot(object)
    def _live_socket_error(self, _error: object) -> None:
        if self._live_expected is not None:
            self._set_live_badge("● 实时连接异常", "warning")

    @Slot()
    def _send_live_ping(self) -> None:
        if self._live_provider == "okx" and self._live_expected is not None:
            self._live_socket.sendTextMessage("ping")

    @Slot()
    def refresh_chart(self) -> None:
        if self.sender() is self.auto_refresh_timer:
            if not self.auto_refresh.isChecked() or not self.isVisible():
                return
        asset = self.current_asset()
        if not asset:
            return
        timeframe = str(self.timeframe_combo.currentData() or "1d")
        limit = int(self.limit_combo.currentData() or 250)
        request = (asset, timeframe, limit)
        if self._thread is not None:
            self._pending_request = request
            self.status_label.setText("已有行情请求进行中，将在完成后刷新…")
            return
        self._start_request(*request)

    def _start_request(self, asset: dict[str, Any], timeframe: str, limit: int) -> None:
        thread = QThread(self)
        worker = ChartDataWorker(self.service, asset, timeframe, limit)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._data_loaded)
        worker.failed.connect(self._data_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._request_finished)
        self._thread = thread
        self._worker = worker
        self.refresh_button.setEnabled(False)
        self.loading.setVisible(True)
        self.status_label.setText("正在后台加载行情…")
        thread.start()

    @Slot(object)
    def _data_loaded(self, result: ChartResult) -> None:
        current = self.current_asset()
        timeframe = str(self.timeframe_combo.currentData() or "")
        if (
            not current
            or result.canonical_id != str(current.get("canonical_id") or "")
            or result.timeframe != timeframe
        ):
            return
        self.current_result = result
        self.annotations = self.annotation_store.get(result.canonical_id, result.timeframe)
        self._render_chart()
        local_time = result.updated_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.status_label.setText(f"{result.provider} · 更新于 {local_time}")
        self.subtitle.setText(result.note or "公共行情仅供研究；可能存在延迟")
        self._configure_live_stream()

    @Slot(str, str, str)
    def _data_failed(self, canonical_id: str, timeframe: str, error: str) -> None:
        if canonical_id == self.current_asset_id() and timeframe == str(
            self.timeframe_combo.currentData() or ""
        ):
            self.status_label.setText(f"行情加载失败：{error}")
            if self.current_result is None:
                self._render_empty("行情加载失败\n" + error)

    @Slot()
    def _request_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.refresh_button.setEnabled(True)
        self.loading.setVisible(False)
        pending = self._pending_request
        self._pending_request = None
        if pending is not None:
            QTimer.singleShot(0, lambda request=pending: self._start_request(*request))

    def _render_empty(self, message: str) -> None:
        self.figure.clear()
        axis = self.figure.add_subplot(111)
        axis.set_facecolor("#ffffff")
        axis.axis("off")
        axis.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            color="#8b929b",
            fontsize=13,
            transform=axis.transAxes,
        )
        self.price_axis = None
        self.volume_axis = None
        self.indicator_axis = None
        self._indicator_values = pd.DataFrame()
        self._active_overlay_columns = ()
        self.canvas.draw_idle()

    def _render_chart(self) -> None:
        if self.current_result is None:
            return
        frame = self.current_result.bars
        self._indicator_values = calculate_chart_indicators(frame)
        panel = str(self.panel_combo.currentData() or "none")
        self.figure.clear()
        if panel == "none":
            grid = self.figure.add_gridspec(
                2, 1, height_ratios=(4.0, 1.0), hspace=0.03
            )
            price_axis = self.figure.add_subplot(grid[0, 0])
            volume_axis = self.figure.add_subplot(grid[1, 0], sharex=price_axis)
            indicator_axis = None
        else:
            grid = self.figure.add_gridspec(
                3, 1, height_ratios=(3.5, 1.0, 1.45), hspace=0.04
            )
            price_axis = self.figure.add_subplot(grid[0, 0])
            volume_axis = self.figure.add_subplot(grid[1, 0], sharex=price_axis)
            indicator_axis = self.figure.add_subplot(grid[2, 0], sharex=price_axis)
        self.price_axis = price_axis
        self.volume_axis = volume_axis
        self.indicator_axis = indicator_axis
        axes = [price_axis, volume_axis]
        if indicator_axis is not None:
            axes.append(indicator_axis)
        for axis in axes:
            axis.set_facecolor("#ffffff")
            axis.grid(True, color="#edf0f2", linewidth=0.7, alpha=0.9)
            axis.tick_params(colors="#6e757d", labelsize=8)
            axis.spines["top"].set_visible(False)
            axis.spines["left"].set_color("#dfe3e6")
            axis.spines["right"].set_color("#dfe3e6")
            axis.spines["bottom"].set_color("#dfe3e6")

        x_values = np.arange(len(frame), dtype=float)
        candle_width = 0.66
        up_color = "#e74c3c"
        down_color = "#12a182"
        neutral_color = "#7f8c8d"
        for position, (_timestamp, row) in enumerate(frame.iterrows()):
            open_price = float(row["open"])
            close_price = float(row["close"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            color = up_color if close_price > open_price else down_color
            if close_price == open_price:
                color = neutral_color
            price_axis.vlines(position, low_price, high_price, color=color, linewidth=0.85)
            lower = min(open_price, close_price)
            height = max(abs(close_price - open_price), max(high_price * 0.00025, 1e-8))
            price_axis.add_patch(
                Rectangle(
                    (position - candle_width / 2, lower),
                    candle_width,
                    height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.6,
                )
            )
            volume_axis.bar(
                position,
                float(row["volume"]),
                width=candle_width,
                color=color,
                alpha=0.68,
            )

        self._draw_price_indicator(price_axis, x_values)
        for column, color, label in (
            ("volume_ma5", "#f39c12", "VMA5"),
            ("volume_ma10", "#3498db", "VMA10"),
        ):
            values = self._indicator_values[column]
            if values.notna().any():
                volume_axis.plot(x_values, values, color=color, linewidth=0.8, label=label)
        if indicator_axis is not None:
            self._draw_panel_indicator(indicator_axis, x_values, panel)
        price_axis.set_title(
            f"{self.current_result.name}  {self.current_result.symbol}  ·  "
            f"{TIMEFRAME_LABELS[self.current_result.timeframe]}",
            loc="left",
            fontsize=12,
            color="#252a30",
            pad=8,
        )
        price_axis.yaxis.tick_right()
        volume_axis.yaxis.tick_right()
        price_axis.tick_params(labelbottom=False)
        if indicator_axis is not None:
            indicator_axis.yaxis.tick_right()
            volume_axis.tick_params(labelbottom=False)
        volume_axis.set_ylabel("VOL", fontsize=8, color="#8b929b")
        tick_count = min(9, len(frame))
        if tick_count:
            ticks = np.unique(np.linspace(0, len(frame) - 1, tick_count, dtype=int))
            intraday = self.current_result.timeframe not in {"1d", "1w", "1M"}
            labels = [
                frame.index[index].strftime("%m-%d\n%H:%M" if intraday else "%Y-%m-%d")
                for index in ticks
            ]
            bottom_axis = indicator_axis or volume_axis
            bottom_axis.set_xticks(ticks)
            bottom_axis.set_xticklabels(labels, fontsize=8)
        full_xlim = (-0.8, max(len(frame) - 0.2, 0.8))
        price_axis.set_xlim(*full_xlim)
        if self._view_xlim is not None:
            left, right = self._bounded_xlim(*self._view_xlim)
            self._view_xlim = (left, right)
            price_axis.set_xlim(left, right)
            self._autoscale_visible_y(left, right)
        self._draw_saved_annotations()
        price_limits = price_axis.get_ylim()
        self._crosshair_vertical = price_axis.axvline(
            0, color="#9aa2aa", linewidth=0.7, linestyle=":", visible=False
        )
        self._crosshair_horizontal = price_axis.axhline(
            0, color="#9aa2aa", linewidth=0.7, linestyle=":", visible=False
        )
        price_axis.set_ylim(price_limits)
        self.figure.subplots_adjust(left=0.035, right=0.965, top=0.94, bottom=0.09)
        self.canvas.draw_idle()

    def _draw_price_indicator(self, axis: Any, x_values: np.ndarray) -> None:
        overlay = str(self.overlay_combo.currentData() or "none")
        specifications: dict[str, tuple[tuple[str, str, str, str], ...]] = {
            "ma": (
                ("ma5", "MA5", "#f39c12", "-"),
                ("ma10", "MA10", "#3498db", "-"),
                ("ma20", "MA20", "#8e44ad", "-"),
                ("ma60", "MA60", "#7f8c8d", "-"),
            ),
            "ema": (
                ("ema12", "EMA12", "#f39c12", "-"),
                ("ema26", "EMA26", "#3498db", "-"),
            ),
            "boll": (
                ("boll_upper", "BOLL上轨", "#8e44ad", "--"),
                ("boll_mid", "BOLL中轨", "#f39c12", "-"),
                ("boll_lower", "BOLL下轨", "#8e44ad", "--"),
            ),
        }
        active: list[str] = []
        for column, label, color, line_style in specifications.get(overlay, ()):
            values = self._indicator_values[column]
            if not values.notna().any():
                continue
            axis.plot(
                x_values,
                values,
                color=color,
                linewidth=1.0,
                linestyle=line_style,
                label=label,
            )
            active.append(column)
        if overlay == "boll" and active:
            upper = self._indicator_values["boll_upper"].to_numpy(dtype=float)
            lower = self._indicator_values["boll_lower"].to_numpy(dtype=float)
            axis.fill_between(
                x_values,
                lower,
                upper,
                where=np.isfinite(lower) & np.isfinite(upper),
                color="#8e44ad",
                alpha=0.055,
            )
        self._active_overlay_columns = tuple(active)
        if active:
            axis.legend(loc="upper left", fontsize=8, frameon=False, ncol=4)

    def _draw_panel_indicator(
        self, axis: Any, x_values: np.ndarray, panel: str
    ) -> None:
        values = self._indicator_values
        if panel == "macd":
            histogram = values["macd_hist"].fillna(0)
            colors = np.where(histogram >= 0, "#e74c3c", "#12a182")
            axis.bar(x_values, histogram, width=0.62, color=colors, alpha=0.65)
            axis.plot(x_values, values["macd_dif"], color="#f39c12", linewidth=0.9, label="DIF")
            axis.plot(x_values, values["macd_dea"], color="#3498db", linewidth=0.9, label="DEA")
            axis.axhline(0, color="#b8bec5", linewidth=0.65)
            axis.set_ylabel("MACD", fontsize=8, color="#8b929b")
        elif panel == "rsi":
            axis.plot(x_values, values["rsi14"], color="#8e44ad", linewidth=1.0, label="RSI14")
            axis.axhline(70, color="#e74c3c", linewidth=0.7, linestyle="--")
            axis.axhline(30, color="#12a182", linewidth=0.7, linestyle="--")
            axis.set_ylim(0, 100)
            axis.set_ylabel("RSI", fontsize=8, color="#8b929b")
        elif panel == "kdj":
            for column, color, label in (
                ("kdj_k", "#f39c12", "K"),
                ("kdj_d", "#3498db", "D"),
                ("kdj_j", "#8e44ad", "J"),
            ):
                axis.plot(x_values, values[column], color=color, linewidth=0.9, label=label)
            axis.axhline(80, color="#e74c3c", linewidth=0.7, linestyle="--")
            axis.axhline(20, color="#12a182", linewidth=0.7, linestyle="--")
            axis.set_ylabel("KDJ", fontsize=8, color="#8b929b")
        elif panel == "atr":
            axis.plot(x_values, values["atr14"], color="#16a085", linewidth=1.0, label="ATR14")
            axis.set_ylabel("ATR", fontsize=8, color="#8b929b")
        axis.legend(loc="upper left", fontsize=7.5, frameon=False, ncol=3)

    def _bounded_xlim(self, left: float, right: float) -> tuple[float, float]:
        if self.current_result is None:
            return left, right
        count = len(self.current_result.bars)
        data_left = -0.8
        data_right = max(count - 0.2, 0.8)
        full_width = data_right - data_left
        width = min(max(right - left, float(self.MIN_VISIBLE_CANDLES)), full_width)
        if width >= full_width:
            return data_left, data_right
        left = max(data_left, min(left, data_right - width))
        return left, left + width

    def _autoscale_visible_y(self, left: float, right: float) -> None:
        if self.current_result is None or self.price_axis is None or self.volume_axis is None:
            return
        frame = self.current_result.bars
        start = max(0, int(np.floor(left)))
        stop = min(len(frame), int(np.ceil(right)) + 1)
        visible = frame.iloc[start:stop]
        if visible.empty:
            return
        visible_indicators = self._indicator_values.iloc[start:stop]
        price_values = [visible["low"], visible["high"]]
        price_values.extend(
            visible_indicators[column] for column in self._active_overlay_columns
        )
        combined_prices = pd.concat(price_values).dropna()
        low = float(combined_prices.min())
        high = float(combined_prices.max())
        padding = max((high - low) * 0.06, abs(high) * 0.002, 1e-8)
        self.price_axis.set_ylim(low - padding, high + padding)
        volume_values = pd.concat(
            [
                visible["volume"],
                visible_indicators["volume_ma5"],
                visible_indicators["volume_ma10"],
            ]
        ).dropna()
        volume_max = float(volume_values.max()) if not volume_values.empty else 0.0
        self.volume_axis.set_ylim(0, max(volume_max * 1.12, 1.0))
        self._autoscale_indicator_axis(visible_indicators)

    def _autoscale_indicator_axis(self, visible: pd.DataFrame) -> None:
        if self.indicator_axis is None:
            return
        panel = str(self.panel_combo.currentData() or "none")
        if panel == "rsi":
            self.indicator_axis.set_ylim(0, 100)
            return
        columns = {
            "macd": ("macd_dif", "macd_dea", "macd_hist"),
            "kdj": ("kdj_k", "kdj_d", "kdj_j"),
            "atr": ("atr14",),
        }.get(panel, ())
        if not columns:
            return
        values = pd.concat([visible[column] for column in columns]).dropna()
        if values.empty:
            return
        low, high = float(values.min()), float(values.max())
        if panel == "macd":
            bound = max(abs(low), abs(high), 1e-8) * 1.15
            self.indicator_axis.set_ylim(-bound, bound)
        elif panel == "kdj":
            padding = max((high - low) * 0.08, 2.0)
            self.indicator_axis.set_ylim(min(-10.0, low - padding), max(110.0, high + padding))
        else:
            self.indicator_axis.set_ylim(0, max(high * 1.15, 1e-8))

    def _chart_scrolled(self, event: Any) -> None:
        if (
            self.current_result is None
            or self.price_axis is None
            or event.inaxes
            not in {self.price_axis, self.volume_axis, self.indicator_axis}
        ):
            return
        key = str(getattr(event, "key", "") or "").casefold()
        modifiers = QApplication.keyboardModifiers()
        control_pressed = (
            "control" in key
            or "ctrl" in key
            or bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        )
        if not control_pressed:
            return
        left, right = self.price_axis.get_xlim()
        current_width = right - left
        count = len(self.current_result.bars)
        full_width = max(count - 0.2, 0.8) - (-0.8)
        step = float(getattr(event, "step", 0) or 0)
        zoom_in = step > 0 or str(getattr(event, "button", "")) == "up"
        target_width = current_width * (0.82 if zoom_in else 1.22)
        target_width = min(max(target_width, float(self.MIN_VISIBLE_CANDLES)), full_width)
        anchor = getattr(event, "xdata", None)
        anchor = float(anchor) if anchor is not None and np.isfinite(anchor) else (left + right) / 2
        ratio = min(1.0, max(0.0, (anchor - left) / max(current_width, 1e-8)))
        new_left = anchor - target_width * ratio
        new_left, new_right = self._bounded_xlim(new_left, new_left + target_width)
        self._view_xlim = (new_left, new_right)
        self.price_axis.set_xlim(new_left, new_right)
        self._autoscale_visible_y(new_left, new_right)
        visible_count = min(count, max(1, int(round(new_right - new_left))))
        if not self._draw_mode:
            self.draw_hint.setText(
                f"Ctrl + 滚轮：当前约显示 {visible_count} 根K线；滚轮向上放大"
            )
        gui_event = getattr(event, "guiEvent", None)
        if gui_event is not None and hasattr(gui_event, "accept"):
            gui_event.accept()
        self.canvas.draw_idle()

    def _draw_saved_annotations(self) -> None:
        if self.current_result is None or self.price_axis is None:
            return
        index = self.current_result.bars.index
        for annotation in self.annotations:
            kind = str(annotation.get("type") or "")
            if kind == "horizontal":
                try:
                    price = float(annotation["price"])
                except (KeyError, TypeError, ValueError):
                    continue
                self.price_axis.axhline(
                    price,
                    color="#f39c12",
                    linewidth=1.15,
                    linestyle="--",
                    alpha=0.9,
                )
            elif kind == "trend":
                points = annotation.get("points") or []
                if len(points) != 2:
                    continue
                try:
                    timestamps = [pd.Timestamp(point[0]) for point in points]
                    prices = [float(point[1]) for point in points]
                except (TypeError, ValueError, IndexError):
                    continue
                if any(timestamp < index[0] or timestamp > index[-1] for timestamp in timestamps):
                    continue
                positions = [int(index.get_indexer([timestamp], method="nearest")[0]) for timestamp in timestamps]
                self.price_axis.plot(
                    positions,
                    prices,
                    color="#f39c12",
                    linewidth=1.45,
                    marker="o",
                    markersize=3.5,
                    zorder=8,
                )

    def _set_draw_mode(self, mode: str) -> None:
        if self.current_result is None:
            QMessageBox.information(self, "没有行情", "请先加载一只股票的 K 线。")
            return
        self._draw_mode = mode
        self._draft_point = None
        if mode == "trend":
            self.draw_hint.setText("趋势线：请依次点击两个价格位置")
        else:
            self.draw_hint.setText("水平线：请点击一个价格位置")

    def _chart_clicked(self, event: Any) -> None:
        if (
            not self._draw_mode
            or self.current_result is None
            or self.price_axis is None
            or event.inaxes is not self.price_axis
            or event.xdata is None
            or event.ydata is None
        ):
            return
        position = max(0, min(len(self.current_result.bars) - 1, int(round(event.xdata))))
        timestamp = self.current_result.bars.index[position].isoformat()
        price = float(event.ydata)
        if self._draw_mode == "horizontal":
            self.annotations.append({"type": "horizontal", "price": price})
            self._save_annotations()
            self._draw_mode = ""
            self.draw_hint.setText(f"水平线已保存：{price:.4f}")
            self._render_chart()
            return
        if self._draft_point is None:
            self._draft_point = (timestamp, price)
            self.draw_hint.setText("已记录第一个点，请点击第二个点")
            return
        self.annotations.append(
            {
                "type": "trend",
                "points": [list(self._draft_point), [timestamp, price]],
            }
        )
        self._draft_point = None
        self._draw_mode = ""
        self._save_annotations()
        self.draw_hint.setText("趋势线已保存")
        self._render_chart()

    def _chart_hovered(self, event: Any) -> None:
        if (
            self.current_result is None
            or self.price_axis is None
            or event.inaxes is not self.price_axis
            or event.xdata is None
            or event.ydata is None
        ):
            return
        position = max(0, min(len(self.current_result.bars) - 1, int(round(event.xdata))))
        timestamp = self.current_result.bars.index[position]
        row = self.current_result.bars.iloc[position]
        indicator_text = self._hover_indicator_text(position)
        self.ohlc_label.setText(
            f"{timestamp:%Y-%m-%d %H:%M}   O {row['open']:.4f}   H {row['high']:.4f}   "
            f"L {row['low']:.4f}   C {row['close']:.4f}   V {row['volume']:.0f}"
            f"{indicator_text}"
        )
        if self._crosshair_vertical is not None and self._crosshair_horizontal is not None:
            self._crosshair_vertical.set_xdata([position, position])
            self._crosshair_horizontal.set_ydata([event.ydata, event.ydata])
            self._crosshair_vertical.set_visible(True)
            self._crosshair_horizontal.set_visible(True)
            self.canvas.draw_idle()

    def _hover_indicator_text(self, position: int) -> str:
        if self._indicator_values.empty or position >= len(self._indicator_values):
            return ""
        row = self._indicator_values.iloc[position]
        overlay = str(self.overlay_combo.currentData() or "none")
        panel = str(self.panel_combo.currentData() or "none")
        columns = {
            "ma": (("ma5", "MA5"), ("ma10", "MA10"), ("ma20", "MA20")),
            "ema": (("ema12", "EMA12"), ("ema26", "EMA26")),
            "boll": (
                ("boll_upper", "UP"),
                ("boll_mid", "MID"),
                ("boll_lower", "LOW"),
            ),
        }.get(overlay, ())
        panel_columns = {
            "macd": (("macd_dif", "DIF"), ("macd_dea", "DEA")),
            "rsi": (("rsi14", "RSI"),),
            "kdj": (("kdj_k", "K"), ("kdj_d", "D"), ("kdj_j", "J")),
            "atr": (("atr14", "ATR"),),
        }.get(panel, ())
        parts = [
            f"{label} {float(row[column]):.2f}"
            for column, label in (*columns, *panel_columns)
            if pd.notna(row[column])
        ]
        return "   |   " + "  ".join(parts) if parts else ""

    def _save_annotations(self) -> None:
        if self.current_result is None:
            return
        self.annotation_store.save(
            self.current_result.canonical_id,
            self.current_result.timeframe,
            self.annotations,
        )

    def undo_annotation(self) -> None:
        if not self.annotations:
            return
        self.annotations.pop()
        self._save_annotations()
        self._render_chart()
        self.draw_hint.setText("已撤销上一条画线")

    def clear_annotations(self) -> None:
        if not self.annotations or self.current_result is None:
            return
        answer = QMessageBox.question(
            self,
            "清空画线",
            "确定清空当前股票、当前周期的全部画线吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.annotations = []
        self._save_annotations()
        self._render_chart()
        self.draw_hint.setText("当前周期画线已清空")

    def shutdown(self) -> None:
        self._stop_live_stream(reset_badge=False)
        self.auto_refresh_timer.stop()
