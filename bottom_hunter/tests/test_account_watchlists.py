from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from bottom_hunter.src import account_watchlist as watchlist_module
from bottom_hunter.src.account_connectors import (
    AccountConnectionService,
    RestrictedLocationError,
    UnsafeApiPermission,
)
from bottom_hunter.src.account_watchlist import (
    UNKNOWN_INDUSTRY,
    AccountWatchlistRepository,
    IndustryResolver,
    normalize_import_row,
    parse_watchlist_file,
)
from bottom_hunter.src.trading_calendar import TradingCalendarService


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_platform_rows_are_normalized_without_mixing_tokenized_stocks_into_crypto() -> None:
    a_share = normalize_import_row(
        "tonghuashun", {"证券代码": "600519", "名称": "贵州茅台", "所属行业": "食品饮料"}
    )
    assert a_share.symbol == "600519.SS"
    assert a_share.category == "cn_equity"

    crypto = normalize_import_row("binance", {"symbol": "BTCUSDT", "name": "Bitcoin"})
    assert crypto.symbol == "BTC-USDT"
    assert crypto.category == "crypto"

    tokenized = normalize_import_row(
        "binance",
        {
            "symbol": "AAPLUSDT",
            "asset_type": "tokenized_stock",
            "underlying_symbol": "AAPL",
            "name": "Apple",
            "industry": "Technology Hardware",
        },
    )
    assert tokenized.symbol == "AAPL"
    assert tokenized.market == "US"
    assert tokenized.category == "global_equity"
    assert tokenized.tokenized_stock is True

    okx_stock = normalize_import_row("okx", {"symbol": "XAAPL-USDT", "name": "Apple"})
    assert okx_stock.symbol == "AAPL"
    assert okx_stock.category == "global_equity"
    assert okx_stock.tokenized_stock is True

    bstock = normalize_import_row(
        "binance", {"symbol": "TSLABUSDT", "asset_type": "stock", "name": "Tesla bStock"}
    )
    assert bstock.symbol == "TSLA"
    assert bstock.tokenized_stock is True

    prefixed_hk = normalize_import_row(
        "tonghuashun", {"股票代码": "HK1810", "股票名称": "小米集团-W"}
    )
    assert prefixed_hk.symbol == "1810.HK"
    assert prefixed_hk.market == "HK"
    assert prefixed_hk.category == "global_equity"


def test_ths_blk_and_exchange_text_files_are_supported(tmp_path) -> None:
    ths = _write(tmp_path / "zxg.blk", "0|000001\n1|600519\n")
    assets = parse_watchlist_file(ths, "tonghuashun")
    assert {item.symbol for item in assets} == {"000001.SZ", "600519.SS"}

    okx = _write(tmp_path / "okx.txt", "BTC-USDT\nETH-USDT\n")
    assets = parse_watchlist_file(okx, "okx")
    assert {item.symbol for item in assets} == {"BTC-USDT", "ETH-USDT"}


def test_tonghuashun_sel_stockblock_and_beijing_symbols_are_supported(tmp_path) -> None:
    selected = tmp_path / "自选股.sel"
    selected.write_bytes(
        (2).to_bytes(2, "little")
        + b"\x07\x21" + b"000001"
        + b"\x07\x11" + b"600519"
    )
    assert {item.symbol for item in parse_watchlist_file(selected, "tonghuashun")} == {
        "000001.SZ",
        "600519.SS",
    }

    stock_block = _write(
        tmp_path / "StockBlock.ini",
        "[BLOCK_NAME_MAP_TABLE]\nSELF=自选股\n"
        "[BLOCK_STOCK_CONTEXT]\nSELF=33:000001,17:600519,87:830799\n",
    )
    symbols = {item.symbol for item in parse_watchlist_file(stock_block, "tonghuashun")}
    assert symbols == {"000001.SZ", "600519.SS", "830799.BJ"}


