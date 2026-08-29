from __future__ import annotations

import csv
import io
import json
import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import requests

from .io_utils import EASTMONEY_SEARCH_TOKEN
from .longbridge_adapter import (
    LongbridgeClient,
    LongbridgeError,
    LongbridgeNotConfigured,
    LongbridgeSdkUnavailable,
    LongbridgeSymbolUnsupported,
)
from .models import DataResult, FundamentalResult, Instrument
from .network_config import apply_requests_session, apply_urllib

# Disable system proxy (Clash, etc.) for all data-provider requests.
apply_urllib()

LOGGER = logging.getLogger(__name__)
OHLCV = ["open", "high", "low", "close", "volume"]


class DataProviderError(RuntimeError):
    """Raised when a provider cannot return trustworthy daily bars."""


class NetworkDataProviderError(DataProviderError):
    """A transient transport failure that may open a batch circuit breaker."""


class ProviderNotApplicable(DataProviderError):
    """The provider deliberately does not support this instrument/market."""


class MarketDataProvider(ABC):
    """Replaceable interface for market, index, sector and fundamental data."""

    name = "abstract"

    @abstractmethod
    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        """Return adjusted, completed daily OHLCV bars in [start, end]."""

    def get_index_data(self, instrument: Instrument, start: date, end: date) -> DataResult:
        return self.get_daily_bars(instrument, start, end)

    def get_sector_data(self, instrument: Instrument, start: date, end: date) -> DataResult:
        return self.get_daily_bars(instrument, start, end)

    def get_fundamental_data(self, instrument: Instrument, as_of: date) -> FundamentalResult:
        return FundamentalResult(
            score=None,
            reason="基本面数据不足，需要人工确认。",
            source=None,
            as_of=None,
        )


