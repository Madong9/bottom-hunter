from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .config import PROJECT_DIR
from .research import ResearchService, macro_regime, official_portal_url
from .research_models import FinancialFact, MacroObservation, ResearchItem, ResearchSnapshot


SENTIMENT_LABELS = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}
TIER_LABELS = {"official": "官方", "professional": "媒体", "community": "社区"}


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _number(value: float, unit: str) -> str:
    if unit in {"CNY", "USD"}:
        absolute = abs(value)
        if absolute >= 1_0000_0000:
            return f"{value / 1_0000_0000:,.2f} 亿 {unit}"
        if absolute >= 1_0000:
            return f"{value / 1_0000:,.2f} 万 {unit}"
    if unit == "%":
        return f"{value:,.2f}%"
    return f"{value:,.4g} {unit}".strip()


class ResearchRefreshWorker(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        service: ResearchService,
        mode: str,
        asset: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.mode = mode
        self.asset = dict(asset or {})

    @Slot()
    def run(self) -> None:
        try:
            if self.mode == "macro":
                result = self.service.refresh_macro()
            else:
                result = self.service.refresh_asset(self.asset)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(self.mode, result)
        finally:
            self.finished.emit()


class ResearchWorkspace(QWidget):
    """Interactive, non-blocking financial/news/macro research workspace."""

    def __init__(self, project_dir: str | Path = PROJECT_DIR, parent: QWidget | None = None):
        super().__init__(parent)
        self.service = ResearchService(project_dir)
        self.current_asset: dict[str, Any] | None = None
        self.mode = "asset"
        self.selection_initialized = False
        self.thread: QThread | None = None
        self.worker: ResearchRefreshWorker | None = None
        self._build_ui()
        self._show_empty()

    @property
    def is_loading(self) -> bool:
        return self.thread is not None

    def _build_ui(self) -> None:
        self.setObjectName("ContentPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(2)
        self.title = QLabel("研究中心")
        self.title.setProperty("role", "pageTitle")
        self.subtitle = QLabel("官方财报与公告、媒体新闻、社区观点和宏观环境")
        self.subtitle.setProperty("role", "pageSubtitle")
        heading.addWidget(self.title)
        heading.addWidget(self.subtitle)
        header.addLayout(heading)
        header.addStretch(1)
        self.status = QLabel("未选择")
        self.status.setProperty("chip", True)
        self.status.setProperty("tone", "idle")
        self.portal_button = QPushButton("官方披露")
        self.portal_button.setEnabled(False)
        self.portal_button.clicked.connect(self.open_official_portal)
        self.import_button = QPushButton("导入观点")
        self.import_button.clicked.connect(self.import_items)
        self.refresh_button = QPushButton("刷新研究数据")
        self.refresh_button.setProperty("kind", "primary")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.status)
        header.addWidget(self.portal_button)
        header.addWidget(self.import_button)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        notice = QLabel(
            "数据分层：官方披露可作为基本面证据；媒体用于事件背景；"
            "雪球等社区内容只作情绪参考，不直接改变评分。"
        )
        notice.setWordWrap(True)
        notice.setProperty("role", "muted")
        layout.addWidget(notice)

        self.tabs = QTabWidget()
        self.overview = QTextBrowser()
        self.overview.setOpenExternalLinks(True)
        self.tabs.addTab(self.overview, "综合研判")
        self.financial_table = _table(["报告期", "类型", "指标", "数值", "来源"])
        self.financial_table.cellDoubleClicked.connect(self._open_table_link)
        self.tabs.addTab(self.financial_table, "财务概览")
        self.filing_table = _table(["披露时间", "报告期", "标题", "来源"])
        self.filing_table.cellDoubleClicked.connect(self._open_table_link)
        self.tabs.addTab(self.filing_table, "财报公告")
        self.news_table = _table(["时间", "来源", "倾向", "标题"])
        self.news_table.cellDoubleClicked.connect(self._open_table_link)
        self.tabs.addTab(self.news_table, "新闻事件")
        self.opinion_table = _table(["时间", "类型", "来源/作者", "倾向", "标题"])
        self.opinion_table.cellDoubleClicked.connect(self._open_table_link)
        self.tabs.addTab(self.opinion_table, "媒体与社区观点")
        self.macro_table = _table(["维度", "指标", "数据日期", "最新值", "前值", "变化", "信号", "来源"])
        self.macro_table.cellDoubleClicked.connect(self._open_table_link)
        self.tabs.addTab(self.macro_table, "宏观经济")
        layout.addWidget(self.tabs, 1)

    @staticmethod
    def _set_status(widget: QLabel, text: str, tone: str) -> None:
        widget.setText(text)
        widget.setProperty("tone", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _show_empty(self) -> None:
        self.overview.setHtml(
            "<div style='text-align:center;color:#888;margin-top:140px'>"
            "<h2>从左侧选择自选股或“宏观经济”</h2>"
            "<p>首次选择会在后台加载，界面不会卡住。</p></div>"
        )

    def select_asset(self, asset: Mapping[str, Any]) -> None:
        self.selection_initialized = True
        self.mode = "asset"
        self.current_asset = dict(asset)
        name = str(asset.get("name") or asset.get("symbol") or "未命名")
        symbol = str(asset.get("symbol") or "")
        self.title.setText(f"{name} · {symbol}")
        self.subtitle.setText(
            f"{asset.get('market') or '--'} · {asset.get('industry') or '待分类'} · "
            "财报、公告、新闻与观点分层展示"
        )
        self.portal_button.setEnabled(bool(official_portal_url(asset)))
        snapshot = self.service.cached_asset(asset)
        self._render_asset(snapshot)
        status = self.service.store.refresh_status(f"asset:{symbol}")
        if status:
            refreshed = str(status.get("refreshed_at") or "")[:19].replace("T", " ")
            self._set_status(self.status, f"缓存 {refreshed}", "idle")
        if not status:
            self._set_status(self.status, "待加载", "warning")
        if self.service.refresh_due(f"asset:{symbol}"):
            self.refresh()

    def select_macro(self) -> None:
        self.selection_initialized = True
        self.mode = "macro"
        self.current_asset = None
        self.title.setText("宏观经济")
        self.subtitle.setText("增长、通胀、流动性和风险偏好的可解释环境信号")
        self.portal_button.setEnabled(False)
        observations, regime = self.service.cached_macro()
        self._render_macro(observations, regime, {})
        self.tabs.setCurrentWidget(self.macro_table)
        if self.service.refresh_due("macro"):
            self.refresh()

    def refresh(self) -> None:
        if self.thread:
            return
        if self.mode == "asset" and not self.current_asset:
            QMessageBox.information(self, "请选择标的", "请先从左侧选择一只自选股。")
            return
        self.refresh_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self._set_status(self.status, "加载中…", "running")
        self.thread = QThread(self)
        self.worker = ResearchRefreshWorker(self.service, self.mode, self.current_asset)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.succeeded.connect(self._refresh_succeeded)
        self.worker.failed.connect(self._refresh_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(str, object)
    def _refresh_succeeded(self, mode: str, result: object) -> None:
        if mode == "macro":
            observations, regime, errors = result
            self._render_macro(observations, regime, errors)
            count = len(observations)
            self._set_status(self.status, f"宏观 {count} 项", "warning" if errors else "idle")
        else:
            snapshot = result
            current_symbol = str((self.current_asset or {}).get("symbol") or "")
            if snapshot.symbol != current_symbol:
                return
            self._render_asset(snapshot)
            count = len(snapshot.financial_facts) + len(snapshot.filings) + len(snapshot.news) + len(snapshot.opinions)
            self._set_status(self.status, f"已更新 {count} 项", "warning" if snapshot.errors else "idle")

    @Slot(str)
    def _refresh_failed(self, error: str) -> None:
        self._set_status(self.status, "加载失败", "danger")
        QMessageBox.warning(self, "研究数据加载失败", error)

    @Slot()
    def _thread_finished(self) -> None:
        self.thread = None
        self.worker = None
        self.refresh_button.setEnabled(True)
        self.import_button.setEnabled(True)

    def _render_asset(self, snapshot: ResearchSnapshot) -> None:
        self._render_facts(snapshot.financial_facts)
        self._render_items(self.filing_table, snapshot.filings, "filing")
        self._render_items(self.news_table, snapshot.news, "news")
        self._render_items(self.opinion_table, snapshot.opinions, "opinion")
        analysis = self.service.analyse(snapshot)
        latest_period = max((item.period_end for item in snapshot.financial_facts), default=None)
        errors = "".join(
            f"<li>{html.escape(name)}：{html.escape(message)}</li>"
            for name, message in snapshot.errors.items()
        )
        bull = "".join(f"<li>{html.escape(item)}</li>" for item in analysis["latest_bullish"]) or "<li>暂无</li>"
        bear = "".join(f"<li>{html.escape(item)}</li>" for item in analysis["latest_bearish"]) or "<li>暂无</li>"
        self.overview.setHtml(
            "<style>body{font-family:'Noto Sans CJK SC';line-height:1.6;color:#272a2f}"
            ".card{background:#f7f9f8;border:1px solid #e3e8e5;border-radius:8px;padding:12px;margin:8px 0}"
            "h2{font-size:18px}h3{font-size:15px;color:#168447}</style>"
            f"<h2>{html.escape(snapshot.symbol)} 研究摘要</h2>"
            "<div class='card'>"
            f"最新财务报告期：<b>{latest_period or '暂无'}</b><br>"
            f"官方公告：{len(snapshot.filings)} 条　新闻：{len(snapshot.news)} 条　"
            f"观点：{len(snapshot.opinions)} 条</div>"
            f"<div class='card'>情绪样本：偏多 {analysis['bullish']} / 偏空 {analysis['bearish']} / "
            f"中性 {analysis['neutral']}；证据完整度 {analysis['confidence']:.0%}</div>"
            f"<h3>偏多线索</h3><ul>{bull}</ul><h3>偏空线索</h3><ul>{bear}</ul>"
            f"<p><b>提示：</b>{html.escape(analysis['warning'])}</p>"
            + (f"<h3>数据源异常</h3><ul>{errors}</ul>" if errors else "")
        )

    def _render_facts(self, facts: list[FinancialFact]) -> None:
        self.financial_table.setRowCount(len(facts))
        for row, item in enumerate(facts):
            values = (
                item.period_end.isoformat(), item.period_type or "--", item.metric,
                _number(item.value, item.unit), item.source,
            )
            self._fill_row(self.financial_table, row, values, item.source_url)
        self.financial_table.resizeColumnsToContents()
        self.financial_table.setColumnWidth(2, max(150, self.financial_table.columnWidth(2)))

    def _render_items(self, table: QTableWidget, items: list[ResearchItem], mode: str) -> None:
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            when = item.published_at.astimezone().strftime("%Y-%m-%d %H:%M")
            if mode == "filing":
                values = (when, item.report_date.isoformat() if item.report_date else "--", item.title, item.source)
            elif mode == "news":
                values = (when, item.source, SENTIMENT_LABELS.get(item.sentiment, item.sentiment), item.title)
            else:
                source_author = item.source + (f" · {item.author}" if item.author else "")
                values = (
                    when, TIER_LABELS.get(item.tier.value, item.tier.value), source_author,
                    SENTIMENT_LABELS.get(item.sentiment, item.sentiment), item.title,
                )
            self._fill_row(table, row, values, item.url, item.summary)
            if item.tier.value == "community":
                for column in range(table.columnCount()):
                    cell = table.item(row, column)
                    if cell:
                        cell.setForeground(QColor("#8b6c26"))
        table.resizeColumnsToContents()

    def _render_macro(
        self,
        observations: list[MacroObservation],
        regime: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> None:
        regime = regime or macro_regime(observations)
        errors = errors or {}
        self.macro_table.setRowCount(len(observations))
        signal_labels = {-2: "明显承压", -1: "偏承压", 0: "中性", 1: "偏支持", 2: "明显支持"}
        for row, item in enumerate(observations):
            change = "--" if item.change is None else f"{item.change:+,.4g}"
            values = (
                item.dimension, item.name, item.observation_date.isoformat(),
                _number(item.value, item.unit),
                "--" if item.previous is None else _number(item.previous, item.unit),
                change, signal_labels.get(item.signal, str(item.signal)), item.source,
            )
            self._fill_row(self.macro_table, row, values, item.source_url)
        self.macro_table.resizeColumnsToContents()
        label = {"risk-on": "风险偏好", "risk-off": "风险规避", "neutral": "中性"}.get(regime.get("label"), "中性")
        details = " / ".join(f"{key} {value:+.2f}" for key, value in regime.get("dimensions", {}).items())
        impact = regime.get("sector_impact") or {}
        benefiting = "、".join(impact.get("benefiting") or []) or "暂无明显倾向"
        pressured = "、".join(impact.get("pressured") or []) or "暂无明显倾向"
        self.tabs.setTabText(self.tabs.indexOf(self.macro_table), f"宏观经济 · {label}")
        if self.mode == "macro":
            self._set_status(self.status, f"{label} {float(regime.get('score', 0)):+.2f}", "warning" if errors else "idle")
            self.overview.setHtml(
                f"<h2>宏观环境：{html.escape(label)}</h2>"
                f"<p>{html.escape(details or '尚无可用数据')}</p>"
                f"<p><b>可能受益行业：</b>{html.escape(benefiting)}<br>"
                f"<b>可能承压行业：</b>{html.escape(pressured)}</p>"
                "<p>该信号由各指标最近两期的变化方向合成，不是买卖指令。"
                "回测时应使用当时已发布的 vintage 数据。</p>"
            )

    @staticmethod
    def _fill_row(
        table: QTableWidget,
        row: int,
        values: tuple[Any, ...],
        url: str = "",
        tooltip: str = "",
    ) -> None:
        for column, value in enumerate(values):
            cell = QTableWidgetItem(str(value))
            cell.setData(Qt.ItemDataRole.UserRole, url)
            if tooltip:
                cell.setToolTip(tooltip)
            table.setItem(row, column, cell)

    @Slot(int, int)
    def _open_table_link(self, row: int, _column: int) -> None:
        table = self.sender()
        if not isinstance(table, QTableWidget):
            return
        item = table.item(row, 0)
        url = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def open_official_portal(self) -> None:
        if not self.current_asset:
            return
        url = official_portal_url(self.current_asset)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def import_items(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "导入新闻或观点",
            str(Path.home()),
            "研究数据 (*.csv *.json);;所有文件 (*)",
        )
        if not path:
            return
        symbol = str((self.current_asset or {}).get("symbol") or "")
        try:
            count = self.service.import_items(path, symbol)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        if self.current_asset:
            self._render_asset(self.service.cached_asset(self.current_asset))
        QMessageBox.information(self, "导入完成", f"已写入 {count} 条新闻/观点。")

    def shutdown(self) -> bool:
        """Return whether the workspace can be closed without killing a worker."""
        return self.thread is None
