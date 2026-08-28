from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from bottom_hunter.src.charting import (
    ChartAnnotationStore,
    ChartDataError,
    MarketChartService,
    calculate_chart_indicators,
)
from bottom_hunter.src.models import DataResult


class _Response:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(self.status_code)

    def json(self):
        return self.payload


class _Session:
    def __init__(self, responses: list[object]) -> None:
        self.headers: dict[str, str] = {}
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.responses.pop(0))


def test_chart_annotations_are_scoped_by_asset_and_timeframe(tmp_path: Path) -> None:
    path = tmp_path / "drawings.json"
    store = ChartAnnotationStore(path)
    annotations = [
        {"type": "horizontal", "price": 100.5},
        {
            "type": "trend",
            "points": [["2026-08-01T00:00:00", 95], ["2026-08-02T00:00:00", 101]],
        },
    ]
    store.save("equity:US:AAPL", "1d", annotations)

    reloaded = ChartAnnotationStore(path)

    assert reloaded.get("equity:US:AAPL", "1d") == annotations
    assert reloaded.get("equity:US:AAPL", "5m") == []
    assert reloaded.get("equity:US:MSFT", "1d") == []


def test_okx_string_timestamps_are_parsed_as_milliseconds() -> None:
    session = _Session(
        [
            {
                "code": "0",
                "data": [
                    ["1786825800000", "100", "103", "99", "102", "12", "0", "0", "1"],
                    ["1786825500000", "98", "101", "97", "100", "8", "0", "0", "1"],
                ],
            }
        ]
    )
    service = MarketChartService(session=session)
    asset = {
        "canonical_id": "crypto:BTC",
        "symbol": "BTC-USDT",
        "name": "Bitcoin",
        "market": "CRYPTO",
        "category": "crypto",
        "source_symbols": {"okx": "BTC-USDT"},
    }

    result = service.fetch(asset, "5m", 80)

    assert len(result.bars) == 2
    assert result.bars.index.is_monotonic_increasing
    assert result.bars.iloc[-1]["close"] == 102
    assert session.calls[0][1]["params"]["bar"] == "5m"


def test_tencent_intraday_uses_expected_period_key() -> None:
    session = _Session(
        [
            {
                "code": 0,
                "data": {
                    "sh600519": {
                        "m5": [
                            ["202608141455", "100", "101", "102", "99", "20"],
                            ["202608141500", "101", "103", "104", "100", "30"],
                        ]
                    }
                },
            }
        ]
    )
    service = MarketChartService(session=session)
    asset = {
        "canonical_id": "equity:CN:600519.SS",
        "symbol": "600519.SS",
        "name": "贵州茅台",
        "market": "CN",
        "category": "cn_equity",
    }

    result = service.fetch(asset, "5m", 80)

    assert len(result.bars) == 2
    assert result.bars.iloc[-1]["high"] == 104
    assert session.calls[0][1]["params"]["param"].startswith("sh600519,m5,")


def test_chart_cleaning_preserves_market_wall_clock_time() -> None:
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-08-14 09:30", tz="America/New_York")],
            "open": [100],
            "high": [102],
            "low": [99],
            "close": [101],
            "volume": [10],
        }
    )

    bars = MarketChartService._clean_bars(frame)

    assert bars.index[0] == pd.Timestamp("2026-08-14 09:30")


def test_equity_daily_chart_falls_back_when_tencent_is_unavailable(monkeypatch) -> None:
    class DailyProvider:
        def get_daily_bars(self, instrument, start: date, end: date) -> DataResult:
            assert instrument.symbol == "3690.HK"
            index = pd.date_range(end=end, periods=40, freq="D")
            bars = pd.DataFrame(
                {
                    "open": range(80, 120),
                    "high": range(82, 122),
                    "low": range(78, 118),
                    "close": range(81, 121),
                    "volume": [1000] * 40,
                },
                index=index,
            )
            return DataResult(
                instrument.symbol,
                bars,
                "local_csv",
                datetime.now(UTC),
            )

    service = MarketChartService(daily_provider=DailyProvider())
    monkeypatch.setattr(
        service,
        "_fetch_tencent_period",
        lambda *_args: (_ for _ in ()).throw(ChartDataError("HTTP 501")),
    )
    asset = {
        "canonical_id": "equity:HK:3690.HK",
        "symbol": "3690.HK",
        "name": "美团-W",
        "market": "HK",
        "category": "global_equity",
    }

    result = service.fetch(asset, "1d", 30)

    assert len(result.bars) == 30
    assert result.provider == "本地扫描缓存"
    assert "自动切换" in result.note


def test_chart_indicators_are_complete_and_do_not_use_future_bars() -> None:
    index = pd.date_range("2026-01-01", periods=120, freq="D")
    frame = pd.DataFrame(
        {
            "open": range(100, 220),
            "high": range(103, 223),
            "low": range(98, 218),
            "close": range(101, 221),
            "volume": range(1000, 1120),
        },
        index=index,
    )

    prefix = calculate_chart_indicators(frame.iloc[:80])
    complete = calculate_chart_indicators(frame)

    expected = {
        "ma5",
        "ma10",
        "ma20",
        "ma60",
        "ema12",
        "ema26",
        "boll_upper",
        "boll_mid",
        "boll_lower",
        "macd_dif",
        "macd_dea",
        "macd_hist",
        "rsi14",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "atr14",
    }
    assert expected.issubset(complete.columns)
    pd.testing.assert_frame_equal(prefix, complete.iloc[:80])

    flat = frame.copy()
    flat[["open", "high", "low", "close"]] = 100.0
    flat_indicators = calculate_chart_indicators(flat)
    assert flat_indicators[["kdj_k", "kdj_d", "kdj_j"]].isna().all().all()