def normalize_bars(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if frame.empty:
        raise DataProviderError("返回了空行情")
    normalized = frame.copy()
    normalized.columns = [str(column).strip().lower() for column in normalized.columns]
    rename = {"adj close": "adj_close", "date": "date"}
    normalized = normalized.rename(columns=rename)
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized = normalized.set_index("date")
    if not isinstance(normalized.index, pd.DatetimeIndex):
        normalized.index = pd.to_datetime(normalized.index, errors="coerce")
    if normalized.index.tz is not None:
        normalized.index = normalized.index.tz_localize(None)
    normalized.index = normalized.index.normalize()
    missing = set(OHLCV) - set(normalized.columns)
    if missing:
        raise DataProviderError(f"行情字段缺失: {sorted(missing)}")
    for column in OHLCV + (["adj_close"] if "adj_close" in normalized else []):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.loc[~normalized.index.isna(), :]
    normalized = normalized.sort_index()
    normalized = normalized.loc[
        ~normalized.index.duplicated(keep="last"), OHLCV + (["adj_close"] if "adj_close" in normalized else [])
    ]
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    normalized = normalized.loc[(normalized.index >= start_ts) & (normalized.index <= end_ts)]
    normalized = normalized.dropna(subset=["open", "high", "low", "close"])
    invalid = (normalized[["open", "high", "low", "close"]] <= 0).any(axis=1) | (normalized["high"] < normalized["low"])
    normalized = normalized.loc[~invalid]
    normalized["volume"] = normalized["volume"].fillna(0).clip(lower=0)
    if "adj_close" in normalized and normalized["adj_close"].notna().any():
        ratio = normalized["adj_close"] / normalized["close"].replace(0, np.nan)
        ratio = ratio.replace([np.inf, -np.inf], np.nan).fillna(1.0)
        for column in ("open", "high", "low", "close"):
            normalized[column] = normalized[column] * ratio
        normalized = normalized.drop(columns="adj_close")
    if normalized.empty:
        raise DataProviderError("清洗后没有有效行情")
    return normalized.astype({column: "float64" for column in OHLCV})


class LocalCsvProvider(MarketDataProvider):
    name = "local_csv"

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    @staticmethod
    def safe_name(symbol: str) -> str:
        return symbol.replace("^", "INDEX_").replace("/", "_")

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        candidates = [
            self.data_dir / f"{self.safe_name(instrument.symbol)}.csv",
            self.data_dir / f"{instrument.symbol}.csv",
        ]
        path = next((item for item in candidates if item.exists()), None)
        if path is None:
            raise DataProviderError(f"本地 CSV 不存在: {instrument.symbol}")
        frame = normalize_bars(pd.read_csv(path), start, end)
        return DataResult(
            symbol=instrument.symbol,
            bars=frame,
            provider=self.name,
            data_timestamp=datetime.fromtimestamp(path.stat().st_mtime, UTC),
        )


class BinanceKlineProvider(MarketDataProvider):
    """Official Binance public daily klines for imported crypto favorites."""

    name = "binance_klines"
    # Binance documents this host specifically for public market-data requests.
    # Private account endpoints must remain on the account API and are still
    # subject to the user's regional eligibility.
    URL = "https://data-api.binance.vision/api/v3/klines"

    def __init__(self, timeout: int = 12):
        self.timeout = timeout

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        if instrument.market != "CRYPTO":
            raise ProviderNotApplicable("币安 K 线数据源仅支持加密货币")
        source_symbol = instrument.source_symbols.get("binance")
        if not source_symbol:
            raise ProviderNotApplicable(f"{instrument.symbol} 不在币安自选快照中")
        symbol = re.sub(r"[^A-Z0-9]", "", source_symbol.upper().removesuffix("SPOT"))
        if not symbol:
            raise ProviderNotApplicable(f"币安交易对无效：{source_symbol}")
        params = {
            "symbol": symbol,
            "interval": "1d",
            "startTime": int(datetime.combine(start, dt_time.min, UTC).timestamp() * 1000),
            "endTime": int(datetime.combine(end + timedelta(days=1), dt_time.min, UTC).timestamp() * 1000 - 1),
            "limit": 1000,
        }
        try:
            response = requests.get(self.URL, params=params, timeout=self.timeout)
            if getattr(response, "status_code", 200) == 451:
                raise ProviderNotApplicable("币安公开 K 线在当前地区无法使用；将自动转用欧易或本地缓存")
            response.raise_for_status()
            payload = response.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            raise NetworkDataProviderError(f"币安 K 线请求失败: {exc}") from exc
        except requests.JSONDecodeError as exc:
            raise DataProviderError(f"币安 K 线响应不是有效 JSON: {exc}") from exc
        if isinstance(payload, dict):
            message = payload.get("msg") or payload.get("message") or payload
            restricted = "restricted location" in str(message).casefold() or "b. eligibility" in str(message).casefold()
            if restricted:
                raise ProviderNotApplicable("币安公开 K 线在当前地区无法使用；将自动转用欧易或本地缓存")
            raise DataProviderError(f"币安返回错误: {message}")
        rows = [
            {
                "date": pd.to_datetime(item[0], unit="ms", utc=True).tz_convert(None),
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            }
            for item in payload
            if isinstance(item, list) and len(item) >= 6
        ]
        bars = normalize_bars(pd.DataFrame(rows), start, end)
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
            warnings=[f"交易所原始交易对：{source_symbol}"],
        )


