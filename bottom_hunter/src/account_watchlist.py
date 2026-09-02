from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

import pandas as pd
import yaml

from .config import PROJECT_DIR
from .import_lock import ImportProcessLock
from .import_transaction import (
    ImportConflict,
    ImportVerificationResult,
    PlannedImportArtifact,
    PreparedFileFingerprint,
    PreparedImport,
    PreparedPathBaseline,
)
from .import_transaction_workspace import (
    ImportConflictError,
    ImportTransactionWorkspace,
    commit_prepared_import,
)
from .io_utils import EASTMONEY_SEARCH_TOKEN
from .io_utils import atomic_json as _atomic_json
from .network_config import apply_urllib

# Disable system proxy for watchlist search/index requests.
apply_urllib()

LOGGER = logging.getLogger(__name__)


SUPPORTED_SOURCES = ("tonghuashun", "binance", "okx")
SOURCE_LABELS = {
    "tonghuashun": "同花顺",
    "binance": "币安",
    "okx": "欧易",
}
CATEGORY_LABELS = {
    "crypto": "加密货币",
    "global_equity": "美港股",
    "cn_equity": "A股",
}
UNKNOWN_INDUSTRY = "待分类"
QUOTE_ASSETS = (
    "FDUSD",
    "USDT",
    "USDC",
    "TUSD",
    "BUSD",
    "USDE",
    "DAI",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "USD",
)

