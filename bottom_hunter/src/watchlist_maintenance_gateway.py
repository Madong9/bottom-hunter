"""Backend gateway for explicit watchlist maintenance commands."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .account_watchlist import AccountWatchlistRepository, _resolve_name_only_row
from .import_lock import ImportProcessLock


class WatchlistMaintenanceGateway:
    def __init__(self, repository: AccountWatchlistRepository) -> None:
        self._repository = repository

    def source_statuses(self) -> dict[str, dict[str, Any]]:
        return self._repository.source_status()

    def execute(self, action: str, payload: dict[str, str]) -> dict[str, Any]:
        source = str(payload.get("source") or "")
        if action == "add_manual":
            row = {
                "symbol": payload.get("symbol", ""),
                "name": payload.get("name", ""),
                "market": payload.get("market", ""),
                "industry": payload.get("industry", ""),
            }
            row = _resolve_name_only_row(source, row)
            with ImportProcessLock(self._repository.state_dir, f"manual-{uuid4().hex}"):
                asset, summary = self._repository.add_manual_asset(
                    source,
                    row,
                    resolve_industry=True,
                )
            return {
                "summary": summary,
                "message": f"已添加 {asset.name or asset.symbol}。",
                "affected_sources": [source],
                "errors": {},
            }
        if action == "clear_source":
            with ImportProcessLock(self._repository.state_dir, f"clear-{uuid4().hex}"):
                summary = self._repository.clear_source(source)
            return {
                "summary": summary,
                "message": "已清空该来源的自选快照。",
                "affected_sources": [source],
                "errors": {},
            }
        if action == "refresh_linked":
            summary, refreshed, errors = self._repository.refresh_linked_files(force=True)
            return {
                "summary": summary,
                "message": (
                    f"已刷新 {len(refreshed)} 个关联文件。"
                    if not errors
                    else f"已刷新 {len(refreshed)} 个，{len(errors)} 个失败。"
                ),
                "affected_sources": refreshed,
                "errors": errors,
            }
        raise ValueError("不支持的自选维护操作。")


def build_watchlist_maintenance_gateway(
    project_dir: str | None = None,
    *,
    state_dir: str | None = None,
    config_dir: str | None = None,
) -> WatchlistMaintenanceGateway:
    kwargs = {"state_dir": state_dir, "config_dir": config_dir}
    repository = (
        AccountWatchlistRepository(**kwargs)
        if project_dir is None
        else AccountWatchlistRepository(project_dir, **kwargs)
    )
    return WatchlistMaintenanceGateway(repository)


__all__ = ["WatchlistMaintenanceGateway", "build_watchlist_maintenance_gateway"]
