from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd

DEFAULT_HTTP_URL = "https://openapi.longbridge.cn"
DEFAULT_QUOTE_WS_URL = "wss://openapi-quote.longbridge.cn/v2"
LONG_BRIDGE_ENV_KEYS = {
    "app_key": "LONGBRIDGE_APP_KEY",
    "app_secret": "LONGBRIDGE_APP_SECRET",
    "access_token": "LONGBRIDGE_ACCESS_TOKEN",
    "http_url": "LONGBRIDGE_HTTP_URL",
    "quote_ws_url": "LONGBRIDGE_QUOTE_WS_URL",
}


class LongbridgeError(RuntimeError):
    """Base error raised by the optional Longbridge integration."""


class LongbridgeNotConfigured(LongbridgeError):
    """The local machine has no complete Longbridge quote credentials."""


class LongbridgeSdkUnavailable(LongbridgeError):
    """The optional official SDK cannot be imported in this interpreter."""


class LongbridgeSymbolUnsupported(LongbridgeError):
    """The instrument cannot be represented by Longbridge's symbol scheme."""


@dataclass(frozen=True)
class LongbridgeVerification:
    member_id: str
    quote_level: str
    packages: tuple[str, ...]


@dataclass(frozen=True)
class LongbridgeCandleResult:
    bars: pd.DataFrame
    quote_level: str


def sanitize_credentials(values: Mapping[str, Any] | None) -> dict[str, str]:
    result = {
        key: str((values or {}).get(key) or "").strip()
        for key in LONG_BRIDGE_ENV_KEYS
    }
    result["http_url"] = result["http_url"] or DEFAULT_HTTP_URL
    result["quote_ws_url"] = result["quote_ws_url"] or DEFAULT_QUOTE_WS_URL
    return result


def credentials_complete(values: Mapping[str, Any] | None) -> bool:
    cleaned = sanitize_credentials(values)
    return all(cleaned[key] for key in ("app_key", "app_secret", "access_token"))


def runtime_credentials(vault: Any | None = None) -> dict[str, str]:
    """Load credentials from environment first, then the desktop keyring."""

    environment = {
        key: os.environ.get(environment_key, "")
        for key, environment_key in LONG_BRIDGE_ENV_KEYS.items()
    }
    if credentials_complete(environment):
        return sanitize_credentials(environment)
    if vault is None:
        try:
            # Local import avoids a module cycle: account_connectors imports this adapter.
            from .account_connectors import CredentialVault

            vault = CredentialVault()
        except Exception:
            vault = None
    stored = vault.load("longbridge") if vault is not None else {}
    return sanitize_credentials(stored) if credentials_complete(stored) else {}


def _sdk_install_hint() -> str:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    suffix = (
        " 当前 Python 3.13 可能需要 Rust 编译环境；建议改用 Python 3.11/3.12。"
        if sys.version_info >= (3, 13)
        else ""
    )
    return (
        f"未安装或无法加载长桥官方 Python SDK（当前 Python {version}）。"
        "请在项目目录执行：pip install -e './bottom_hunter[longbridge]'。"
        + suffix
    )


def load_sdk() -> SimpleNamespace:
    try:
        from longbridge.openapi import AdjustType, Config, Period, QuoteContext
    except (ImportError, OSError) as exc:
        raise LongbridgeSdkUnavailable(_sdk_install_hint()) from exc
    return SimpleNamespace(
        AdjustType=AdjustType,
        Config=Config,
        Period=Period,
        QuoteContext=QuoteContext,
    )


def normalize_symbol(symbol: str, market: str) -> str:
    value = str(symbol or "").strip().upper()
    market = str(market or "").strip().upper()
    if value.startswith("^"):
        raise LongbridgeSymbolUnsupported(f"长桥行情源不处理市场指数：{value}")
    if market == "CN":
        if value.endswith(".SS"):
            return value.removesuffix(".SS") + ".SH"
        if value.endswith(".SZ"):
            return value
        if value.endswith(".BJ"):
            raise LongbridgeSymbolUnsupported("长桥当前不覆盖北交所行情")
        if value.endswith((".SH", ".SZ")):
            return value
    elif market == "HK":
        raw = value.removesuffix(".HK")
        if raw.isdigit():
            return f"{int(raw)}.HK"
    elif market == "US":
        raw = value.removesuffix(".US")
        if raw and re_symbol(raw):
            return f"{raw}.US"
    raise LongbridgeSymbolUnsupported(f"无法转换长桥行情代码：{value or '<empty>'}")