def test_tonghuashun_excel_with_title_row_and_common_chinese_headers(tmp_path) -> None:
    spreadsheet = tmp_path / "我的自选.xlsx"
    pd.DataFrame(
        [
            ["我的同花顺自选", "", ""],
            ["股票代码", "股票名称", "所属行业"],
            ["600519", "贵州茅台", "食品饮料"],
            ["00700", "腾讯控股", "软件与互联网"],
        ]
    ).to_excel(spreadsheet, header=False, index=False)

    assets = parse_watchlist_file(spreadsheet, "tonghuashun")

    assert {item.symbol for item in assets} == {"600519.SS", "00700.HK"}
    assert {item.name for item in assets} == {"贵州茅台", "腾讯控股"}


def test_binance_excel_accepts_base_symbols_and_classifies_leveraged_etfs(tmp_path) -> None:
    spreadsheet = tmp_path / "币安自选.xlsx"
    pd.DataFrame(
        [
            ["币安自选清单", "", "", ""],
            ["截图整理", "", "", ""],
            ["", "", "", ""],
            ["序号", "代码", "名称", "类别"],
            [1, "DOGE", "Dogecoin", "加密资产"],
            [2, "PDDL", "2倍做多PDD ETF", "杠杆ETF"],
            [3, "USDT", "TetherUS", "稳定币"],
        ]
    ).to_excel(spreadsheet, header=False, index=False)
    failures: list[str] = []

    assets = parse_watchlist_file(spreadsheet, "binance", failures_out=failures)

    doge = next(item for item in assets if item.symbol == "DOGE-USDT")
    assert doge.source_symbol == "DOGEUSDT"
    assert doge.name == "Dogecoin"
    etf = next(item for item in assets if item.symbol == "PDDL")
    assert etf.category == "global_equity"
    assert etf.tokenized_stock is True
    assert any("USDT" in failure for failure in failures)


def test_tonghuashun_spreadsheet_preserves_market_type_and_skips_unsupported(
    tmp_path,
) -> None:
    spreadsheet = tmp_path / "截图自选.xlsx"
    pd.DataFrame(
        [
            ["名称（按截图）", "代码", "市场/类别", "证券类型"],
            ["小米集团-W", "HK1810", "港股", "股票"],
            ["红利ETF易方达", "515180", "A股", "ETF"],
            ["光刻胶", "885864", "同花顺", "概念指数"],
        ]
    ).to_excel(spreadsheet, header=False, index=False)
    failures: list[str] = []

    assets = parse_watchlist_file(spreadsheet, "tonghuashun", failures_out=failures)

    by_symbol = {item.symbol: item for item in assets}
    assert set(by_symbol) == {"1810.HK", "515180.SS"}
    assert by_symbol["1810.HK"].name == "小米集团-W"
    assert by_symbol["1810.HK"].market == "HK"
    assert by_symbol["515180.SS"].asset_type == "etf"
    assert by_symbol["515180.SS"].industry == "红利与价值策略"
    assert len(failures) == 1
    assert "概念指数" in failures[0]


def test_tonghuashun_name_only_csv_requires_one_exact_match(tmp_path, monkeypatch) -> None:
    source = _write(tmp_path / "names.csv", "股票名称,市场\n贵州茅台,A股\n")

    def fake_search(query: str, market_hint: str = "", timeout: int = 8):
        assert (query, market_hint, timeout) == ("贵州茅台", "A股", 8)
        return [
            {
                "symbol": "600519.SS",
                "code": "600519",
                "name": "贵州茅台",
                "market": "CN",
                "security_type": "沪A",
            }
        ]

    monkeypatch.setattr(watchlist_module, "search_equities", fake_search)

    assets = parse_watchlist_file(source, "tonghuashun")

    assert len(assets) == 1
    assert assets[0].symbol == "600519.SS"
    assert assets[0].name == "贵州茅台"


def test_equity_profile_fills_code_only_name_and_industry(tmp_path, monkeypatch) -> None:
    payload = {
        "data": {
            "f57": "600519",
            "f58": "贵州茅台",
            "f127": "白酒Ⅱ",
        }
    }

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    calls: list[str] = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        assert timeout == 4
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(watchlist_module, "urlopen", fake_urlopen)
    resolver = IndustryResolver(tmp_path / "industry_cache.json")
    asset = normalize_import_row("tonghuashun", {"股票代码": "600519"})

    profile = resolver.resolve_profile(asset)
    cached_profile = resolver.resolve_profile(asset)

    assert profile["name"] == "贵州茅台"
    assert profile["industry"] == "白酒Ⅱ"
    assert cached_profile == profile
    assert len(calls) == 1