class OkxCandleProvider(MarketDataProvider):
    """Official OKX public UTC daily candles for imported crypto favorites."""

    name = "okx_candles"
    URL = "https://www.okx.com/api/v5/market/history-candles"

    def __init__(self, timeout: int = 12):
        self.timeout = timeout

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        if instrument.market != "CRYPTO":
            raise ProviderNotApplicable("欧易 K 线数据源仅支持加密货币")
        source_symbol = instrument.source_symbols.get("okx")
        cross_exchange_fallback = not source_symbol
        if not source_symbol:
            parts = instrument.symbol.upper().split("-", 1)
            if len(parts) != 2 or not all(parts):
                raise ProviderNotApplicable(f"无法为 {instrument.symbol} 生成欧易备用交易对")
            source_symbol = f"{parts[0]}-{parts[1]}"
        cursor: str | None = None
        collected: dict[int, list[Any]] = {}
        start_ms = int(datetime.combine(start, dt_time.min, UTC).timestamp() * 1000)
        for _page in range(5):
            params = {"instId": source_symbol.upper(), "bar": "1Dutc", "limit": "300"}
            if cursor:
                params["after"] = cursor
            try:
                response = requests.get(self.URL, params=params, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                raise NetworkDataProviderError(f"欧易 K 线请求失败: {exc}") from exc
            except requests.JSONDecodeError as exc:
                raise DataProviderError(f"欧易 K 线响应不是有效 JSON: {exc}") from exc
            if not isinstance(payload, dict) or str(payload.get("code")) != "0":
                message = payload.get("msg") if isinstance(payload, dict) else payload
                raise DataProviderError(f"欧易返回错误: {message}")
            rows = payload.get("data") or []
            if not rows:
                break
            for item in rows:
                if not isinstance(item, list) or len(item) < 6:
                    continue
                if len(item) >= 9 and str(item[8]) != "1":
                    continue
                collected[int(item[0])] = item
            valid_rows = [int(item[0]) for item in rows if isinstance(item, list) and len(item) >= 6]
            if not valid_rows:
                break
            oldest = min(valid_rows)
            if oldest <= start_ms or cursor == str(oldest):
                break
            cursor = str(oldest)
        parsed = [
            {
                "date": pd.to_datetime(timestamp, unit="ms", utc=True).tz_convert(None),
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            }
            for timestamp, item in collected.items()
        ]
        bars = normalize_bars(pd.DataFrame(parsed), start, end)
        warnings = [f"交易所原始交易对：{source_symbol}"]
        if cross_exchange_fallback:
            warnings.append("自选来源行情不可用，已使用欧易同交易对备用行情。")
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
            warnings=warnings,
        )


class LongbridgeProvider(MarketDataProvider):
    """Official authenticated, forward-adjusted CN/HK/US daily candles."""

    name = "longbridge"

    def __init__(self, client: LongbridgeClient | None = None):
        self.client = client or LongbridgeClient()

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        if instrument.market not in {"CN", "HK", "US"}:
            raise ProviderNotApplicable("长桥行情源仅用于 A股、港股和美股")
        if not self.client.configured():
            raise ProviderNotApplicable("长桥行情尚未配置")
        try:
            result = self.client.candles(
                instrument.symbol,
                instrument.market,
                "1d",
                start=start,
                end=end,
            )
            bars = normalize_bars(result.bars, start, end)
        except (
            LongbridgeNotConfigured,
            LongbridgeSdkUnavailable,
            LongbridgeSymbolUnsupported,
        ) as exc:
            raise ProviderNotApplicable(str(exc)) from exc
        except LongbridgeError as exc:
            raise NetworkDataProviderError(str(exc)) from exc
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
            warnings=[f"长桥行情等级：{result.quote_level or '未知'}；前复权"],
        )


class YahooChartProvider(MarketDataProvider):
    name = "yahoo_chart"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        symbol = instrument.provider_symbol or instrument.symbol
        period1 = int(datetime.combine(start, dt_time.min, UTC).timestamp())
        period2 = int(datetime.combine(end + timedelta(days=1), dt_time.min, UTC).timestamp())
        query = urlencode(
            {
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "div,splits",
                "includeAdjustedClose": "true",
            }
        )
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?{query}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 BottomHunter/0.1"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise NetworkDataProviderError(f"Yahoo 请求失败: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DataProviderError(f"Yahoo 响应不是有效 JSON: {exc}") from exc
        chart = payload.get("chart", {})
        if chart.get("error"):
            raise DataProviderError(f"Yahoo 返回错误: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            raise DataProviderError("Yahoo 没有返回结果")
        result = results[0]
        timestamps = result.get("timestamp") or []
        quote_rows = (result.get("indicators", {}).get("quote") or [{}])[0]
        adjusted = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose", [])
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None),
                "open": quote_rows.get("open", []),
                "high": quote_rows.get("high", []),
                "low": quote_rows.get("low", []),
                "close": quote_rows.get("close", []),
                "volume": quote_rows.get("volume", []),
            }
        )
        if adjusted and len(adjusted) == len(frame):
            frame["adj_close"] = adjusted
        bars = normalize_bars(frame, start, end)
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
        )


