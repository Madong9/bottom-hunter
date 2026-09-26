"""Linux desktop packaging and frozen-runtime safety checks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PACKAGING_DIR = PACKAGE_DIR / "packaging"


def test_source_runtime_keeps_repository_layout(monkeypatch) -> None:
    from bottom_hunter.packaging.app_runtime import application_paths

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("BOTTOM_HUNTER_PROJECT_DIR", raising=False)
    monkeypatch.delenv("BOTTOM_HUNTER_CONFIG_DIR", raising=False)

    paths = application_paths()

    assert paths.packaged is False
    assert paths.project_dir == PACKAGE_DIR
    assert paths.config_dir == PACKAGE_DIR / "config"


def test_packaged_runtime_seeds_only_public_empty_templates(tmp_path: Path, monkeypatch) -> None:
    from bottom_hunter.packaging.app_runtime import prepare_application_runtime

    data_home = tmp_path / "share"
    config_home = tmp_path / "config"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("BOTTOM_HUNTER_PROJECT_DIR", raising=False)
    monkeypatch.delenv("BOTTOM_HUNTER_CONFIG_DIR", raising=False)

    paths = prepare_application_runtime()

    watchlist = yaml.safe_load((paths.config_dir / "watchlist.yaml").read_text(encoding="utf-8"))
    notify = yaml.safe_load((paths.config_dir / "notify.yaml").read_text(encoding="utf-8"))
    assert paths.project_dir == data_home / "bottom-hunter"
    assert paths.config_dir == config_home / "bottom-hunter"
    assert watchlist["sectors"] == {}
    assert notify["enabled"] is False
    assert notify["channels"]["serverchan"]["sendkey"] == ""
    assert notify["channels"]["wecom"]["webhook"] == ""
    assert notify["channels"]["wxpusher"]["app_token"] == ""
    assert notify["channels"]["telegram"]["bot_token"] == ""
    assert not list(paths.report_dir.glob("daily_report_*"))
    assert not list(paths.state_dir.glob("*.db"))
    assert (paths.project_dir / "config" / "thresholds.yaml").is_file()
    assert os.stat(paths.config_dir / "notify.yaml").st_mode & 0o777 == 0o600


def test_frozen_task_commands_reenter_application_binary(tmp_path: Path, monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages.task_adapter import TaskCommandAdapter

    project = tmp_path / "data" / "bottom-hunter"
    config = tmp_path / "config" / "bottom-hunter"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("BOTTOM_HUNTER_PROJECT_DIR", str(project))
    monkeypatch.setenv("BOTTOM_HUNTER_CONFIG_DIR", str(config))

    scan = TaskCommandAdapter().build_scan("", True, 3)
    backtest = TaskCommandAdapter().build_backtest("2026-01-01", "2026-02-01", True, 2)

    assert scan.program == sys.executable
    assert scan.arguments[0] == "--internal-scan"
    assert "--state-db" in scan.arguments
    assert "scanner.py" not in " ".join(scan.arguments)
    assert backtest.arguments[0] == "--internal-backtest"
    assert "--state-db" not in backtest.arguments
    assert str(config) in scan.arguments and str(project / "reports") in scan.arguments


def test_packaging_recipe_excludes_personal_runtime_data() -> None:
    spec = (PACKAGING_DIR / "bottom-hunter.spec").read_text(encoding="utf-8")
    script = (PACKAGING_DIR / "build_linux.sh").read_text(encoding="utf-8")
    desktop = (PACKAGING_DIR / "bottom-hunter.desktop").read_text(encoding="utf-8")

    assert '"config/notify.example.yaml"' in spec
    assert '"config/notify.yaml"' not in spec
    assert "state/" not in spec and "reports/" not in spec
    assert '{".qml", ".qsb"}' in spec
    assert "PySide6.QtQuickControls2" in spec
    assert '"libssl.so.3"' in spec
    assert '"libcrypto.so.3"' in spec
    assert "dpkg-deb --build --root-owner-group" in script
    assert "appimagetool-$APPIMAGE_ARCH.AppImage" in script
    assert "Terminal=false" in desktop
    assert "Exec=bottom-hunter" in desktop
