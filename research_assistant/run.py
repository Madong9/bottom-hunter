"""Run the investment-research backend and frontend as one local service.

The desktop shell starts this process and owns its lifetime.  It can also be
used directly from a terminal while developing the research assistant.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/api/v1/health"
FRONTEND_URL = "http://127.0.0.1:5173"


def _backend_ready() -> bool:
    try:
        with urllib.request.urlopen(BACKEND_HEALTH_URL, timeout=0.4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return payload.get("service") == "ai-investment-research-backend"


def _frontend_ready() -> bool:
    try:
        with urllib.request.urlopen(FRONTEND_URL, timeout=0.4) as response:
            body = response.read(4096).decode("utf-8", errors="ignore")
    except (OSError, urllib.error.URLError):
        return False
    return response.status == 200 and '<div id="root"></div>' in body


def _requirements_error() -> str:
    missing_python = [
        module
        for module in ("fastapi", "uvicorn")
        if importlib.util.find_spec(module) is None
    ]
    if missing_python:
        return (
            "缺少后端依赖："
            + ", ".join(missing_python)
            + "。请在仓库根目录运行 "
            + "python -m pip install -e './bottom_hunter[research-assistant]'"
        )
    if shutil.which("npm") is None:
        return "未找到 npm，请安装 Node.js 18 或更高版本。"
    if not (FRONTEND_DIR / "node_modules" / ".bin" / "vite").is_file():
        return "前端依赖未安装。请运行 cd research_assistant/frontend && npm ci"
    if (
        not (BACKEND_DIR / "app" / "main.py").is_file()
        or not (FRONTEND_DIR / "package.json").is_file()
    ):
        return "投研助手源码不完整，请检查 research_assistant 目录。"
    return ""


def _start_services() -> list[subprocess.Popen[bytes]]:
    processes: list[subprocess.Popen[bytes]] = []
    environment = os.environ.copy()
    environment.setdefault("PYTHONUNBUFFERED", "1")

    if not _backend_ready():
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                cwd=BACKEND_DIR,
                env=environment,
                start_new_session=True,
            )
        )
    else:
        print("检测到已运行的投研助手后端，直接复用。", flush=True)

    if not _frontend_ready():
        processes.append(
            subprocess.Popen(
                [
                    shutil.which("npm") or "npm",
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                ],
                cwd=FRONTEND_DIR,
                env=environment,
                start_new_session=True,
            )
        )
    else:
        print("检测到已运行的投研助手前端，直接复用。", flush=True)
    return processes


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动 AI 投研助手前后端")
    parser.add_argument("--open", action="store_true", help="就绪后用浏览器打开")
    parser.add_argument("--check", action="store_true", help="仅检查运行依赖")
    arguments = parser.parse_args(argv)

    error = _requirements_error()
    if error:
        print(error, file=sys.stderr, flush=True)
        return 2
    if arguments.check:
        print("投研助手运行依赖已就绪。")
        return 0

    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    processes = _start_services()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not stop_event.is_set():
            failed = [
                process.returncode
                for process in processes
                if process.poll() is not None
            ]
            if failed:
                print(f"投研助手子进程启动失败：{failed}", file=sys.stderr, flush=True)
                return 1
            if _backend_ready() and _frontend_ready():
                print(f"投研助手已就绪：{FRONTEND_URL}", flush=True)
                if arguments.open:
                    webbrowser.open(FRONTEND_URL)
                break
            time.sleep(0.25)
        else:
            if not stop_event.is_set():
                print(
                    "投研助手启动超时，请检查 8000/5173 端口。",
                    file=sys.stderr,
                    flush=True,
                )
                return 1

        while not stop_event.wait(0.5):
            failed = [
                process.returncode
                for process in processes
                if process.poll() is not None
            ]
            if failed:
                print(f"投研助手子进程异常退出：{failed}", file=sys.stderr, flush=True)
                return 1
        return 0
    finally:
        for process in reversed(processes):
            _stop_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