class StooqProvider(MarketDataProvider):
    name = "stooq"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    @staticmethod
    def _symbol(instrument: Instrument) -> str:
        symbol = (instrument.provider_symbol or instrument.symbol).lower()
        symbol = {"^gspc": "^spx"}.get(symbol, symbol)
        if instrument.market == "US" and not symbol.startswith("^") and "." not in symbol:
            return f"{symbol}.us"
        return symbol

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        if instrument.market != "US":
            raise ProviderNotApplicable(f"Stooq 未配置 {instrument.market} 市场映射")
        query = urlencode(
            {
                "s": self._symbol(instrument),
                "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"),
                "i": "d",
            }
        )
        request = Request(
            f"https://stooq.com/q/d/l/?{query}",
            headers={"User-Agent": "Mozilla/5.0 BottomHunter/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                rows = list(csv.DictReader(line.decode("utf-8") for line in response))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise NetworkDataProviderError(f"Stooq 请求失败: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise DataProviderError(f"Stooq 响应编码无效: {exc}") from exc
        bars = normalize_bars(pd.DataFrame(rows), start, end)
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
            warnings=["Stooq 数据通常为调整后行情，请与交易所数据复核。"],
        )


class CboeVixProvider(MarketDataProvider):
    """Official Cboe VIX daily history; VIX has no meaningful share volume."""

    name = "cboe_vix"
    URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        if instrument.symbol != "^VIX":
            raise ProviderNotApplicable("Cboe VIX 数据源仅支持 ^VIX")
        request = Request(
            self.URL,
            headers={"User-Agent": "Mozilla/5.0 BottomHunter/0.2"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise NetworkDataProviderError(f"Cboe VIX 请求失败: {exc}") from exc
        try:
            frame = pd.read_csv(io.BytesIO(content))
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise DataProviderError(f"Cboe VIX CSV 解析失败: {exc}") from exc
        frame["volume"] = 0.0
        bars = normalize_bars(frame, start, end)
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
            warnings=["VIX 行情来自 Cboe 官方历史 CSV；成交量字段不适用。"],
        )


class TencentProvider(MarketDataProvider):
    """Tencent daily K-lines for A/H shares and resolved US symbols."""

    name = "tencent"
    FQ_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
    SEARCH_URL = "https://smartbox.gtimg.cn/s3/"
    INDEX_CODES = {"^GSPC": "us.INX", "^HSI": "hkHSI"}

    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self._resolved: dict[str, str] = {}
        self._lock = threading.Lock()

    def _read(self, url: str) -> bytes:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 BottomHunter/0.2",
                "Referer": "https://gu.qq.com/",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise NetworkDataProviderError(f"腾讯行情请求失败: {exc}") from exc

    def _us_code(self, symbol: str) -> str:
        with self._lock:
            cached = self._resolved.get(symbol)
        if cached:
            return cached
        query = urlencode({"q": symbol, "t": "us"})
        try:
            text = self._read(f"{self.SEARCH_URL}?{query}").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DataProviderError(f"腾讯代码搜索响应编码无效: {exc}") from exc
        marker = 'v_hint="'
        if marker not in text:
            raise ProviderNotApplicable(f"腾讯行情无法解析美股代码 {symbol}")
        body = text.split(marker, 1)[1].split('"', 1)[0]
        matches: list[str] = []
        for candidate in body.split("^"):
            parts = candidate.split("~")
            if len(parts) < 2:
                continue
            code = parts[1]
            if code.split(".", 1)[0].upper() == symbol.upper():
                matches.append(code)
        if not matches:
            raise ProviderNotApplicable(f"腾讯行情无法解析美股代码 {symbol}")
        resolved = "us" + matches[0]
        with self._lock:
            self._resolved[symbol] = resolved
        return resolved

    def _code(self, instrument: Instrument) -> str:
        if instrument.provider_symbol and instrument.provider_symbol.startswith(("sh", "sz", "hk", "us")):
            return instrument.provider_symbol
        symbol = instrument.symbol.upper()
        if symbol in self.INDEX_CODES:
            return self.INDEX_CODES[symbol]
        if symbol == "^VIX":
            raise ProviderNotApplicable("腾讯行情未提供 VIX 日K")
        if instrument.market == "CN" and symbol.endswith(".SZ"):
            return "sz" + symbol.removesuffix(".SZ")
        if instrument.market == "CN" and symbol.endswith(".SS"):
            return "sh" + symbol.removesuffix(".SS")
        if instrument.market == "CN" and symbol.endswith(".CSI"):
            raise ProviderNotApplicable(f"腾讯行情未映射中证代码 {symbol}")
        if instrument.market == "HK" and symbol.endswith(".HK"):
            return "hk" + symbol.removesuffix(".HK").zfill(5)
        if instrument.market == "US" and not symbol.startswith("^"):
            return self._us_code(symbol)
        raise ProviderNotApplicable(f"腾讯行情不支持代码 {instrument.symbol}")

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        code = self._code(instrument)
        parameters = ",".join([code, "day", start.isoformat(), end.isoformat(), "1000", "qfq"])
        url = f"{self.FQ_URL}?{urlencode({'param': parameters})}"
        raw = self._read(url)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DataProviderError(f"腾讯行情响应不是有效 JSON: {exc}") from exc
        if payload.get("code") != 0:
            raise DataProviderError(f"腾讯行情返回错误 {payload.get('code')}: {payload.get('msg', '')}")
        data = payload.get("data") or {}
        section = data.get(code) or next(iter(data.values()), {})
        lines = section.get("qfqday") or section.get("day") or []
        if not lines:
            raise DataProviderError(f"腾讯行情无日K: {instrument.symbol} ({code})")
        rows: list[dict[str, Any]] = []
        for values in lines:
            if not isinstance(values, list) or len(values) < 6:
                continue
            rows.append(
                {
                    "date": values[0],
                    "open": values[1],
                    "close": values[2],
                    "high": values[3],
                    "low": values[4],
                    "volume": values[5],
                }
            )
        bars = normalize_bars(pd.DataFrame(rows), start, end)
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
            warnings=["腾讯为公共行情接口，生产使用前请与授权行情复核。"],
        )


class EastmoneyProvider(MarketDataProvider):
    """Eastmoney daily K-lines with deterministic A/H mappings and US lookup."""

    name = "eastmoney"
    SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
    KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    SEARCH_TOKEN = EASTMONEY_SEARCH_TOKEN
    INDEX_IDS = {
        "^GSPC": "100.SPX",
        "^HSI": "100.HSI",
        "^VIX": "100.VIX",
    }

    def __init__(self, timeout: int = 8, max_concurrency: int = 3):
        self.timeout = timeout
        self._limit = threading.BoundedSemaphore(max(1, max_concurrency))
        self._local = threading.local()
        self._resolved: dict[str, str] = {}
        self._resolved_lock = threading.Lock()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": "Mozilla/5.0 BottomHunter/0.2",
                    "Referer": "https://quote.eastmoney.com/",
                    "Accept": "application/json,text/plain,*/*",
                }
            )
            apply_requests_session(session)
            self._local.session = session
        return session

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with self._limit:
                    response = self._session().get(
                        url,
                        params=params,
                        timeout=(min(3, self.timeout), self.timeout),
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise DataProviderError("东方财富响应结构无效")
                return payload
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                raise NetworkDataProviderError(f"东方财富请求失败: {exc}") from exc
            except requests.JSONDecodeError as exc:
                raise DataProviderError(f"东方财富响应不是有效 JSON: {exc}") from exc
        raise NetworkDataProviderError(f"东方财富请求失败: {last_error}")

    def _quote_id(self, instrument: Instrument) -> str:
        if instrument.provider_symbol and instrument.provider_symbol.split(".", 1)[0].isdigit():
            return instrument.provider_symbol
        symbol = instrument.symbol.upper()
        if symbol in self.INDEX_IDS:
            return self.INDEX_IDS[symbol]
        with self._resolved_lock:
            cached = self._resolved.get(symbol)
        if cached:
            return cached
        if instrument.market == "CN" and symbol.endswith(".SS"):
            quote_id = f"1.{symbol.removesuffix('.SS')}"
        elif instrument.market == "CN" and symbol.endswith(".SZ"):
            quote_id = f"0.{symbol.removesuffix('.SZ')}"
        elif instrument.market == "HK" and symbol.endswith(".HK"):
            quote_id = f"116.{symbol.removesuffix('.HK').zfill(5)}"
        else:
            raw = symbol.removeprefix("^").split(".", 1)[0]
            payload = self._get_json(
                self.SEARCH_URL,
                {
                    "input": raw,
                    "type": 14,
                    "token": self.SEARCH_TOKEN,
                    "count": 10,
                },
            )
            candidates = payload.get("QuotationCodeTable", {}).get("Data") or []
            exact = [
                item
                for item in candidates
                if str(item.get("Code", "")).upper() == raw.upper()
                and (instrument.market != "US" or str(item.get("Classify", "")) == "UsStock")
            ]
            if not exact:
                raise ProviderNotApplicable(f"东方财富无法解析代码 {instrument.symbol}")
            quote_id = str(exact[0].get("QuoteID", ""))
            if not quote_id:
                raise ProviderNotApplicable(f"东方财富未返回 QuoteID: {instrument.symbol}")
        with self._resolved_lock:
            self._resolved[symbol] = quote_id
        return quote_id

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        quote_id = self._quote_id(instrument)
        payload = self._get_json(
            self.KLINE_URL,
            {
                "secid": quote_id,
                "klt": 101,
                "fqt": 1,
                "beg": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "lmt": 100000,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            },
        )
        data = payload.get("data")
        lines = data.get("klines") if isinstance(data, dict) else None
        if not lines:
            raise DataProviderError(f"东方财富无日K: {instrument.symbol} ({quote_id})")
        rows: list[dict[str, Any]] = []
        for line in lines:
            values = str(line).split(",")
            if len(values) < 6:
                continue
            rows.append(
                {
                    "date": values[0],
                    "open": values[1],
                    "close": values[2],
                    "high": values[3],
                    "low": values[4],
                    "volume": values[5],
                }
            )
        bars = normalize_bars(pd.DataFrame(rows), start, end)
        return DataResult(
            symbol=instrument.symbol,
            bars=bars,
            provider=self.name,
            data_timestamp=datetime.now(UTC),
            warnings=["东方财富为公共行情接口，生产使用前请与授权行情复核。"],
        )


class CircuitBreakerProvider(MarketDataProvider):
    """Stop hammering a provider after repeated transport failures in one batch."""

    def __init__(self, provider: MarketDataProvider, failure_threshold: int = 3):
        self.provider = provider
        self.name = provider.name
        self.failure_threshold = max(1, failure_threshold)
        self._network_failures = 0
        self._open = False
        self._lock = threading.Lock()

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        with self._lock:
            if self._open:
                raise ProviderNotApplicable(f"{self.name} 本批次连续网络失败，熔断后跳过")
        try:
            result = self.provider.get_daily_bars(instrument, start, end)
        except NetworkDataProviderError:
            with self._lock:
                self._network_failures += 1
                if self._network_failures >= self.failure_threshold and not self._open:
                    self._open = True
                    LOGGER.error(
                        "%s 连续 %d 次网络失败，本批次已熔断",
                        self.name,
                        self._network_failures,
                    )
            raise
        else:
            with self._lock:
                self._network_failures = 0
            return result


class CompositeMarketDataProvider(MarketDataProvider):
    name = "composite"

    def __init__(self, providers: Iterable[MarketDataProvider]):
        self.providers = list(providers)
        if not self.providers:
            raise ValueError("至少需要一个行情提供器")

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        errors: list[str] = []
        for provider in self.providers:
            try:
                result = provider.get_daily_bars(instrument, start, end)
                if errors:
                    result.warnings.append("备用源已启用；" + " | ".join(errors))
                return result
            except ProviderNotApplicable:
                continue
            except (DataProviderError, OSError, ValueError) as exc:
                message = f"{provider.name}: {exc}"
                errors.append(message)
                LOGGER.warning("%s 获取失败 (%s)", instrument.symbol, message)
        raise DataProviderError(f"所有行情源均失败: {' | '.join(errors)}")


class CachedMarketDataProvider(MarketDataProvider):
    """Use a complete local range, otherwise refresh it from remote providers."""

    name = "cached_composite"

    def __init__(
        self,
        cache: LocalCsvProvider,
        remote: MarketDataProvider,
        allow_stale_fallback: bool = True,
    ):
        self.cache = cache
        self.remote = remote
        self.allow_stale_fallback = allow_stale_fallback

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        cached: DataResult | None = None
        try:
            cached = self.cache.get_daily_bars(instrument, start, end)
            if cached.bars.index[-1].date() >= end:
                return cached
        except DataProviderError:
            cached = None
        try:
            remote = self.remote.get_daily_bars(instrument, start, end)
            path = self.cache.data_dir / f"{self.cache.safe_name(instrument.symbol)}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            try:
                remote.bars.rename_axis("date").to_csv(tmp_path)
                tmp_path.replace(path)
            finally:
                tmp_path.unlink(missing_ok=True)
            return remote
        except DataProviderError as exc:
            if cached is not None and self.allow_stale_fallback:
                cached.quality = "stale"
                cached.warnings.append(f"远程更新失败，使用旧缓存: {exc}")
                return cached
            raise


class CsvFundamentalProvider:
    """Point-in-time manual fundamentals; later rows are never visible early."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._frame: pd.DataFrame | None = None

    def _load_frame(self) -> pd.DataFrame | None:
        """Load and index the CSV once; the same file is read for every call."""
        if self._frame is not None:
            return self._frame
        if not self.path.exists():
            self._frame = pd.DataFrame()
            return self._frame
        try:
            frame = pd.read_csv(self.path, comment="#")
        except (pd.errors.EmptyDataError, OSError):
            self._frame = pd.DataFrame()
            return self._frame
        required = {"date", "symbol", "score", "reason", "source"}
        if frame.empty or not required.issubset(frame.columns):
            self._frame = pd.DataFrame()
            return self._frame
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        frame = frame[frame["date"].notna()]
        self._frame = frame.sort_values("date") if not frame.empty else frame
        return self._frame

    def get_fundamental_data(self, instrument: Instrument, as_of: date) -> FundamentalResult:
        frame = self._load_frame()
        if frame.empty:
            return self._missing()
        candidates = frame.loc[frame["symbol"].astype(str) == instrument.symbol,]
        candidates = candidates[candidates["date"] <= as_of]
        if candidates.empty:
            return self._missing()
        row = candidates.iloc[-1]
        try:
            score = int(row["score"])
        except (TypeError, ValueError):
            return self._missing("基本面评分无效，需要人工确认。")
        if score not in {0, 1, 2}:
            return self._missing("基本面评分必须是 0、1 或 2。")
        return FundamentalResult(
            score=score,
            reason=str(row["reason"]),
            source=str(row["source"]),
            as_of=row["date"],
        )

    @staticmethod
    def _missing(reason: str = "基本面数据不足，需要人工确认。") -> FundamentalResult:
        return FundamentalResult(score=None, reason=reason, source=None, as_of=None)


class FallbackFundamentalProvider:
    """Use the first point-in-time fundamental source that has a score."""

    def __init__(self, providers: list[Any]):
        self.providers = list(providers)

    def get_fundamental_data(self, instrument: Instrument, as_of: date) -> FundamentalResult:
        fallback = FundamentalResult(None, "没有可用的时点基本面数据。", None, None)
        for provider in self.providers:
            result = provider.get_fundamental_data(instrument, as_of)
            if result.score is not None:
                return result
            fallback = result
        return fallback


def fetch_many(
    provider: MarketDataProvider,
    instruments: Iterable[Instrument],
    start: date,
    end: date,
    workers: int = 8,
) -> tuple[dict[str, DataResult], dict[str, str]]:
    """Fetch independent symbols concurrently without hiding individual failures."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    unique = {instrument.symbol: instrument for instrument in instruments}
    results: dict[str, DataResult] = {}
    errors: dict[str, str] = {}
    executor = ThreadPoolExecutor(max_workers=max(1, min(workers, len(unique))))
    futures = {
        executor.submit(provider.get_daily_bars, instrument, start, end): symbol
        for symbol, instrument in unique.items()
    }
    try:
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception as exc:  # one failed symbol must not abort the market
                errors[symbol] = str(exc)
                LOGGER.error("无法取得 %s: %s", symbol, exc)
    except KeyboardInterrupt:
        LOGGER.warning("收到中断信号，正在取消尚未开始的行情任务……")
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    return results, errors
