"""Create a compatible local environment and install the Longbridge integration."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / ".venv"
SUPPORTED_MIN = (3, 11)
SUPPORTED_MAX = (3, 13)


def _version(executable: Path) -> tuple[int, int] | None:
    try:
        output = subprocess.check_output(
            [
                str(executable),
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        major, minor = output.split(".", 1)
        return int(major), int(minor)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def find_compatible_python() -> Path:
    candidates = [Path(sys.executable)]
    for command in ("python3.12", "python3.11"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))
    conda_root = Path(sys.executable).resolve().parents[1]
    candidates.extend((conda_root / "envs").glob("*/bin/python"))
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        version = _version(resolved)
        if version is not None and SUPPORTED_MIN <= version < SUPPORTED_MAX:
            return resolved
    raise RuntimeError("找不到 Python 3.11/3.12；请先安装兼容版本后重试")


def main() -> int:
    existing_python = VENV_DIR / "bin" / "python"
    if existing_python.is_file():
        version = _version(existing_python)
        if version is None or not (SUPPORTED_MIN <= version < SUPPORTED_MAX):
            raise RuntimeError(
                f"现有 {VENV_DIR} 不是兼容环境；请先将它改名备份，再重新运行本脚本"
            )
        interpreter = existing_python
        print(f"复用项目环境：{interpreter}（Python {version[0]}.{version[1]}）")
    else:
        source_python = find_compatible_python()
        version = _version(source_python)
        print(f"使用 {source_python} 创建 Python {version[0]}.{version[1]} 项目环境…")
        subprocess.run(
            [str(source_python), "-m", "venv", "--copies", str(VENV_DIR)],
            check=True,
        )
        interpreter = existing_python
    subprocess.run(
        [
            str(interpreter),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ],
        check=True,
    )
    subprocess.run(
        [
            str(interpreter),
            "-m",
            "pip",
            "install",
            "-e",
            f"{PROJECT_ROOT / 'bottom_hunter'}[dev,longbridge]",
        ],
        check=True,
    )
    print("\n安装完成。以后直接运行：python gui.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
