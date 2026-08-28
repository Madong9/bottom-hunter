from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
from bottom_hunter.src.account_connectors import AccountConnectionService
from bottom_hunter.src.charting import MarketChartService
from bottom_hunter.src.data_provider import LongbridgeProvider
from bottom_hunter.src.longbridge_adapter import (
    LongbridgeCandleResult,
    LongbridgeClient,
    LongbridgeVerification,
    normalize_symbol,
)
from bottom_hunter.src.models import Instrument


class _Vault:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, str]] = {}

    def save(self, source: str, values: dict[str, str]) -> bool:
        self.values[source] = dict(values)
        return True

    def load(self, source: str) -> dict[str, str]:
        return dict(self.values.get(source, {}))

    def delete(self, source: str) -> None:
        self.values.pop(source, None)


def _credentials() -> dict[str, str]:
    return {
        "app_key": "app-key",
        "app_secret": "app-secret",
        "access_token": "access-token",
    }


def test_longbridge_symbol_mapping_matches_official_market_suffixes() -> None:
    assert normalize_symbol("600519.SS", "CN") == "600519.SH"
    assert normalize_symbol("000001.SZ", "CN") == "000001.SZ"
    assert normalize_symbol("03690.HK", "HK") == "3690.HK"
    assert normalize_symbol("AAPL", "US") == "AAPL.US"


def test_quote_only_client_verifies_and_converts_forward_adjusted_candles() -> None:
    captured: dict[str, object] = {}

    class Context:
        def member_id(self):
            return 7788

        def quote_level(self):
            return "Lv1"

        def quote_package_details(self):
            return [SimpleNamespace(package_name="HK LV1")]

        def history_candlesticks_by_date(
            self, symbol, period, adjust_type, start, end
        ):
            captured.update(
                {
                    "symbol": symbol,
                    "period": period,
                    "adjust_type": adjust_type,
                    "start": start,
                    "end": end,
                }
            )
            return [
                SimpleNamespace(
                    timestamp=1786579200,
                    open=Decimal("100"),
                    high=Decimal("110"),
                    low=Decimal("98"),
                    close=Decimal("108"),
                    volume=1234,
                )
            ]

    sdk = SimpleNamespace(
        Period=SimpleNamespace(Day="day"),
        AdjustType=SimpleNamespace(ForwardAdjust="forward"),
    )
    client = LongbridgeClient(
        _credentials(),
        sdk_loader=lambda: sdk,
        context_factory=lambda _values, _sdk: Context(),
    )

    verification = client.verify()
    result = client.candles(
        "3690.HK",
        "HK",
        "1d",
        start=date(2026, 8, 13),
        end=date(2026, 8, 14),
    )

    assert verification == LongbridgeVerification("7788", "Lv1", ("HK LV1",))
    assert captured["symbol"] == "3690.HK"
    assert captured["adjust_type"] == "forward"
    assert result.bars.iloc[0]["close"] == Decimal("108")
    assert result.bars.iloc[0]["volume"] == 1234


def test_pypi_sdk_direct_config_and_four_hour_aggregation_are_supported() -> None:
    captured: dict[str, object] = {}

    class Config:
        def __init__(self, app_key, app_secret, access_token, **kwargs):
            captured["config"] = (app_key, app_secret, access_token, kwargs)

    class Context:
        def __init__(self, _config):
            pass

        def quote_level(self):
            return "BMP"

        def candlesticks(self, symbol, period, count, adjust_type):
            captured["request"] = (symbol, period, count, adjust_type)
            start = pd.Timestamp("2026-08-24 09:00", tz="Asia/Shanghai")
            return [
                SimpleNamespace(
                    timestamp=(start + pd.Timedelta(hours=offset)).timestamp(),
                    open=100 + offset,
                    high=102 + offset,
                    low=99 + offset,
                    close=101 + offset,
                    volume=100,
                )
                for offset in range(8)
            ]

    sdk = SimpleNamespace(
        Config=Config,
        QuoteContext=Context,
        Period=SimpleNamespace(Min_60="60m"),
        AdjustType=SimpleNamespace(ForwardAdjust="forward"),
    )
    client = LongbridgeClient(_credentials(), sdk_loader=lambda: sdk)

    result = client.candles("600519.SS", "CN", "4h", 80)

    assert captured["config"][0:3] == ("app-key", "app-secret", "access-token")
    assert captured["request"] == ("600519.SH", "60m", 320, "forward")
    assert len(result.bars) >= 2
    assert result.quote_level == "BMP"


def test_longbridge_provider_returns_normalized_daily_bars() -> None:
    class Client:
        @staticmethod
        def configured() -> bool:
            return True

        @staticmethod
        def candles(symbol, market, timeframe, **_kwargs):
            assert (symbol, market, timeframe) == ("600519.SS", "CN", "1d")
            return LongbridgeCandleResult(
                pd.DataFrame(
                    [
                        {
                            "date": "2026-08-13",
                            "open": "100",
                            "high": "110",
                            "low": "99",
                            "close": "108",
                            "volume": "1200",
                        }
                    ]
                ),
                "Lv1",
            )

    result = LongbridgeProvider(Client()).get_daily_bars(
        Instrument("600519.SS", "贵州茅台", "CN"),
        date(2026, 8, 13),
        date(2026, 8, 13),
    )

    assert result.provider == "longbridge"
    assert result.bars.iloc[0]["close"] == 108.0
    assert "前复权" in result.warnings[0]


def test_longbridge_account_verification_does_not_write_secrets_to_metadata(tmp_path) -> None:
    class Client:
        @staticmethod
        def verify():
            return LongbridgeVerification("member-1", "Lv1", ("US LV1",))

    vault = _Vault()
    metadata = tmp_path / "connections.json"
    service = AccountConnectionService(
        metadata,
        vault=vault,
        longbridge_client_factory=lambda _credentials: Client(),
    )

    result = service.connect_longbridge(
        "app-key",
        "app-secret",
        "access-token",
        account_label="我的行情",
    )

    persisted = metadata.read_text(encoding="utf-8")
    assert result.permissions == "quote_only"
    assert "QuoteContext" in result.detail
    assert "app-secret" not in persisted
    assert "access-token" not in persisted
    assert json.loads(persisted)["longbridge"]["account_id"] == "member-1"
    assert vault.load("longbridge")["app_secret"] == "app-secret"


def test_chart_prefers_longbridge_for_equity_timeframes() -> None:
    class Client:
        @staticmethod
        def configured() -> bool:
            return True

        @staticmethod
        def candles(symbol, market, timeframe, limit):
            assert (symbol, market, timeframe, limit) == ("AAPL", "US", "5m", 80)
            index = pd.date_range("2026-08-24 09:30", periods=40, freq="5min")
            return LongbridgeCandleResult(
                pd.DataFrame(
                    {
                        "open": range(100, 140),
                        "high": range(101, 141),
                        "low": range(99, 139),
                        "close": range(100, 140),
                        "volume": [1000] * 40,
                    },
                    index=index,
                ),
                "Lv1",
            )

    result = MarketChartService(longbridge_client=Client()).fetch(
        {
            "canonical_id": "equity:US:AAPL",
            "symbol": "AAPL",
            "name": "Apple",
            "market": "US",
            "category": "global_equity",
        },
        "5m",
        80,
    )

    assert result.provider == "长桥 OpenAPI"
    assert len(result.bars) == 40
    assert result.updated_at <= datetime.now(UTC)
