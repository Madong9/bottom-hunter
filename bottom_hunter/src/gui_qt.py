from __future__ import annotations

# Qt must be preloaded before the PySide imports below on some Linux/Conda setups.
# ruff: noqa: E402
import argparse
import ctypes
import os
import re
import shutil
import signal
import sys
import threading
from datetime import date
from pathlib import Path
from typing import Any


def _preload_linux_qt_dependencies() -> None:
    """Allow a Conda-owned xcb-cursor library to satisfy Qt's xcb plugin."""

    if not sys.platform.startswith("linux"):
        return
    prefixes = [Path(sys.prefix), Path(sys.base_prefix)]
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        prefixes.append(Path(conda_prefix))
    if Path(sys.base_prefix).parent.name == "envs":
        prefixes.append(Path(sys.base_prefix).parent.parent)
    candidates = [prefix / "lib" / "libxcb-cursor.so.0" for prefix in prefixes]
    candidates.extend(
        (
            Path("/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0"),
            Path("/lib/x86_64-linux-gnu/libxcb-cursor.so.0"),
        )
    )
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            ctypes.CDLL(str(candidate), mode=ctypes.RTLD_GLOBAL)
        except OSError:
            continue
        break


_preload_linux_qt_dependencies()

from PySide6.QtCore import (
    QDate,
    QObject,
    QProcess,
    QProcessEnvironment,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .account_connectors import AccountConnectionService, ConnectionResult
from .account_watchlist import (
    CATEGORY_LABELS,
    SOURCE_LABELS,
    UNKNOWN_INDUSTRY,
    AccountWatchlistRepository,
    ImportResult,
    search_equities,
)
from .chart_widget import ChartWorkspace
from .charting import MarketChartService
from .gui_core import (
    PACKAGE_DIR,
    CommandSpec,
    build_backtest_command,
    build_scan_command,
    health_check,
    latest_json_report,
    list_reports,
    load_report_summary,
    recent_scan_runs,
    save_editor_content,
)
from .longbridge_adapter import (
    DEFAULT_HTTP_URL,
    DEFAULT_QUOTE_WS_URL,
    LONG_BRIDGE_ENV_KEYS,
    LongbridgeClient,
)
from .research_widget import ResearchWorkspace
from .storage import StateStore

ACCOUNT_SOURCE_LABELS = {**SOURCE_LABELS, "longbridge": "长桥行情"}


APP_STYLE = r"""
* {
    font-family: "Noto Sans CJK SC", "Noto Sans CJK JP", sans-serif;
    color: #191919;
}
QMainWindow, QWidget#AppRoot, QWidget#ContentPage {
    background: #f5f6f7;
}
QFrame#NavRail {
    background: #2e2e2e;
    border: none;
}
QLabel#Avatar {
    background: #07c160;
    color: white;
    border-radius: 22px;
    font-size: 15px;
    font-weight: 700;
}
QToolButton[nav="true"] {
    background: transparent;
    color: #a9aaad;
    border: none;
    border-radius: 9px;
    font-family: "DejaVu Sans";
    font-size: 22px;
    padding: 0;
}
QToolButton[nav="true"]:hover {
    background: #383838;
    color: white;
}
QToolButton[nav="true"]:checked {
    background: #424242;
    color: #07c160;
}
QLabel#RailCaption {
    color: #77797d;
    font-size: 9px;
}
QFrame#SidePanel {
    background: #f7f7f7;
    border-right: 1px solid #e2e2e2;
}
QLabel[role="sideTitle"] {
    font-size: 18px;
    font-weight: 700;
    color: #171717;
}
QLabel[role="muted"] {
    color: #8a8f98;
    font-size: 9pt;
}
QLineEdit {
    min-height: 34px;
    padding: 0 10px;
    background: white;
    border: 1px solid #dfe2e6;
    border-radius: 7px;
    selection-background-color: #07c160;
}
QLineEdit:focus {
    border-color: #70ce96;
}
QLineEdit#SearchBox {
    min-height: 36px;
    padding: 0 13px;
    background: #ededed;
    border: 1px solid #ededed;
    border-radius: 7px;
    selection-background-color: #07c160;
}
QLineEdit#SearchBox:focus {
    background: white;
    border-color: #b9dfc8;
}
QListWidget#ContextList {
    background: transparent;
    border: none;
    outline: none;
    padding: 2px 0;
}
QListWidget#ContextList::item {
    border: none;
    border-radius: 7px;
    margin: 2px 0;
    padding: 9px 11px;
    color: #353535;
}
QListWidget#ContextList::item:hover {
    background: #ededed;
}
QListWidget#ContextList::item:selected {
    background: #dedede;
    color: #111111;
}
QLabel#SafetyNote {
    background: #edf8f1;
    color: #398557;
    border: 1px solid #d5ebdd;
    border-radius: 7px;
    padding: 9px;
    font-size: 8.5pt;
}
QLabel[role="pageTitle"] {
    color: #171717;
    font-size: 23px;
    font-weight: 700;
}
QLabel[role="pageSubtitle"] {
    color: #7b818a;
    font-size: 9pt;
}
QFrame[card="true"] {
    background: white;
    border: 1px solid #e6e8eb;
    border-radius: 10px;
}
QLabel[role="cardTitle"] {
    color: #292d32;
    font-size: 10pt;
    font-weight: 650;
}
QLabel[role="metricLabel"] {
    color: #8a9099;
    font-size: 9pt;
}
QLabel[role="metricValue"] {
    color: #181a1f;
    font-size: 20px;
    font-weight: 700;
}
QLabel[role="metricHint"] {
    color: #9ba0a8;
    font-size: 8.5pt;
}
QLabel[role="contextTitle"] {
    color: #24272b;
    font-size: 10pt;
    font-weight: 600;
}
QLabel[role="contextSubtitle"] {
    color: #92979e;
    font-size: 8.5pt;
}
QLabel[chip="true"] {
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 9pt;
    font-weight: 600;
}
QLabel[chip="true"][tone="idle"] {
    background: #edf8f1;
    color: #168447;
}
QLabel[chip="true"][tone="running"] {
    background: #e8f7ee;
    color: #07a851;
}
QLabel[chip="true"][tone="warning"] {
    background: #fff4df;
    color: #a66408;
}
QLabel[chip="true"][tone="danger"] {
    background: #ffebec;
    color: #c33a43;
}
QPushButton {
    min-height: 34px;
    padding: 0 16px;
    background: white;
    border: 1px solid #d9dce1;
    border-radius: 7px;
    font-weight: 550;
}
QPushButton:hover {
    background: #f5f6f7;
    border-color: #c7cbd1;
}
QPushButton:pressed {
    background: #eceeef;
}
QPushButton:disabled {
    color: #afb3ba;
    background: #f5f5f5;
    border-color: #e5e5e5;
}
QPushButton[kind="primary"] {
    color: white;
    background: #07c160;
    border-color: #07c160;
}
QPushButton[kind="primary"]:hover {
    background: #06ad56;
    border-color: #06ad56;
}
QPushButton[kind="primary"]:disabled {
    color: #afb3ba;
    background: #f1f2f3;
    border-color: #e1e3e6;
}
QPushButton[kind="danger"] {
    color: #c54149;
    background: #fff7f7;
    border-color: #f0d0d2;
}
QPushButton[kind="ghost"] {
    padding: 0 9px;
    color: #6e737b;
    border-color: transparent;
    background: transparent;
}
QDateEdit, QSpinBox {
    min-height: 34px;
    padding: 0 9px;
    background: white;
    border: 1px solid #dfe2e6;
    border-radius: 7px;
    selection-background-color: #07c160;
}
QDateEdit:focus, QSpinBox:focus {
    border-color: #70ce96;
}
QCheckBox {
    spacing: 7px;
    color: #5c626a;
}
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid #c8ccd1;
    border-radius: 4px;
    background: white;
}
QCheckBox::indicator:checked {
    background: #07c160;
    border-color: #07c160;
    image: none;
}
QFrame#InnerPanel {
    background: #fafafa;
    border: 1px solid #eceef0;
    border-radius: 8px;
}
QFrame#Divider {
    background: #e7e9ec;
    border: none;
}
QTabWidget::pane {
    background: white;
    border: 1px solid #e3e6e9;
    border-radius: 9px;
    top: -1px;
}
QTabBar::tab {
    min-width: 92px;
    min-height: 34px;
    padding: 3px 13px;
    margin-right: 3px;
    color: #666d75;
    background: #eceff1;
    border: 1px solid #e1e4e7;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:hover {
    color: #168447;
    background: #f4faf6;
}
QTabBar::tab:selected {
    color: #137d42;
    background: white;
    font-weight: 600;
    border-top: 2px solid #07c160;
}
QTableWidget {
    background: white;
    alternate-background-color: #fafbfb;
    border: none;
    gridline-color: transparent;
    selection-background-color: #e8f7ee;
    selection-color: #1c3b29;
    outline: none;
}
QTableWidget::item {
    padding: 7px 8px;
    border-bottom: 1px solid #f0f1f2;
}
QHeaderView::section {
    background: #f8f9fa;
    color: #747a83;
    border: none;
    border-bottom: 1px solid #e8eaed;
    padding: 8px;
    font-size: 9pt;
    font-weight: 600;
}
QPlainTextEdit, QTextBrowser {
    background: white;
    border: 1px solid #e3e6e9;
    border-radius: 8px;
    padding: 10px;
    selection-background-color: #89d7a8;
}
QPlainTextEdit#TaskLog {
    background: #242629;
    color: #d9dde3;
    border-color: #242629;
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 9pt;
}
QPlainTextEdit#ConfigEditor {
    font-family: "DejaVu Sans Mono", "Noto Sans Mono CJK SC", monospace;
    font-size: 10.5pt;
    line-height: 1.4;
}
QProgressBar {
    min-height: 4px;
    max-height: 4px;
    background: #e9ebed;
    border: none;
    border-radius: 2px;
    text-align: center;
}
QProgressBar::chunk {
    background: #07c160;
    border-radius: 2px;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #cfd2d6;
    min-height: 35px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}
QSplitter::handle {
    background: transparent;
    width: 8px;
}
QStatusBar {
    background: #ffffff;
    color: #727780;
    border-top: 1px solid #e8eaed;
    min-height: 25px;
}
QToolTip {
    background: #303030;
    color: white;
    border: none;
    padding: 6px;
}
"""


ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _app_version() -> str:
    try:
        import tomllib

        with open(PACKAGE_DIR / "pyproject.toml", "rb") as handle:
            data = tomllib.load(handle)
        return f"v{data['project']['version']}"
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return ""


def _font_family() -> str:
    families = set(QFontDatabase.families())
    for candidate in (
        "Noto Sans CJK SC",
        "Microsoft YaHei UI",
        "PingFang SC",
        "Noto Sans CJK JP",
    ):
        if candidate in families:
            return candidate
    return QApplication.font().family()


def _card(parent: QWidget | None = None) -> QFrame:
    frame = QFrame(parent)
    frame.setProperty("card", True)
    return frame


def _set_dynamic_property(widget: QWidget, name: str, value: str) -> None:
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(37)
    table.horizontalHeader().setStretchLastSection(True)
    table.setShowGrid(False)
    return table


class MetricCard(QFrame):
    def __init__(self, title: str, value: str, hint: str, accent: str) -> None:
        super().__init__()
        self.setProperty("card", True)
        self.setMinimumHeight(91)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 13, 15, 13)
        layout.setSpacing(11)

        marker = QFrame()
        marker.setFixedSize(4, 45)
        marker.setStyleSheet(f"background: {accent}; border-radius: 2px;")
        layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        title_label = QLabel(title)
        title_label.setProperty("role", "metricLabel")
        self.value_label = QLabel(value)
        self.value_label.setProperty("role", "metricValue")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hint_label = QLabel(hint)
        self.hint_label.setProperty("role", "metricHint")
        text_box.addWidget(title_label)
        text_box.addWidget(self.value_label)
        text_box.addWidget(self.hint_label)
        layout.addLayout(text_box, 1)

    def set_value(self, value: str, hint: str | None = None) -> None:
        self.value_label.setText(value)
        if hint is not None:
            self.hint_label.setText(hint)


