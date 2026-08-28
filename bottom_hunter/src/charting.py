from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .config import PROJECT_DIR
from .data_provider import (
    CachedMarketDataProvider,
    CompositeMarketDataProvider,
    DataProviderError,
    EastmoneyProvider,
    LocalCsvProvider,
    MarketDataProvider,
    StooqProvider,
    YahooChartProvider,
)
from .indicators import atr, rsi
from .io_utils import atomic_json as _atomic_json
from .longbridge_adapter import (
    LongbridgeClient,
    LongbridgeError,
    LongbridgeNotConfigured,
    LongbridgeSdkUnavailable,
    LongbridgeSymbolUnsupported,
)
from .models import Instrument
from .network_config import apply_requests_session, apply_urllib

# Disable system proxy (Clash, etc.) for all chart-service requests.
apply_urllib()


TIMEFRAME_LABELS = {
    "1m": "1分钟",
    "5m": "5分钟",
    "15m": "15分钟",
    "30m": "30分钟",
    "60m": "60分钟",
    "4h": "4小时",
    "1d": "日K",
    "1w": "周K",
    "1M": "月K",
}
INTRADAY_TIMEFRAMES = {"1m", "5m", "15m", "30m", "60m", "4h"}


class ChartDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChartResult:
    canonical_id: str
    symbol: str
    name: str
    timeframe: str
    bars: pd.DataFrame
    provider: str
    updated_at: datetime
    note: str = ""


