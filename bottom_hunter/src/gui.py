from __future__ import annotations

import argparse
import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import webbrowser
from datetime import date, timedelta
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

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


COLORS = {
    "navy": "#172033",
    "blue": "#2563EB",
    "blue_hover": "#1D4ED8",
    "background": "#F3F5F8",
    "surface": "#FFFFFF",
    "border": "#DDE3EA",
    "text": "#1F2937",
    "muted": "#64748B",
    "success": "#15803D",
    "warning": "#B45309",
    "danger": "#B91C1C",
    "log": "#101827",
    "log_text": "#D5E2F2",
}


class BottomHunterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("每日板块超跌反弹狩猎系统 · 操作台")
        self.geometry("1320x860")
        self.minsize(1080, 720)
        self.configure(bg=COLORS["background"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._process: subprocess.Popen[str] | None = None
        self._task_name = ""
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._report_paths: list[Path] = []
        self._config_paths = [
            PACKAGE_DIR / "config" / "watchlist.yaml",
            PACKAGE_DIR / "config" / "thresholds.yaml",
            PACKAGE_DIR / "data" / "fundamentals.csv",
        ]
        self._config_current: Path | None = None
        self.ui_font = self._resolve_ui_font()
        self._configure_style()
        self._build_header()
        self._build_tabs()
        self.after(100, self._poll_events)
        self.after(150, self.refresh_all)

    def _resolve_ui_font(self) -> str:
        families = {str(name).lower(): str(name) for name in self.tk.call("font", "families")}
        for candidate in (
            "Microsoft YaHei UI",
            "PingFang SC",
            "Noto Sans CJK SC",
            "WenQuanYi Micro Hei",
            "Droid Sans Fallback",
            "Song Ti",
            "FangSong Ti",
        ):
            if candidate.lower() in families:
                return families[candidate.lower()]
        return "TkDefaultFont"

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        default_font = (self.ui_font, 10)
        self.option_add("*Font", default_font)
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"])
        style.configure("Surface.TLabel", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("Muted.TLabel", foreground=COLORS["muted"])
        style.configure("Header.TLabel", font=(self.ui_font, 12, "bold"))
        style.configure(
            "Primary.TButton",
            background=COLORS["blue"],
            foreground="white",
            padding=(14, 8),
            borderwidth=0,
        )
        style.map("Primary.TButton", background=[("active", COLORS["blue_hover"])])
        style.configure("Danger.TButton", foreground=COLORS["danger"], padding=(12, 8))
        style.configure("TButton", padding=(10, 7))
        style.configure("TNotebook", background=COLORS["background"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=(self.ui_font, 10, "bold"))
        style.configure("Treeview", rowheight=29, background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=(self.ui_font, 9, "bold"))
        style.configure("TLabelframe", background=COLORS["surface"], bordercolor=COLORS["border"])
        style.configure("TLabelframe.Label", background=COLORS["surface"], font=(self.ui_font, 10, "bold"))

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        title_box = tk.Frame(header, bg=COLORS["navy"])
        title_box.pack(side="left", padx=24, pady=12)
        tk.Label(
            title_box,
            text="BOTTOM HUNTER",
            bg=COLORS["navy"],
            fg="white",
            font=("DejaVu Sans", 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="每日板块超跌反弹狩猎系统 · 只产生观察信号，不自动下单",
            bg=COLORS["navy"],
            fg="#AFC0D9",
            font=(self.ui_font, 9),
        ).pack(anchor="w")
        self.header_status = tk.StringVar(value="就绪")
        tk.Label(
            header,
            textvariable=self.header_status,
            bg="#23304A",
            fg="#D8E5F7",
            padx=15,
            pady=8,
            font=(self.ui_font, 9, "bold"),
        ).pack(side="right", padx=24)

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(14, 12))
        self.control_tab = ttk.Frame(self.notebook)
        self.report_tab = ttk.Frame(self.notebook)
        self.config_tab = ttk.Frame(self.notebook)
        self.system_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.control_tab, text="扫描控制")
        self.notebook.add(self.report_tab, text="报告中心")
        self.notebook.add(self.config_tab, text="系统配置")
        self.notebook.add(self.system_tab, text="系统状态")
        self._build_control_tab()
        self._build_report_tab()
        self._build_config_tab()
        self._build_system_tab()

    def _card(self, parent: tk.Widget, title: str, variable: tk.StringVar, accent: str) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        tk.Frame(frame, bg=accent, width=5).pack(side="left", fill="y")
        body = tk.Frame(frame, bg=COLORS["surface"])
        body.pack(fill="both", expand=True, padx=13, pady=9)
        tk.Label(
            body, text=title, bg=COLORS["surface"], fg=COLORS["muted"], font=(self.ui_font, 9)
        ).pack(anchor="w")
        tk.Label(
            body,
            textvariable=variable,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=(self.ui_font, 15, "bold"),
            anchor="w",
        ).pack(anchor="w")
        return frame

    def _build_control_tab(self) -> None:
        self.card_vars = {
            "date": tk.StringVar(value="--"),
            "market": tk.StringVar(value="--"),
            "signals": tk.StringVar(value="0"),
            "opportunities": tk.StringVar(value="0"),
            "quality": tk.StringVar(value="--"),
        }
        cards = tk.Frame(self.control_tab, bg=COLORS["background"])
        cards.pack(fill="x", pady=(0, 10))
        definitions = [
            ("date", "最新报告", COLORS["blue"]),
            ("market", "市场环境", "#7C3AED"),
            ("signals", "有效信号", "#0891B2"),
            ("opportunities", "高优先级", COLORS["success"]),
            ("quality", "数据质量", COLORS["warning"]),
        ]
        for index, (key, title, accent) in enumerate(definitions):
            cards.grid_columnconfigure(index, weight=1, uniform="cards")
            self._card(cards, title, self.card_vars[key], accent).grid(
                row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 5)
            )

        controls = ttk.LabelFrame(self.control_tab, text="任务控制", style="TLabelframe")
        controls.pack(fill="x", pady=(0, 10))
        controls.columnconfigure(10, weight=1)
        ttk.Label(controls, text="扫描日期").grid(row=0, column=0, padx=(12, 5), pady=11)
        self.scan_date = tk.StringVar(value="")
        ttk.Entry(controls, textvariable=self.scan_date, width=13).grid(row=0, column=1, padx=4)
        ttk.Label(controls, text="留空=最新完整交易日", style="Muted.TLabel").grid(
            row=0, column=2, padx=(0, 12)
        )
        self.offline = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="离线缓存", variable=self.offline).grid(row=0, column=3, padx=8)
        ttk.Label(controls, text="线程").grid(row=0, column=4, padx=(10, 4))
        self.workers = tk.IntVar(value=6)
        ttk.Spinbox(controls, from_=1, to=32, width=5, textvariable=self.workers).grid(row=0, column=5)
        self.scan_button = ttk.Button(
            controls, text="开始扫描", style="Primary.TButton", command=self.start_scan
        )
        self.scan_button.grid(row=0, column=6, padx=(14, 5))
        self.stop_button = ttk.Button(
            controls, text="停止任务", style="Danger.TButton", command=self.stop_task, state="disabled"
        )
        self.stop_button.grid(row=0, column=7, padx=5)
        self.progress = ttk.Progressbar(controls, mode="indeterminate", length=150)
        self.progress.grid(row=0, column=10, padx=12, sticky="e")

        ttk.Separator(controls, orient="horizontal").grid(
            row=1, column=0, columnspan=11, sticky="ew", padx=12
        )
        today = date.today()
        self.backtest_start = tk.StringVar(value=(today - timedelta(days=365)).isoformat())
        self.backtest_end = tk.StringVar(value=today.isoformat())
        ttk.Label(controls, text="回测区间").grid(row=2, column=0, padx=(12, 5), pady=11)
        ttk.Entry(controls, textvariable=self.backtest_start, width=13).grid(row=2, column=1, padx=4)
        ttk.Label(controls, text="至").grid(row=2, column=2, padx=4)
        ttk.Entry(controls, textvariable=self.backtest_end, width=13).grid(row=2, column=3, padx=4)
        self.backtest_button = ttk.Button(
            controls, text="开始回测", command=self.start_backtest
        )
        self.backtest_button.grid(row=2, column=4, columnspan=2, padx=12)
        ttk.Label(
            controls,
            text="回测严格按信号日截断数据，完成后自动刷新报告中心。",
            style="Muted.TLabel",
        ).grid(row=2, column=6, columnspan=5, padx=12, sticky="w")

        middle = ttk.Panedwindow(self.control_tab, orient="horizontal")
        middle.pack(fill="both", expand=True, pady=(0, 10))
        signal_frame = ttk.LabelFrame(middle, text="个股信号排行")
        sector_frame = ttk.LabelFrame(middle, text="板块排行")
        middle.add(signal_frame, weight=3)
        middle.add(sector_frame, weight=2)
        self.signal_tree = self._tree(
            signal_frame,
            ("symbol", "name", "sector", "score", "state", "level"),
            ("代码", "名称", "板块", "评分", "状态", "等级"),
            (100, 105, 170, 75, 125, 120),
        )
        self.sector_tree = self._tree(
            sector_frame,
            ("name", "market", "score", "breadth", "coverage"),
            ("板块", "市场", "评分", "上涨宽度", "覆盖率"),
            (210, 60, 75, 90, 80),
        )

        log_frame = ttk.LabelFrame(self.control_tab, text="实时运行日志")
        log_frame.pack(fill="both", expand=True)
        log_toolbar = ttk.Frame(log_frame, style="Surface.TFrame")
        log_toolbar.pack(fill="x")
        self.task_status = tk.StringVar(value="等待任务")
        ttk.Label(log_toolbar, textvariable=self.task_status, style="Surface.TLabel").pack(
            side="left", padx=8, pady=5
        )
        ttk.Button(log_toolbar, text="清空", command=self.clear_log).pack(side="right", padx=5, pady=4)
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=9,
            bg=COLORS["log"],
            fg=COLORS["log_text"],
            insertbackground="white",
            relief="flat",
            font=("DejaVu Sans Mono", 9),
            padx=10,
            pady=8,
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True)

    def _tree(self, parent, columns, headings, widths) -> ttk.Treeview:
        wrapper = ttk.Frame(parent, style="Surface.TFrame")
        wrapper.pack(fill="both", expand=True, padx=6, pady=6)
        tree = ttk.Treeview(wrapper, columns=columns, show="headings", selectmode="browse")
        for column, heading, width in zip(columns, headings, widths, strict=True):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=50, anchor="center")
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    def _build_report_tab(self) -> None:
        toolbar = ttk.Frame(self.report_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="刷新列表", command=self.refresh_reports).pack(side="left")
        ttk.Button(toolbar, text="外部打开", command=self.open_selected_report).pack(side="left", padx=6)
        self.report_label = tk.StringVar(value="请选择报告")
        ttk.Label(toolbar, textvariable=self.report_label, style="Muted.TLabel").pack(
            side="left", padx=12
        )
        pane = ttk.Panedwindow(self.report_tab, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.LabelFrame(pane, text="历史报告")
        right = ttk.LabelFrame(pane, text="内容预览")
        pane.add(left, weight=1)
        pane.add(right, weight=4)
        self.report_list = tk.Listbox(
            left,
            bg="white",
            fg=COLORS["text"],
            selectbackground=COLORS["blue"],
            relief="flat",
            activestyle="none",
            font=("DejaVu Sans Mono", 9),
        )
        report_scroll = ttk.Scrollbar(left, command=self.report_list.yview)
        self.report_list.configure(yscrollcommand=report_scroll.set)
        self.report_list.pack(side="left", fill="both", expand=True, padx=(7, 0), pady=7)
        report_scroll.pack(side="right", fill="y", padx=(0, 7), pady=7)
        self.report_list.bind("<<ListboxSelect>>", self.preview_selected_report)
        self.report_preview = scrolledtext.ScrolledText(
            right,
            wrap="word",
            bg="white",
            fg=COLORS["text"],
            relief="flat",
            padx=18,
            pady=14,
            font=(self.ui_font, 10),
            state="disabled",
        )
        self.report_preview.pack(fill="both", expand=True, padx=7, pady=7)

    def _build_config_tab(self) -> None:
        toolbar = ttk.Frame(self.config_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="配置文件").pack(side="left")
        self.config_selector = ttk.Combobox(
            toolbar,
            state="readonly",
            values=[path.name for path in self._config_paths],
            width=24,
        )
        self.config_selector.pack(side="left", padx=8)
        self.config_selector.current(0)
        self.config_selector.bind("<<ComboboxSelected>>", lambda _: self.load_config_editor())
        ttk.Button(toolbar, text="重新载入", command=self.load_config_editor).pack(side="left", padx=4)
        ttk.Button(
            toolbar, text="校验并保存", style="Primary.TButton", command=self.save_config_editor
        ).pack(side="left", padx=4)
        self.config_status = tk.StringVar(value="保存时会自动创建 .bak 备份")
        ttk.Label(toolbar, textvariable=self.config_status, style="Muted.TLabel").pack(
            side="left", padx=12
        )
        self.config_editor = scrolledtext.ScrolledText(
            self.config_tab,
            wrap="none",
            bg="#FCFCFD",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            padx=14,
            pady=12,
            undo=True,
            font=(self.ui_font, 11),
        )
        self.config_editor.pack(fill="both", expand=True)

    def _build_system_tab(self) -> None:
        toolbar = ttk.Frame(self.system_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="重新检查", command=self.refresh_health).pack(side="left")
        ttk.Label(
            toolbar, text=f"项目目录：{PACKAGE_DIR}", style="Muted.TLabel"
        ).pack(side="left", padx=12)
        pane = ttk.Panedwindow(self.system_tab, orient="horizontal")
        pane.pack(fill="both", expand=True)
        health_frame = ttk.LabelFrame(pane, text="健康检查")
        run_frame = ttk.LabelFrame(pane, text="最近扫描批次")
        pane.add(health_frame, weight=2)
        pane.add(run_frame, weight=3)
        self.health_tree = self._tree(
            health_frame,
            ("item", "status", "detail"),
            ("项目", "状态", "说明"),
            (120, 80, 280),
        )
        self.run_tree = self._tree(
            run_frame,
            ("id", "date", "started", "completed", "status"),
            ("ID", "报告日", "开始时间", "结束时间", "状态"),
            (55, 95, 175, 175, 90),
        )
        note = ttk.LabelFrame(self.system_tab, text="操作说明")
        note.pack(fill="x", pady=(10, 0))
        ttk.Label(
            note,
            text=(
                "扫描日期留空时，各市场自动使用最新完整交易日；离线模式只读本地缓存。  "
                "基本面缺失时评分最高按 8 分显示，界面不会自动下单。"
            ),
            style="Surface.TLabel",
            wraplength=1100,
        ).pack(anchor="w", padx=12, pady=10)

    def refresh_all(self) -> None:
        self.refresh_dashboard()
        self.refresh_reports()
        self.load_config_editor()
        self.refresh_health()

    def refresh_dashboard(self) -> None:
        path = latest_json_report()
        for tree in (self.signal_tree, self.sector_tree):
            tree.delete(*tree.get_children())
        if path is None:
            return
        try:
            summary = load_report_summary(path)
        except Exception as exc:
            self._append_log(f"[界面] 日报读取失败：{exc}\n", "error")
            return
        self.card_vars["date"].set(summary.report_date)
        short_environment = {"Risk-On": "On", "Risk-Off": "Off", "Neutral": "N"}
        environment = "  ".join(
            f"{market}:{short_environment.get(value, value)}"
            for market, value in summary.environments.items()
        )
        self.card_vars["market"].set(environment or "--")
        self.card_vars["signals"].set(str(summary.signal_count))
        self.card_vars["opportunities"].set(str(summary.opportunity_count))
        self.card_vars["quality"].set("完整" if summary.error_count == 0 else f"{summary.error_count} 项警告")
        for item in summary.signals[:20]:
            score = item.get("score", {})
            self.signal_tree.insert(
                "",
                "end",
                values=(
                    item.get("symbol", ""),
                    item.get("name", ""),
                    item.get("sector_name", ""),
                    f"{score.get('total', 0)}/{score.get('available_max', 10)}",
                    item.get("state", ""),
                    item.get("signal_level", ""),
                ),
            )
        for item in summary.sectors:
            breadth = item.get("breadth", {})
            self.sector_tree.insert(
                "",
                "end",
                values=(
                    item.get("sector_name", ""),
                    item.get("market", ""),
                    f"{item.get('score', 0)}/100",
                    f"{float(breadth.get('up_ratio', 0)):.0%}",
                    f"{float(breadth.get('coverage', 0)):.0%}",
                ),
            )

    def refresh_reports(self) -> None:
        selected_name = None
        selection = self.report_list.curselection()
        if selection and selection[0] < len(self._report_paths):
            selected_name = self._report_paths[selection[0]].name
        self._report_paths = list_reports()
        self.report_list.delete(0, "end")
        selected_index = 0
        for index, path in enumerate(self._report_paths):
            self.report_list.insert("end", path.name)
            if path.name == selected_name:
                selected_index = index
        if self._report_paths:
            self.report_list.selection_set(selected_index)
            self.report_list.activate(selected_index)
            self.preview_selected_report()

    def preview_selected_report(self, _event=None) -> None:
        selection = self.report_list.curselection()
        if not selection or selection[0] >= len(self._report_paths):
            return
        path = self._report_paths[selection[0]]
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("读取失败", str(exc), parent=self)
            return
        self.report_label.set(str(path))
        self.report_preview.configure(state="normal")
        self.report_preview.delete("1.0", "end")
        self.report_preview.insert("1.0", content)
        self.report_preview.configure(state="disabled")

    def open_selected_report(self) -> None:
        selection = self.report_list.curselection()
        if not selection or selection[0] >= len(self._report_paths):
            messagebox.showinfo("报告中心", "请先选择一个报告。", parent=self)
            return
        webbrowser.open(self._report_paths[selection[0]].resolve().as_uri())

    def load_config_editor(self) -> None:
        index = self.config_selector.current()
        if index < 0:
            index = 0
        path = self._config_paths[index]
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("读取失败", str(exc), parent=self)
            return
        self._config_current = path
        self.config_editor.delete("1.0", "end")
        self.config_editor.insert("1.0", content)
        self.config_editor.edit_reset()
        self.config_status.set(str(path))

    def save_config_editor(self) -> None:
        if self._config_current is None:
            return
        content = self.config_editor.get("1.0", "end-1c") + "\n"
        try:
            backup = save_editor_content(self._config_current, content)
        except Exception as exc:
            messagebox.showerror("配置无效", str(exc), parent=self)
            self.config_status.set("保存失败，原配置已保留")
            return
        self.config_status.set(f"已保存；备份：{backup.name}")
        messagebox.showinfo("保存成功", "配置已校验并保存。下次任务立即生效。", parent=self)
        self.refresh_health()

    def refresh_health(self) -> None:
        self.health_tree.delete(*self.health_tree.get_children())
        for name, passed, detail in health_check():
            self.health_tree.insert("", "end", values=(name, "正常" if passed else "异常", detail))
        self.run_tree.delete(*self.run_tree.get_children())
        try:
            runs = recent_scan_runs(limit=20)
        except Exception as exc:
            self.run_tree.insert("", "end", values=("--", "--", "--", "--", str(exc)))
            return
        for run in runs:
            self.run_tree.insert(
                "",
                "end",
                values=(
                    run["id"],
                    run["report_date"],
                    str(run["started_at"] or "")[:19],
                    str(run["completed_at"] or "")[:19],
                    run["status"],
                ),
            )

    def start_scan(self) -> None:
        try:
            spec = build_scan_command(
                self.scan_date.get(), self.offline.get(), int(self.workers.get())
            )
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("参数错误", str(exc), parent=self)
            return
        self._start_task(spec)

    def start_backtest(self) -> None:
        try:
            spec = build_backtest_command(
                self.backtest_start.get(),
                self.backtest_end.get(),
                self.offline.get(),
                int(self.workers.get()),
            )
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("参数错误", str(exc), parent=self)
            return
        self._start_task(spec)

    def _start_task(self, spec: CommandSpec) -> None:
        if self._process is not None and self._process.poll() is None:
            messagebox.showwarning("任务运行中", "请先等待或停止当前任务。", parent=self)
            return
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        kwargs: dict[str, object] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(
                spec.argv,
                cwd=spec.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=environment,
                **kwargs,
            )
        except OSError as exc:
            messagebox.showerror("启动失败", str(exc), parent=self)
            return
        self._process = process
        self._task_name = spec.name
        self.header_status.set(f"运行中 · {spec.name}")
        self.task_status.set(f"{spec.name} · PID {process.pid}")
        self.scan_button.configure(state="disabled")
        self.backtest_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.start(10)
        self._append_log(f"\n$ {shlex.join(spec.argv)}\n", "command")
        thread = threading.Thread(
            target=self._read_process, args=(process, spec.name), daemon=True
        )
        thread.start()

    def _read_process(self, process: subprocess.Popen[str], name: str) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                self._events.put(("log", line))
        return_code = process.wait()
        self._events.put(("done", (process, name, return_code)))

    def stop_task(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        self.header_status.set(f"正在停止 · {self._task_name}")
        self.task_status.set("正在请求任务安全退出……")
        self._append_log("[界面] 已发送停止请求。\n", "warning")
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(process.pid, signal.SIGINT)
        except (OSError, ProcessLookupError):
            return
        self.after(4000, lambda: self._force_stop(process))

    def _force_stop(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        self._append_log("[界面] 安全退出超时，正在终止任务。\n", "error")
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "done":
                    process, name, return_code = payload  # type: ignore[misc]
                    if self._process is process:
                        self._process = None
                    self.progress.stop()
                    self.scan_button.configure(state="normal")
                    self.backtest_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    success = return_code == 0
                    self.header_status.set("完成" if success else f"任务结束 · 退出码 {return_code}")
                    self.task_status.set(f"{name} {'完成' if success else '未成功'}")
                    self._append_log(
                        f"[界面] {name}结束，退出码 {return_code}。\n",
                        "success" if success else "error",
                    )
                    self.refresh_dashboard()
                    self.refresh_reports()
                    self.refresh_health()
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _append_log(self, text: str, tag: str = "normal") -> None:
        self.log_text.configure(state="normal")
        self.log_text.tag_configure("error", foreground="#FF9B9B")
        self.log_text.tag_configure("warning", foreground="#FFD28A")
        self.log_text.tag_configure("success", foreground="#83E6A1")
        self.log_text.tag_configure("command", foreground="#86B7FF")
        self.log_text.insert("end", text, tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            if not messagebox.askyesno(
                "任务运行中", "关闭窗口会同时停止当前任务，确定继续吗？", parent=self
            ):
                return
            self.stop_task()
            self.after(600, self.destroy)
            return
        self.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bottom Hunter 桌面操作台")
    parser.add_argument(
        "--check", action="store_true", help="只运行无界面健康检查并退出"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        checks = health_check()
        for name, passed, detail in checks:
            print(f"[{'OK' if passed else 'FAIL'}] {name}: {detail}")
        return 0 if all(passed for _, passed, _ in checks) else 1
    try:
        app = BottomHunterApp()
    except tk.TclError as exc:
        print(f"无法启动桌面界面：{exc}", file=sys.stderr)
        print("请在图形桌面会话中运行，或使用 python gui.py --check。", file=sys.stderr)
        return 2
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
