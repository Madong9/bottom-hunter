"""PHASE 4-D4-A — zero-write backend import preparation tests."""

from __future__ import annotations

import json
from pathlib import Path

from bottom_hunter.src import account_watchlist as watchlist_module
from bottom_hunter.src.account_watchlist import AccountWatchlistRepository, IndustryResolver
from bottom_hunter.src.import_transaction import PreparedImport


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_prepare_does_not_change_existing_repository_files(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    repository = AccountWatchlistRepository(project)
    existing = _write(
        tmp_path / "binance.csv",
        "symbol,name,asset_type,underlying_symbol,market,industry\n"
        "AAPLUSDT,Apple,tokenized_stock,AAPL,US,Technology Hardware\n",
    )
    repository.import_file("binance", existing, resolve_industries=False)
    selected = _write(
        tmp_path / "tonghuashun.csv",
        "symbol,name,industry\nAAPL,Apple,Technology Hardware\n600519,贵州茅台,食品饮料\n",
    )
    before = _tree_snapshot(project)
    monkeypatch.setattr(watchlist_module, "_utc_now", lambda: "2026-09-02T08:00:00+00:00")

    prepared = repository.prepare_import(
        "tonghuashun",
        selected,
        "main",
        resolve_industries=False,
        transaction_id="txn-prepare-1",
    )

    assert _tree_snapshot(project) == before
    assert prepared.imported_count == 2
    assert prepared.merged_count == 2
    assert prepared.duplicate_count == 1
    assert prepared.generated_sector_count == 2
    assert {artifact.kind for artifact in prepared.planned_artifacts} == {
        "source_snapshot",
        "active_watchlist",
        "watchlist_summary",
    }


def test_prepare_never_calls_persistence_or_resolver_save(tmp_path, monkeypatch) -> None:
    repository = AccountWatchlistRepository(tmp_path / "project")
    selected = _write(tmp_path / "watchlist.csv", "symbol,name\nAAPL,Apple\n")

    def fail_persistence(*_args, **_kwargs):
        raise AssertionError("prepare_import attempted persistence")

    def fake_resolve(self, asset):
        resolved = {
            "name": "Apple",
            "industry": "Technology Hardware",
            "source": "fake-profile",
        }
        self.cache[asset.canonical_id] = resolved
        return resolved

    monkeypatch.setattr(watchlist_module, "_atomic_json", fail_persistence)
    monkeypatch.setattr(watchlist_module, "_atomic_yaml", fail_persistence)
    monkeypatch.setattr(IndustryResolver, "save", fail_persistence)
    monkeypatch.setattr(IndustryResolver, "resolve_profile", fake_resolve)

    prepared = repository.prepare_import(
        "tonghuashun",
        selected,
        resolve_industries=True,
        transaction_id="txn-no-write",
    )

    assert prepared.parsed_assets[0].industry == "Technology Hardware"
    assert "industry_cache" in {artifact.kind for artifact in prepared.planned_artifacts}
    assert not repository.industry_cache_path.exists()
    assert not repository.source_snapshot_path("tonghuashun").exists()
    assert not repository.active_watchlist_path.exists()
    assert not repository.summary_path.exists()


def test_prepare_result_is_stable_for_same_inputs(tmp_path, monkeypatch) -> None:
    repository = AccountWatchlistRepository(tmp_path / "project")
    selected = _write(
        tmp_path / "watchlist.csv",
        "symbol,name,industry\n600519,贵州茅台,食品饮料\n",
    )
    monkeypatch.setattr(watchlist_module, "_utc_now", lambda: "2026-09-02T08:00:00+00:00")

    first = repository.prepare_import(
        "tonghuashun",
        selected,
        resolve_industries=False,
        transaction_id="txn-stable",
    )
    second = repository.prepare_import(
        "tonghuashun",
        selected,
        resolve_industries=False,
        transaction_id="txn-stable",
    )

    assert first == second


def test_prepared_import_is_json_serializable(tmp_path, monkeypatch) -> None:
    repository = AccountWatchlistRepository(tmp_path / "project")
    selected = _write(tmp_path / "okx.txt", "BTC-USDT\n")
    monkeypatch.setattr(watchlist_module, "_utc_now", lambda: "2026-09-02T08:00:00+00:00")

    prepared = repository.prepare_import(
        "okx",
        selected,
        resolve_industries=False,
        transaction_id="txn-json",
    )
    encoded = json.dumps(prepared.to_dict(), ensure_ascii=False, sort_keys=True)

    assert isinstance(prepared, PreparedImport)
    assert '"transaction_id": "txn-json"' in encoded
    assert '"symbol": "BTC-USDT"' in encoded


def test_legacy_import_file_still_writes_same_outputs(tmp_path) -> None:
    repository = AccountWatchlistRepository(tmp_path / "project")
    selected = _write(tmp_path / "binance.csv", "symbol,name\nBTCUSDT,Bitcoin\nETHUSDT,Ethereum\n")

    result = repository.import_file("binance", selected, "main", resolve_industries=False)

    assert result.imported_count == 2
    assert result.merged_count == 2
    assert result.duplicate_count == 0
    assert result.generated_sector_count == 1
    assert result.active_watchlist == repository.active_watchlist_path
    assert repository.source_snapshot_path("binance").is_file()
    assert repository.active_watchlist_path.is_file()
    assert repository.summary_path.is_file()
    assert repository.summary()["source_counts"] == {
        "tonghuashun": 0,
        "binance": 2,
        "okx": 0,
    }