def calculate_chart_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate causal, display-only indicators for the chart workspace."""

    if frame.empty:
        return pd.DataFrame(index=frame.index)
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
    result = pd.DataFrame(index=frame.index)
    for window in (5, 10, 20, 60):
        result[f"ma{window}"] = close.rolling(window, min_periods=window).mean()
    result["ema12"] = close.ewm(span=12, adjust=False, min_periods=12).mean()
    result["ema26"] = close.ewm(span=26, adjust=False, min_periods=26).mean()

    result["boll_mid"] = result["ma20"]
    boll_std = close.rolling(20, min_periods=20).std(ddof=0)
    result["boll_upper"] = result["boll_mid"] + 2 * boll_std
    result["boll_lower"] = result["boll_mid"] - 2 * boll_std

    result["macd_dif"] = result["ema12"] - result["ema26"]
    result["macd_dea"] = result["macd_dif"].ewm(
        span=9, adjust=False, min_periods=9
    ).mean()
    result["macd_hist"] = 2 * (result["macd_dif"] - result["macd_dea"])
    result["rsi14"] = rsi(close, 14)

    lowest = low.rolling(9, min_periods=9).min()
    highest = high.rolling(9, min_periods=9).max()
    spread = highest - lowest
    spread = spread.where(spread.ne(0))
    rsv = ((close - lowest) / spread * 100).astype("float64")
    result["kdj_k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    result["kdj_d"] = result["kdj_k"].ewm(alpha=1 / 3, adjust=False).mean()
    result["kdj_j"] = 3 * result["kdj_k"] - 2 * result["kdj_d"]
    result["atr14"] = atr(frame, 14)
    result["volume_ma5"] = volume.rolling(5, min_periods=5).mean()
    result["volume_ma10"] = volume.rolling(10, min_periods=10).mean()
    return result


class ChartAnnotationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        self.payload: dict[str, list[dict[str, Any]]] = (
            payload if isinstance(payload, dict) else {}
        )

    @staticmethod
    def _key(canonical_id: str, timeframe: str) -> str:
        return f"{canonical_id}|{timeframe}"

    def get(self, canonical_id: str, timeframe: str) -> list[dict[str, Any]]:
        values = self.payload.get(self._key(canonical_id, timeframe)) or []
        return [dict(item) for item in values if isinstance(item, dict)]

    def save(
        self,
        canonical_id: str,
        timeframe: str,
        annotations: list[dict[str, Any]],
    ) -> None:
        key = self._key(canonical_id, timeframe)
        if annotations:
            self.payload[key] = annotations
        else:
            self.payload.pop(key, None)
        _atomic_json(self.path, self.payload)


class MarketChartService:
    TENCENT_FQ_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
    TENCENT_MKLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
    TENCENT_SEARCH_URL = "https://smartbox.gtimg.cn/s3/"
    NASDAQ_CHART_URL = "https://api.nasdaq.com/api/quote/{symbol}/chart"
    BINANCE_KLINE_URL = "https://data-api.binance.vision/api/v3/klines"
    OKX_CANDLE_URL = "https://www.okx.com/api/v5/market/candles"

    def __init__(
        self,
        timeout: int = 10,
        session: requests.Session | None = None,
        *,
        daily_provider: MarketDataProvider | None = None,
        data_dir: str | Path | None = None,
        longbridge_client: LongbridgeClient | None = None,
    ) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()
        apply_requests_session(self.session)
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/136.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://gu.qq.com/",
            }
        )
        self._us_codes: dict[str, str] = {}
        resolved_data_dir = (
            Path(data_dir) if data_dir is not None else PROJECT_DIR / "data" / "raw"
        )
        self.local_daily_provider = (
            None if daily_provider is not None else LocalCsvProvider(resolved_data_dir)
        )
        self.daily_provider = daily_provider or self._build_daily_provider(resolved_data_dir)
        self.longbridge_client = longbridge_client or LongbridgeClient()

    def _build_daily_provider(self, data_dir: Path) -> MarketDataProvider:
        """Reuse the scanner's resilient sources after the chart-specific source fails."""

        remote = CompositeMarketDataProvider(
            [
                EastmoneyProvider(timeout=self.timeout),
                YahooChartProvider(timeout=self.timeout),
                StooqProvider(timeout=self.timeout),
            ]
        )
        return CachedMarketDataProvider(LocalCsvProvider(data_dir), remote)

    def fetch(
        self,
        asset: Mapping[str, Any],
        timeframe: str,
        limit: int = 250,
    ) -> ChartResult:
        if timeframe not in TIMEFRAME_LABELS:
            raise ValueError(f"不支持的 K 线周期：{timeframe}")
        limit = max(30, min(int(limit), 500))
        if str(asset.get("category")) == "crypto" or str(asset.get("market")) == "CRYPTO":
            bars, provider, note = self._fetch_crypto(asset, timeframe, limit)
        else:
            bars, provider, note = self._fetch_equity(asset, timeframe, limit)
        bars = self._clean_bars(bars).tail(limit)
        if bars.empty:
            raise ChartDataError("行情源没有返回有效 K 线")
        return ChartResult(
            canonical_id=str(asset.get("canonical_id") or asset.get("symbol") or ""),
            symbol=str(asset.get("symbol") or ""),
            name=str(asset.get("name") or asset.get("symbol") or ""),
            timeframe=timeframe,
            bars=bars,
            provider=provider,
            updated_at=datetime.now(UTC),
            note=note,
        )

    def _request_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        referer: str | None = None,
    ) -> Any:
        headers = {"Referer": referer} if referer else {}
        if "api.nasdaq.com" in url:
            headers["Origin"] = "https://www.nasdaq.com"
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self.session.get(
                    url,
                    params=dict(params),
                    headers=headers,
                    timeout=(min(3, self.timeout), self.timeout),
                )
                response.raise_for_status()
                return response.json()
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.2)
                    continue
                detail = str(exc)
                if getattr(exc.response, "status_code", None) == 451:
                    detail = "币安公开行情当前地区不可用"
                raise ChartDataError(f"行情请求失败：{detail}") from exc
            except requests.JSONDecodeError as exc:
                raise ChartDataError(f"行情响应格式无效：{exc}") from exc
        raise ChartDataError(f"行情请求失败：{last_error}")

    @staticmethod
    def _clean_bars(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        result = frame.copy()
        if "date" in result.columns:
            result["date"] = pd.to_datetime(result["date"], errors="coerce")
            result = result.set_index("date")
        result.index = pd.to_datetime(result.index, errors="coerce")
        if isinstance(result.index, pd.DatetimeIndex) and result.index.tz is not None:
            result.index = result.index.tz_localize(None)
        for column in ("open", "high", "low", "close", "volume"):
            if column not in result:
                result[column] = 0
            result[column] = pd.to_numeric(result[column], errors="coerce")
        result = result.loc[~result.index.isna()]
        result = result.dropna(subset=["open", "high", "low", "close"])
        result = result.loc[
            (result[["open", "high", "low", "close"]] > 0).all(axis=1)
            & (result["high"] >= result["low"])
        ]
        result["volume"] = result["volume"].fillna(0).clip(lower=0)
        return result.sort_index().loc[
            lambda item: ~item.index.duplicated(keep="last"),
            ["open", "high", "low", "close", "volume"],
        ]

    def _tencent_code(self, asset: Mapping[str, Any]) -> str:
        symbol = str(asset.get("symbol") or "").upper()
        market = str(asset.get("market") or "").upper()
        if market == "CN" and symbol.endswith(".SS"):
            return "sh" + symbol.removesuffix(".SS")
        if market == "CN" and symbol.endswith(".SZ"):
            return "sz" + symbol.removesuffix(".SZ")
        if market == "CN" and symbol.endswith(".BJ"):
            return "bj" + symbol.removesuffix(".BJ")
        if market == "HK" and symbol.endswith(".HK"):
            return "hk" + symbol.removesuffix(".HK").zfill(5)
        if market != "US":
            raise ChartDataError(f"暂不支持该市场的图表代码：{symbol}")
        raw = symbol.split(".", 1)[0]
        if raw in self._us_codes:
            return self._us_codes[raw]
        payload = self._request_text(
            self.TENCENT_SEARCH_URL,
            params={"q": raw, "t": "us"},
        )
        marker = 'v_hint="'
        if marker not in payload:
            raise ChartDataError(f"无法解析美股代码：{symbol}")
        body = payload.split(marker, 1)[1].split('"', 1)[0]
        candidates: list[str] = []
        for candidate in body.split("^"):
            parts = candidate.split("~")
            if len(parts) >= 2 and parts[1].split(".", 1)[0].upper() == raw:
                candidates.append(parts[1])
        if not candidates:
            raise ChartDataError(f"无法解析美股代码：{symbol}")
        code = "us" + candidates[0]
        self._us_codes[raw] = code
        return code

    def _request_text(self, url: str, *, params: Mapping[str, Any]) -> str:
        try:
            response = self.session.get(
                url,
                params=dict(params),
                timeout=(min(3, self.timeout), self.timeout),
            )
            response.raise_for_status()
            return response.text
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            raise ChartDataError(f"行情代码查询失败：{exc}") from exc

    def _fetch_equity(
        self,
        asset: Mapping[str, Any],
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        market = str(asset.get("market") or "").upper()
        longbridge_error = ""
        if self.longbridge_client.configured():
            try:
                return self._fetch_longbridge(asset, timeframe, limit)
            except (
                LongbridgeError,
                LongbridgeNotConfigured,
                LongbridgeSdkUnavailable,
                LongbridgeSymbolUnsupported,
            ) as exc:
                longbridge_error = str(exc)

        try:
            code = self._tencent_code(asset)
            if timeframe not in INTRADAY_TIMEFRAMES:
                try:
                    result = self._fetch_tencent_period(code, timeframe, limit)
                except ChartDataError as primary_error:
                    try:
                        result = self._fetch_daily_fallback(asset, timeframe, limit)
                    except (DataProviderError, OSError, ValueError) as fallback_error:
                        raise ChartDataError(
                            f"主行情源失败：{primary_error}；"
                            f"本地缓存与备用源也不可用：{fallback_error}"
                        ) from fallback_error
            elif market == "CN":
                result = self._fetch_tencent_cn_intraday(code, timeframe, limit)
            elif market == "HK":
                result = self._fetch_tencent_price_minutes(code, timeframe, limit)
            elif market == "US":
                result = self._fetch_nasdaq_minutes(asset, timeframe, limit)
            else:
                raise ChartDataError(f"暂不支持 {market} 的分钟 K 线")
        except ChartDataError as exc:
            if longbridge_error:
                raise ChartDataError(
                    f"长桥行情失败：{longbridge_error}；公开备用行情也失败：{exc}"
                ) from exc
            raise
        if longbridge_error:
            frame, provider, note = result
            detail = f"长桥不可用，已降级：{longbridge_error}"
            return frame, provider, "；".join(item for item in (detail, note) if item)
        return result

    def _fetch_longbridge(
        self,
        asset: Mapping[str, Any],
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        result = self.longbridge_client.candles(
            str(asset.get("symbol") or ""),
            str(asset.get("market") or ""),
            timeframe,
            limit,
        )
        if result.bars.empty:
            raise LongbridgeError("长桥没有返回有效 K 线")
        return (
            result.bars,
            "长桥 OpenAPI",
            f"官方认证行情 · {result.quote_level or '行情等级未知'} · 前复权",
        )

    def _fetch_daily_fallback(
        self,
        asset: Mapping[str, Any],
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        market = str(asset.get("market") or "").upper()
        symbol = str(asset.get("symbol") or "").upper()
        instrument = Instrument(
            symbol=symbol,
            name=str(asset.get("name") or symbol),
            market=market,
            category=str(asset.get("category") or ""),
            industry=str(asset.get("industry") or ""),
            asset_type=str(asset.get("asset_type") or "equity"),
            tokenized_stock=bool(asset.get("tokenized_stock")),
            sources=tuple(asset.get("sources") or ()),
            source_symbols=dict(asset.get("source_symbols") or {}),
        )
        calendar_days_per_bar = {"1d": 2, "1w": 9, "1M": 35}[timeframe]
        end = date.today()
        start = end - timedelta(days=max(120, limit * calendar_days_per_bar))
        result = None
        if self.local_daily_provider is not None:
            try:
                result = self.local_daily_provider.get_daily_bars(instrument, start, end)
            except DataProviderError:
                result = None
        if result is None:
            result = self.daily_provider.get_daily_bars(instrument, start, end)
        frame = result.bars
        if timeframe in {"1w", "1M"}:
            rule = "W-FRI" if timeframe == "1w" else "ME"
            frame = (
                frame.resample(rule)
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )
                .dropna(subset=["open", "high", "low", "close"])
            )
        provider_names = {
            "local_csv": "本地扫描缓存",
            "eastmoney": "东方财富备用行情",
            "yahoo_chart": "Yahoo 备用行情",
            "stooq": "Stooq 备用行情",
        }
        provider = provider_names.get(result.provider, result.provider)
        details = ["主行情源不可用，已自动切换"]
        if result.provider == "local_csv" and not frame.empty:
            details.append(f"缓存最新日期 {frame.index[-1]:%Y-%m-%d}")
        details.extend(result.warnings)
        return frame.tail(limit), provider, "；".join(details)

    def _fetch_tencent_period(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        period = {"1d": "day", "1w": "week", "1M": "month"}[timeframe]
        payload = self._request_json(
            self.TENCENT_FQ_URL,
            params={"param": ",".join([code, period, "", "", str(limit), "qfq"])},
            referer="https://gu.qq.com/",
        )
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise ChartDataError(f"腾讯行情返回错误：{getattr(payload, 'get', lambda *_: '')('msg')}")
        data = payload.get("data") or {}
        section = data.get(code) or next(iter(data.values()), {})
        lines = section.get("qfq" + period) or section.get(period) or []
        rows = [
            {
                "date": values[0],
                "open": values[1],
                "close": values[2],
                "high": values[3],
                "low": values[4],
                "volume": values[5],
            }
            for values in lines
            if isinstance(values, list) and len(values) >= 6
        ]
        if not rows:
            raise ChartDataError(f"腾讯行情没有返回 {code} 的{TIMEFRAME_LABELS[timeframe]}")
        return pd.DataFrame(rows), "腾讯公共行情", "前复权；行情可能延迟"

    def _fetch_tencent_cn_intraday(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        source_period = {
            "1m": "m1",
            "5m": "m5",
            "15m": "m15",
            "30m": "m30",
            "60m": "m60",
            "4h": "m60",
        }[timeframe]
        request_limit = min(500, limit * (4 if timeframe == "4h" else 1))
        payload = self._request_json(
            self.TENCENT_MKLINE_URL,
            params={"param": f"{code},{source_period},,{request_limit}"},
            referer="https://gu.qq.com/",
        )
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise ChartDataError(f"腾讯分钟行情返回错误：{getattr(payload, 'get', lambda *_: '')('msg')}")
        data = payload.get("data") or {}
        section = data.get(code) or next(iter(data.values()), {})
        lines = section.get(source_period) or []
        rows = [
            {
                "date": values[0],
                "open": values[1],
                "close": values[2],
                "high": values[3],
                "low": values[4],
                "volume": values[5],
            }
            for values in lines
            if isinstance(values, list) and len(values) >= 6
        ]
        frame = pd.DataFrame(rows)
        if timeframe == "4h":
            frame = self._resample(frame, "4h")
        if frame.empty:
            raise ChartDataError(f"腾讯行情没有返回 {code} 的分钟 K 线")
        return frame, "腾讯公共行情", "盘中自动刷新；行情可能延迟"

    def _fetch_tencent_price_minutes(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        payload = self._request_json(
            self.TENCENT_MINUTE_URL,
            params={"code": code},
            referer="https://gu.qq.com/",
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        section = (data or {}).get(code) or next(iter((data or {}).values()), {})
        minute_data = section.get("data") or {}
        trading_date = str(minute_data.get("date") or datetime.now().strftime("%Y%m%d"))
        raw_lines = minute_data.get("data") or []
        rows: list[dict[str, Any]] = []
        previous_volume = 0.0
        for line in raw_lines:
            values = str(line).split()
            if len(values) < 2 or not re.fullmatch(r"\d{4}", values[0]):
                continue
            cumulative = float(values[2]) if len(values) >= 3 else previous_volume
            rows.append(
                {
                    "date": trading_date + values[0],
                    "open": values[1],
                    "high": values[1],
                    "low": values[1],
                    "close": values[1],
                    "volume": max(0.0, cumulative - previous_volume),
                }
            )
            previous_volume = cumulative
        frame = pd.DataFrame(rows)
        if timeframe != "1m":
            frame = self._resample(frame, timeframe)
        if frame.empty:
            raise ChartDataError(f"腾讯行情没有返回 {code} 的分钟数据")
        return (
            frame.tail(limit),
            "腾讯公共行情",
            "分钟报价聚合为 K 线；高低价精度有限，行情可能延迟",
        )

    def _fetch_nasdaq_minutes(
        self,
        asset: Mapping[str, Any],
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        symbol = str(asset.get("symbol") or "").split(".", 1)[0].upper()
        payload = self._request_json(
            self.NASDAQ_CHART_URL.format(symbol=symbol),
            params={"assetclass": "stocks"},
            referer=f"https://www.nasdaq.com/market-activity/stocks/{symbol.casefold()}",
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        points = (data or {}).get("chart") or []
        rows = [
            {
                "date": pd.to_datetime(
                    item.get("x"), unit="ms", utc=True, errors="coerce"
                ).tz_convert("America/New_York"),
                "open": item.get("y"),
                "high": item.get("y"),
                "low": item.get("y"),
                "close": item.get("y"),
                "volume": 0,
            }
            for item in points
            if item.get("x") is not None and item.get("y") is not None
        ]
        frame = pd.DataFrame(rows)
        if timeframe != "1m":
            frame = self._resample(frame, timeframe)
        if frame.empty:
            raise ChartDataError(f"Nasdaq 没有返回 {symbol} 的盘中图表")
        return (
            frame.tail(limit),
            "Nasdaq 公共行情",
            "逐分钟报价聚合为 K 线；分钟成交量不可用，行情可能延迟",
        )

    @staticmethod
    def _resample(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        working = frame.copy()
        working["date"] = pd.to_datetime(working["date"], errors="coerce", utc=True)
        working = working.dropna(subset=["date"]).set_index("date")
        rule = {
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "60m": "60min",
            "4h": "4h",
        }[timeframe]
        result = working.resample(rule, origin="start_day", label="right", closed="right").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        return result.dropna(subset=["open", "high", "low", "close"]).reset_index()

    def _fetch_crypto(
        self,
        asset: Mapping[str, Any],
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        source_symbols = dict(asset.get("source_symbols") or {})
        errors: list[str] = []
        if source_symbols.get("binance"):
            try:
                return self._fetch_binance(source_symbols["binance"], timeframe, limit)
            except ChartDataError as exc:
                errors.append(str(exc))
        okx_symbol = source_symbols.get("okx") or str(asset.get("symbol") or "")
        try:
            return self._fetch_okx(okx_symbol, timeframe, limit)
        except ChartDataError as exc:
            errors.append(str(exc))
        raise ChartDataError("；".join(errors) or "没有可用的加密货币行情源")

    def _fetch_binance(
        self,
        source_symbol: str,
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        interval = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "60m": "1h",
            "4h": "4h",
            "1d": "1d",
            "1w": "1w",
            "1M": "1M",
        }[timeframe]
        symbol = re.sub(r"[^A-Z0-9]", "", source_symbol.upper().removesuffix("SPOT"))
        try:
            payload = self._request_json(
                self.BINANCE_KLINE_URL,
                params={"symbol": symbol, "interval": interval, "limit": min(limit, 500)},
                referer="https://www.binance.com/",
            )
        except ChartDataError:
            # Public Binance endpoints are also geo-restricted; the caller will
            # fall back to OKX (see _fetch_crypto). Do not re-throw here.
            raise
        if not isinstance(payload, list):
            message = payload.get("msg") if isinstance(payload, dict) else payload
            restricted = (
                'restricted location' in str(message).casefold()
                or 'b. eligibility' in str(message).casefold()
            )
            if restricted:
                raise ChartDataError(
                    "币安公开行情当前地区不可用；将自动转用欧易"
                )
            raise ChartDataError(f"币安返回错误：{message}")
        rows = [
            {
                "date": pd.to_datetime(int(item[0]), unit="ms", utc=True),
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            }
            for item in payload
            if isinstance(item, list) and len(item) >= 6
        ]
        return pd.DataFrame(rows), "币安公开行情", "交易所 K 线（UTC）；当前柱可能尚未收盘"

    def _fetch_okx(
        self,
        source_symbol: str,
        timeframe: str,
        limit: int,
    ) -> tuple[pd.DataFrame, str, str]:
        bar = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "60m": "1H",
            "4h": "4H",
            "1d": "1Dutc",
            "1w": "1Wutc",
            "1M": "1Mutc",
        }[timeframe]
        inst_id = source_symbol.upper().replace("/", "-").replace("_", "-")
        if "-" not in inst_id:
            for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
                if inst_id.endswith(quote) and len(inst_id) > len(quote):
                    inst_id = inst_id[: -len(quote)] + "-" + quote
                    break
        payload = self._request_json(
            self.OKX_CANDLE_URL,
            params={"instId": inst_id, "bar": bar, "limit": min(limit, 300)},
            referer="https://www.okx.com/",
        )
        if not isinstance(payload, dict) or str(payload.get("code")) != "0":
            raise ChartDataError(f"欧易返回错误：{getattr(payload, 'get', lambda *_: '')('msg')}")
        rows = [
            {
                "date": pd.to_datetime(int(item[0]), unit="ms", utc=True),
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            }
            for item in payload.get("data") or []
            if isinstance(item, list) and len(item) >= 6
        ]
        return pd.DataFrame(rows), "欧易公开行情", "交易所 K 线（UTC）；当前柱可能尚未收盘"
