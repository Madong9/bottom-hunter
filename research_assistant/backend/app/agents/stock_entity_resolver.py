import json
import os
import re
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, ClassVar

from app.agents.base import BaseAgent
from app.core.exceptions import DataProviderError, StockNotFoundError
from app.providers.base import FinancialDataProvider
from app.schemas.agents import (
    ResolvedStockEntity,
    StockEntityResolverInput,
    StockEntityResolverOutput,
)
from app.schemas.common import Intent
from app.schemas.research import StockSearchItem


class StockEntityResolverAgent(
    BaseAgent[StockEntityResolverInput, StockEntityResolverOutput]
):
    """Resolve company names and codes before question understanding begins."""

    name = "stock_entity_resolver"
    _ignored_tickers: ClassVar[frozenset[str]] = frozenset(
        {"AI", "PE", "PB", "ROE", "TTM", "ETF", "VS", "SH", "SZ", "BJ", "HK", "US"}
    )
    _task_phrases = (
        "请帮我",
        "帮我",
        "你来",
        "请",
        "看一下",
        "查一下",
        "查一查",
        "查询",
        "看看",
        "分析",
        "研究",
        "解读",
        "比较",
        "对比",
        "同行",
        "竞品",
        "风险查询",
        "风险分析",
        "公司分析",
        "财务分析",
        "估值分析",
        "新闻解读",
        "基本面",
        "财务",
        "财报",
        "营收",
        "利润",
        "现金流",
        "毛利",
        "负债",
        "估值",
        "市盈率",
        "市净率",
        "风险",
        "隐患",
        "利空",
        "新闻",
        "消息",
        "舆情",
        "事件",
        "公告",
        "影响",
        "贵不贵",
        "怎么样",
        "如何",
        "是什么意思",
        "什么",
        "意思",
        "近期",
        "最近",
        "未来",
        "现在",
        "当前",
        "股票",
        "个股",
        "的",
        "PE",
        "PB",
        "ROE",
        "一下",
        "analyze",
        "analysis",
        "research",
        "compare",
        "comparison",
        "financial",
        "valuation",
        "risk",
        "news",
        "stock",
        "company",
        "A股",
        "港股",
        "美股",
        "沪市",
        "深市",
        "北交所",
        "科创板",
        "创业板",
        "纳斯达克",
        "纽交所",
        "with",
        "and",
        "of",
    )

    def __init__(
        self,
        provider: FinancialDataProvider,
        cache_path: str | Path | None = None,
        workspace_master_path: str | Path | None = None,
    ) -> None:
        self._provider = provider
        self._cache_path = self._normalize_cache_path(cache_path)
        self._workspace_master_path = self._resolve_workspace_master_path(
            workspace_master_path
        )
        self._lock = RLock()
        self._catalog: dict[str, dict[str, Any]] = {}
        self._initialize_cache()
        self._load_cache()
        self._load_workspace_master()
        self._load_provider_catalog()

    def run(self, agent_input: StockEntityResolverInput) -> StockEntityResolverOutput:
        explicit_symbols = self._explicit_symbols(agent_input.query)
        entities = [
            self._entity_for_symbol(symbol, symbol, "explicit_code", 1.0)
            for symbol in explicit_symbols
        ]
        terms = self._company_terms(agent_input.query, agent_input.routing.intent)
        preferred_market = self._preferred_market(agent_input.query)
        unresolved: list[str] = []

        for term in terms:
            if self._term_is_already_resolved(term, entities):
                continue
            matches = self._local_matches(term, preferred_market=preferred_market)
            if not matches:
                matches = self._remote_matches(term, preferred_market=preferred_market)
            if not matches:
                unresolved.append(term)
                continue
            if self._is_ambiguous(matches):
                choices = "、".join(
                    f"{item.name}（{item.symbol}）" for item in matches[:4]
                )
                raise StockNotFoundError(
                    f"公司名称“{term}”存在多个匹配：{choices}。请补充市场或股票代码。"
                )
            entities.append(matches[0])

        entities = list({item.symbol: item for item in entities}.values())
        if not entities:
            detail = (
                f"未识别到公司名称：{'、'.join(unresolved)}。"
                if unresolved
                else "未识别到股票。"
            )
            raise StockNotFoundError(
                detail + "请输入公司简称、全称或标准代码，"
                "例如：贵州茅台、腾讯、600519、0700.HK、AAPL。"
            )
        if agent_input.routing.intent == Intent.STOCK_COMPARISON and unresolved:
            raise StockNotFoundError(
                f"以下比较对象未识别：{'、'.join(unresolved)}。请补充股票代码后重试。"
            )
        if agent_input.routing.intent == Intent.STOCK_COMPARISON and len(entities) == 1:
            entities.extend(self._industry_peers(entities[0], limit=2))
        if agent_input.routing.intent == Intent.STOCK_COMPARISON and len(entities) < 2:
            raise StockNotFoundError(
                f"已识别{entities[0].name}，但未找到可解释的同行标的。"
                "请明确输入第二家公司，例如：比较快手和腾讯。"
            )

        return StockEntityResolverOutput(
            entities=entities,
            unresolved_terms=unresolved,
        )

    def _industry_peers(
        self, entity: ResolvedStockEntity, limit: int
    ) -> list[ResolvedStockEntity]:
        target = self._catalog.get(entity.symbol)
        if target is None:
            return []
        industry = self._normalize_name(str(target.get("industry") or ""))
        if not industry or industry in {"待获取", "待确认", "待分类", "其他"}:
            return []
        candidates = [
            item
            for item in self._catalog.values()
            if item["symbol"] != entity.symbol
            and self._normalize_name(str(item.get("industry") or "")) == industry
        ]
        candidates.sort(
            key=lambda item: (
                item["market"] != entity.market,
                item["source"] != "provider_catalog",
                item["symbol"],
            )
        )
        return [
            self._entity_for_item(
                item,
                matched_term=f"{entity.name}同行",
                confidence=0.82,
                source="industry_peer",
            )
            for item in candidates[:limit]
        ]

    def search_stocks(self, query: str, limit: int = 20) -> list[StockSearchItem]:
        preferred_market = self._preferred_market(query)
        matches = self._local_matches(
            query, limit=limit, preferred_market=preferred_market
        )
        if not matches:
            matches = self._remote_matches(
                query, limit=limit, preferred_market=preferred_market
            )
        return [
            StockSearchItem(
                symbol=item.symbol,
                name=item.name,
                market=item.market,
                industry=item.industry,
            )
            for item in matches[:limit]
        ]

    def _local_matches(
        self,
        term: str,
        limit: int = 8,
        preferred_market: str | None = None,
    ) -> list[ResolvedStockEntity]:
        needle = self._normalize_name(term)
        if not needle:
            return []
        ranked: list[ResolvedStockEntity] = []
        for item in self._catalog.values():
            best = 0.0
            for alias in item["aliases"]:
                normalized_alias = self._normalize_name(alias)
                if not normalized_alias:
                    continue
                if needle == normalized_alias:
                    best = max(best, 0.98)
                elif needle in normalized_alias:
                    best = max(best, 0.90)
                elif normalized_alias in needle and len(normalized_alias) >= 2:
                    best = max(best, 0.84)
            if best == 0:
                continue
            if preferred_market is not None and item["market"] != preferred_market:
                continue
            source_bonus = 0.015 if item["source"] == "provider_catalog" else 0
            ranked.append(
                self._entity_for_item(
                    item,
                    term,
                    min(1.0, best + source_bonus),
                )
            )
        ranked.sort(key=lambda item: (-item.confidence, item.market, item.symbol))
        return ranked[:limit]

    def _remote_matches(
        self,
        term: str,
        limit: int = 8,
        preferred_market: str | None = None,
    ) -> list[ResolvedStockEntity]:
        try:
            results = self._provider.search_stocks(term)
        except DataProviderError:
            return []
        if not results:
            return []
        self._ingest_search_results(results)
        matches = self._local_matches(
            term, limit=limit, preferred_market=preferred_market
        )
        if matches:
            return matches
        return [
            ResolvedStockEntity(
                symbol=item.symbol,
                name=item.name,
                market=item.market,
                industry=item.industry,
                matched_term=term,
                match_source="remote_search",
                confidence=0.76,
            )
            for item in results[:limit]
            if preferred_market is None or item.market == preferred_market
        ]

    def _entity_for_symbol(
        self,
        symbol: str,
        matched_term: str,
        source: str,
        confidence: float,
    ) -> ResolvedStockEntity:
        item = self._catalog.get(symbol)
        if item is None:
            market = self._market_for_symbol(symbol)
            return ResolvedStockEntity(
                symbol=symbol,
                name=symbol,
                market=market,
                industry="待获取",
                matched_term=matched_term,
                match_source=source,
                confidence=confidence,
            )
        return self._entity_for_item(item, matched_term, confidence, source)

    @staticmethod
    def _entity_for_item(
        item: dict[str, Any],
        matched_term: str,
        confidence: float,
        source: str | None = None,
    ) -> ResolvedStockEntity:
        return ResolvedStockEntity(
            symbol=item["symbol"],
            name=item["name"],
            market=item["market"],
            industry=item["industry"],
            matched_term=matched_term,
            match_source=source or item["source"],
            confidence=confidence,
        )

    def _load_provider_catalog(self) -> None:
        for raw in self._provider.stock_catalog():
            self._merge_item(
                symbol=self._canonical_symbol(
                    str(raw.get("symbol") or ""), str(raw.get("market") or "")
                ),
                name=str(raw.get("name") or ""),
                market=self._normalize_market(str(raw.get("market") or "")),
                industry=str(raw.get("industry") or "待获取"),
                aliases=[str(item) for item in raw.get("aliases", [])],
                source="provider_catalog",
            )

    def _load_workspace_master(self) -> None:
        path = self._workspace_master_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        for raw in payload.get("assets", []):
            if not isinstance(raw, dict) or raw.get("asset_type") != "equity":
                continue
            market = self._normalize_market(str(raw.get("market") or ""))
            symbol = self._canonical_symbol(str(raw.get("symbol") or ""), market)
            aliases = list((raw.get("source_symbols") or {}).values())
            self._merge_item(
                symbol=symbol,
                name=str(raw.get("name") or symbol),
                market=market,
                industry=str(raw.get("industry") or "待获取"),
                aliases=[str(item) for item in aliases],
                source="bottom_hunter_master",
            )

    def _ingest_search_results(self, results: list[StockSearchItem]) -> None:
        for result in results:
            self._merge_item(
                symbol=self._canonical_symbol(result.symbol, result.market),
                name=result.name,
                market=self._normalize_market(result.market),
                industry=result.industry,
                aliases=[],
                source="remote_search",
            )
        self._persist_cache()

    def _merge_item(
        self,
        *,
        symbol: str,
        name: str,
        market: str,
        industry: str,
        aliases: list[str],
        source: str,
    ) -> None:
        if not symbol or not name:
            return
        existing = self._catalog.get(symbol)
        combined_aliases = self._alias_variants(name, symbol, *aliases)
        if existing is not None:
            combined_aliases = list(
                dict.fromkeys([*existing["aliases"], *combined_aliases])
            )
            if source != "provider_catalog":
                name = existing["name"]
                market = existing["market"]
                industry = existing["industry"]
                source = existing["source"]
        self._catalog[symbol] = {
            "symbol": symbol,
            "name": name,
            "market": market or self._market_for_symbol(symbol),
            "industry": industry or "待获取",
            "aliases": combined_aliases,
            "source": source,
        }

    @classmethod
    def _company_terms(cls, query: str, intent: Intent) -> list[str]:
        text = re.sub(r"[？?！!，,。；;：:]", " ", query)
        if intent == Intent.STOCK_COMPARISON:
            parts = re.split(
                r"(?:比较|对比|同行|竞品|和|与|、|\bvs\b)", text, flags=re.IGNORECASE
            )
        else:
            parts = [text]
        terms: list[str] = []
        for part in parts:
            cleaned = part
            for phrase in sorted(cls._task_phrases, key=len, reverse=True):
                pattern = re.escape(phrase)
                if phrase.isascii():
                    pattern = rf"\b{pattern}\b"
                cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(
                r"\b\d{4,6}\.(?:SH|SS|SZ|BJ|HK)\b", " ", cleaned, flags=re.IGNORECASE
            )
            cleaned = re.sub(r"\b[A-Z]{1,5}\.US\b", " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_/·")
            if len(cls._normalize_name(cleaned)) >= 2:
                terms.append(cleaned)
        return list(dict.fromkeys(terms))

    @classmethod
    def _explicit_symbols(cls, query: str) -> list[str]:
        symbols: list[str] = []
        upper = query.upper()
        for code, suffix in re.findall(
            r"(?<!\d)(\d{6})(?:\.(SH|SS|SZ|BJ))?(?!\d)", upper
        ):
            suffix = suffix or (
                "SH"
                if code.startswith("6")
                else "BJ"
                if code.startswith(("4", "8"))
                else "SZ"
            )
            symbols.append(f"{code}.{('SH' if suffix == 'SS' else suffix)}")
        for code in re.findall(r"(?<!\d)(\d{4,5})\.HK\b", upper):
            symbols.append(f"{str(int(code)).zfill(4)}.HK")
        for ticker in re.findall(r"\b([A-Z]{1,5})\.US\b", upper):
            if ticker not in cls._ignored_tickers:
                symbols.append(f"{ticker}.US")
        return list(dict.fromkeys(symbols))

    @classmethod
    def _alias_variants(cls, *values: str) -> list[str]:
        aliases: list[str] = []
        for value in values:
            cleaned = str(value).strip()
            if not cleaned:
                continue
            aliases.append(cleaned)
            symbol_without_suffix = re.sub(
                r"\.(?:SH|SS|SZ|BJ|HK|US)$", "", cleaned, flags=re.IGNORECASE
            )
            if symbol_without_suffix != cleaned:
                aliases.append(symbol_without_suffix)
            without_share_suffix = re.sub(
                r"-(?:W|SW|B)$", "", cleaned, flags=re.IGNORECASE
            )
            aliases.append(without_share_suffix)
            shortened = re.sub(
                r"(?:股份有限公司|有限责任公司|控股|集团|科技|Corporation|Corp\.?|Incorporated|Inc\.?|Holdings?|Group|Limited|Ltd\.?)$",
                "",
                without_share_suffix,
                flags=re.IGNORECASE,
            ).strip()
            if len(cls._normalize_name(shortened)) >= 2:
                aliases.append(shortened)
        return list(dict.fromkeys(aliases))

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value.casefold())

    @staticmethod
    def _normalize_market(value: str) -> str:
        upper = value.upper()
        if upper in {"CN", "A股", "SH", "SZ", "BJ"}:
            return "A股"
        if upper in {"HK", "港股"}:
            return "港股"
        if upper in {"US", "美股"}:
            return "美股"
        return value or "其他"

    @staticmethod
    def _preferred_market(query: str) -> str | None:
        if re.search(r"港股|香港", query, flags=re.IGNORECASE):
            return "港股"
        if re.search(r"美股|纳斯达克|纽交所", query, flags=re.IGNORECASE):
            return "美股"
        if re.search(r"A股|沪市|深市|北交所|科创板|创业板", query, flags=re.IGNORECASE):
            return "A股"
        return None

    @classmethod
    def _canonical_symbol(cls, symbol: str, market: str) -> str:
        upper = symbol.strip().upper()
        if not upper:
            return ""
        upper = upper.replace(".SS", ".SH")
        normalized_market = cls._normalize_market(market)
        if upper.endswith((".SH", ".SZ", ".BJ", ".HK", ".US")):
            return upper
        if normalized_market == "A股" and upper.isdigit():
            suffix = (
                "SH"
                if upper.startswith("6")
                else "BJ"
                if upper.startswith(("4", "8"))
                else "SZ"
            )
            return f"{upper}.{suffix}"
        if normalized_market == "港股":
            try:
                return f"{str(int(upper)).zfill(4)}.HK"
            except ValueError:
                return f"{upper}.HK"
        if normalized_market == "美股":
            return f"{upper}.US"
        return upper

    @staticmethod
    def _market_for_symbol(symbol: str) -> str:
        if symbol.endswith((".SH", ".SZ", ".BJ")):
            return "A股"
        if symbol.endswith(".HK"):
            return "港股"
        if symbol.endswith(".US"):
            return "美股"
        return "其他"

    @classmethod
    def _term_is_already_resolved(
        cls, term: str, entities: list[ResolvedStockEntity]
    ) -> bool:
        needle = cls._normalize_name(term)
        return any(
            needle in cls._normalize_name(item.name)
            or needle == cls._normalize_name(item.symbol)
            for item in entities
        )

    @staticmethod
    def _is_ambiguous(matches: list[ResolvedStockEntity]) -> bool:
        return (
            len(matches) > 1
            and matches[0].symbol != matches[1].symbol
            and matches[0].confidence - matches[1].confidence < 0.01
        )

    @staticmethod
    def _normalize_cache_path(cache_path: str | Path | None) -> Path | None:
        if cache_path is None or str(cache_path) == ":memory:":
            return None
        return Path(cache_path).expanduser().resolve()

    @staticmethod
    def _resolve_workspace_master_path(value: str | Path | None) -> Path | None:
        configured = value or os.getenv("BOTTOM_HUNTER_SECURITY_MASTER_PATH")
        if configured:
            return Path(configured).expanduser().resolve()
        candidate = (
            Path(__file__).resolve().parents[4]
            / "bottom_hunter"
            / "state"
            / "watchlist_summary.json"
        )
        return candidate if candidate.is_file() else None

    def _initialize_cache(self) -> None:
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._cache_path, timeout=10) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS security_entities (
                    symbol TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def _load_cache(self) -> None:
        if self._cache_path is None:
            return
        with self._lock, sqlite3.connect(self._cache_path, timeout=10) as connection:
            rows = connection.execute(
                "SELECT payload_json FROM security_entities"
            ).fetchall()
        for (payload_json,) in rows:
            try:
                item = json.loads(payload_json)
                self._merge_item(**item)
            except (TypeError, ValueError):
                continue

    def _persist_cache(self) -> None:
        if self._cache_path is None:
            return
        rows = []
        for item in self._catalog.values():
            payload = {
                "symbol": item["symbol"],
                "name": item["name"],
                "market": item["market"],
                "industry": item["industry"],
                "aliases": item["aliases"],
                "source": item["source"],
            }
            rows.append((item["symbol"], json.dumps(payload, ensure_ascii=False)))
        with self._lock, sqlite3.connect(self._cache_path, timeout=10) as connection:
            connection.executemany(
                """
                INSERT INTO security_entities(symbol, payload_json) VALUES (?, ?)
                ON CONFLICT(symbol) DO UPDATE SET payload_json = excluded.payload_json
                """,
                rows,
            )