def test_repository_merges_overlaps_and_generates_only_account_sectors(tmp_path) -> None:
    project = tmp_path / "project"
    config_dir = project / "config"
    state_dir = project / "state"
    config_dir.mkdir(parents=True)
    repository = AccountWatchlistRepository(project, state_dir=state_dir, config_dir=config_dir)

    ths = _write(
        tmp_path / "ths.csv",
        "symbol,name,industry\n600519,贵州茅台,食品饮料\nAAPL,Apple,Technology Hardware\n",
    )
    binance = _write(
        tmp_path / "binance.csv",
        "symbol,name,asset_type,underlying_symbol,market,industry\n"
        "BTCUSDT,Bitcoin,crypto,,,\n"
        "AAPLUSDT,Apple Token,tokenized_stock,AAPL,US,Technology Hardware\n",
    )
    okx = _write(tmp_path / "okx.txt", "BTC-USDT\n")
    repository.import_file("tonghuashun", ths, "ths-user", resolve_industries=False)
    repository.import_file("binance", binance, "binance-user", resolve_industries=False)
    result = repository.import_file("okx", okx, "okx-user", resolve_industries=False)

    assert result.merged_count == 3
    assert result.duplicate_count == 2
    summary = repository.summary()
    assert summary["category_counts"] == {
        "crypto": 1,
        "global_equity": 1,
        "cn_equity": 1,
    }
    apple = next(item for item in summary["assets"] if item["symbol"] == "AAPL")
    assert apple["sources"] == ["tonghuashun", "binance"]
    assert apple["tokenized_stock"] is True
    bitcoin = next(item for item in summary["assets"] if item["category"] == "crypto")
    assert bitcoin["sources"] == ["binance", "okx"]

    watchlist_text = repository.active_watchlist_path.read_text(encoding="utf-8")
    assert "PDD" not in watchlist_text
    assert "NVDA" not in watchlist_text
    assert "crypto_all" in watchlist_text
    assert "A股 · 食品饮料" in watchlist_text


def test_manual_industry_override_rebuilds_dynamic_sector(tmp_path) -> None:
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    repository = AccountWatchlistRepository(project)
    source = _write(tmp_path / "ths.csv", "symbol,name\nAAPL,Apple\n")
    repository.import_file("tonghuashun", source, resolve_industries=False)
    summary = repository.summary()
    asset = summary["assets"][0]
    assert asset["industry"] == UNKNOWN_INDUSTRY
    updated = repository.update_industry(asset["canonical_id"], "Consumer Electronics")
    assert updated["unresolved_industry_count"] == 0
    assert "Consumer Electronics" in repository.active_watchlist_path.read_text(encoding="utf-8")


def test_repository_refreshes_previously_linked_export_file(tmp_path) -> None:
    repository = AccountWatchlistRepository(tmp_path)
    export = _write(tmp_path / "binance.csv", "symbol,name\nBTCUSDT,Bitcoin\n")
    repository.import_file("binance", export, "main", resolve_industries=False)
    assert repository.changed_linked_sources() == []
    unchanged_summary, unchanged, unchanged_errors = repository.refresh_linked_files(force=False)
    assert unchanged == []
    assert unchanged_errors == {}
    assert [item["symbol"] for item in unchanged_summary["assets"]] == ["BTC-USDT"]

    export.write_text("symbol,name\nETHUSDT,Ethereum\n", encoding="utf-8")
    assert repository.changed_linked_sources() == ["binance"]

    summary, refreshed, errors = repository.refresh_linked_files(force=False)

    assert refreshed == ["binance"]
    assert errors == {}
    assert [item["symbol"] for item in summary["assets"]] == ["ETH-USDT"]
    assert repository.changed_linked_sources() == []


