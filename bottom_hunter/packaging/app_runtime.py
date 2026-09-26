"""Runtime directories and first-launch bootstrap for packaged desktop builds.

This module belongs to the distribution boundary rather than the application
backend, so launchers can prepare writable paths without importing business
modules.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR_ENV = "BOTTOM_HUNTER_PROJECT_DIR"
CONFIG_DIR_ENV = "BOTTOM_HUNTER_CONFIG_DIR"


@dataclass(frozen=True)
class ApplicationPaths:
    project_dir: Path
    config_dir: Path
    state_dir: Path
    data_dir: Path
    report_dir: Path
    resource_dir: Path
    packaged: bool


def _xdg_path(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable, "").strip()
    return Path(value).expanduser() if value else fallback


def application_paths() -> ApplicationPaths:
    """Resolve source-tree paths or isolated XDG paths for a frozen app."""

    resource_dir = Path(__file__).resolve().parents[1]
    packaged = bool(getattr(sys, "frozen", False))
    explicit_project = os.environ.get(PROJECT_DIR_ENV, "").strip()
    if explicit_project:
        project_dir = Path(explicit_project).expanduser().resolve()
    elif packaged:
        data_home = _xdg_path("XDG_DATA_HOME", Path.home() / ".local" / "share")
        project_dir = (data_home / "bottom-hunter").resolve()
    else:
        project_dir = resource_dir

    explicit_config = os.environ.get(CONFIG_DIR_ENV, "").strip()
    if explicit_config:
        config_dir = Path(explicit_config).expanduser().resolve()
    elif packaged:
        config_home = _xdg_path("XDG_CONFIG_HOME", Path.home() / ".config")
        config_dir = (config_home / "bottom-hunter").resolve()
    else:
        config_dir = project_dir / "config"

    return ApplicationPaths(
        project_dir=project_dir,
        config_dir=config_dir,
        state_dir=project_dir / "state",
        data_dir=project_dir / "data" / "raw",
        report_dir=project_dir / "reports",
        resource_dir=resource_dir,
        packaged=packaged,
    )


def _copy_once(source: Path, target: Path) -> None:
    if target.exists() or not source.is_file():
        return
    shutil.copyfile(source, target)


def prepare_application_runtime() -> ApplicationPaths:
    """Create writable app directories and seed non-secret configuration.

    Source-tree launches keep their existing layout. Frozen builds receive an
    empty watchlist and public templates; personal snapshots, reports, caches,
    databases and notification credentials are never copied into the bundle.
    """

    paths = application_paths()
    os.environ[PROJECT_DIR_ENV] = str(paths.project_dir)
    os.environ[CONFIG_DIR_ENV] = str(paths.config_dir)
    if not paths.packaged:
        return paths

    for directory in (
        paths.project_dir,
        paths.config_dir,
        paths.state_dir,
        paths.state_dir / "watchlists",
        paths.data_dir,
        paths.report_dir,
        paths.report_dir / "charts",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    defaults = paths.resource_dir / "packaging" / "defaults"
    source_config = paths.resource_dir / "config"
    _copy_once(defaults / "watchlist.yaml", paths.config_dir / "watchlist.yaml")
    _copy_once(defaults / "industry_overrides.yaml", paths.config_dir / "industry_overrides.yaml")
    _copy_once(source_config / "thresholds.yaml", paths.config_dir / "thresholds.yaml")
    _copy_once(source_config / "research.yaml", paths.config_dir / "research.yaml")
    _copy_once(source_config / "notify.example.yaml", paths.config_dir / "notify.yaml")
    _copy_once(paths.resource_dir / "data" / "fundamentals.csv", paths.project_dir / "data" / "fundamentals.csv")
    _copy_once(
        paths.resource_dir / "data" / "research_import_template.csv",
        paths.project_dir / "data" / "research_import_template.csv",
    )

    # Backend compatibility: existing read-only helpers resolve
    # ``PROJECT_DIR/config``. Keep that location linked to the XDG config dir.
    project_config = paths.project_dir / "config"
    if not project_config.exists():
        try:
            project_config.symlink_to(paths.config_dir, target_is_directory=True)
        except OSError:
            project_config.mkdir(parents=True, exist_ok=True)
            for source in paths.config_dir.iterdir():
                _copy_once(source, project_config / source.name)

    try:
        paths.config_dir.chmod(0o700)
        notify_path = paths.config_dir / "notify.yaml"
        if notify_path.exists():
            notify_path.chmod(0o600)
    except OSError:
        pass
    return paths


__all__ = [
    "ApplicationPaths",
    "CONFIG_DIR_ENV",
    "PROJECT_DIR_ENV",
    "application_paths",
    "prepare_application_runtime",
]