def re_symbol(value: str) -> bool:
    return all(character.isalnum() or character in {"-", "."} for character in value)


class LongbridgeClient:
    """A quote-only wrapper. This class never imports or constructs TradeContext."""

    PERIOD_NAMES = {
        "1m": "Min_1",
        "5m": "Min_5",
        "15m": "Min_15",
        "30m": "Min_30",
        "60m": "Min_60",
        "4h": "Min_240",
        "1d": "Day",
        "1w": "Week",
        "1M": "Month",
    }

    def __init__(
        self,
        credentials: Mapping[str, Any] | None = None,
        *,
        credentials_loader: Callable[[], Mapping[str, Any]] | None = None,
        sdk_loader: Callable[[], Any] | None = None,
        context_factory: Callable[[dict[str, str], Any], Any] | None = None,
        max_concurrency: int = 5,
    ) -> None:
        self._credentials = sanitize_credentials(credentials) if credentials else {}
        self._credentials_loader = credentials_loader or runtime_credentials
        self._sdk_loader = sdk_loader or load_sdk
        self._context_factory = context_factory
        self._context: Any | None = None
        self._sdk: Any | None = None
        self._context_lock = threading.Lock()
        self._requests = threading.BoundedSemaphore(max(1, int(max_concurrency)))

    def configured(self) -> bool:
        if credentials_complete(self._credentials):
            return True
        loaded = dict(self._credentials_loader() or {})
        if credentials_complete(loaded):
            self._credentials = sanitize_credentials(loaded)
            return True
        return False

    def reset(self) -> None:
        """Drop the current quote session so changed credentials take effect."""

        with self._requests:
            with self._context_lock:
                self._credentials = {}
                self._context = None
                self._sdk = None

    def credentials(self) -> dict[str, str]:
        if not self.configured():
            raise LongbridgeNotConfigured("请先在“导入”页验证并启用长桥行情")
        return dict(self._credentials)

    def _bindings(self) -> Any:
        if self._sdk is None:
            self._sdk = self._sdk_loader()
        return self._sdk

    def _make_context(self) -> Any:
        bindings = self._bindings()
        credentials = self.credentials()
        if self._context_factory is not None:
            return self._context_factory(credentials, bindings)
        kwargs: dict[str, Any] = {
            "http_url": credentials["http_url"],
            "quote_ws_url": credentials["quote_ws_url"],
        }
        try:
            from_apikey = getattr(bindings.Config, "from_apikey", None)
            if callable(from_apikey):
                config = from_apikey(
                    credentials["app_key"],
                    credentials["app_secret"],
                    credentials["access_token"],
                    **kwargs,
                )
            else:
                # PyPI 0.2.x exposes the API-key constructor directly.
                config = bindings.Config(
                    credentials["app_key"],
                    credentials["app_secret"],
                    credentials["access_token"],
                    **kwargs,
                )
            return bindings.QuoteContext(config)
        except Exception as exc:
            raise LongbridgeError(f"初始化长桥只读行情连接失败：{exc}") from exc

    def context(self) -> Any:
        if self._context is None:
            with self._context_lock:
                if self._context is None:
                    self._context = self._make_context()
        return self._context

    @staticmethod
    def _package_names(values: Any) -> tuple[str, ...]:
        if not values:
            return ()
        result: list[str] = []
        for item in values:
            name = (
                getattr(item, "package_name", None)
                or getattr(item, "name", None)
                or str(item)
            )
            if str(name).strip():
                result.append(str(name).strip())
        return tuple(result)

    @staticmethod
    def _context_value(context: Any, name: str, default: str = "") -> str:
        value = getattr(context, name, None)
        if callable(value):
            value = value()
        return str(value) if value not in (None, "") else default

    def verify(self) -> LongbridgeVerification:
        try:
            with self._requests:
                context = self.context()
                member_id = self._context_value(context, "member_id")
                quote_level = self._context_value(context, "quote_level", "按账号套餐")
                package_accessor = getattr(context, "quote_package_details", None)
                package_values = package_accessor() if callable(package_accessor) else ()
                packages = self._package_names(package_values)
                if not member_id and not callable(package_accessor):
                    # PyPI 0.2.x does not expose connection metadata. Querying the
                    # current subscription list forces an authenticated round trip
                    # without assuming that a particular market package is enabled.
                    subscription_accessor = getattr(context, "subscriptions", None)
                    if callable(subscription_accessor):
                        subscription_accessor()
                    else:
                        context.static_info(["700.HK"])
        except LongbridgeError:
            raise
        except Exception as exc:
            raise LongbridgeError(f"长桥行情权限验证失败：{exc}") from exc
        return LongbridgeVerification(member_id, quote_level, packages)

    def candles(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        limit: int = 250,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> LongbridgeCandleResult:
        if timeframe not in self.PERIOD_NAMES:
            raise LongbridgeSymbolUnsupported(f"长桥不支持 K 线周期：{timeframe}")
        longbridge_symbol = normalize_symbol(symbol, market)
        bindings = self._bindings()
        period_name = self.PERIOD_NAMES[timeframe]
        aggregate_four_hours = timeframe == "4h" and not hasattr(
            bindings.Period, period_name
        )
        period = getattr(
            bindings.Period,
            "Min_60" if aggregate_four_hours else period_name,
        )
        adjust_type = bindings.AdjustType.ForwardAdjust
        try:
            with self._requests:
                context = self.context()
                if start is not None or end is not None:
                    values = context.history_candlesticks_by_date(
                        longbridge_symbol,
                        period,
                        adjust_type,
                        start,
                        end,
                    )
                else:
                    values = context.candlesticks(
                        longbridge_symbol,
                        period,
                        min(
                            1000,
                            max(1, int(limit) * (4 if aggregate_four_hours else 1)),
                        ),
                        adjust_type,
                    )
                quote_level = self._context_value(
                    context, "quote_level", "按账号套餐"
                )
        except LongbridgeError:
            raise
        except Exception as exc:
            raise LongbridgeError(
                f"长桥 {longbridge_symbol} 行情请求失败：{exc}"
            ) from exc
        bars = self._candles_frame(values, market)
        if aggregate_four_hours:
            bars = self._resample_four_hours(bars)
        return LongbridgeCandleResult(bars=bars, quote_level=quote_level)

    @staticmethod
    def _resample_four_hours(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        working = frame.copy()
        working["date"] = pd.to_datetime(working["date"], errors="coerce")
        working = working.dropna(subset=["date"]).set_index("date")
        result = working.resample(
            "4h", origin="start_day", label="right", closed="right"
        ).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        return result.dropna(subset=["open", "high", "low", "close"]).reset_index()

    @staticmethod
    def _candles_frame(values: Any, market: str) -> pd.DataFrame:
        zone = {"CN": "Asia/Shanghai", "HK": "Asia/Hong_Kong", "US": "America/New_York"}.get(
            str(market).upper(), "UTC"
        )
        rows: list[dict[str, Any]] = []
        for item in values or ():
            timestamp = getattr(item, "timestamp", None)
            if isinstance(timestamp, (int, float)):
                timestamp = pd.to_datetime(timestamp, unit="s", utc=True).tz_convert(zone)
            else:
                timestamp = pd.to_datetime(timestamp, errors="coerce")
                if isinstance(timestamp, pd.Timestamp) and timestamp.tzinfo is not None:
                    timestamp = timestamp.tz_convert(zone)
            rows.append(
                {
                    "date": timestamp,
                    "open": getattr(item, "open", None),
                    "high": getattr(item, "high", None),
                    "low": getattr(item, "low", None),
                    "close": getattr(item, "close", None),
                    "volume": getattr(item, "volume", 0),
                }
            )
        return pd.DataFrame(rows)