def test_manual_stock_survives_linked_file_refresh(tmp_path) -> None:
    repository = AccountWatchlistRepository(tmp_path)
    spreadsheet = _write(tmp_path / "ths.csv", "股票代码,股票名称\nAAPL,苹果\n")
    repository.import_file("tonghuashun", spreadsheet, "main", resolve_industries=False)
    repository.add_manual_asset(
        "tonghuashun",
        {"股票代码": "600519", "股票名称": "贵州茅台", "行业": "食品饮料"},
        resolve_industry=False,
    )
    spreadsheet.write_text("股票代码,股票名称\nMSFT,微软\n", encoding="utf-8")

    summary, refreshed, errors = repository.refresh_linked_files()

    assert refreshed == ["tonghuashun"]
    assert errors == {}
    assert {item["symbol"] for item in summary["assets"]} == {"MSFT", "600519.SS"}
    assert repository.source_status()["tonghuashun"]["manual_count"] == 1


def test_binance_manual_pair_creates_local_account_watchlist(tmp_path) -> None:
    repository = AccountWatchlistRepository(tmp_path)

    asset, summary = repository.add_manual_asset(
        "binance",
        {"symbol": "BTCUSDT"},
        "我的币安",
        resolve_industry=False,
    )

    assert asset.symbol == "BTC-USDT"
    assert summary["asset_count"] == 1
    status = repository.source_status()["binance"]
    assert status["account_alias"] == "我的币安"
    assert status["manual_count"] == 1
    assert status["import_file"] == ""


class _MemoryVault:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, str]] = {}

    def save(self, source: str, values: dict[str, str]) -> bool:
        self.values[source] = values
        return True

    def load(self, source: str) -> dict[str, str]:
        return self.values.get(source, {})

    def delete(self, source: str) -> None:
        self.values.pop(source, None)


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class _Session:
    def __init__(self, restrictions: dict | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.restrictions = restrictions or {"enableReading": True}

    def get(self, url: str, **_kwargs):
        if "apiRestrictions" in url:
            return _Response(self.restrictions)
        if "api/v3/account" in url:
            return _Response({"uid": 12345, "accountType": "SPOT"})
        if "api/v5/account/config" in url:
            return _Response({"code": "0", "data": [{"uid": "okx-1", "perm": "read_only"}]})
        raise AssertionError(url)


def test_account_connectors_accept_only_read_only_keys(tmp_path) -> None:
    vault = _MemoryVault()
    service = AccountConnectionService(
        tmp_path / "connections.json", vault=vault, session=_Session()
    )
    binance = service.connect_binance("api-key", "secret", account_label="my-binance")
    assert binance.permissions == "read_only"
    assert binance.persisted_in_keyring is True
    okx = service.connect_okx("api-key", "secret", "pass", account_label="my-okx")
    assert okx.account_id == "okx-1"
    metadata = json.loads((tmp_path / "connections.json").read_text(encoding="utf-8"))
    assert "secret" not in json.dumps(metadata)

    unsafe = AccountConnectionService(
        tmp_path / "unsafe.json",
        vault=_MemoryVault(),
        session=_Session({"enableReading": True, "enableWithdrawals": True}),
    )
    with pytest.raises(UnsafeApiPermission, match="拒绝关联"):
        unsafe.connect_binance("api-key", "secret")


def test_binance_restricted_location_has_actionable_non_bypass_message() -> None:
    response = _Response(
        {
            "code": 0,
            "msg": (
                "Service unavailable from a restricted location according to "
                "'b. Eligibility'"
            ),
        },
        status_code=451,
    )

    with pytest.raises(RestrictedLocationError) as captured:
        AccountConnectionService._safe_response(response, "币安")

    message = str(captured.value)
    assert "不是 API Key" in message
    assert "直接导入币安自选文件" in message
    assert "不会绕过" in message


def test_continuous_calendar_uses_last_completed_utc_day() -> None:
    service = TradingCalendarService(
        {
            "CRYPTO": {
                "calendar": "24/7",
                "timezone": "UTC",
                "close_time": "00:00",
            }
        }
    )
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    session, reliable = service.latest_completed_session("CRYPTO", now=now)
    assert reliable is True
    assert session == date(2026, 8, 13)
    assert len(service.sessions_between("CRYPTO", date(2026, 8, 1), date(2026, 8, 3))) == 3