class ContextRow(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("role", "contextTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setProperty("role", "contextSubtitle")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        subtitle_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)


class WatchlistImportWorker(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        repository: AccountWatchlistRepository,
        source: str,
        path: str,
        account_alias: str,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.source = source
        self.path = path
        self.account_alias = account_alias

    @Slot()
    def run(self) -> None:
        try:
            result = self.repository.import_file(
                self.source,
                self.path,
                self.account_alias,
                resolve_industries=True,
            )
        except Exception as exc:
            self.failed.emit(self.source, str(exc))
        else:
            self.succeeded.emit(self.source, result)
        finally:
            self.finished.emit()


class WatchlistSyncWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, repository: AccountWatchlistRepository, force: bool) -> None:
        super().__init__()
        self.repository = repository
        self.force = force

    @Slot()
    def run(self) -> None:
        try:
            result = self.repository.refresh_linked_files(force=self.force)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


class AccountConnectWorker(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        service: AccountConnectionService,
        source: str,
        parameters: dict[str, str],
    ) -> None:
        super().__init__()
        self.service = service
        self.source = source
        self.parameters = parameters

    @Slot()
    def run(self) -> None:
        try:
            method = getattr(self.service, f"connect_{self.source}")
            result = method(**self.parameters)
        except Exception as exc:
            self.failed.emit(self.source, str(exc))
        else:
            self.succeeded.emit(self.source, result)
        finally:
            self.finished.emit()


class BottomHunterWindow(QMainWindow):
    PAGE_META = (
        ("总览", "我的自选与今日机会"),
        ("自选", "跨平台去重与行业划分"),
        ("研究", "财报、新闻、观点与宏观"),
        ("报告", "日报与回测结果"),
        ("导入", "文件导入与手动维护"),
        ("状态", "运行环境与批次记录"),
        ("行情", "实时 K 线与画线分析"),
    )

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bottom Hunter · 每日板块超跌反弹狩猎系统")
        self.resize(1460, 900)
        self.setMinimumSize(1180, 820)

        self.process: QProcess | None = None
        self.task_name = ""
        self.current_page = 0
        self.current_report: Path | None = None
        self.current_config: Path | None = None
        self.config_dirty = False
        self.config_paths = (
            PACKAGE_DIR / "config" / "watchlist.yaml",
            PACKAGE_DIR / "config" / "thresholds.yaml",
            PACKAGE_DIR / "data" / "fundamentals.csv",
        )
        self.nav_buttons: list[QToolButton] = []
        self.watchlist_repo = AccountWatchlistRepository()
        self.account_service = AccountConnectionService()
        self.watchlist_filter: dict[str, str] = {}
        self.account_fields: dict[str, dict[str, QWidget]] = {}
        self.import_threads: dict[str, QThread] = {}
        self.import_workers: dict[str, WatchlistImportWorker] = {}
        self.sync_thread: QThread | None = None
        self.sync_worker: WatchlistSyncWorker | None = None
        self.account_connect_thread: QThread | None = None
        self.account_connect_worker: AccountConnectWorker | None = None
        self.account_connect_source = ""
        self.account_connection_errors: dict[str, str] = {}
        self.sync_quiet = False
        self.pending_task_after_sync: CommandSpec | None = None

        self._build_shell()
        # 后台预热长桥凭据缓存，避免首次启动任务时在 UI 线程触发 keyring I/O
        threading.Thread(
            target=self.account_service.vault.load, args=("longbridge",), daemon=True
        ).start()
        self.statusBar().showMessage("系统就绪 · 所有结果仅供观察和量化研究", 6000)
        QTimer.singleShot(80, self.refresh_all)

    # ---------- shell ----------
    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._build_nav_rail())
        shell.addWidget(self._build_side_panel())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_dashboard_page())
        self.pages.addWidget(self._build_watchlist_page())
        self.research_workspace = ResearchWorkspace(PACKAGE_DIR)
        self.pages.addWidget(self.research_workspace)
        self.pages.addWidget(self._build_reports_page())
        self.pages.addWidget(self._build_accounts_page())
        self.pages.addWidget(self._build_system_page())
        self.pages.addWidget(self._build_chart_page())
        shell.addWidget(self.pages, 1)
        self.setCentralWidget(root)

    def _build_nav_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("NavRail")
        rail.setFixedWidth(76)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(10, 20, 10, 15)
        layout.setSpacing(10)

        avatar = QLabel("BH")
        avatar.setObjectName("Avatar")
        avatar.setFixedSize(44, 44)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(13)

        definitions = (
            ("⌂", "总览"),
            ("☆", "我的自选"),
            ("◇", "研究中心"),
            ("▤", "报告"),
            ("＋", "自选导入"),
            ("◉", "系统状态"),
            ("⌁", "K线与画线"),
        )
        for index, (glyph, tooltip) in enumerate(definitions):
            button = QToolButton()
            button.setText(glyph)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedSize(56, 50)
            button.clicked.connect(lambda _checked=False, page=index: self.switch_page(page))
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True)

        layout.addStretch(1)
        pulse = QLabel("●")
        pulse.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pulse.setStyleSheet("color: #07c160; font-size: 11px;")
        pulse.setToolTip("系统可用")
        layout.addWidget(pulse)
        caption = QLabel(_app_version() or "Bottom Hunter")
        caption.setObjectName("RailCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption)
        return rail

    def _build_side_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel.setFixedWidth(278)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(17, 23, 17, 17)
        layout.setSpacing(10)

        self.side_title = QLabel("总览")
        self.side_title.setProperty("role", "sideTitle")
        self.side_subtitle = QLabel("我的自选与今日机会")
        self.side_subtitle.setProperty("role", "muted")
        layout.addWidget(self.side_title)
        layout.addWidget(self.side_subtitle)
        layout.addSpacing(5)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("搜索")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._filter_context_list)
        layout.addWidget(self.search_box)

        self.context_list = QListWidget()
        self.context_list.setObjectName("ContextList")
        self.context_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.context_list.itemClicked.connect(self._context_item_clicked)
        layout.addWidget(self.context_list, 1)

        safety = QLabel("●  研究模式\n不连接券商，不自动下单")
        safety.setObjectName("SafetyNote")
        layout.addWidget(safety)
        return panel

    def switch_page(self, index: int) -> None:
        self.current_page = index
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        title, subtitle = self.PAGE_META[index]
        self.side_title.setText(title)
        self.side_subtitle.setText(subtitle)
        self.search_box.clear()
        self._populate_context_list()
        if (
            index == 2
            and self.context_list.count()
            and not self.research_workspace.selection_initialized
        ):
            self.context_list.setCurrentRow(0)
            self._context_item_clicked(self.context_list.item(0))
        elif index == 3 and self.context_list.count() and self.current_report is None:
            self.context_list.setCurrentRow(0)
            self._context_item_clicked(self.context_list.item(0))
        elif index == 1:
            self.refresh_watchlist()
        elif index == 4:
            self.refresh_accounts()
        elif index == 5:
            self.refresh_system()
        elif index == 6:
            self.chart_workspace.ensure_loaded()

    def _page_header(self, title: str, subtitle: str) -> tuple[QWidget, QHBoxLayout]:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("role", "pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setProperty("role", "pageSubtitle")
        text.addWidget(title_label)
        text.addWidget(subtitle_label)
        layout.addLayout(text)
        layout.addStretch(1)
        return header, layout

    # ---------- dashboard ----------
    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 20, 25, 18)
        layout.setSpacing(12)

        header, header_layout = self._page_header("工作台", "捕捉超跌后的结构性反转，不追逐单一指标")
        self.task_chip = QLabel("就绪")
        self.task_chip.setProperty("chip", True)
        self.task_chip.setProperty("tone", "idle")
        header_layout.addWidget(self.task_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.metric_cards = {
            "total": MetricCard("我的自选", "0", "三个来源合并后", "#07c160"),
            "crypto": MetricCard("加密货币", "0", "不含链上股票", "#f3ba2f"),
            "global_equity": MetricCard("美港股", "0", "包含链上股票", "#2d8cf0"),
            "cn_equity": MetricCard("A股", "0", "来自同花顺自选", "#ea5455"),
            "overlap": MetricCard("跨平台重合", "0", "按底层资产去重", "#8854d0"),
            "validation": MetricCard("信号验证", "--", "近30天5日持有胜率", "#2d8cf0"),
            "paper": MetricCard("模拟组合", "1.0000", "三阶段框架净值", "#8854d0"),
        }
        for card in self.metric_cards.values():
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        command_card = _card()
        command_card.setMinimumHeight(196)
        command_layout = QVBoxLayout(command_card)
        command_layout.setContentsMargins(16, 13, 16, 13)
        command_layout.setSpacing(10)
        title_row = QHBoxLayout()
        command_title = QLabel("运行任务")
        command_title.setProperty("role", "cardTitle")
        title_row.addWidget(command_title)
        title_row.addStretch(1)
        self.offline_check = QCheckBox("仅使用离线缓存")
        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(1, 32)
        self.worker_spin.setValue(6)
        self.worker_spin.setPrefix("并发 ")
        self.worker_spin.setSuffix(" 线程")
        title_row.addWidget(self.offline_check)
        title_row.addWidget(self.worker_spin)
        command_layout.addLayout(title_row)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        scan_panel = self._build_scan_panel()
        backtest_panel = self._build_backtest_panel()
        actions.addWidget(scan_panel, 1)
        actions.addWidget(backtest_panel, 1)
        command_layout.addLayout(actions)

        task_row = QHBoxLayout()
        self.task_detail = QLabel("当前没有运行中的任务")
        self.task_detail.setProperty("role", "muted")
        task_row.addWidget(self.task_detail)
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 0)
        self.task_progress.hide()
        task_row.addWidget(self.task_progress, 1)
        self.stop_button = QPushButton("停止")
        self.stop_button.setProperty("kind", "danger")
        self.stop_button.setFixedWidth(76)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_task)
        task_row.addWidget(self.stop_button)
        command_layout.addLayout(task_row)
        layout.addWidget(command_card)

        data_splitter = QSplitter(Qt.Orientation.Horizontal)
        data_splitter.setChildrenCollapsible(False)
        data_splitter.addWidget(self._build_table_card("信号观察", "按总分与拒绝创新低强度排序", "signal"))
        data_splitter.addWidget(self._build_table_card("领先板块", "板块宽度与反转结构综合得分", "sector"))
        data_splitter.setSizes([560, 440])
        layout.addWidget(data_splitter, 1)

        log_card = _card()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(13, 10, 13, 12)
        log_layout.setSpacing(7)
        log_header = QHBoxLayout()
        log_title = QLabel("实时日志")
        log_title.setProperty("role", "cardTitle")
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        clear_button = QPushButton("清空")
        clear_button.setProperty("kind", "ghost")
        clear_button.clicked.connect(lambda: self.task_log.clear())
        log_header.addWidget(clear_button)
        log_layout.addLayout(log_header)
        self.task_log = QPlainTextEdit()
        self.task_log.setObjectName("TaskLog")
        self.task_log.setReadOnly(True)
        self.task_log.setMaximumBlockCount(5000)
        self.task_log.setMinimumHeight(105)
        self.task_log.setMaximumHeight(145)
        self.task_log.setPlaceholderText("任务输出会实时显示在这里")
        log_layout.addWidget(self.task_log)
        layout.addWidget(log_card)
        return page

    def _build_scan_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("InnerPanel")
        panel.setMinimumHeight(86)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title = QLabel("每日扫描")
        title.setProperty("role", "cardTitle")
        subtitle = QLabel("生成最新日报与机会列表")
        subtitle.setProperty("role", "muted")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        heading.addStretch(1)
        layout.addLayout(heading)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.latest_check = QCheckBox("最新交易日")
        self.latest_check.setChecked(True)
        self.scan_date = QDateEdit(QDate.currentDate())
        self.scan_date.setCalendarPopup(True)
        self.scan_date.setDisplayFormat("yyyy-MM-dd")
        self.scan_date.setEnabled(False)
        self.latest_check.toggled.connect(lambda checked: self.scan_date.setEnabled(not checked))
        self.scan_button = QPushButton("开始扫描")
        self.scan_button.setProperty("kind", "primary")
        self.scan_button.clicked.connect(self.start_scan)
        controls.addStretch(1)
        controls.addWidget(self.latest_check)
        controls.addWidget(self.scan_date)
        controls.addWidget(self.scan_button)
        layout.addLayout(controls)
        return panel

    def _build_backtest_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("InnerPanel")
        panel.setMinimumHeight(86)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title = QLabel("历史回测")
        title.setProperty("role", "cardTitle")
        subtitle = QLabel("验证信号后的收益与回撤")
        subtitle.setProperty("role", "muted")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        heading.addStretch(1)
        layout.addLayout(heading)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.backtest_start = QDateEdit(QDate.currentDate().addYears(-1))
        self.backtest_end = QDateEdit(QDate.currentDate())
        for editor in (self.backtest_start, self.backtest_end):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
        self.backtest_button = QPushButton("运行回测")
        self.backtest_button.clicked.connect(self.start_backtest)
        controls.addStretch(1)
        controls.addWidget(self.backtest_start)
        arrow = QLabel("至")
        arrow.setProperty("role", "muted")
        controls.addWidget(arrow)
        controls.addWidget(self.backtest_end)
        controls.addWidget(self.backtest_button)
        layout.addLayout(controls)
        return panel

    def _build_table_card(self, title: str, subtitle: str, kind: str) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setProperty("role", "cardTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setProperty("role", "muted")
        heading.addWidget(title_label)
        heading.addWidget(subtitle_label)
        heading.addStretch(1)
        layout.addLayout(heading)
        if kind == "signal":
            self.signal_table = _table(["代码", "名称 / 市场", "板块", "评分", "阶段"])
            widths = (108, 150, 115, 55)
            for column, width in enumerate(widths):
                self.signal_table.setColumnWidth(column, width)
            table = self.signal_table
        else:
            self.sector_table = _table(["板块", "市场", "得分", "上涨 / 覆盖"])
            self.sector_table.setColumnWidth(0, 108)
            self.sector_table.setColumnWidth(1, 45)
            self.sector_table.setColumnWidth(2, 48)
            self.sector_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table = self.sector_table
        table.setMinimumHeight(150)
        layout.addWidget(table)
        return card

    # ---------- account watchlist ----------
    def _build_watchlist_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(14)
        header, header_layout = self._page_header(
            "我的自选",
            "按底层资产跨平台去重；链上股票归入美港股，加密货币不再细分行业",
        )
        self.watchlist_count_chip = QLabel("0 个标的")
        self.watchlist_count_chip.setProperty("chip", True)
        self.watchlist_count_chip.setProperty("tone", "idle")
        clear_filter_button = QPushButton("显示全部")
        clear_filter_button.clicked.connect(self._clear_watchlist_filter)
        edit_industry_button = QPushButton("修改选中股票行业")
        edit_industry_button.setProperty("kind", "primary")
        edit_industry_button.clicked.connect(self.edit_selected_industry)
        open_chart_button = QPushButton("查看K线 / 画线")
        open_chart_button.setProperty("kind", "primary")
        open_chart_button.clicked.connect(self.open_selected_chart)
        header_layout.addWidget(self.watchlist_count_chip)
        header_layout.addWidget(clear_filter_button)
        header_layout.addWidget(edit_industry_button)
        header_layout.addWidget(open_chart_button)
        layout.addWidget(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.watchlist_metric_cards = {
            "crypto": MetricCard("加密货币", "0", "不含链上股票", "#f3ba2f"),
            "global_equity": MetricCard("美港股", "0", "包含链上股票", "#2d8cf0"),
            "cn_equity": MetricCard("A股", "0", "同花顺自选", "#ea5455"),
            "overlap": MetricCard("跨平台重合", "0", "已合并底层标的", "#8854d0"),
            "unresolved": MetricCard("待确认行业", "0", "可选中后修改", "#ff9f43"),
        }
        for card in self.watchlist_metric_cards.values():
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        table_card = _card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(13, 11, 13, 13)
        table_layout.setSpacing(8)
        title_row = QHBoxLayout()
        title = QLabel("合并后的活动观察池")
        title.setProperty("role", "cardTitle")
        self.watchlist_filter_label = QLabel("全部类别 · 全部行业")
        self.watchlist_filter_label.setProperty("role", "muted")
        title_row.addWidget(title)
        title_row.addWidget(self.watchlist_filter_label)
        title_row.addStretch(1)
        table_layout.addLayout(title_row)
        self.watchlist_table = _table(
            ["大类", "行业领域", "代码 / 资产", "名称", "自选来源", "类型"]
        )
        self.watchlist_table.setColumnWidth(0, 105)
        self.watchlist_table.setColumnWidth(1, 180)
        self.watchlist_table.setColumnWidth(2, 135)
        self.watchlist_table.setColumnWidth(3, 150)
        self.watchlist_table.setColumnWidth(4, 170)
        self.watchlist_table.doubleClicked.connect(self.open_selected_chart)
        table_layout.addWidget(self.watchlist_table, 1)
        layout.addWidget(table_card, 1)
        return page

    def _build_chart_page(self) -> QWidget:
        client = LongbridgeClient(
            credentials_loader=lambda: self.account_service.vault.load("longbridge")
        )
        service = MarketChartService(longbridge_client=client)
        self.chart_workspace = ChartWorkspace(
            PACKAGE_DIR / "state" / "chart_drawings.json",
            service=service,
        )
        return self.chart_workspace

    def _build_accounts_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(13)
        header, header_layout = self._page_header(
            "自选导入与维护",
            "三个来源统一使用文件导入或手动添加，不需要绑定平台账号",
        )
        self.sync_button = QPushButton("刷新已导入文件")
        self.sync_button.setProperty("kind", "primary")
        self.sync_button.clicked.connect(lambda _checked=False: self.sync_linked_watchlists())
        header_layout.addWidget(self.sync_button)
        layout.addWidget(header)

        notice = QLabel(
            "同花顺、币安和欧易自选统一保存在本地：可上传 Excel / CSV / JSON / TXT，"
            "也可手动添加。程序不再要求这三个平台的 API Key、密码或 Cookie。"
            "长桥仅作为可选股票行情源，不参与自选读取。"
        )
        notice.setWordWrap(True)
        notice.setObjectName("SafetyNote")
        layout.addWidget(notice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        content = QWidget()
        content.setObjectName("ContentPage")
        cards = QVBoxLayout(content)
        cards.setContentsMargins(0, 0, 5, 0)
        cards.setSpacing(11)
        watchlist_heading = QLabel("自选来源")
        watchlist_heading.setProperty("role", "cardTitle")
        cards.addWidget(watchlist_heading)
        cards.addWidget(self._build_account_source_card("tonghuashun"))
        cards.addWidget(self._build_account_source_card("binance"))
        cards.addWidget(self._build_account_source_card("okx"))
        cards.addSpacing(8)
        market_heading = QLabel("可选行情数据源")
        market_heading.setProperty("role", "cardTitle")
        cards.addWidget(market_heading)
        cards.addWidget(self._build_longbridge_card())
        cards.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def _build_account_source_card(self, source: str) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(9)
        heading = QHBoxLayout()
        title = QLabel(SOURCE_LABELS[source])
        title.setProperty("role", "cardTitle")
        subtitles = {
            "tonghuashun": "A股、港股和美股 · 表格或手动添加",
            "binance": "加密货币与链上股票 · 文件或手动添加",
            "okx": "加密货币与链上股票 · 文件或手动添加",
        }
        subtitle = QLabel(subtitles[source])
        subtitle.setProperty("role", "muted")
        status = QLabel("暂无自选")
        status.setProperty("chip", True)
        status.setProperty("tone", "warning")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        heading.addStretch(1)
        heading.addWidget(status)
        layout.addLayout(heading)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(7)
        alias = QLineEdit()
        alias.setPlaceholderText("可选，例如：币安主列表")
        form.addRow("列表名称", alias)
        fields: dict[str, QWidget] = {"alias": alias, "status": status}
        layout.addLayout(form)

        actions = QHBoxLayout()
        detail = QLabel("尚未添加自选")
        detail.setProperty("role", "muted")
        detail.setWordWrap(True)
        fields["detail"] = detail
        actions.addWidget(detail, 1)
        import_button = QPushButton("导入文件")
        import_button.setProperty("kind", "primary")
        import_button.clicked.connect(
            lambda _checked=False, selected=source: self.import_account_watchlist(selected)
        )
        fields["import_button"] = import_button
        if source == "tonghuashun":
            manual_button = QPushButton("手动添加股票")
            manual_button.clicked.connect(lambda _checked=False: self.manual_add_stock())
            actions.addWidget(manual_button)
        elif source in {"binance", "okx"}:
            manual_button = QPushButton("手动添加币种")
            manual_button.clicked.connect(
                lambda _checked=False, selected=source: self.manual_add_crypto(selected)
            )
            actions.addWidget(manual_button)
        clear_button = QPushButton("清空自选")
        clear_button.setProperty("kind", "danger")
        clear_button.clicked.connect(
            lambda _checked=False, selected=source: self.clear_account_source(selected)
        )
        actions.addWidget(import_button)
        actions.addWidget(clear_button)
        layout.addLayout(actions)
        self.account_fields[source] = fields
        return card

    def _build_longbridge_card(self) -> QFrame:
        source = "longbridge"
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(9)

        heading = QHBoxLayout()
        title = QLabel(ACCOUNT_SOURCE_LABELS[source])
        title.setProperty("role", "cardTitle")
        subtitle = QLabel("A股、港股、美股多周期官方行情主源 · 只读")
        subtitle.setProperty("role", "muted")
        status = QLabel("未启用")
        status.setProperty("chip", True)
        status.setProperty("tone", "warning")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        heading.addStretch(1)
        heading.addWidget(status)
        layout.addLayout(heading)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(7)
        alias = QLineEdit()
        alias.setPlaceholderText("例如：长桥股票行情")
        form.addRow("行情源名称", alias)
        fields: dict[str, QWidget] = {"alias": alias, "status": status}
        definitions = (
            ("app_key", "App Key", "长桥开发者中心 App Key"),
            ("app_secret", "App Secret", "仅进入系统密钥环"),
            ("access_token", "Access Token", "仅进入系统密钥环"),
        )
        for name, label, placeholder in definitions:
            editor = QLineEdit()
            editor.setEchoMode(QLineEdit.EchoMode.Password)
            editor.setPlaceholderText(placeholder)
            form.addRow(label, editor)
            fields[name] = editor
        http_url = QLineEdit(DEFAULT_HTTP_URL)
        quote_ws_url = QLineEdit(DEFAULT_QUOTE_WS_URL)
        http_url.setToolTip("长桥官方 OpenAPI HTTP 地址")
        quote_ws_url.setToolTip("长桥官方行情 WebSocket 地址")
        form.addRow("HTTP 地址", http_url)
        form.addRow("行情 WS 地址", quote_ws_url)
        fields.update({"http_url": http_url, "quote_ws_url": quote_ws_url})
        layout.addLayout(form)

        actions = QHBoxLayout()
        detail = QLabel("尚未启用；需要安装可选的长桥官方 SDK")
        detail.setProperty("role", "muted")
        detail.setWordWrap(True)
        fields["detail"] = detail
        actions.addWidget(detail, 1)
        docs_button = QPushButton("开发者中心")
        docs_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://open.longbridge.com/"))
        )
        verify_button = QPushButton("验证并启用行情")
        verify_button.setProperty("kind", "primary")
        verify_button.clicked.connect(lambda _checked=False: self.connect_account(source))
        disconnect_button = QPushButton("停用行情")
        disconnect_button.clicked.connect(lambda _checked=False: self.disconnect_account(source))
        fields.update(
            {
                "verify_button": verify_button,
                "disconnect_button": disconnect_button,
            }
        )
        actions.addWidget(docs_button)
        actions.addWidget(verify_button)
        actions.addWidget(disconnect_button)
        layout.addLayout(actions)
        self.account_fields[source] = fields
        return card

    # ---------- reports ----------
    def _build_reports_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(14)
        header, header_layout = self._page_header("报告中心", "在应用内阅读 Markdown 日报与历史回测")
        self.report_meta = QLabel("请选择一份报告")
        self.report_meta.setProperty("role", "muted")
        self.open_report_button = QPushButton("用默认应用打开")
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self.open_current_report)
        folder_button = QPushButton("打开报告目录")
        folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(PACKAGE_DIR / "reports")))
        )
        header_layout.addWidget(self.report_meta)
        header_layout.addWidget(self.open_report_button)
        header_layout.addWidget(folder_button)
        layout.addWidget(header)

        browser_card = _card()
        browser_layout = QVBoxLayout(browser_card)
        browser_layout.setContentsMargins(13, 13, 13, 13)
        self.report_browser = QTextBrowser()
        self.report_browser.setOpenExternalLinks(True)
        self.report_browser.document().setDefaultStyleSheet(
            "body{font-family:'Noto Sans CJK SC';color:#26292e;line-height:1.55;}"
            "h1{font-size:23px;color:#17191d;margin-bottom:14px;}"
            "h2{font-size:17px;color:#202328;border-bottom:1px solid #eceef0;padding-bottom:7px;}"
            "h3{font-size:14px;color:#2e3238;}"
            "table{border-collapse:collapse;}th{background:#f5f7f8;font-weight:600;}"
            "th,td{border:1px solid #e2e5e8;padding:7px 9px;}"
            "code{background:#f2f4f5;padding:2px 4px;color:#47645a;}"
            "blockquote{color:#6f767e;border-left:3px solid #07c160;margin-left:0;padding-left:12px;}"
        )
        self.report_browser.setHtml(
            "<div style='text-align:center;color:#93979d;margin-top:150px;'>"
            "<h2 style='border:0;color:#5f646b;'>选择一份报告</h2>"
            "<p>左侧会列出所有日报与回测结果</p></div>"
        )
        browser_layout.addWidget(self.report_browser)
        layout.addWidget(browser_card, 1)
        return page

    # ---------- config ----------
    def _build_config_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(14)
        header, header_layout = self._page_header("系统配置", "保存前自动校验，并为原文件创建 .bak 备份")
        self.config_state = QLabel("未选择文件")
        self.config_state.setProperty("chip", True)
        self.config_state.setProperty("tone", "idle")
        header_layout.addWidget(self.config_state)
        layout.addWidget(header)

        editor_card = _card()
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(14, 13, 14, 14)
        editor_layout.setSpacing(9)
        editor_header = QHBoxLayout()
        self.config_path_label = QLabel("从左侧选择配置文件")
        self.config_path_label.setProperty("role", "cardTitle")
        editor_header.addWidget(self.config_path_label)
        editor_header.addStretch(1)
        self.reload_config_button = QPushButton("重新载入")
        self.reload_config_button.setEnabled(False)
        self.reload_config_button.clicked.connect(self.reload_config)
        self.save_config_button = QPushButton("校验并保存")
        self.save_config_button.setProperty("kind", "primary")
        self.save_config_button.setEnabled(False)
        self.save_config_button.clicked.connect(self.save_config)
        editor_header.addWidget(self.reload_config_button)
        editor_header.addWidget(self.save_config_button)
        editor_layout.addLayout(editor_header)
        self.config_editor = QPlainTextEdit()
        self.config_editor.setObjectName("ConfigEditor")
        self.config_editor.setPlaceholderText("选择 watchlist.yaml、thresholds.yaml 或 fundamentals.csv")
        self.config_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.config_editor.textChanged.connect(self._config_changed)
        editor_layout.addWidget(self.config_editor, 1)
        tip = QLabel("修改观察池和阈值只影响后续任务；已生成的历史报告不会被改写。")
        tip.setProperty("role", "muted")
        editor_layout.addWidget(tip)
        layout.addWidget(editor_card, 1)
        return page

    # ---------- system ----------
    def _build_system_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("ContentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(14)
        header, header_layout = self._page_header("系统状态", "检查桌面组件、配置、数据库与最新日报")
        refresh_button = QPushButton("重新检查")
        refresh_button.clicked.connect(self.refresh_system)
        header_layout.addWidget(refresh_button)
        layout.addWidget(header)

        health_card = _card()
        health_layout = QVBoxLayout(health_card)
        health_layout.setContentsMargins(13, 11, 13, 13)
        health_title = QLabel("健康检查")
        health_title.setProperty("role", "cardTitle")
        health_layout.addWidget(health_title)
        self.health_table = _table(["组件", "状态", "详情"])
        self.health_table.setColumnWidth(0, 150)
        self.health_table.setColumnWidth(1, 90)
        health_layout.addWidget(self.health_table)
        layout.addWidget(health_card, 1)

        run_card = _card()
        run_layout = QVBoxLayout(run_card)
        run_layout.setContentsMargins(13, 11, 13, 13)
        run_title = QLabel("最近扫描批次")
        run_title.setProperty("role", "cardTitle")
        run_layout.addWidget(run_title)
        self.run_table = _table(["批次", "报告日期", "开始时间", "完成时间", "状态"])
        self.run_table.setColumnWidth(0, 80)
        self.run_table.setColumnWidth(1, 120)
        self.run_table.setColumnWidth(2, 190)
        self.run_table.setColumnWidth(3, 190)
        run_layout.addWidget(self.run_table)
        layout.addWidget(run_card, 1)
        return page

    # ---------- context list ----------
    def _active_reports(self) -> list[Path]:
        """Hide reports produced before the current account-watchlist generation."""

        try:
            generated_at = self.watchlist_repo.active_watchlist_path.stat().st_mtime
        except OSError:
            generated_at = 0.0
        return [path for path in list_reports() if path.stat().st_mtime >= generated_at]

    def _populate_context_list(self) -> None:
        self.context_list.clear()
        if self.current_page == 0:
            self._add_context_item("每日扫描", "最新或指定交易日", {"kind": "scan"})
            self._add_context_item("历史回测", "验证收益与最大回撤", {"kind": "backtest"})
            runs = recent_scan_runs(limit=8)
            for run in runs:
                report_date = str(run.get("report_date") or "未完成")
                status = str(run.get("status") or "unknown")
                self._add_context_item(
                    f"{report_date}", f"批次 #{run.get('id')}  ·  {status}", {"kind": "run"}
                )
        elif self.current_page == 1:
            summary = self.watchlist_repo.summary()
            counts = summary.get("category_counts") or {}
            for category in ("crypto", "global_equity", "cn_equity"):
                self._add_context_item(
                    CATEGORY_LABELS[category],
                    f"{int(counts.get(category, 0))} 个标的",
                    {"kind": "watchlist_filter", "category": category},
                )
            for sector in summary.get("sectors") or []:
                self._add_context_item(
                    str(sector.get("name") or "未命名行业"),
                    f"{int(sector.get('asset_count', 0))} 个标的",
                    {
                        "kind": "watchlist_filter",
                        "category": str(sector.get("category") or ""),
                        "industry": str(sector.get("industry") or ""),
                    },
                )
        elif self.current_page == 2:
            self._add_context_item(
                "宏观经济",
                "增长 · 通胀 · 流动性 · 风险偏好",
                {"kind": "research_macro"},
            )
            for asset in self.watchlist_repo.summary().get("assets") or []:
                self._add_context_item(
                    str(asset.get("name") or asset.get("symbol") or "未命名标的"),
                    f"{asset.get('symbol') or '--'} · {asset.get('industry') or '待分类'}",
                    {
                        "kind": "research_asset",
                        "canonical_id": str(asset.get("canonical_id") or ""),
                    },
                )
        elif self.current_page == 3:
            for path in self._active_reports():
                title = path.stem.replace("daily_report_", "日报 · ").replace("backtest_", "回测 · ")
                modified = path.stat().st_mtime
                detail = date.fromtimestamp(modified).isoformat()
                self._add_context_item(title, detail, {"kind": "report", "path": str(path)})
            if not self.context_list.count():
                self._add_context_item("暂无当前报告", "导入自选后运行一次扫描", {"kind": "empty"})
        elif self.current_page == 4:
            source_status = self.watchlist_repo.source_status()
            for source in ("tonghuashun", "binance", "okx"):
                snapshot = source_status[source]
                self._add_context_item(
                    SOURCE_LABELS[source],
                    f"{snapshot['count']} 项自选" if snapshot.get("count") else "暂无自选",
                    {"kind": "account_source", "source": source},
                )
        elif self.current_page == 5:
            for name, passed, detail in health_check():
                self._add_context_item(
                    f"{'正常' if passed else '异常'} · {name}", detail, {"kind": "health"}
                )
        else:
            for asset in self.watchlist_repo.summary().get("assets") or []:
                self._add_context_item(
                    str(asset.get("name") or asset.get("symbol") or "未命名标的"),
                    f"{asset.get('symbol') or '--'} · {asset.get('market') or '--'}",
                    {
                        "kind": "chart_asset",
                        "canonical_id": str(asset.get("canonical_id") or ""),
                    },
                )

    def _add_context_item(self, title: str, subtitle: str, payload: dict[str, str]) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, payload)
        search_role = int(Qt.ItemDataRole.UserRole) + 1
        item.setData(search_role, f"{title}\n{subtitle}")
        item.setToolTip(f"{title}\n{subtitle}")
        item.setSizeHint(QSize(0, 61))
        self.context_list.addItem(item)
        self.context_list.setItemWidget(item, ContextRow(title, subtitle))

    def _filter_context_list(self, query: str) -> None:
        normalized = query.strip().casefold()
        for row in range(self.context_list.count()):
            item = self.context_list.item(row)
            searchable = str(item.data(int(Qt.ItemDataRole.UserRole) + 1) or "")
            item.setHidden(bool(normalized) and normalized not in searchable.casefold())

    def _context_item_clicked(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole) or {}
        kind = payload.get("kind")
        if kind == "scan":
            self.scan_button.setFocus()
            self.statusBar().showMessage("设置扫描日期后点击“开始扫描”", 3500)
        elif kind == "backtest":
            self.backtest_button.setFocus()
            self.statusBar().showMessage("选择回测区间后点击“运行回测”", 3500)
        elif kind == "report":
            self.load_report(Path(payload["path"]))
        elif kind == "research_macro":
            self.research_workspace.select_macro()
        elif kind == "research_asset":
            canonical_id = str(payload.get("canonical_id") or "")
            asset = next(
                (
                    value
                    for value in self.watchlist_repo.summary().get("assets") or []
                    if str(value.get("canonical_id") or "") == canonical_id
                ),
                None,
            )
            if asset:
                self.research_workspace.select_asset(asset)
        elif kind == "watchlist_filter":
            self.watchlist_filter = {
                key: str(payload[key])
                for key in ("category", "industry")
                if payload.get(key)
            }
            self.refresh_watchlist()
        elif kind == "account_source":
            source = str(payload.get("source") or "")
            alias = self.account_fields.get(source, {}).get("alias")
            if isinstance(alias, QLineEdit):
                alias.setFocus()
        elif kind == "chart_asset":
            canonical_id = str(payload.get("canonical_id") or "")
            asset = next(
                (
                    value
                    for value in self.watchlist_repo.summary().get("assets") or []
                    if str(value.get("canonical_id") or "") == canonical_id
                ),
                None,
            )
            if asset:
                self.chart_workspace.select_asset(asset)

    # ---------- data refresh ----------
    def refresh_all(self) -> None:
        self.refresh_watchlist()
        self.refresh_accounts()
        self.refresh_dashboard()
        self.refresh_reports()
        self.refresh_system()
        self._populate_context_list()

    def refresh_reports(self) -> None:
        active_reports = self._active_reports()
        if self.current_report in active_reports:
            return
        self.current_report = None
        self.open_report_button.setEnabled(False)
        self.report_meta.setText("请选择一份当前自选生成的报告")
        self.report_browser.setHtml(
            "<div style='text-align:center;color:#93979d;margin-top:150px;'>"
            "<h2 style='border:0;color:#5f646b;'>暂无当前报告</h2>"
            "<p>添加自选后，从工作台运行每日扫描</p></div>"
        )

    def _clear_watchlist_filter(self) -> None:
        self.watchlist_filter = {}
        self.refresh_watchlist()

    def refresh_watchlist(self) -> None:
        summary = self.watchlist_repo.summary()
        counts = summary.get("category_counts") or {}
        self.watchlist_metric_cards["crypto"].set_value(str(int(counts.get("crypto", 0))))
        self.watchlist_metric_cards["global_equity"].set_value(
            str(int(counts.get("global_equity", 0))),
            f"链上股票 {int(summary.get('tokenized_stock_count', 0))} 个",
        )
        self.watchlist_metric_cards["cn_equity"].set_value(str(int(counts.get("cn_equity", 0))))
        self.watchlist_metric_cards["overlap"].set_value(str(int(summary.get("overlap_count", 0))))
        self.watchlist_metric_cards["unresolved"].set_value(
            str(int(summary.get("unresolved_industry_count", 0)))
        )
        asset_count = int(summary.get("asset_count", 0))
        self.watchlist_count_chip.setText(f"{asset_count} 个标的")
        _set_dynamic_property(
            self.watchlist_count_chip,
            "tone",
            "idle" if asset_count else "warning",
        )

        category = self.watchlist_filter.get("category", "")
        industry = self.watchlist_filter.get("industry", "")
        category_text = CATEGORY_LABELS.get(category, "全部类别")
        self.watchlist_filter_label.setText(
            f"{category_text} · {industry or '全部行业'}"
        )
        assets = [
            item
            for item in summary.get("assets") or []
            if (not category or item.get("category") == category)
            and (not industry or item.get("industry") == industry)
        ]
        self.chart_workspace.set_assets(list(summary.get("assets") or []))
        self.watchlist_table.setRowCount(len(assets))
        for row, item in enumerate(assets):
            sources = " / ".join(
                SOURCE_LABELS.get(str(source), str(source))
                for source in item.get("sources") or []
            )
            if item.get("tokenized_stock"):
                asset_type = "链上股票"
            elif item.get("category") == "crypto":
                asset_type = "加密货币"
            elif item.get("asset_type") == "etf":
                asset_type = "ETF"
            else:
                asset_type = "股票"
            values = (
                CATEGORY_LABELS.get(str(item.get("category")), "--"),
                item.get("industry") or UNKNOWN_INDUSTRY,
                item.get("symbol") or "--",
                item.get("name") or "--",
                sources or "--",
                asset_type,
            )
            self._fill_table_row(self.watchlist_table, row, values)
            first = self.watchlist_table.item(row, 0)
            first.setData(Qt.ItemDataRole.UserRole, str(item.get("canonical_id") or ""))

    def open_selected_chart(self, *_args: Any) -> None:
        row = self.watchlist_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "选择标的", "请先在自选表格中选中一只股票或加密货币。")
            return
        item = self.watchlist_table.item(row, 0)
        canonical_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        asset = next(
            (
                value
                for value in self.watchlist_repo.summary().get("assets") or []
                if str(value.get("canonical_id") or "") == canonical_id
            ),
            None,
        )
        if not asset:
            QMessageBox.warning(self, "无法打开行情", "找不到选中的自选标的。")
            return
        self.chart_workspace.select_asset(asset)
        self.switch_page(6)

    def edit_selected_industry(self, *_args: Any) -> None:
        row = self.watchlist_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "选择股票", "请先在表格中选中一只股票。")
            return
        canonical_item = self.watchlist_table.item(row, 0)
        canonical_id = str(canonical_item.data(Qt.ItemDataRole.UserRole) or "")
        asset = next(
            (
                item
                for item in self.watchlist_repo.summary().get("assets") or []
                if item.get("canonical_id") == canonical_id
            ),
            None,
        )
        if not asset:
            QMessageBox.warning(self, "无法修改", "找不到选中标的，请刷新后重试。")
            return
        if asset.get("category") == "crypto":
            QMessageBox.information(self, "无需分类", "加密货币按要求不划分行业领域。")
            return
        industry, accepted = QInputDialog.getText(
            self,
            "修改行业领域",
            f"{asset.get('name')} ({asset.get('symbol')}) 的行业：",
            QLineEdit.EchoMode.Normal,
            str(asset.get("industry") or ""),
        )
        if not accepted:
            return
        try:
            self.watchlist_repo.update_industry(canonical_id, industry)
        except ValueError as exc:
            QMessageBox.warning(self, "行业无效", str(exc))
            return
        self.refresh_all()
        self.statusBar().showMessage(f"已将 {asset.get('symbol')} 划分为“{industry.strip()}”", 5000)

    def import_account_watchlist(self, source: str) -> None:
        if self.import_threads:
            running_source = next(iter(self.import_threads))
            QMessageBox.information(
                self,
                "导入正在进行",
                f"{SOURCE_LABELS[running_source]}自选正在后台导入，请完成后再导入其他文件。",
            )
            return
        file_filter = (
            "股票表格/自选文件 (*.xlsx *.xls *.xlsm *.csv *.json *.txt *.sel *.ini);;所有文件 (*)"
            if source == "tonghuashun"
            else "自选表格/文件 (*.xlsx *.xls *.xlsm *.csv *.json *.txt);;所有文件 (*)"
        )
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            f"导入{SOURCE_LABELS[source]}自选",
            "",
            file_filter,
        )
        if not path:
            return
        fields = self.account_fields[source]
        alias_field = fields.get("alias")
        alias = alias_field.text().strip() if isinstance(alias_field, QLineEdit) else ""
        thread = QThread(self)
        worker = WatchlistImportWorker(self.watchlist_repo, source, path, alias)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._watchlist_import_succeeded)
        worker.failed.connect(self._watchlist_import_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda selected=source: self._watchlist_import_thread_finished(selected)
        )
        self.import_threads[source] = thread
        self.import_workers[source] = worker
        self._set_watchlist_import_busy(source, True)
        self.statusBar().showMessage(
            f"正在后台解析{SOURCE_LABELS[source]}自选，可继续使用其他页面…"
        )
        thread.start()

    def _set_watchlist_import_busy(self, source: str, busy: bool) -> None:
        fields = self.account_fields.get(source, {})
        button = fields.get("import_button")
        if isinstance(button, QPushButton):
            button.setEnabled(not busy)
            button.setText(
                "正在后台导入…"
                if busy
                else "导入文件"
            )
        detail = fields.get("detail")
        if busy and isinstance(detail, QLabel):
            detail.setText("正在解析表格、匹配股票并补全行业，请稍候…")

    @Slot(str, object)
    def _watchlist_import_succeeded(self, source: str, result: ImportResult) -> None:
        self.refresh_all()
        self._set_watchlist_import_busy(source, False)
        self.statusBar().showMessage(f"{SOURCE_LABELS[source]}自选导入完成", 6000)
        skipped_detail = ""
        if result.skipped_count:
            skipped_detail = f"\n跳过不支持或无效的记录：{result.skipped_count} 项。"
            if result.warnings:
                examples = "\n".join(f"• {item}" for item in result.warnings[:3])
                skipped_detail += f"\n前 {min(3, len(result.warnings))} 项原因：\n{examples}"
        QMessageBox.information(
            self,
            "自选已导入",
            f"{SOURCE_LABELS[source]}识别 {result.imported_count} 项；"
            f"跨平台合并后 {result.merged_count} 个标的，"
            f"生成 {result.generated_sector_count} 个检测板块。\n"
            f"待确认行业：{result.unresolved_industry_count} 个。"
            + skipped_detail,
        )

    @Slot(str, str)
    def _watchlist_import_failed(self, source: str, error: str) -> None:
        self._set_watchlist_import_busy(source, False)
        self.statusBar().showMessage(f"{SOURCE_LABELS[source]}自选导入失败", 6000)
        QMessageBox.critical(self, "导入失败", error)

    def _watchlist_import_thread_finished(self, source: str) -> None:
        self.import_threads.pop(source, None)
        self.import_workers.pop(source, None)
        self._set_watchlist_import_busy(source, False)

    def manual_add_crypto(self, source: str) -> None:
        symbols_text, accepted = QInputDialog.getMultiLineText(
            self,
            f"手动添加{SOURCE_LABELS[source]}自选",
            "输入现货交易对，用换行、逗号或空格分隔。\n"
            "例如：BTCUSDT  ETHUSDT  SOL/USDT",
        )
        if not accepted or not symbols_text.strip():
            return
        symbols = [
            value.strip().upper()
            for value in re.split(r"[\s,，;；]+", symbols_text)
            if value.strip()
        ]
        symbols = list(dict.fromkeys(symbols))
        fields = self.account_fields[source]
        alias_field = fields.get("alias")
        alias = alias_field.text().strip() if isinstance(alias_field, QLineEdit) else ""
        added: list[str] = []
        failures: list[str] = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for symbol in symbols:
                try:
                    asset, _summary = self.watchlist_repo.add_manual_asset(
                        source,
                        {"symbol": symbol},
                        alias,
                        resolve_industry=False,
                    )
                except Exception as exc:
                    failures.append(f"{symbol}：{exc}")
                else:
                    added.append(asset.symbol)
        finally:
            QApplication.restoreOverrideCursor()
        if not added:
            QMessageBox.warning(
                self,
                "没有添加任何交易对",
                "\n".join(failures[:8]) or "请输入完整的现货交易对，例如 BTCUSDT。",
            )
            return
        self.refresh_all()
        detail = f"已添加 {len(added)} 个{SOURCE_LABELS[source]}交易对。"
        if failures:
            detail += f"\n另有 {len(failures)} 项未识别：\n" + "\n".join(failures[:5])
        QMessageBox.information(self, "本地自选已更新", detail)

    def manual_add_stock(self) -> None:
        query, accepted = QInputDialog.getText(
            self,
            "手动添加股票",
            "输入股票代码或名称（例如 600519、腾讯控股、AAPL）：",
        )
        query = query.strip()
        if not accepted or not query:
            return
        market_choice, accepted = QInputDialog.getItem(
            self,
            "选择市场",
            "所属市场：",
            ["自动识别", "A股", "港股", "美股"],
            0,
            False,
        )
        if not accepted:
            return
        market_hints = {"自动识别": "", "A股": "CN", "港股": "HK", "美股": "US"}
        market_hint = market_hints[market_choice]
        code_like = bool(
            re.fullmatch(r"(?:SH|SZ|BJ)?\d{4,6}(?:\.(?:SS|SZ|BJ|HK))?", query.upper())
            or re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", query.upper())
        )

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        search_error = ""
        try:
            candidates = search_equities(query, market_hint)
        except ValueError as exc:
            candidates = []
            search_error = str(exc)
        finally:
            QApplication.restoreOverrideCursor()

        query_folded = query.casefold()
        exact_candidates = [
            item
            for item in candidates
            if item["name"].casefold() == query_folded
            or item["code"].casefold() == query_folded
            or item["symbol"].casefold() == query_folded
        ]
        if exact_candidates:
            candidates = exact_candidates

        selected: dict[str, str] | None = None
        if candidates:
            market_labels = {"CN": "A股", "HK": "港股", "US": "美股"}
            labels = [
                f"{item['name']} · {item['symbol']} · "
                f"{market_labels.get(item['market'], item['market'])}"
                for item in candidates
            ]
            if len(candidates) == 1:
                answer = QMessageBox.question(
                    self,
                    "确认股票",
                    f"确认添加：\n{labels[0]}？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                selected = candidates[0]
            else:
                choice, accepted = QInputDialog.getItem(
                    self,
                    "确认搜索结果",
                    "请选择要加入的股票：",
                    labels,
                    0,
                    False,
                )
                if not accepted:
                    return
                selected = candidates[labels.index(choice)]
        elif not code_like:
            QMessageBox.warning(
                self,
                "未找到股票",
                search_error or "没有找到可确认的股票，请尝试输入股票代码并选择市场。",
            )
            return

        if selected:
            row: dict[str, str] = {
                "symbol": selected["symbol"],
                "name": selected["name"],
                "market": selected["market"],
            }
        else:
            stock_name, accepted = QInputDialog.getText(
                self,
                "补充股票名称",
                f"未取得在线名称。请确认 {query} 的显示名称：",
                QLineEdit.EchoMode.Normal,
                query,
            )
            if not accepted or not stock_name.strip():
                return
            row = {"symbol": query, "name": stock_name.strip(), "market": market_hint}

        industry, accepted = QInputDialog.getText(
            self,
            "行业领域（可选）",
            "填写行业领域；留空时系统会尝试自动识别：",
        )
        if not accepted:
            return
        if industry.strip():
            row["industry"] = industry.strip()
        fields = self.account_fields["tonghuashun"]
        alias_field = fields.get("alias")
        alias = alias_field.text().strip() if isinstance(alias_field, QLineEdit) else ""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            asset, summary = self.watchlist_repo.add_manual_asset(
                "tonghuashun",
                row,
                alias,
                resolve_industry=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "添加失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh_all()
        QMessageBox.information(
            self,
            "已加入自选",
            f"已添加 {asset.name}（{asset.symbol}），当前合并观察池共 "
            f"{summary['asset_count']} 个标的。",
        )

    def clear_account_source(self, source: str) -> None:
        status = self.watchlist_repo.source_status()[source]
        if not status.get("count"):
            return
        answer = QMessageBox.question(
            self,
            "清空自选",
            f"确定清空{SOURCE_LABELS[source]}已导入的 {status['count']} 项自选吗？\n"
            "不会影响平台原账号中的收藏。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.watchlist_repo.clear_source(source)
        self.refresh_all()

    def sync_linked_watchlists(
        self,
        *,
        quiet: bool = False,
        force: bool = True,
        pending_task: CommandSpec | None = None,
    ) -> None:
        if self.sync_thread or self.import_threads:
            if not quiet:
                QMessageBox.information(self, "自选正在处理", "请等待当前自选任务完成。")
            return
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            if not quiet:
                QMessageBox.information(self, "扫描正在运行", "请等待当前扫描或回测结束。")
            return
        thread = QThread(self)
        worker = WatchlistSyncWorker(self.watchlist_repo, force)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._watchlist_sync_succeeded)
        worker.failed.connect(self._watchlist_sync_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._watchlist_sync_thread_finished)
        self.sync_thread = thread
        self.sync_worker = worker
        self.sync_quiet = quiet
        self.pending_task_after_sync = pending_task
        self.sync_button.setEnabled(False)
        self.sync_button.setText("正在后台同步…")
        self.scan_button.setEnabled(False)
        self.backtest_button.setEnabled(False)
        self.statusBar().showMessage("正在后台检查并同步自选，界面可继续使用…")
        thread.start()

    @Slot(object)
    def _watchlist_sync_succeeded(self, result: object) -> None:
        _summary, refreshed, errors = result
        self.refresh_all()
        if self.sync_quiet:
            for source, error in errors.items():
                self._append_log(f"{SOURCE_LABELS[source]}自选同步失败：{error}", "warning")
        else:
            if not refreshed and not errors:
                QMessageBox.information(
                    self,
                    "没有需要同步的文件",
                    "没有已导入文件，或文件内容没有变化。",
                )
            else:
                lines = [
                    f"已同步：{', '.join(SOURCE_LABELS[item] for item in refreshed) or '无'}"
                ]
                lines.extend(
                    f"{SOURCE_LABELS[source]}：{error}" for source, error in errors.items()
                )
                QMessageBox.information(self, "自选同步结果", "\n".join(lines))

    @Slot(str)
    def _watchlist_sync_failed(self, error: str) -> None:
        if self.sync_quiet:
            self._append_log(f"自选后台同步失败，将使用上次快照：{error}", "warning")
        else:
            QMessageBox.critical(self, "自选同步失败", error)

    @Slot()
    def _watchlist_sync_thread_finished(self) -> None:
        pending_task = self.pending_task_after_sync
        self.sync_thread = None
        self.sync_worker = None
        self.pending_task_after_sync = None
        self.sync_button.setEnabled(True)
        self.sync_button.setText("刷新已导入文件")
        self._set_busy(False)
        if pending_task is not None:
            QTimer.singleShot(0, lambda spec=pending_task: self._start_task(spec))
        else:
            self.statusBar().showMessage("自选同步完成", 5000)

    def connect_account(self, source: str) -> None:
        if source != "longbridge":
            QMessageBox.information(
                self,
                "无需绑定账号",
                "同花顺、币安和欧易自选统一通过文件或手动添加维护。",
            )
            return
        if self.account_connect_thread is not None:
            QMessageBox.information(self, "行情源正在验证", "请等待长桥行情验证完成。")
            return
        fields = self.account_fields[source]
        self.account_connection_errors.pop(source, None)

        def line(name: str) -> str:
            widget = fields.get(name)
            return widget.text().strip() if isinstance(widget, QLineEdit) else ""

        parameters = {
            "app_key": line("app_key"),
            "app_secret": line("app_secret"),
            "access_token": line("access_token"),
            "account_label": line("alias"),
            "http_url": line("http_url"),
            "quote_ws_url": line("quote_ws_url"),
        }
        for name in ("app_key", "app_secret", "access_token"):
            widget = fields.get(name)
            if isinstance(widget, QLineEdit):
                widget.clear()

        thread = QThread(self)
        worker = AccountConnectWorker(self.account_service, source, parameters)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._account_connect_succeeded)
        worker.failed.connect(self._account_connect_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda selected=source: self._account_connect_thread_finished(selected)
        )
        self.account_connect_thread = thread
        self.account_connect_worker = worker
        self.account_connect_source = source
        self._set_account_connect_busy(source, True)
        self.statusBar().showMessage("正在后台验证长桥行情，界面可继续使用…")
        thread.start()

    def _set_account_connect_busy(self, source: str, busy: bool) -> None:
        fields = self.account_fields.get(source, {})
        button = fields.get("verify_button")
        if isinstance(button, QPushButton):
            button.setEnabled(not busy)
            button.setText(
                "正在验证…"
                if busy
                else "验证并启用行情"
            )
        detail = fields.get("detail")
        if busy and isinstance(detail, QLabel):
            detail.setText("正在通过官方接口验证，请稍候…")

    @Slot(str, object)
    def _account_connect_succeeded(self, source: str, result: ConnectionResult) -> None:
        self.account_connection_errors.pop(source, None)
        if source == "longbridge":
            self.chart_workspace.service.longbridge_client.reset()
        self.refresh_all()
        persistence = "系统密钥环" if result.persisted_in_keyring else "仅当前运行内存"
        permission = "只读行情" if result.permissions == "quote_only" else "只读"
        QMessageBox.information(
            self,
            "行情源已启用",
            f"{result.account_label}\n权限：{permission}\n凭据保存：{persistence}\n\n{result.detail}",
        )

    @Slot(str, str)
    def _account_connect_failed(self, source: str, error: str) -> None:
        self.account_connection_errors[source] = error
        self.refresh_accounts()
        self.statusBar().showMessage(f"{ACCOUNT_SOURCE_LABELS[source]}验证失败", 6000)
        QMessageBox.critical(self, "长桥行情验证失败", error)

    @Slot()
    def _account_connect_thread_finished(self, source: str) -> None:
        self.account_connect_thread = None
        self.account_connect_worker = None
        self.account_connect_source = ""
        self._set_account_connect_busy(source, False)
        self.refresh_accounts()

    def disconnect_account(self, source: str) -> None:
        if source != "longbridge":
            return
        if not self.account_service.status(source).get("connected"):
            return
        answer = QMessageBox.question(
            self,
            "停用行情",
            f"确定删除{ACCOUNT_SOURCE_LABELS[source]}的本地行情关联吗？\n"
            "已导入的自选快照会保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.account_service.disconnect(source)
        self.account_connection_errors.pop(source, None)
        if source == "longbridge":
            self.chart_workspace.service.longbridge_client.reset()
        self.refresh_all()

    def refresh_accounts(self) -> None:
        snapshots = self.watchlist_repo.source_status()
        for source, fields in self.account_fields.items():
            snapshot = snapshots.get(source, {})
            count = int(snapshot.get("count", 0))
            status_widget = fields.get("status")
            detail_widget = fields.get("detail")
            alias_widget = fields.get("alias")
            if source == "longbridge":
                connection = self.account_service.status(source)
                connection_error = self.account_connection_errors.get(source, "")
                verified = bool(
                    connection.get("connected") and connection.get("credential_available")
                )
                if isinstance(status_widget, QLabel):
                    status_widget.setText(
                        "行情已启用"
                        if verified
                        else ("需重新验证" if connection.get("connected") else "未启用")
                    )
                    _set_dynamic_property(status_widget, "tone", "idle" if verified else "warning")
                alias = str(connection.get("account_label") or "")
                if isinstance(alias_widget, QLineEdit) and alias and not alias_widget.text().strip():
                    alias_widget.setText(alias)
                details = [connection_error] if connection_error else []
                if verified:
                    details.append("只读行情已验证")
                    if connection.get("detail"):
                        details.append(str(connection["detail"]))
                if isinstance(detail_widget, QLabel):
                    detail_widget.setText(" · ".join(details) or "尚未启用长桥认证行情")
                continue

            if isinstance(status_widget, QLabel):
                status_widget.setText(f"{count} 项自选" if count else "暂无自选")
                _set_dynamic_property(status_widget, "tone", "idle" if count else "warning")
            alias = str(snapshot.get("account_alias") or "")
            if isinstance(alias_widget, QLineEdit) and alias and not alias_widget.text().strip():
                alias_widget.setText(alias)
            details: list[str] = []
            if count:
                details.append(f"共 {count} 项")
                manual_count = int(snapshot.get("manual_count", 0))
                if manual_count:
                    details.append(f"手动添加 {manual_count} 项")
                if snapshot.get("imported_at"):
                    details.append(f"导入于 {str(snapshot['imported_at'])[:19].replace('T', ' ')}")
            if isinstance(detail_widget, QLabel):
                detail_widget.setText(" · ".join(details) or "尚未添加自选")

    def _refresh_validation_cards(self) -> None:
        """Load rolling win-rate and paper equity in a background thread."""
        database = PACKAGE_DIR / "state" / "signals.db"
        if not database.exists():
            return

        def _load():
            try:
                store = StateStore(database)
                summary = store.outcome_summary(window_days=30, horizon=5)
                paper = store.paper_history_summary()
                return summary, paper
            except Exception:
                return None, None

        def _worker():
            summary, paper = _load()
            QTimer.singleShot(
                0,
                lambda: self._apply_validation_cards(summary, paper),
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_validation_cards(self, summary: Any, paper: Any) -> None:
        card = self.metric_cards.get("validation")
        if card is not None:
            if summary and summary.get("sample_size"):
                card.set_value(
                    f"{summary['win_rate']:.0%}",
                    f"{summary['sample_size']} 样本 · {summary['average_return']:+.2%}",
                )
            else:
                card.set_value("--", "暂无已到期样本")
        paper_card = self.metric_cards.get("paper")
        if paper_card is not None and paper and paper.get("latest") is not None:
            latest = float(paper["latest"])
            paper_card.set_value(
                f"{latest:.4f}",
                f"{len(paper['points'])} 个交易日",
            )

    def refresh_dashboard(self) -> None:
        watchlist = self.watchlist_repo.summary()
        category_counts = watchlist.get("category_counts") or {}
        asset_count = int(watchlist.get("asset_count", 0))
        self.metric_cards["total"].set_value(
            str(asset_count), f"{int(watchlist.get('sector_count', 0))} 个动态检测板块"
        )
        self.metric_cards["crypto"].set_value(str(int(category_counts.get("crypto", 0))))
        self.metric_cards["global_equity"].set_value(
            str(int(category_counts.get("global_equity", 0))),
            f"链上股票 {int(watchlist.get('tokenized_stock_count', 0))} 个",
        )
        self.metric_cards["cn_equity"].set_value(str(int(category_counts.get("cn_equity", 0))))
        self.metric_cards["overlap"].set_value(str(int(watchlist.get("overlap_count", 0))))
        self._refresh_validation_cards()
        busy = bool(self.process and self.process.state() != QProcess.ProcessState.NotRunning)
        self.scan_button.setEnabled(asset_count > 0 and not busy)
        self.backtest_button.setEnabled(asset_count > 0 and not busy)

        report_path = latest_json_report()
        try:
            watchlist_mtime = self.watchlist_repo.active_watchlist_path.stat().st_mtime
        except OSError:
            # watchlist.yaml 尚未生成（首次安装未导入自选）时按最早时间处理
            watchlist_mtime = 0.0
        if not report_path or report_path.stat().st_mtime < watchlist_mtime:
            self.signal_table.setRowCount(0)
            self.sector_table.setRowCount(0)
            if not busy:
                if asset_count:
                    self._set_task_status("待扫描", "warning")
                    self.task_detail.setText("自选池已更新，请运行每日扫描")
                else:
                    self._set_task_status("等待导入", "warning")
                    self.task_detail.setText("请先在“导入”页添加同花顺、币安或欧易自选")
            return
        try:
            summary = load_report_summary(report_path)
        except (OSError, ValueError, KeyError) as exc:
            self._set_task_status("日报异常", "danger")
            self._append_log(f"无法读取最新日报：{exc}", "error")
            return

        if not busy:
            self._set_task_status(f"报告 {summary.report_date}", "idle")
            self.task_detail.setText(
                f"有效信号 {summary.signal_count} 个 · 高优先级 {summary.opportunity_count} 个"
            )

        self.signal_table.setRowCount(len(summary.signals[:40]))
        for row, item in enumerate(summary.signals[:40]):
            score = item.get("score") or {}
            values = (
                item.get("symbol", "--"),
                f"{item.get('name', '--')}  ·  {item.get('market', '--')}",
                item.get("sector_name", item.get("sector_id", "--")),
                f"{score.get('total', 0)}/{score.get('available_max', 10)}",
                item.get("entry_stage") or item.get("signal_level") or item.get("state", "--"),
            )
            self._fill_table_row(self.signal_table, row, values)

        self.sector_table.setRowCount(len(summary.sectors[:25]))
        for row, item in enumerate(summary.sectors[:25]):
            breadth = item.get("breadth") or {}
            values = (
                item.get("sector_name", item.get("sector_id", "--")),
                item.get("market", "--"),
                item.get("score", 0),
                f"{float(breadth.get('up_ratio', 0)):.0%} / "
                f"{float(breadth.get('coverage', 0)):.0%}",
            )
            self._fill_table_row(self.sector_table, row, values)

    @staticmethod
    def _fill_table_row(table: QTableWidget, row: int, values: tuple[Any, ...]) -> None:
        for column, value in enumerate(values):
            cell = QTableWidgetItem(str(value))
            if column >= len(values) - 2:
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, column, cell)

    def refresh_system(self) -> None:
        checks = health_check()
        self.health_table.setRowCount(len(checks))
        for row, (name, passed, detail) in enumerate(checks):
            values = (name, "正常" if passed else "异常", detail)
            self._fill_table_row(self.health_table, row, values)
            status_item = self.health_table.item(row, 1)
            status_item.setForeground(QColor("#168447" if passed else "#c33a43"))

        try:
            runs = recent_scan_runs(limit=20)
        except Exception as exc:
            runs = []
            self.statusBar().showMessage(f"读取扫描批次失败：{exc}", 5000)
        self.run_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            values = (
                f"#{run.get('id', '--')}",
                run.get("report_date") or "--",
                run.get("started_at") or "--",
                run.get("completed_at") or "--",
                run.get("status") or "--",
            )
            self._fill_table_row(self.run_table, row, values)

    # ---------- report actions ----------
    def load_report(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "无法读取报告", str(exc))
            return
        self.current_report = path
        self.report_browser.setMarkdown(content)
        self.report_browser.moveCursor(QTextCursor.MoveOperation.Start)
        self.report_meta.setText(f"{path.name}  ·  {path.stat().st_size / 1024:.1f} KB")
        self.open_report_button.setEnabled(True)

    def open_current_report(self) -> None:
        if self.current_report:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_report)))

    # ---------- config actions ----------
    def _confirm_config_switch(self) -> bool:
        if not self.config_dirty or not self.current_config:
            return True
        answer = QMessageBox.question(
            self,
            "配置尚未保存",
            f"{self.current_config.name} 有未保存修改。是否先保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_config()
        self.config_dirty = False
        return True

    def load_config(self, path: Path) -> None:
        if path == self.current_config:
            return
        if not self._confirm_config_switch():
            return
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "无法读取配置", str(exc))
            return
        self.current_config = path
        self.config_editor.blockSignals(True)
        self.config_editor.setPlainText(content)
        self.config_editor.blockSignals(False)
        self.config_dirty = False
        self.config_path_label.setText(f"{path.name}   ·   {path.parent}")
        self.reload_config_button.setEnabled(True)
        self.save_config_button.setEnabled(True)
        self._set_config_state("已载入", "idle")

    def reload_config(self) -> None:
        if not self.current_config:
            return
        path = self.current_config
        self.current_config = None
        self.config_dirty = False
        self.load_config(path)
        self.statusBar().showMessage(f"已重新载入 {path.name}", 3500)

    def _config_changed(self) -> None:
        if not self.current_config:
            return
        self.config_dirty = True
        self._set_config_state("有未保存修改", "warning")

    def _set_config_state(self, text: str, tone: str) -> None:
        self.config_state.setText(text)
        _set_dynamic_property(self.config_state, "tone", tone)

    def save_config(self) -> bool:
        if not self.current_config:
            return False
        try:
            backup = save_editor_content(self.current_config, self.config_editor.toPlainText())
        except Exception as exc:
            self._set_config_state("校验失败", "danger")
            QMessageBox.critical(self, "配置未保存", str(exc))
            return False
        self.config_dirty = False
        self._set_config_state("已保存", "idle")
        self.statusBar().showMessage(f"已保存 {self.current_config.name}；备份：{backup.name}", 6000)
        return True

    # ---------- tasks ----------
    @staticmethod
    def _qdate_text(editor: QDateEdit) -> str:
        return editor.date().toString("yyyy-MM-dd")

    def start_scan(self) -> None:
        if self.import_threads or self.sync_thread:
            QMessageBox.information(self, "自选正在处理", "请等待自选导入或同步完成后再扫描。")
            return
        if int(self.watchlist_repo.summary().get("asset_count", 0)) == 0:
            QMessageBox.information(self, "自选池为空", "请先在“导入”页添加至少一个自选标的。")
            return
        requested = "" if self.latest_check.isChecked() else self._qdate_text(self.scan_date)
        try:
            spec = build_scan_command(requested, self.offline_check.isChecked(), self.worker_spin.value())
        except ValueError as exc:
            QMessageBox.warning(self, "扫描参数无效", str(exc))
            return
        if self.watchlist_repo.changed_linked_sources():
            self.sync_linked_watchlists(quiet=True, force=False, pending_task=spec)
        else:
            self._start_task(spec)

    def start_backtest(self) -> None:
        if self.import_threads or self.sync_thread:
            QMessageBox.information(self, "自选正在处理", "请等待自选导入或同步完成后再回测。")
            return
        if int(self.watchlist_repo.summary().get("asset_count", 0)) == 0:
            QMessageBox.information(self, "自选池为空", "请先在“导入”页添加至少一个自选标的。")
            return
        try:
            spec = build_backtest_command(
                self._qdate_text(self.backtest_start),
                self._qdate_text(self.backtest_end),
                self.offline_check.isChecked(),
                self.worker_spin.value(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "回测参数无效", str(exc))
            return
        if self.watchlist_repo.changed_linked_sources():
            self.sync_linked_watchlists(quiet=True, force=False, pending_task=spec)
        else:
            self._start_task(spec)

    def _start_task(self, spec: CommandSpec) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "任务正在运行", "请等待当前任务结束，或先点击停止。")
            return
        self.task_name = spec.name
        process = QProcess(self)
        process.setWorkingDirectory(str(spec.cwd))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUNBUFFERED", "1")
        longbridge_credentials = self.account_service.vault.load("longbridge")
        for key, environment_key in LONG_BRIDGE_ENV_KEYS.items():
            value = str(longbridge_credentials.get(key) or "").strip()
            if value:
                environment.insert(environment_key, value)
        process.setProcessEnvironment(environment)
        if os.name == "posix" and shutil.which("setsid"):
            process.setProgram(shutil.which("setsid") or "setsid")
            process.setArguments(spec.argv)
        else:
            process.setProgram(spec.argv[0])
            process.setArguments(spec.argv[1:])
        process.readyReadStandardOutput.connect(self._read_task_output)
        process.finished.connect(self._task_finished)
        process.errorOccurred.connect(self._task_error)
        self.process = process

        command = " ".join(spec.argv)
        self._append_log(f"$ {command}", "command")
        self._append_log(f"[{spec.name}] 正在启动……", "muted")
        self._set_busy(True)
        self._set_task_status("运行中", "running")
        self.task_detail.setText(spec.name)
        process.start()

    def _read_task_output(self) -> None:
        if not self.process:
            return
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        cleaned = ANSI_ESCAPE.sub("", raw).rstrip("\n")
        if cleaned:
            self._append_log(cleaned)

    def _append_log(self, message: str, tone: str = "normal") -> None:
        if not message:
            return
        colors = {
            "normal": "#d9dde3",
            "command": "#74dca0",
            "success": "#70df9c",
            "warning": "#ffd27c",
            "error": "#ff9298",
            "muted": "#99a0aa",
        }
        cursor = self.task_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.task_log.document().characterCount() > 1:
            cursor.insertText("\n")
        char_format = QTextCharFormat()
        char_format.setForeground(QColor(colors.get(tone, colors["normal"])))
        cursor.insertText(message, char_format)
        self.task_log.setTextCursor(cursor)
        self.task_log.ensureCursorVisible()

    def _set_busy(self, busy: bool) -> None:
        has_assets = int(self.watchlist_repo.summary().get("asset_count", 0)) > 0
        self.scan_button.setEnabled(not busy and has_assets)
        self.backtest_button.setEnabled(not busy and has_assets)
        self.stop_button.setEnabled(busy)
        self.task_progress.setVisible(busy)

    def _set_task_status(self, text: str, tone: str) -> None:
        self.task_chip.setText(text)
        _set_dynamic_property(self.task_chip, "tone", tone)

    def stop_task(self) -> None:
        if not self.process or self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.stop_button.setEnabled(False)
        self.task_detail.setText(f"正在安全停止 {self.task_name}……")
        self._set_task_status("停止中", "warning")
        self._append_log("已请求安全停止任务……", "warning")
        pid = int(self.process.processId())
        try:
            if os.name == "posix" and pid > 0:
                os.killpg(pid, signal.SIGINT)
            else:
                self.process.terminate()
        except (OSError, ProcessLookupError):
            self.process.terminate()
        QTimer.singleShot(5000, self._force_stop_task)

    def _force_stop_task(self) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self._append_log("安全停止超时，正在强制结束任务。", "error")
            pid = int(self.process.processId())
            try:
                if os.name == "posix" and pid > 0:
                    os.killpg(pid, signal.SIGKILL)
                else:
                    self.process.kill()
            except (OSError, ProcessLookupError):
                self.process.kill()

    def _task_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._read_task_output()
        self._set_busy(False)
        if exit_code == 0:
            self._set_task_status("已完成", "idle")
            self.task_detail.setText(f"{self.task_name} 已完成")
            self._append_log(f"[{self.task_name}] 完成，退出码 0", "success")
            self.statusBar().showMessage(f"{self.task_name} 已完成，数据已刷新", 6000)
        elif exit_code == 130:
            self._set_task_status("已停止", "warning")
            self.task_detail.setText(f"{self.task_name} 已安全停止")
            self._append_log(f"[{self.task_name}] 已中止，退出码 130", "warning")
        else:
            self._set_task_status("执行失败", "danger")
            self.task_detail.setText(f"{self.task_name} 失败 · 退出码 {exit_code}")
            self._append_log(f"[{self.task_name}] 失败，退出码 {exit_code}", "error")
        self.refresh_all()

    def _task_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.Crashed:
            return
        detail = self.process.errorString() if self.process else str(error)
        self._append_log(f"无法运行任务：{detail}", "error")
        self._set_task_status("启动失败", "danger")
        self.task_detail.setText(detail)
        self._set_busy(False)

    # ---------- lifecycle ----------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.research_workspace.is_loading:
            QMessageBox.information(
                self,
                "研究数据仍在加载",
                "财报、新闻或宏观数据正在后台刷新，请等待完成后再关闭。",
            )
            event.ignore()
            return
        if self.account_connect_thread:
            QMessageBox.information(
                self,
                "行情源仍在验证",
                "长桥行情仍在后台验证。请等待完成后再关闭窗口。",
            )
            event.ignore()
            return
        if self.chart_workspace.is_loading:
            QMessageBox.information(
                self,
                "行情仍在加载",
                "K 线行情仍在后台加载。请等待完成后再关闭窗口。",
            )
            event.ignore()
            return
        if self.sync_thread:
            QMessageBox.information(
                self,
                "自选仍在同步",
                "自选仍在后台同步。请等待完成后再关闭窗口。",
            )
            event.ignore()
            return
        if self.import_threads:
            source = next(iter(self.import_threads))
            QMessageBox.information(
                self,
                "自选仍在导入",
                f"{SOURCE_LABELS[source]}自选仍在后台处理。请等待导入完成后再关闭窗口。",
            )
            event.ignore()
            return
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            answer = QMessageBox.question(
                self,
                "任务仍在运行",
                "关闭窗口会停止当前任务，确定继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop_task()
        self.chart_workspace.shutdown()
        event.accept()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bottom Hunter 微信风格桌面操作台")
    parser.add_argument("--check", action="store_true", help="只运行无界面健康检查并退出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        checks = health_check()
        for name, passed, detail in checks:
            print(f"[{'OK' if passed else 'FAIL'}] {name}: {detail}")
        return 0 if all(passed for _, passed, _ in checks) else 1

    try:
        app = QApplication.instance() or QApplication(sys.argv[:1])
    except Exception as exc:
        print(f"无法启动桌面界面：{exc}", file=sys.stderr)
        print("请在图形桌面会话中运行，或使用 python gui.py --check。", file=sys.stderr)
        return 2
    app.setApplicationName("Bottom Hunter")
    app.setOrganizationName("Bottom Hunter")
    app.setStyle("Fusion")
    font = QFont(_font_family(), 10)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)
    app.setStyleSheet(APP_STYLE)
    window = BottomHunterWindow()
    window.show()
    interrupt_count = 0

    def handle_interrupt(_signum: int, _frame: Any) -> None:
        nonlocal interrupt_count
        interrupt_count += 1
        if interrupt_count == 1:
            # Run closeEvent from Qt's loop instead of raising KeyboardInterrupt
            # while a Python-backed Qt callback is active.
            QTimer.singleShot(0, window.close)
        else:
            app.exit(130)

    previous_sigint = None
    signal_timer = QTimer()
    if os.name == "posix":
        previous_sigint = signal.signal(signal.SIGINT, handle_interrupt)
        # Let Python dispatch terminal signals even while Qt owns the main loop.
        signal_timer.timeout.connect(lambda: None)
        signal_timer.start(200)
    try:
        return app.exec()
    finally:
        signal_timer.stop()
        if previous_sigint is not None:
            signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    raise SystemExit(main())