SYMBOL_FIELD_NAMES = (
    "symbol",
    "ticker",
    "code",
    "代码",
    "股票代码",
    "证券代码",
    "交易对",
    "instid",
    "pair",
)
NAME_FIELD_NAMES = (
    "name",
    "名称",
    "名称（按截图）",
    "名称(按截图)",
    "股票名称",
    "股票简称",
    "证券名称",
    "证券简称",
    "asset",
    "coin",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _file_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _prepared_file_fingerprint(path: Path) -> PreparedFileFingerprint:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return PreparedFileFingerprint(
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def _path_baseline(kind: str, path: Path) -> PreparedPathBaseline:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return PreparedPathBaseline(kind=kind, path=str(path), existed=False)
    return PreparedPathBaseline(kind=kind, path=str(path), existed=True, sha256=digest)


def _atomic_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    temporary.replace(path)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return _clean(value).casefold() in {"1", "true", "yes", "y", "是", "链上股票"}


def _row_value(row: Mapping[str, Any], *names: str) -> str:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.casefold())
        if value is not None and _clean(value):
            return _clean(value)
    return ""


def _normalize_source(source: str) -> str:
    normalized = source.strip().casefold()
    aliases = {
        "ths": "tonghuashun",
        "10jqka": "tonghuashun",
        "同花顺": "tonghuashun",
        "币安": "binance",
        "欧易": "okx",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_SOURCES:
        raise ValueError(f"不支持的自选来源：{source}")
    return normalized


def _normalize_market_hint(market_hint: str) -> str:
    hint = market_hint.strip().upper()
    aliases = {
        "A": "CN",
        "A股": "CN",
        "沪深": "CN",
        "沪深京": "CN",
        "CHINA": "CN",
        "港股": "HK",
        "HONG KONG": "HK",
        "美股": "US",
        "USA": "US",
        "OTC": "US",
    }
    return aliases.get(hint, hint)


def _equity_symbol(raw_symbol: str, market_hint: str = "") -> tuple[str, str]:
    symbol = raw_symbol.strip().upper().replace("SHSE.", "").replace("SZSE.", "").replace("BJSE.", "")
    symbol = symbol.replace(".SH", ".SS")
    hint = _normalize_market_hint(market_hint)
    prefixed = re.fullmatch(r"(SH|SZ|BJ)(\d{6})", symbol)
    if prefixed:
        prefix, code = prefixed.groups()
        suffix = {"SH": ".SS", "SZ": ".SZ", "BJ": ".BJ"}[prefix]
        return code + suffix, "CN"
    prefixed_hk = re.fullmatch(r"HK(\d{1,5})", symbol)
    if prefixed_hk:
        return prefixed_hk.group(1).zfill(4) + ".HK", "HK"
    if symbol.endswith((".SS", ".SZ", ".BJ")):
        return symbol, "CN"
    if symbol.endswith(".HK"):
        return symbol.removesuffix(".HK").zfill(4) + ".HK", "HK"
    if symbol.isdigit() and len(symbol) == 6:
        if symbol.startswith(("4", "8")):
            suffix = ".BJ"
        else:
            suffix = ".SS" if symbol.startswith(("5", "6", "9")) else ".SZ"
        return symbol + suffix, "CN"
    if symbol.isdigit() and 1 <= len(symbol) <= 5:
        return symbol.zfill(4) + ".HK", "HK"
    if hint == "HK":
        return symbol.removesuffix(".HK").zfill(4) + ".HK", "HK"
    return symbol, hint if hint in {"US", "HK", "CN"} else "US"


def _crypto_pair(raw_symbol: str, default_quote: str = "") -> tuple[str, str, str]:
    compact = raw_symbol.strip().upper().replace("/", "-").replace("_", "-")
    compact = compact.removesuffix("-SPOT")
    parts = [part for part in compact.split("-") if part]
    if len(parts) >= 2:
        base, quote_asset = parts[0], parts[1]
    else:
        plain = re.sub(r"[^A-Z0-9]", "", compact)
        quote_asset = next((quote for quote in QUOTE_ASSETS if plain.endswith(quote)), "")
        if not quote_asset and default_quote and plain:
            base = plain
            quote_asset = default_quote.upper()
        elif not quote_asset or len(plain) <= len(quote_asset):
            raise ValueError(f"无法识别加密货币交易对：{raw_symbol}")
        else:
            base = plain[: -len(quote_asset)]
    if not base or not quote_asset:
        raise ValueError(f"无法识别加密货币交易对：{raw_symbol}")
    return base, quote_asset, f"{base}-{quote_asset}"


def _keyword_industry(name: str) -> str:
    value = name.casefold()
    groups = (
        ("海外指数", ("标普", "纳指", "日经", "日本东证", "韩国综合")),
        ("红利与价值策略", ("红利", "现金流")),
        ("贵金属", ("黄金", "gold")),
        ("旅游与服务", ("旅游", "travel")),
        ("机器人与自动化", ("机器人", "robotics")),
        ("消费", ("消费", "consumer")),
        ("银行", ("银行", "bank", "bancorp")),
        ("保险", ("保险", "insurance")),
        ("证券", ("证券", "证券股份", "broker")),
        ("半导体", ("半导体", "芯片", "semiconductor")),
        ("软件与互联网", ("软件", "互联网", "software", "internet", "cloud")),
        ("通信设备", ("通信", "光模块", "telecom", "network")),
        ("电子元器件", ("pcb", "电子", "元器件", "display")),
        ("汽车", ("汽车", "车辆", "automotive", "motor")),
        ("医药生物", ("医药", "医疗", "生物", "pharma", "biotech", "health")),
        ("食品饮料", ("食品", "饮料", "酒", "food", "beverage")),
        ("房地产", ("地产", "置业", "房产", "real estate", "property")),
        ("电力与公用事业", ("电力", "电网", "能源", "utility", "power")),
        ("工业制造", ("工业", "机械", "制造", "industrial", "machinery")),
        ("材料", ("材料", "化工", "钢铁", "mining", "materials", "chemical")),
        ("商业零售", ("零售", "商业", "retail", "commerce")),
        ("传媒娱乐", ("传媒", "影业", "游戏", "media", "entertainment", "gaming")),
        ("航空航天与国防", ("航空", "航天", "军工", "aerospace", "defense")),
    )
    for industry, keywords in groups:
        if any(keyword in value for keyword in keywords):
            return industry
    return UNKNOWN_INDUSTRY


def _is_placeholder_name(asset: WatchAsset) -> bool:
    name = asset.name.strip().casefold()
    candidates = {
        asset.symbol.strip().casefold(),
        asset.source_symbol.strip().casefold(),
        asset.symbol.split(".", 1)[0].strip().casefold(),
    }
    return not name or name in candidates or "..." in name or "…" in name


INDUSTRY_TRANSLATIONS = {
    "technology": "信息技术",
    "financial services": "金融",
    "financial": "金融",
    "consumer cyclical": "可选消费",
    "consumer defensive": "必选消费",
    "communication services": "通信与传媒",
    "healthcare": "医疗保健",
    "industrials": "工业",
    "basic materials": "材料",
    "energy": "能源",
    "utilities": "公用事业",
    "real estate": "房地产",
}


@dataclass(frozen=True)
class WatchAsset:
    source: str
    source_symbol: str
    symbol: str
    name: str
    market: str
    category: str
    industry: str
    asset_type: str
    quote_currency: str = ""
    underlying_symbol: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def canonical_id(self) -> str:
        if self.category == "crypto":
            return f"crypto:{self.symbol.split('-', 1)[0]}"
        return f"equity:{self.market}:{self.symbol}"

    @property
    def tokenized_stock(self) -> bool:
        return self.asset_type == "tokenized_stock"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["canonical_id"] = self.canonical_id
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WatchAsset:
        return cls(
            source=_clean(payload.get("source")),
            source_symbol=_clean(payload.get("source_symbol")),
            symbol=_clean(payload.get("symbol")),
            name=_clean(payload.get("name")),
            market=_clean(payload.get("market")),
            category=_clean(payload.get("category")),
            industry=_clean(payload.get("industry")) or UNKNOWN_INDUSTRY,
            asset_type=_clean(payload.get("asset_type")),
            quote_currency=_clean(payload.get("quote_currency")),
            underlying_symbol=_clean(payload.get("underlying_symbol")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ImportResult:
    source: str
    imported_count: int
    merged_count: int
    duplicate_count: int
    unresolved_industry_count: int
    generated_sector_count: int
    active_watchlist: Path
    skipped_count: int = 0
    warnings: tuple[str, ...] = ()


def normalize_import_row(source: str, row: Mapping[str, Any]) -> WatchAsset:
    source = _normalize_source(source)
    raw_symbol = _row_value(row, *SYMBOL_FIELD_NAMES)
    if not raw_symbol:
        raise ValueError("自选记录缺少 symbol/代码/交易对")
    raw_name = _row_value(row, *NAME_FIELD_NAMES)
    market_hint = _row_value(
        row,
        "market",
        "市场",
        "市场/类别",
        "市场类别",
        "exchange",
        "交易所",
    )
    industry = _row_value(
        row,
        "industry",
        "sector",
        "行业",
        "所属行业",
        "领域",
        "行业领域",
    )
    asset_type_raw = _row_value(
        row,
        "asset_type",
        "instrument_type",
        "product_type",
        "资产类型",
        "证券类型",
        "产品类型",
        "类别",
    ).casefold()
    tokenized = asset_type_raw in {
        "tokenized_stock",
        "tokenized equity",
        "equity token",
        "stock token",
        "链上股票",
        "股票代币",
        "杠杆etf",
        "leveraged etf",
    } or _truthy(_row_value(row, "tokenized_stock", "is_tokenized_stock", "链上股票"))
    if source != "tonghuashun" and asset_type_raw in {"equity", "stock", "股票"}:
        tokenized = True
    tokenized = tokenized or _row_value(row, "instCategory", "instrument_category") == "3"
    inferred_underlying = ""
    if source == "okx" and not tokenized:
        try:
            okx_base, _okx_quote, _okx_pair = _crypto_pair(raw_symbol)
        except ValueError:
            okx_base = ""
        # Unified Tokenized Stocks use an X-prefixed ticker, e.g. XAAPL.
        if re.fullmatch(r"X[A-Z]{1,6}", okx_base):
            tokenized = True
            inferred_underlying = okx_base[1:]

    if source == "tonghuashun":
        unsupported_types = {"概念指数", "行业指数", "期货/主连", "期货", "主连"}
        unsupported_markets = {"同花顺", "商品", "韩国"}
        if asset_type_raw in unsupported_types or market_hint.strip() in unsupported_markets:
            detail = asset_type_raw or market_hint.strip()
            raise ValueError(f"暂不支持扫描此类非证券标的：{raw_name or raw_symbol}（{detail}）")
        symbol, market = _equity_symbol(raw_symbol, market_hint)
        category = "cn_equity" if market == "CN" else "global_equity"
        name = raw_name or symbol
        asset_type = "etf" if asset_type_raw in {"etf", "基金"} else "equity"
        return WatchAsset(
            source,
            raw_symbol,
            symbol,
            name,
            market,
            category,
            industry or _keyword_industry(name),
            asset_type,
        )

    if tokenized:
        underlying = _row_value(
            row,
            "underlying_symbol",
            "underlying",
            "ticker",
            "底层股票",
            "正股代码",
        )
        underlying = underlying or inferred_underlying
        if not underlying:
            try:
                base_asset, _quote_asset, _pair = _crypto_pair(raw_symbol)
                if source == "okx" and re.fullmatch(r"X[A-Z]{1,6}", base_asset):
                    underlying = base_asset[1:]
                elif source == "binance" and base_asset.endswith("B"):
                    underlying = base_asset[:-1]
                elif source == "binance" and base_asset.endswith("ON"):
                    underlying = base_asset[:-2]
                else:
                    underlying = base_asset
            except ValueError:
                underlying = raw_symbol
        symbol, market = _equity_symbol(underlying, market_hint or "US")
        name = raw_name or symbol
        return WatchAsset(
            source,
            raw_symbol,
            symbol,
            name,
            market,
            "global_equity",
            industry or _keyword_industry(name),
            "tokenized_stock",
            underlying_symbol=symbol,
        )

    base_asset, quote_asset, pair = _crypto_pair(raw_symbol, default_quote="USDT")
    source_pair = f"{base_asset}{quote_asset}" if source == "binance" else pair
    return WatchAsset(
        source,
        source_pair,
        pair,
        raw_name or base_asset,
        "CRYPTO",
        "crypto",
        "加密货币",
        "crypto",
        quote_currency=quote_asset,
    )


def _decode_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-16", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别文件编码：{path.name}")


def _rows_from_json(content: str) -> list[dict[str, Any]]:
    payload = json.loads(content)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next(
            (
                value
                for key in ("items", "symbols", "watchlist", "favorites", "data")
                if isinstance((value := payload.get(key)), list)
            ),
            [],
        )
    else:
        rows = []
    return [dict(item) if isinstance(item, dict) else {"symbol": item} for item in rows]


def _rows_from_delimited(content: str) -> list[dict[str, Any]]:
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    fieldnames = [str(name or "").strip().casefold() for name in (reader.fieldnames or [])]
    known = {name.casefold() for name in (*SYMBOL_FIELD_NAMES, *NAME_FIELD_NAMES)}
    if known.intersection(fieldnames):
        return [dict(row) for row in reader if any(_clean(value) for value in row.values())]
    rows: list[dict[str, Any]] = []
    for line in content.splitlines():
        cleaned = line.strip().strip('"')
        if not cleaned or cleaned.startswith(("#", "//")):
            continue
        ths_match = re.fullmatch(r"\d+\|(\d{4,6})", cleaned)
        if ths_match:
            rows.append({"symbol": ths_match.group(1)})
            continue
        parts = [part.strip() for part in re.split(r"[,\t; ]+", cleaned) if part.strip()]
        if not parts:
            continue
        row: dict[str, Any] = {"symbol": parts[0]}
        if len(parts) > 1:
            row["name"] = parts[1]
        if len(parts) > 2:
            row["industry"] = parts[2]
        rows.append(row)
    return rows


def _looks_like_equity_code(value: str) -> bool:
    compact = value.strip().upper()
    return bool(
        re.fullmatch(r"(?:SH|SZ|BJ)?\d{4,6}(?:\.(?:SS|SZ|BJ|HK))?", compact)
        or re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", compact)
    )


def _rows_from_spreadsheet(path: Path) -> list[dict[str, Any]]:
    try:
        sheets = pd.read_excel(
            path,
            sheet_name=None,
            header=None,
            dtype=str,
            keep_default_na=False,
        )
    except Exception as exc:
        raise ValueError(f"无法读取表格 {path.name}：{exc}") from exc

    known_headers = {name.casefold() for name in (*SYMBOL_FIELD_NAMES, *NAME_FIELD_NAMES)}
    rows: list[dict[str, Any]] = []
    for frame in sheets.values():
        if frame.empty:
            continue
        header_index: int | None = None
        headers: list[str] = []
        for index in range(min(30, len(frame.index))):
            candidate = [_clean(value) for value in frame.iloc[index].tolist()]
            if known_headers.intersection(value.casefold() for value in candidate if value):
                header_index = index
                headers = candidate
                break
        if header_index is not None:
            for row_index in range(header_index + 1, len(frame.index)):
                values = [_clean(value) for value in frame.iloc[row_index].tolist()]
                row = {
                    header: values[column]
                    for column, header in enumerate(headers)
                    if header and column < len(values) and values[column]
                }
                if row:
                    rows.append(row)
            continue

        # A table without a header is still useful when each row starts with a
        # stock code or name. Additional columns are interpreted conservatively.
        for row_values in frame.itertuples(index=False, name=None):
            values = [_clean(value) for value in row_values if _clean(value)]
            if not values:
                continue
            if _looks_like_equity_code(values[0]):
                row = {"symbol": values[0]}
                if len(values) > 1:
                    row["name"] = values[1]
                if len(values) > 2:
                    row["industry"] = values[2]
            else:
                row = {"name": values[0]}
                if len(values) > 1:
                    row["industry"] = values[1]
            rows.append(row)
    return rows


def search_equities(query: str, market_hint: str = "", timeout: int = 8) -> list[dict[str, str]]:
    """Search A/H/US equities for an explicit user confirmation or exact name match."""

    cleaned_query = query.strip()
    if not cleaned_query:
        return []
    params = {
        "input": cleaned_query,
        "type": "14",
        "token": EASTMONEY_SEARCH_TOKEN,
        "count": "20",
    }
    request = Request(
        "https://searchapi.eastmoney.com/api/suggest/get?" + urlencode(params),
        headers={
            "User-Agent": "Mozilla/5.0 BottomHunter/0.4",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except Exception as exc:
        raise ValueError(f"股票名称查询失败，请检查网络后重试：{exc}") from exc

    market_by_classify = {"AStock": "CN", "HK": "HK", "UsStock": "US"}
    requested_market = _normalize_market_hint(market_hint)
    raw_items = payload.get("QuotationCodeTable", {}).get("Data") or []
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_items:
        classify = _clean(item.get("Classify"))
        market = market_by_classify.get(classify)
        if not market or (requested_market in {"CN", "HK", "US"} and market != requested_market):
            continue
        code = _clean(item.get("Code"))
        name = _clean(item.get("Name"))
        if not code or not name:
            continue
        symbol, normalized_market = _equity_symbol(code, market)
        key = (normalized_market, symbol)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "symbol": symbol,
                "code": code,
                "name": name,
                "market": normalized_market,
                "security_type": _clean(item.get("SecurityTypeName")),
                "quote_id": _clean(item.get("QuoteID")),
            }
        )

    query_folded = cleaned_query.casefold()
    candidates.sort(
        key=lambda item: (
            item["name"].casefold() != query_folded,
            item["code"].casefold() != query_folded and item["symbol"].casefold() != query_folded,
            item["market"],
            item["symbol"],
        )
    )
    return candidates


def _resolve_name_only_row(source: str, row: Mapping[str, Any]) -> dict[str, Any]:
    resolved_row = dict(row)
    if _row_value(resolved_row, *SYMBOL_FIELD_NAMES):
        return resolved_row
    name = _row_value(resolved_row, *NAME_FIELD_NAMES)
    if source != "tonghuashun" or not name:
        return resolved_row
    market_hint = _row_value(resolved_row, "market", "市场", "exchange", "交易所")
    matches = [
        candidate for candidate in search_equities(name, market_hint) if candidate["name"].casefold() == name.casefold()
    ]
    if len(matches) != 1:
        reason = "没有精确匹配" if not matches else f"找到 {len(matches)} 个同名结果"
        raise ValueError(f"股票名称“{name}”{reason}，请在表格中补充股票代码和市场")
    match = matches[0]
    resolved_row["symbol"] = match["symbol"]
    resolved_row.setdefault("name", match["name"])
    resolved_row.setdefault("market", match["market"])
    return resolved_row


def _rows_from_ths_sel(raw: bytes) -> list[dict[str, Any]]:
    """Read the binary board export created by Tonghuashun desktop clients."""

    rows: list[dict[str, Any]] = []
    # Classic SEL records are: 0x07, one-byte market id, six ASCII digits.
    for match in re.finditer(rb"\x07[\x00-\xff](\d{6})", raw):
        rows.append({"symbol": match.group(1).decode("ascii")})
    if rows:
        return rows
    # Some OEM clients export a text-flavoured SEL. Keep this fallback strict.
    for code in re.findall(rb"(?<!\d)(\d{6})(?!\d)", raw):
        rows.append({"symbol": code.decode("ascii")})
    return rows


def _rows_from_ths_stockblock(content: str) -> list[dict[str, Any]]:
    """Extract only user self-selected boards from Tonghuashun StockBlock.ini."""

    sections: dict[str, list[str]] = {}
    current = ""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        section_match = re.fullmatch(r"\[([^]]+)\]", line)
        if section_match:
            current = section_match.group(1).strip()
            sections.setdefault(current, [])
        elif current and line and not line.startswith((";", "#")):
            sections[current].append(line)

    names: dict[str, str] = {}
    for line in sections.get("BLOCK_NAME_MAP_TABLE", []):
        if "=" in line:
            key, value = line.split("=", 1)
            names[key.strip()] = value.strip()
    selected_ids = {
        key
        for key, value in names.items()
        if value.strip().casefold() in {"自选股", "我的自选", "self stock", "selfstock"}
    }

    candidate_lines: list[str] = []
    for line in sections.get("BLOCK_STOCK_CONTEXT", []):
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in selected_ids:
            candidate_lines.append(value)
    for section, lines in sections.items():
        if "自选" in section or section.casefold() in {"selfstock", "self stock"}:
            candidate_lines.extend(lines)

    rows: list[dict[str, Any]] = []
    for line in candidate_lines:
        for code in re.findall(r"(?:\d+:)?([0-9]{4,6}|[A-Z]{1,6}(?:\.[A-Z]{1,4})?)", line.upper()):
            rows.append({"symbol": code})
    return rows


def parse_watchlist_file(
    path: str | Path,
    source: str,
    *,
    failures_out: list[str] | None = None,
) -> list[WatchAsset]:
    source = _normalize_source(source)
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"自选文件不存在：{file_path}")
    try:
        suffix = file_path.suffix.casefold()
        if suffix in {".xlsx", ".xls", ".xlsm"}:
            rows = _rows_from_spreadsheet(file_path)
        elif source == "tonghuashun" and suffix == ".sel":
            rows = _rows_from_ths_sel(file_path.read_bytes())
        else:
            content = _decode_text(file_path)
            if source == "tonghuashun" and file_path.name.casefold() == "stockblock.ini":
                rows = _rows_from_ths_stockblock(content)
            elif suffix == ".json":
                rows = _rows_from_json(content)
            else:
                rows = _rows_from_delimited(content)
    except (json.JSONDecodeError, csv.Error) as exc:
        raise ValueError(f"无法解析 {file_path.name}：{exc}") from exc
    resolved_rows: list[Mapping[str, Any] | None] = list(rows)
    resolution_failures: dict[int, str] = {}
    name_only_indexes = [
        index
        for index, row in enumerate(rows)
        if source == "tonghuashun"
        and not _row_value(row, *SYMBOL_FIELD_NAMES)
        and bool(_row_value(row, *NAME_FIELD_NAMES))
    ]
    if name_only_indexes:
        with ThreadPoolExecutor(max_workers=min(6, len(name_only_indexes))) as executor:
            futures = {
                executor.submit(_resolve_name_only_row, source, rows[index]): index for index in name_only_indexes
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    resolved_rows[index] = future.result()
                except Exception as exc:
                    resolved_rows[index] = None
                    resolution_failures[index] = str(exc)

    assets: dict[str, WatchAsset] = {}
    failures: list[str] = []
    for line_number, row in enumerate(resolved_rows, 1):
        if row is None:
            failures.append(f"第 {line_number} 条：{resolution_failures[line_number - 1]}")
            continue
        try:
            asset = normalize_import_row(source, row)
        except ValueError as exc:
            failures.append(f"第 {line_number} 条：{exc}")
            continue
        assets[asset.canonical_id] = asset
    if not assets:
        detail = "；".join(failures[:3]) if failures else "没有识别到股票代码或名称列"
        raise ValueError(f"自选文件中没有可用标的：{detail}")
    if failures_out is not None:
        failures_out.extend(failures)
    return list(assets.values())


class IndustryResolver:
    """Best-effort stock name/industry resolver with a persistent cache."""

    PROFILE_URL = "https://push2.eastmoney.com/api/qt/stock/get"

    def __init__(self, cache_path: Path, timeout: int = 4) -> None:
        self.cache_path = cache_path
        self.timeout = timeout
        try:
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.cache = {}
        self._cache_lock = Lock()

    def resolve(self, asset: WatchAsset) -> str:
        return self.resolve_profile(asset)["industry"]

    def resolve_profile(self, asset: WatchAsset) -> dict[str, str]:
        if asset.category == "crypto":
            return {"name": asset.name, "industry": asset.industry, "source": "import"}
        needs_name = _is_placeholder_name(asset)
        needs_industry = asset.industry == UNKNOWN_INDUSTRY
        if not needs_name and not needs_industry:
            return {"name": asset.name, "industry": asset.industry, "source": "import"}

        with self._cache_lock:
            cached = dict(self.cache.get(asset.canonical_id) or {})
        name = _clean(cached.get("name")) if needs_name else asset.name
        industry = _clean(cached.get("industry")) if needs_industry else asset.industry
        sources = [_clean(cached.get("source"))] if cached else []

        if (needs_name and not name) or (needs_industry and not industry):
            eastmoney = self._eastmoney_profile(asset)
            if needs_name and not name:
                name = _clean(eastmoney.get("name"))
            if needs_industry and not industry:
                industry = _clean(eastmoney.get("industry"))
            if eastmoney:
                sources.append("eastmoney_stock_profile")

        if needs_industry and not industry:
            industry = self._yahoo_industry(asset)
            if industry:
                sources.append("yahoo_asset_profile")

        resolved = {
            "name": name or asset.name,
            "industry": industry or UNKNOWN_INDUSTRY,
            "source": "+".join(filter(None, sources)) or "unresolved",
        }
        if resolved["name"] != asset.name or resolved["industry"] != asset.industry:
            with self._cache_lock:
                self.cache[asset.canonical_id] = {
                    **cached,
                    **resolved,
                    "updated_at": _utc_now(),
                }
        return resolved

    def _eastmoney_quote_id(self, asset: WatchAsset) -> str:
        symbol = asset.symbol.upper()
        if asset.market == "CN" and symbol.endswith(".SS"):
            return "1." + symbol.removesuffix(".SS")
        if asset.market == "CN" and symbol.endswith((".SZ", ".BJ")):
            return "0." + symbol.rsplit(".", 1)[0]
        if asset.market == "HK" and symbol.endswith(".HK"):
            return "116." + symbol.removesuffix(".HK").zfill(5)
        if asset.market == "US":
            exact = [
                item
                for item in search_equities(symbol, "US", timeout=self.timeout)
                if item["symbol"].casefold() == symbol.casefold() and _clean(item.get("quote_id"))
            ]
            if exact:
                return exact[0]["quote_id"]
        return ""

    def _eastmoney_profile(self, asset: WatchAsset) -> dict[str, str]:
        quote_id = self._eastmoney_quote_id(asset)
        if not quote_id:
            return {}
        request = Request(
            self.PROFILE_URL + "?" + urlencode({"secid": quote_id, "fields": "f57,f58,f127"}),
            headers={
                "User-Agent": "Mozilla/5.0 BottomHunter/0.5",
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except Exception as exc:
            LOGGER.warning("东财资料获取失败 (%s)：%s", asset.symbol, exc)
            return {}
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return {}
        name = re.sub(r"\s*\(已切换\)$", "", _clean(data.get("f58")))
        return {
            "name": name,
            "industry": _clean(data.get("f127")),
        }

    def _yahoo_industry(self, asset: WatchAsset) -> str:
        url = (
            "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{quote(asset.symbol, safe='')}?{urlencode({'modules': 'assetProfile'})}"
        )
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 BottomHunter/0.3"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except Exception as exc:
            LOGGER.warning("Yahoo 行业资料获取失败 (%s)：%s", asset.symbol, exc)
            return ""
        results = payload.get("quoteSummary", {}).get("result") or []
        if not results:
            return ""
        profile = results[0].get("assetProfile") or {}
        industry = _clean(profile.get("industry"))
        sector = _clean(profile.get("sector"))
        if industry:
            return industry
        return INDUSTRY_TRANSLATIONS.get(sector.casefold(), sector)

    def save(self) -> None:
        _atomic_json(self.cache_path, self.cache)


class AccountWatchlistRepository:
    def __init__(
        self,
        project_dir: str | Path = PROJECT_DIR,
        *,
        state_dir: str | Path | None = None,
        config_dir: str | Path | None = None,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.state_dir = Path(state_dir).resolve() if state_dir else self.project_dir / "state"
        self.config_dir = Path(config_dir).resolve() if config_dir else self.project_dir / "config"
        self.snapshot_dir = self.state_dir / "watchlists"
        self.summary_path = self.state_dir / "watchlist_summary.json"
        self.industry_cache_path = self.state_dir / "industry_cache.json"
        self.override_path = self.config_dir / "industry_overrides.yaml"
        self.active_watchlist_path = self.config_dir / "watchlist.yaml"
        self._summary_cache: tuple[int, int, dict[str, Any]] | None = None

    def source_snapshot_path(self, source: str) -> Path:
        return self.snapshot_dir / f"{_normalize_source(source)}.json"

    def _capture_import_baselines(self) -> tuple[PreparedPathBaseline, ...]:
        paths = [
            *((f"source_snapshot:{source}", self.source_snapshot_path(source)) for source in SUPPORTED_SOURCES),
            ("industry_overrides", self.override_path),
            ("industry_cache", self.industry_cache_path),
            ("active_watchlist", self.active_watchlist_path),
            ("watchlist_summary", self.summary_path),
        ]
        return tuple(_path_baseline(kind, path) for kind, path in paths)

    def _load_source_payload(self, source: str) -> dict[str, Any]:
        path = self.source_snapshot_path(source)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def load_source_assets(self, source: str) -> list[WatchAsset]:
        payload = self._load_source_payload(source)
        return [WatchAsset.from_dict(item) for item in payload.get("items") or []]

    def source_status(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for source in SUPPORTED_SOURCES:
            payload = self._load_source_payload(source)
            items = payload.get("items") or []
            result[source] = {
                "source": source,
                "label": SOURCE_LABELS[source],
                "account_alias": _clean(payload.get("account_alias")),
                "imported_at": _clean(payload.get("imported_at")),
                "count": len(items),
                "manual_count": sum(
                    _clean((item.get("metadata") or {}).get("entry_method")) == "manual"
                    for item in items
                    if isinstance(item, dict)
                ),
                "import_file": _clean(payload.get("import_file")),
                "file_signature": dict(payload.get("file_signature") or {}),
                "connected": bool(payload),
            }
        return result

    def prepare_import(
        self,
        source: str,
        path: str | Path,
        account_alias: str = "",
        *,
        resolve_industries: bool = True,
        transaction_id: str,
    ) -> PreparedImport:
        """Build a complete import plan without mutating repository state."""

        normalized_transaction_id = transaction_id.strip()
        if not normalized_transaction_id:
            raise ValueError("prepare_import 缺少 transaction_id")
        source = _normalize_source(source)
        file_path = Path(path).expanduser().resolve()
        fingerprint = _prepared_file_fingerprint(file_path)
        baselines = self._capture_import_baselines()
        import_warnings: list[str] = []
        assets = parse_watchlist_file(file_path, source, failures_out=import_warnings)
        if _prepared_file_fingerprint(file_path) != fingerprint:
            raise ValueError("导入文件在解析期间已变化，请重新预览")

        industry_cache_payload: dict[str, Any] | None = None
        if resolve_industries:
            assets, resolver, _cache_changed = self._resolve_industries_in_memory(assets)
            industry_cache_payload = dict(resolver.cache)

        source_payloads = {item_source: self._load_source_payload(item_source) for item_source in SUPPORTED_SOURCES}
        previous = source_payloads[source]
        previous_assets = [WatchAsset.from_dict(item) for item in previous.get("items") or []]
        manual_assets = {
            asset.canonical_id: asset
            for asset in previous_assets
            if _clean(asset.metadata.get("entry_method")) == "manual"
        }
        combined = {asset.canonical_id: asset for asset in assets}
        combined.update(manual_assets)
        generated_at = _utc_now()
        source_snapshot = {
            "schema_version": 2,
            "source": source,
            "source_label": SOURCE_LABELS[source],
            "account_alias": account_alias.strip() or _clean(previous.get("account_alias")),
            "import_file": str(file_path),
            "file_signature": {
                "size": fingerprint.size,
                "mtime_ns": fingerprint.mtime_ns,
            },
            "imported_at": generated_at,
            "items": [asset.to_dict() for asset in combined.values()],
        }
        source_payloads[source] = source_snapshot
        assets_by_source = {
            item_source: [WatchAsset.from_dict(item) for item in payload.get("items") or []]
            for item_source, payload in source_payloads.items()
        }
        merged_assets = self._merge_assets(assets_by_source, self._industry_overrides())
        source_counts = {item_source: len(items) for item_source, items in assets_by_source.items()}
        watchlist, summary = self._build_active_watchlist_payloads(
            merged_assets,
            source_counts,
            generated_at,
        )
        if self._capture_import_baselines() != baselines:
            raise RuntimeError("导入准备期间 repository 状态已变化，请重试")

        artifacts: list[PlannedImportArtifact] = []
        if industry_cache_payload is not None:
            artifacts.append(
                PlannedImportArtifact(
                    kind="industry_cache",
                    target=str(self.industry_cache_path),
                    format="json",
                    payload=industry_cache_payload,
                )
            )
        artifacts.extend(
            (
                PlannedImportArtifact(
                    kind="source_snapshot",
                    target=str(self.source_snapshot_path(source)),
                    format="json",
                    payload=source_snapshot,
                ),
                PlannedImportArtifact(
                    kind="active_watchlist",
                    target=str(self.active_watchlist_path),
                    format="yaml",
                    payload=watchlist,
                ),
                PlannedImportArtifact(
                    kind="watchlist_summary",
                    target=str(self.summary_path),
                    format="json",
                    payload=summary,
                ),
            )
        )
        return PreparedImport(
            transaction_id=normalized_transaction_id,
            source=source,
            source_file=str(file_path),
            prepared_at=generated_at,
            fingerprint=fingerprint,
            baselines=baselines,
            parsed_assets=tuple(assets),
            warnings=tuple(import_warnings),
            imported_count=len(assets),
            merged_count=int(summary["asset_count"]),
            duplicate_count=int(summary["overlap_count"]),
            unresolved_industry_count=int(summary["unresolved_industry_count"]),
            generated_sector_count=int(summary["sector_count"]),
            planned_artifacts=tuple(artifacts),
        )

    def verify_import(
        self,
        prepared: PreparedImport,
        *,
        max_age_seconds: int = 900,
        now: datetime | None = None,
    ) -> ImportVerificationResult:
        """Validate a prepared plan against current read-only repository state."""

        conflicts: list[ImportConflict] = []
        try:
            actual_fingerprint = _prepared_file_fingerprint(Path(prepared.source_file))
        except OSError as exc:
            conflicts.append(
                ImportConflict(
                    code="SOURCE_FILE_UNAVAILABLE",
                    message=f"无法读取导入源文件：{exc}",
                    path=prepared.source_file,
                    expected=prepared.fingerprint.sha256,
                    actual="unavailable",
                )
            )
        else:
            if actual_fingerprint != prepared.fingerprint:
                conflicts.append(
                    ImportConflict(
                        code="SOURCE_FILE_CHANGED",
                        message="导入源文件在 prepare 后已变化。",
                        path=prepared.source_file,
                        expected=prepared.fingerprint.sha256,
                        actual=actual_fingerprint.sha256,
                    )
                )

        current_time = now or datetime.now(UTC)
        try:
            prepared_time = datetime.fromisoformat(prepared.prepared_at)
            if prepared_time.tzinfo is None:
                prepared_time = prepared_time.replace(tzinfo=UTC)
            age_seconds = (current_time - prepared_time).total_seconds()
        except (TypeError, ValueError):
            conflicts.append(
                ImportConflict(
                    code="INVALID_PREPARED_AT",
                    message="PreparedImport 的准备时间无效。",
                    actual=prepared.prepared_at,
                )
            )
        else:
            if age_seconds > max_age_seconds:
                conflicts.append(
                    ImportConflict(
                        code="TRANSACTION_EXPIRED",
                        message="导入准备结果已过期，请重新预览。",
                        expected=f"<={max_age_seconds}s",
                        actual=f"{int(age_seconds)}s",
                    )
                )

        baseline_paths = {baseline.path for baseline in prepared.baselines}
        for artifact in prepared.planned_artifacts:
            if artifact.target not in baseline_paths:
                conflicts.append(
                    ImportConflict(
                        code="MISSING_TARGET_BASELINE",
                        message="候选产物缺少目标文件基线。",
                        path=artifact.target,
                    )
                )

        for baseline in prepared.baselines:
            try:
                actual = _path_baseline(baseline.kind, Path(baseline.path))
            except OSError as exc:
                conflicts.append(
                    ImportConflict(
                        code="BASELINE_UNAVAILABLE",
                        message=f"无法验证 repository 基线：{exc}",
                        path=baseline.path,
                        expected=baseline.sha256 if baseline.existed else "missing",
                        actual="unavailable",
                    )
                )
                continue
            if actual.existed == baseline.existed and actual.sha256 == baseline.sha256:
                continue
            if baseline.kind == f"source_snapshot:{prepared.source}":
                code = "SOURCE_SNAPSHOT_CHANGED"
            elif baseline.kind == "industry_overrides":
                code = "INDUSTRY_OVERRIDE_CHANGED"
            elif baseline.kind in {"industry_cache", "active_watchlist", "watchlist_summary"}:
                code = "TARGET_CHANGED"
            else:
                code = "DEPENDENCY_CHANGED"
            conflicts.append(
                ImportConflict(
                    code=code,
                    message=f"{baseline.kind} 在 prepare 后已变化。",
                    path=baseline.path,
                    expected=baseline.sha256 if baseline.existed else "missing",
                    actual=actual.sha256 if actual.existed else "missing",
                )
            )

        return ImportVerificationResult(
            transaction_id=prepared.transaction_id,
            valid=not conflicts,
            conflicts=tuple(conflicts),
        )

    def import_file(
        self,
        source: str,
        path: str | Path,
        account_alias: str = "",
        *,
        resolve_industries: bool = True,
    ) -> ImportResult:
        transaction_id = f"legacy-{uuid4().hex}"
        with ImportProcessLock(self.state_dir, transaction_id):
            prepared = self.prepare_import(
                source,
                path,
                account_alias,
                resolve_industries=resolve_industries,
                transaction_id=transaction_id,
            )
            verification = self.verify_import(prepared)
            if not verification.valid:
                raise ImportConflictError(verification)
            workspace = ImportTransactionWorkspace(
                self.state_dir,
                transaction_id,
                allowed_target_roots=(self.state_dir, self.config_dir),
            )
            commit_prepared_import(self, prepared, workspace)
        self._summary_cache = None
        return ImportResult(
            source=prepared.source,
            imported_count=prepared.imported_count,
            merged_count=prepared.merged_count,
            duplicate_count=prepared.duplicate_count,
            unresolved_industry_count=prepared.unresolved_industry_count,
            generated_sector_count=prepared.generated_sector_count,
            active_watchlist=self.active_watchlist_path,
            skipped_count=len(prepared.warnings),
            warnings=prepared.warnings[:20],
        )

    def add_manual_asset(
        self,
        source: str,
        row: Mapping[str, Any],
        account_alias: str = "",
        *,
        resolve_industry: bool = True,
    ) -> tuple[WatchAsset, dict[str, Any]]:
        source = _normalize_source(source)
        asset = normalize_import_row(source, row)
        previous = self._load_source_payload(source)
        existing = {item.canonical_id: item for item in self.load_source_assets(source)}
        old_asset = existing.get(asset.canonical_id)
        added_at = (
            _clean(old_asset.metadata.get("added_at"))
            if old_asset and _clean(old_asset.metadata.get("entry_method")) == "manual"
            else _utc_now()
        )
        asset = WatchAsset(
            **{
                **asdict(asset),
                "metadata": {
                    **asset.metadata,
                    "entry_method": "manual",
                    "added_at": added_at,
                },
            }
        )
        if resolve_industry:
            asset = self._resolve_industries([asset])[0]
        existing[asset.canonical_id] = asset
        snapshot = {
            "schema_version": 2,
            "source": source,
            "source_label": SOURCE_LABELS[source],
            "account_alias": account_alias.strip() or _clean(previous.get("account_alias")),
            "import_file": _clean(previous.get("import_file")),
            "file_signature": dict(previous.get("file_signature") or {}),
            "imported_at": _clean(previous.get("imported_at")),
            "manual_updated_at": _utc_now(),
            "items": [item.to_dict() for item in existing.values()],
        }
        _atomic_json(self.source_snapshot_path(source), snapshot)
        summary = self.rebuild_active_watchlist()
        return asset, summary

    def _resolve_industries(self, assets: list[WatchAsset]) -> list[WatchAsset]:
        prepared_assets, resolver, _cache_changed = self._resolve_industries_in_memory(assets)
        resolver.save()
        return prepared_assets

    def _resolve_industries_in_memory(
        self,
        assets: list[WatchAsset],
    ) -> tuple[list[WatchAsset], IndustryResolver, bool]:
        """Resolve profiles and return a cache plan without persisting it."""

        resolver = IndustryResolver(self.industry_cache_path)
        original_cache = dict(resolver.cache)
        unresolved = [
            asset
            for asset in assets
            if asset.category != "crypto" and (asset.industry == UNKNOWN_INDUSTRY or _is_placeholder_name(asset))
        ]
        resolved: dict[str, dict[str, str]] = {}
        with ThreadPoolExecutor(max_workers=min(6, max(1, len(unresolved)))) as executor:
            futures = {executor.submit(resolver.resolve_profile, asset): asset for asset in unresolved}
            for future in as_completed(futures):
                asset = futures[future]
                try:
                    resolved[asset.canonical_id] = future.result()
                except Exception:
                    resolved[asset.canonical_id] = {
                        "name": asset.name,
                        "industry": asset.industry,
                        "source": "unresolved",
                    }
        prepared_assets = [
            WatchAsset(
                **{
                    **asdict(asset),
                    "name": resolved.get(asset.canonical_id, {}).get("name", asset.name),
                    "industry": resolved.get(asset.canonical_id, {}).get("industry", asset.industry),
                    "metadata": {
                        **asset.metadata,
                        **(
                            {"profile_source": resolved[asset.canonical_id]["source"]}
                            if asset.canonical_id in resolved
                            else {}
                        ),
                    },
                }
            )
            for asset in assets
        ]
        return prepared_assets, resolver, resolver.cache != original_cache

    def _industry_overrides(self) -> dict[str, str]:
        try:
            payload = yaml.safe_load(self.override_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return {}
        values = payload.get("overrides", payload)
        return {
            _clean(key): _clean(value)
            for key, value in (values.items() if isinstance(values, dict) else [])
            if _clean(key) and _clean(value)
        }

    def update_industry(self, canonical_id: str, industry: str) -> dict[str, Any]:
        cleaned = industry.strip()
        if not cleaned or cleaned == "加密货币":
            raise ValueError("股票行业不能为空，也不能设为加密货币")
        overrides = self._industry_overrides()
        overrides[canonical_id] = cleaned
        _atomic_yaml(self.override_path, {"overrides": dict(sorted(overrides.items()))})
        return self.rebuild_active_watchlist()

    def clear_source(self, source: str) -> dict[str, Any]:
        path = self.source_snapshot_path(source)
        if path.exists():
            path.unlink()
        return self.rebuild_active_watchlist()

    def changed_linked_sources(self) -> list[str]:
        changed: list[str] = []
        for source in SUPPORTED_SOURCES:
            payload = self._load_source_payload(source)
            import_file = _clean(payload.get("import_file"))
            if not import_file:
                continue
            path = Path(import_file).expanduser()
            expected = payload.get("file_signature") or {}
            try:
                actual = _file_signature(path)
            except OSError:
                changed.append(source)
                continue
            if expected:
                if actual != {
                    "size": int(expected.get("size", -1)),
                    "mtime_ns": int(expected.get("mtime_ns", -1)),
                }:
                    changed.append(source)
                continue
            # Snapshots created before file signatures were introduced are
            # considered current when the source file predates the import.
            imported_at = _clean(payload.get("imported_at"))
            try:
                imported_timestamp = datetime.fromisoformat(imported_at).timestamp()
            except (ValueError, TypeError):
                changed.append(source)
            else:
                if path.stat().st_mtime > imported_timestamp + 1:
                    changed.append(source)
        return changed

    def refresh_linked_files(
        self,
        *,
        force: bool = True,
    ) -> tuple[dict[str, Any], list[str], dict[str, str]]:
        """Re-import files selected earlier, retaining the last good snapshot on errors."""

        refreshed: list[str] = []
        errors: dict[str, str] = {}
        statuses = self.source_status()
        changed_sources = set(SUPPORTED_SOURCES if force else self.changed_linked_sources())
        for source in SUPPORTED_SOURCES:
            if source not in changed_sources:
                continue
            status = statuses[source]
            import_file = _clean(status.get("import_file"))
            if not import_file:
                continue
            try:
                self.import_file(
                    source,
                    import_file,
                    _clean(status.get("account_alias")),
                    resolve_industries=True,
                )
            except Exception as exc:
                errors[source] = str(exc)
            else:
                refreshed.append(source)
        return self.summary(), refreshed, errors

    @staticmethod
    def _merge_assets(
        assets_by_source: Mapping[str, list[WatchAsset]],
        overrides: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        """Pure cross-source merge used by preparation and legacy rebuilds."""

        merged: dict[str, dict[str, Any]] = {}
        for source in SUPPORTED_SOURCES:
            for asset in assets_by_source.get(source, []):
                key = asset.canonical_id
                current = merged.get(key)
                if current is None:
                    current = {
                        "canonical_id": key,
                        "symbol": asset.symbol,
                        "name": asset.name,
                        "market": asset.market,
                        "category": asset.category,
                        "industry": asset.industry,
                        "asset_type": asset.asset_type,
                        "tokenized_stock": asset.tokenized_stock,
                        "quote_currency": asset.quote_currency,
                        "underlying_symbol": asset.underlying_symbol,
                        "sources": [],
                        "source_symbols": {},
                    }
                    merged[key] = current
                current["sources"].append(source)
                current["source_symbols"][source] = asset.source_symbol
                current["tokenized_stock"] = bool(current["tokenized_stock"] or asset.tokenized_stock)
                if current["industry"] == UNKNOWN_INDUSTRY and asset.industry != UNKNOWN_INDUSTRY:
                    current["industry"] = asset.industry
                if current["name"] in {current["symbol"], current["symbol"].split("-", 1)[0]}:
                    current["name"] = asset.name
        for key, item in merged.items():
            item["sources"] = sorted(set(item["sources"]), key=SUPPORTED_SOURCES.index)
            if key in overrides and item["category"] != "crypto":
                item["industry"] = overrides[key]
            if item["category"] == "crypto":
                preferred_source = "binance" if "binance" in item["sources"] else item["sources"][0]
                preferred_symbol = item["source_symbols"][preferred_source]
                try:
                    base, quote_asset, pair = _crypto_pair(preferred_symbol)
                    item["symbol"] = pair
                    item["name"] = item["name"] or base
                    item["quote_currency"] = quote_asset
                except ValueError:
                    pass
            if item["tokenized_stock"] and item["asset_type"] == "equity":
                item["asset_type"] = "equity+tokenized_stock"
        return sorted(
            merged.values(),
            key=lambda item: (
                ("crypto", "global_equity", "cn_equity").index(item["category"]),
                item["industry"],
                item["symbol"],
            ),
        )

    def merged_assets(self) -> list[dict[str, Any]]:
        assets_by_source = {source: self.load_source_assets(source) for source in SUPPORTED_SOURCES}
        return self._merge_assets(assets_by_source, self._industry_overrides())

    @staticmethod
    def _sector_id(category: str, industry: str) -> str:
        if category == "crypto":
            return "crypto_all"
        digest = hashlib.sha1(industry.encode("utf-8")).hexdigest()[:10]
        prefix = "cn" if category == "cn_equity" else "global"
        return f"{prefix}_industry_{digest}"

    @classmethod
    def _build_active_watchlist_payloads(
        cls,
        assets: list[dict[str, Any]],
        source_counts: Mapping[str, int],
        generated_at: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Pure builder for active-watchlist and summary payloads."""

        markets: dict[str, dict[str, Any]] = {
            "CN": {
                "name": "A股",
                "category": "cn_equity",
                "calendar": "XSHG",
                "timezone": "Asia/Shanghai",
                "close_time": "15:00",
                "benchmark": "000001.SS",
            },
            "HK": {
                "name": "港股",
                "category": "global_equity",
                "calendar": "XHKG",
                "timezone": "Asia/Hong_Kong",
                "close_time": "16:00",
                "benchmark": "^HSI",
            },
            "US": {
                "name": "美股",
                "category": "global_equity",
                "calendar": "XNYS",
                "timezone": "America/New_York",
                "close_time": "16:00",
                "benchmark": "^GSPC",
            },
            "CRYPTO": {
                "name": "加密货币",
                "category": "crypto",
                "calendar": "24/7",
                "timezone": "UTC",
                "close_time": "00:00",
                "benchmark": "BTC-USDT",
                "benchmark_source_symbols": {
                    "binance": "BTCUSDT",
                    "okx": "BTC-USDT",
                },
            },
        }
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for asset in assets:
            industry = "加密货币" if asset["category"] == "crypto" else asset["industry"]
            grouped.setdefault((asset["category"], industry), []).append(asset)
        sectors: dict[str, dict[str, Any]] = {}
        for (category, industry), items in sorted(grouped.items()):
            sector_id = cls._sector_id(category, industry)
            category_label = CATEGORY_LABELS[category]
            sector_name = category_label if category == "crypto" else f"{category_label} · {industry}"
            sector_assets: list[dict[str, Any]] = []
            for item in items:
                sector_assets.append(
                    {
                        "symbol": item["symbol"],
                        "name": item["name"],
                        "market": item["market"],
                        "industry": industry,
                        "category": category,
                        "asset_type": item["asset_type"],
                        "tokenized_stock": bool(item["tokenized_stock"]),
                        "sources": item["sources"],
                        "source_symbols": item["source_symbols"],
                        "volume_optional": False,
                    }
                )
            sectors[sector_id] = {
                "name": sector_name,
                "category": category,
                "industry": industry,
                "dynamic": True,
                "etfs": [],
                "assets": sector_assets,
            }
        watchlist = {
            "schema_version": 2,
            "mode": "account_watchlists",
            "generated_at": generated_at,
            "description": "由同花顺、币安和欧易账号自选快照生成；不含内置公司列表。",
            "markets": markets,
            "sectors": sectors,
            "risk_appetite": [],
        }
        category_counts = {
            category: sum(item["category"] == category for item in assets) for category in CATEGORY_LABELS
        }
        summary = {
            "generated_at": watchlist["generated_at"],
            "asset_count": len(assets),
            "sector_count": len(sectors),
            "overlap_count": sum(len(item["sources"]) > 1 for item in assets),
            "tokenized_stock_count": sum(bool(item["tokenized_stock"]) for item in assets),
            "unresolved_industry_count": sum(
                item["category"] != "crypto" and item["industry"] == UNKNOWN_INDUSTRY for item in assets
            ),
            "category_counts": category_counts,
            "source_counts": {source: int(source_counts.get(source, 0)) for source in SUPPORTED_SOURCES},
            "assets": assets,
            "sectors": [
                {
                    "sector_id": sector_id,
                    "name": sector["name"],
                    "category": sector["category"],
                    "industry": sector["industry"],
                    "asset_count": len(sector["assets"]),
                }
                for sector_id, sector in sectors.items()
            ],
        }
        return watchlist, summary

    def rebuild_active_watchlist(self) -> dict[str, Any]:
        assets = self.merged_assets()
        source_counts = {source: len(self.load_source_assets(source)) for source in SUPPORTED_SOURCES}
        watchlist, summary = self._build_active_watchlist_payloads(
            assets,
            source_counts,
            _utc_now(),
        )
        _atomic_yaml(self.active_watchlist_path, watchlist)
        _atomic_json(self.summary_path, summary)
        self._summary_cache = None
        return summary

    def summary(self) -> dict[str, Any]:
        try:
            stat = self.summary_path.stat()
            cached = self._summary_cache
            if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
                return cached[2]
            data = json.loads(self.summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.rebuild_active_watchlist()
        self._summary_cache = (stat.st_mtime_ns, stat.st_size, data)
        return data
