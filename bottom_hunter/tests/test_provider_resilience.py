from __future__ import annotations

import json
from datetime import date

import pytest

from bottom_hunter.src.data_provider import (
    BinanceKlineProvider,
    CboeVixProvider,
    CircuitBreakerProvider,
    MarketDataProvider,
    NetworkDataProviderError,
    OkxCandleProvider,
    ProviderNotApplicable,
    StooqProvider,
    TencentProvider,
)
from bottom_hunter.src.models import Instrument


def test_tencent_parses_a_share_and_resolves_us(monkeypatch) -> None:
    provider = TencentProvider()

    def fake_read(url: str) -> bytes:
        if "smartbox" in url:
            return b'v_hint="us~nvda.oq~NVDA~nvda~GP"'
        code = "usnvda.oq" if "usnvda" in url.lower() else "sz300308"
        return json.dumps(
            {
                "code": 0,
                "msg": "",
                "data": {
                    code: {
                        "day": [
                            ["2026-08-12", "10", "11", "12", "9", "100"],
                            ["2026-08-13", "11", "12", "13", "10", "120"],
                        ]
                    }
                },
            }
        ).encode()

    monkeypatch.setattr(provider, "_read", fake_read)
    cn = provider.get_daily_bars(
        Instrument("300308.SZ", "中际旭创", "CN"),
        date(2026, 8, 1),
        date(2026, 8, 13),
    )
    us = provider.get_daily_bars(
        Instrument("NVDA", "英伟达", "US"),
        date(2026, 8, 1),
        date(2026, 8, 13),
    )
    assert cn.bars.iloc[-1]["close"] == 12
    assert us.bars.iloc[-1]["volume"] == 120
    assert us.provider == "tencent"


def test_cboe_vix_accepts_zero_volume(monkeypatch) -> None:
    provider = CboeVixProvider()
    csv_bytes = b"DATE,OPEN,HIGH,LOW,CLOSE\n08/12/2026,17,18,16,17.5\n"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return csv_bytes

    monkeypatch.setattr("bottom_hunter.src.data_provider.urlopen", lambda *a, **k: Response())
    result = provider.get_daily_bars(
        Instrument("^VIX", "VIX", "US", volume_optional=True),
        date(2026, 8, 1),
        date(2026, 8, 13),
    )
    assert result.bars.iloc[-1]["close"] == 17.5
    assert result.bars.iloc[-1]["volume"] == 0


def test_circuit_breaker_skips_after_network_failures() -> None:
    class Failing(MarketDataProvider):
        name = "failing"

        def __init__(self):
            self.calls = 0

        def get_daily_bars(self, instrument, start, end):
            self.calls += 1
            raise NetworkDataProviderError("offline")

    failing = Failing()
    provider = CircuitBreakerProvider(failing, failure_threshold=2)
    instrument = Instrument("TEST", "TEST", "US")
    with pytest.raises(NetworkDataProviderError):
        provider.get_daily_bars(instrument, date(2026, 1, 1), date(2026, 1, 2))
    with pytest.raises(NetworkDataProviderError):
        provider.get_daily_bars(instrument, date(2026, 1, 1), date(2026, 1, 2))
    with pytest.raises(ProviderNotApplicable):
        provider.get_daily_bars(instrument, date(2026, 1, 1), date(2026, 1, 2))
    assert failing.calls == 2


def test_stooq_does_not_request_unsupported_market() -> None:
    with pytest.raises(ProviderNotApplicable):
        StooqProvider().get_daily_bars(
            Instrument("300308.SZ", "中际旭创", "CN"),
            date(2026, 1, 1),
            date(2026, 1, 2),
        )


def test_binance_reads_imported_crypto_source_symbol(monkeypatch) -> None:
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                [1786579200000, "100", "110", "90", "105", "1234"],
                [1786665600000, "105", "115", "101", "112", "1500"],
            ]

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs.get("params") or {})
        return Response()

    monkeypatch.setattr("bottom_hunter.src.data_provider.requests.get", fake_get)
    instrument = Instrument(
        "BTC-USDT",
        "Bitcoin",
        "CRYPTO",
        category="crypto",
        source_symbols={"binance": "BTCUSDT"},
    )
    result = BinanceKlineProvider().get_daily_bars(
        instrument, date(2026, 8, 13), date(2026, 8, 14)
    )
    assert captured["symbol"] == "BTCUSDT"
    assert result.provider == "binance_klines"
    assert captured["url"] == "https://data-api.binance.vision/api/v3/klines"
    assert result.bars.iloc[-1]["close"] == 112


def test_okx_ignores_unfinished_daily_candle(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": "0",
                "data": [
                    ["1786665600000", "105", "115", "101", "112", "1500", "", "", "0"],
                    ["1786579200000", "100", "110", "90", "105", "1234", "", "", "1"],
                ],
            }

    monkeypatch.setattr(
        "bottom_hunter.src.data_provider.requests.get", lambda *args, **kwargs: Response()
    )
    instrument = Instrument(
        "BTC-USDT",
        "Bitcoin",
        "CRYPTO",
        category="crypto",
        source_symbols={"okx": "BTC-USDT"},
    )
    result = OkxCandleProvider().get_daily_bars(
        instrument, date(2026, 8, 13), date(2026, 8, 14)
    )
    assert len(result.bars) == 1
    assert result.bars.iloc[0]["close"] == 105


def test_okx_can_supply_fallback_bars_for_binance_only_pair(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": "0",
                "data": [
                    ["1786579200000", "100", "110", "90", "105", "1234", "", "", "1"]
                ],
            }

    def fake_get(_url, **kwargs):
        captured.update(kwargs.get("params") or {})
        return Response()

    monkeypatch.setattr("bottom_hunter.src.data_provider.requests.get", fake_get)
    instrument = Instrument(
        "BTC-USDT",
        "Bitcoin",
        "CRYPTO",
        category="crypto",
        source_symbols={"binance": "BTCUSDT"},
    )

    result = OkxCandleProvider().get_daily_bars(
        instrument, date(2026, 8, 13), date(2026, 8, 13)
    )

    assert captured["instId"] == "BTC-USDT"
    assert result.provider == "okx_candles"
    assert any("备用行情" in warning for warning in result.warnings)
    OkxCandleProvider,
