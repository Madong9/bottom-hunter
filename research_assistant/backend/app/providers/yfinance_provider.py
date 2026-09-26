import hashlib
import html
import math
import re
from datetime import datetime, timezone
from typing import Any, ClassVar

import httpx
import pandas as pd
import yfinance as yf

from app.core.exceptions import DataProviderError
from app.providers.base import FinancialDataProvider
from app.schemas.agents import (
    CompanyProfile,
    FinancialSnapshot,
    MarketQuote,
    NewsItem,
    StockDataBundle,
)
from app.schemas.research import StockSearchItem


class YFinanceProvider(FinancialDataProvider):
    """Personal-use market-data provider for A-shares, Hong Kong and US equities."""

    _ignored_us_tokens: ClassVar[set[str]] = {
        "AI",
        "PE",
        "PB",
        "ROE",
        "TTM",
        "ETF",
        "VS",
        "SH",
        "SZ",
        "BJ",
        "HK",
        "US",
    }
    _known_companies = (
        (
            "600519.SH",
            "贵州茅台",
            "A股",
            "Beverages - Wineries & Distilleries",
            ("茅台",),
        ),
        ("300750.SZ", "宁德时代", "A股", "Electrical Equipment & Parts", ("CATL",)),
        ("002594.SZ", "比亚迪", "A股", "Auto Manufacturers", ("BYD",)),
        (
            "0700.HK",
            "腾讯控股",
            "港股",
            "Internet Content & Information",
            ("腾讯", "Tencent"),
        ),
        ("9988.HK", "阿里巴巴", "港股", "Internet Retail", ("阿里", "Alibaba")),
        ("3690.HK", "美团", "港股", "Internet Retail", ("Meituan",)),
        (
            "1024.HK",
            "快手科技",
            "港股",
            "Internet Content & Information",
            ("快手", "Kuaishou", "Kuaishou Technology"),
        ),
        (
            "AAPL.US",
            "Apple Inc.",
            "美股",
            "Consumer Electronics",
            ("Apple", "苹果", "苹果公司"),
        ),
        ("MSFT.US", "Microsoft Corporation", "美股", "Software", ("Microsoft", "微软")),
        (
            "NVDA.US",
            "NVIDIA Corporation",
            "美股",
            "Semiconductors",
            ("NVIDIA", "英伟达"),
        ),
        ("TSLA.US", "Tesla, Inc.", "美股", "Auto Manufacturers", ("Tesla", "特斯拉")),
    )

    _eastmoney_search_url = "https://searchapi.eastmoney.com/api/suggest/get"
    _eastmoney_public_token = "D43BF722C8E33BECE2D31D0925E07DAE"
    _known_descriptions: ClassVar[dict[str, str]] = {
        "1024.HK": "以短视频、直播、线上营销和电商为主要业务的内容社区平台。",
        "0700.HK": "业务覆盖社交通信、网络游戏、广告、金融科技与企业服务的综合互联网公司。",
        "9988.HK": "业务覆盖电商、云计算、本地生活与数字媒体的综合互联网公司。",
        "3690.HK": "以本地商业、外卖、到店酒旅和新业务为主的本地生活服务平台。",
    }

    def __init__(
        self,
        timeout_seconds: int = 15,
        search_client: httpx.Client | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._search_client = search_client
        self._catalog: dict[str, dict[str, Any]] = {
            symbol: {
                "symbol": symbol,
                "name": name,
                "market": market,
                "industry": industry,
                "aliases": [symbol, name, *aliases],
            }
            for symbol, name, market, industry, aliases in self._known_companies
        }
        self._search_cache: dict[str, list[StockSearchItem]] = {}

    @property
    def provider_name(self) -> str:
        return "Yahoo Finance"

    @property
    def is_real_data(self) -> bool:
        return True

    def stock_catalog(self) -> list[dict[str, Any]]:
        return list(self._catalog.values())

    def resolve_symbols(self, query: str) -> list[str]:
        resolved = self._explicit_symbols(query)
        normalized = query.casefold()
        for item in self._catalog.values():
            if any(alias.casefold() in normalized for alias in item["aliases"]):
                if item["symbol"] not in resolved:
                    resolved.append(item["symbol"])
        candidates = self._company_candidates(query)
        for candidate in candidates:
            for result in self.search_stocks(candidate)[:1]:
                if result.symbol not in resolved:
                    resolved.append(result.symbol)
        if not resolved:
            for result in self.search_stocks(query)[:1]:
                resolved.append(result.symbol)
        return resolved[:4]

    def source_url(self, symbol: str) -> str | None:
        return f"https://finance.yahoo.com/quote/{self._to_yahoo_symbol(symbol)}"

    def search_stocks(self, query: str) -> list[StockSearchItem]:
        needle = query.strip()
        if not needle:
            return [
                StockSearchItem(
                    symbol=item["symbol"],
                    name=item["name"],
                    market=item["market"],
                    industry=item.get("industry", "待确认"),
                )
                for item in self._catalog.values()
            ]
        local_results = [
            StockSearchItem(
                symbol=item["symbol"],
                name=item["name"],
                market=item["market"],
                industry=item["industry"],
            )
            for item in self._catalog.values()
            if any(needle.casefold() in alias.casefold() for alias in item["aliases"])
        ]
        if local_results:
            return local_results
        cached = self._search_cache.get(needle.casefold())
        if cached is not None:
            return cached
        if re.search(r"[\u4e00-\u9fff]", needle):
            chinese_results = self._search_chinese_stocks(needle)
            if chinese_results:
                self._search_cache[needle.casefold()] = chinese_results
                return chinese_results
        try:
            quotes = (
                yf.Search(
                    needle,
                    max_results=8,
                    news_count=0,
                    include_research=False,
                    timeout=self._timeout_seconds,
                    raise_errors=False,
                ).quotes
                or []
            )
        except Exception as exc:
            raise DataProviderError(f"股票搜索服务暂时不可用：{exc}") from exc

        if not isinstance(quotes, list):
            quotes = []

        results: list[StockSearchItem] = []
        for quote in quotes:
            if str(quote.get("quoteType", "")).upper() not in {"EQUITY", ""}:
                continue
            raw_symbol = str(quote.get("symbol", "")).upper()
            if not raw_symbol:
                continue
            symbol = self._to_canonical_symbol(raw_symbol)
            market = self._market_for_symbol(symbol)
            if market == "其他":
                continue
            name = str(quote.get("longname") or quote.get("shortname") or raw_symbol)
            industry = str(quote.get("industry") or quote.get("sector") or "待确认")
            item = StockSearchItem(
                symbol=symbol,
                name=name,
                market=market,
                industry=industry,
            )
            if symbol not in {existing.symbol for existing in results}:
                results.append(item)
                self._catalog[symbol] = {
                    "symbol": symbol,
                    "name": name,
                    "market": market,
                    "industry": industry,
                    "aliases": [raw_symbol, name],
                }
        self._search_cache[needle.casefold()] = results
        return results

    def _search_chinese_stocks(self, query: str) -> list[StockSearchItem]:
        params = {
            "input": query,
            "type": "14",
            "count": "10",
            "token": self._eastmoney_public_token,
        }
        try:
            if self._search_client is not None:
                response = self._search_client.get(
                    self._eastmoney_search_url, params=params
                )
            else:
                response = httpx.get(
                    self._eastmoney_search_url,
                    params=params,
                    timeout=self._timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
            quotation_table = payload.get("QuotationCodeTable") or {}
            raw_items = quotation_table.get("Data") or []
        except (httpx.HTTPError, TypeError, ValueError, AttributeError):
            return []

        if not isinstance(raw_items, list):
            return []

        results: list[StockSearchItem] = []
        for raw in raw_items:
            symbol = self._eastmoney_symbol(raw)
            if symbol is None:
                continue
            market = self._market_for_symbol(symbol)
            name = str(raw.get("Name") or symbol)
            item = StockSearchItem(
                symbol=symbol,
                name=name,
                market=market,
                industry="待获取",
            )
            if symbol in {existing.symbol for existing in results}:
                continue
            results.append(item)
            self._catalog[symbol] = {
                "symbol": symbol,
                "name": name,
                "market": market,
                "industry": "待获取",
                "aliases": [str(raw.get("Code") or ""), name],
            }
        return results

    @staticmethod
    def _eastmoney_symbol(raw: dict[str, Any]) -> str | None:
        code = str(raw.get("Code") or "").upper()
        security_type = str(raw.get("SecurityTypeName") or "")
        classify = str(raw.get("Classify") or "")
        quote_id = str(raw.get("QuoteID") or "")
        if not code:
            return None
        if classify == "HK" or "港股" in security_type:
            try:
                return f"{str(int(code)).zfill(4)}.HK"
            except ValueError:
                return None
        if classify == "UsStock" or "美股" in security_type:
            return f"{code}.US"
        if classify != "AStock":
            return None
        if "京" in security_type:
            suffix = "BJ"
        elif quote_id.startswith("1.") or "沪" in security_type:
            suffix = "SH"
        else:
            suffix = "SZ"
        return f"{code}.{suffix}"

    def get_stock(self, symbol: str) -> StockDataBundle | None:
        yahoo_symbol = self._to_yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)
        info: dict[str, Any] = {}
        history = pd.DataFrame()
        history_error: Exception | None = None
        try:
            history = ticker.history(
                period="5d", auto_adjust=False, timeout=self._timeout_seconds
            )
        except Exception as exc:
            history_error = exc

        price = None
        if not history.empty and "Close" in history:
            price = self._number(history["Close"].dropna().iloc[-1])
        info_error: Exception | None = None
        if price is None:
            try:
                raw_info = ticker.get_info()
                info = raw_info if isinstance(raw_info, dict) else {}
            except Exception as exc:
                info_error = exc
            price = self._number(
                info.get("currentPrice") or info.get("regularMarketPrice")
            )
        if price is None or price <= 0:
            details = info_error or history_error
            if details is not None:
                raise DataProviderError(
                    f"获取 {symbol} 行情失败：{details}"
                ) from details
            raise DataProviderError(
                f"{symbol} 缺少可用的最新价格，无法生成真实数据报告"
            )

        change_percent = self._number(info.get("regularMarketChangePercent"))
        if change_percent is None and len(history.index) >= 2:
            closes = history["Close"].dropna()
            change_percent = float((closes.iloc[-1] / closes.iloc[-2] - 1) * 100)
        as_of = datetime.now(timezone.utc)
        if not history.empty:
            timestamp = history.index[-1]
            as_of = timestamp.to_pydatetime()
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=timezone.utc)

        try:
            income = ticker.get_income_stmt(freq="yearly")
            balance = ticker.get_balance_sheet(freq="yearly")
            cashflow = ticker.get_cash_flow(freq="yearly")
        except Exception:
            income = pd.DataFrame()
            balance = pd.DataFrame()
            cashflow = pd.DataFrame()

        revenue_values = self._row_values(income, "Total Revenue", "Operating Revenue")
        profit_values = self._row_values(
            income, "Net Income", "Net Income Common Stockholders"
        )
        gross_values = self._row_values(income, "Gross Profit")
        assets_values = self._row_values(balance, "Total Assets")
        liabilities_values = self._row_values(
            balance,
            "Total Liabilities Net Minority Interest",
            "Total Liabilities",
        )
        cash_values = self._row_values(
            cashflow, "Operating Cash Flow", "Total Cash From Operating Activities"
        )

        revenue = self._first(revenue_values) or self._number(info.get("totalRevenue"))
        net_profit = self._first(profit_values) or self._number(
            info.get("netIncomeToCommon")
        )
        gross_profit = self._first(gross_values)
        revenue_growth = self._growth(revenue_values)
        if revenue_growth is None:
            revenue_growth = self._fraction_percent(info.get("revenueGrowth"))
        profit_growth = self._growth(profit_values)
        if profit_growth is None:
            profit_growth = self._fraction_percent(info.get("earningsGrowth"))
        gross_margin = (
            gross_profit / revenue * 100
            if gross_profit is not None and revenue not in (None, 0)
            else self._fraction_percent(info.get("grossMargins"))
        )
        roe = self._fraction_percent(info.get("returnOnEquity"))
        total_assets = self._first(assets_values)
        total_liabilities = self._first(liabilities_values)
        debt_ratio = (
            total_liabilities / total_assets * 100
            if total_liabilities is not None and total_assets not in (None, 0)
            else None
        )
        fiscal_period = "最近年度"
        if not income.empty and len(income.columns):
            column = income.columns[0]
            fiscal_period = (
                column.strftime("FY%Y") if hasattr(column, "strftime") else str(column)
            )

        canonical_symbol = self._to_canonical_symbol(yahoo_symbol)
        live_company_name = str(
            info.get("longName") or info.get("shortName") or canonical_symbol
        )
        existing_catalog_item = self._catalog.get(canonical_symbol, {})
        catalog_name = str(existing_catalog_item.get("name") or "")
        company_name = (
            catalog_name
            if re.search(r"[\u4e00-\u9fff]", catalog_name)
            else live_company_name
        )
        market = self._market_for_symbol(canonical_symbol)
        industry = str(
            info.get("industry")
            or info.get("sector")
            or existing_catalog_item.get("industry")
            or "待确认"
        )
        description = str(
            info.get("longBusinessSummary")
            or self._known_descriptions.get(canonical_symbol)
            or f"{company_name}是一家在{market}上市的公司，详细业务请查阅公司最新公告。"
        )
        self._catalog[canonical_symbol] = {
            "symbol": canonical_symbol,
            "name": company_name,
            "market": market,
            "industry": industry,
            "aliases": list(
                dict.fromkeys(
                    [
                        *existing_catalog_item.get("aliases", []),
                        yahoo_symbol,
                        live_company_name,
                        company_name,
                    ]
                )
            ),
        }

        return StockDataBundle(
            company=CompanyProfile(
                symbol=canonical_symbol,
                name=company_name,
                market=market,
                industry=industry,
                description=description,
            ),
            quote=MarketQuote(
                symbol=canonical_symbol,
                price=price,
                currency=str(
                    info.get("currency")
                    or {"A股": "CNY", "港股": "HKD", "美股": "USD"}.get(market)
                    or "待确认"
                ),
                change_percent=change_percent,
                pe_ttm=self._number(info.get("trailingPE")),
                pb=self._number(info.get("priceToBook")),
                market_cap_billion=self._billions(info.get("marketCap")),
                as_of=as_of,
            ),
            financial=FinancialSnapshot(
                symbol=canonical_symbol,
                fiscal_period=fiscal_period,
                revenue_billion=self._billions(revenue),
                revenue_growth_percent=revenue_growth,
                net_profit_billion=self._billions(net_profit),
                net_profit_growth_percent=profit_growth,
                gross_margin_percent=gross_margin,
                roe_percent=roe,
                debt_ratio_percent=debt_ratio,
                operating_cash_flow_billion=self._billions(self._first(cash_values)),
            ),
        )

    def get_news(self, symbols: list[str]) -> list[NewsItem]:
        news_items: list[NewsItem] = []
        seen_ids: set[str] = set()
        for symbol in symbols:
            yahoo_symbol = self._to_yahoo_symbol(symbol)
            try:
                raw_items = yf.Ticker(yahoo_symbol).get_news(count=20, tab="news") or []
            except Exception:
                continue
            if not isinstance(raw_items, list):
                continue
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                content = (
                    raw.get("content") if isinstance(raw.get("content"), dict) else raw
                )
                title = self._clean_news_text(content.get("title"))
                if not title:
                    continue
                summary = self._clean_news_text(
                    content.get("summary") or content.get("description") or title
                )
                provider_data = content.get("provider")
                source = (
                    self._clean_news_text(provider_data.get("displayName"))
                    if isinstance(provider_data, dict)
                    else self._clean_news_text(
                        content.get("publisher") or "Yahoo Finance"
                    )
                )
                source = source or "Yahoo Finance"
                url = self._news_url(content)
                published_at = self._news_datetime(content)
                news_id = str(content.get("id") or raw.get("id") or "")
                if not news_id:
                    news_id = hashlib.sha256(f"{title}|{url}".encode()).hexdigest()[:20]
                if news_id in seen_ids:
                    continue
                seen_ids.add(news_id)
                related = (
                    content.get("relatedTickers") or raw.get("relatedTickers") or []
                )
                if not isinstance(related, (list, tuple, set)):
                    related = []
                related_symbols = [
                    self._to_canonical_symbol(str(item)) for item in related
                ]
                aliases = self._catalog.get(symbol, {}).get("aliases", [])
                searchable_text = f"{title} {summary}".casefold()
                alias_match = any(
                    len(str(alias).strip()) >= 2
                    and str(alias).casefold() in searchable_text
                    for alias in aliases
                )
                if symbol not in related_symbols and not alias_match:
                    continue
                if symbol not in related_symbols:
                    related_symbols.append(symbol)
                news_items.append(
                    NewsItem(
                        news_id=f"yf-{news_id}",
                        symbols=related_symbols,
                        title=title,
                        summary=summary,
                        source=source,
                        published_at=published_at,
                        url=url,
                        sentiment=self._sentiment(f"{title} {summary}"),
                        credibility=self._credibility(source),
                    )
                )
        return news_items

    @staticmethod
    def _clean_news_text(value: Any) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]*>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _explicit_symbols(cls, query: str) -> list[str]:
        symbols: list[str] = []
        for value in re.findall(
            r"(?<!\d)(\d{6})(?:\.(SH|SZ|BJ))?(?!\d)", query.upper()
        ):
            code, suffix = value
            suffix = suffix or (
                "SH"
                if code.startswith("6")
                else "BJ"
                if code.startswith(("4", "8"))
                else "SZ"
            )
            symbols.append(f"{code}.{suffix}")
        for value in re.findall(r"(?<!\d)(\d{4,5})\.HK\b", query.upper()):
            symbols.append(f"{value.zfill(4)}.HK")
        for value in re.findall(r"\b([A-Z]{1,5})(?:\.US)?\b", query.upper()):
            if value not in cls._ignored_us_tokens:
                symbols.append(f"{value}.US")
        return list(dict.fromkeys(symbols))

    @staticmethod
    def _company_candidates(query: str) -> list[str]:
        normalized = re.sub(r"[？?！!，,。]", " ", query)
        parts = re.split(
            r"(?:比较|对比|和|与|、|\bvs\b)", normalized, flags=re.IGNORECASE
        )
        stop_phrases = (
            "请帮我",
            "帮我",
            "你来",
            "请",
            "分析",
            "研究",
            "看一下",
            "查一下",
            "查一查",
            "查询",
            "看看",
            "一下",
            "近期",
            "最近",
            "未来",
            "现在",
            "基本面",
            "估值",
            "新闻",
            "风险",
            "怎么样",
            "如何",
            "是什么意思",
            "能买吗",
            "可以买了吗",
            "PE",
            "ROE",
            "股票",
            "公司",
            "的",
        )
        candidates = []
        for part in parts:
            candidate = part.strip()
            for phrase in stop_phrases:
                candidate = candidate.replace(phrase, "")
            candidate = candidate.strip()
            looks_like_symbol = bool(
                re.fullmatch(
                    r"(?:\d{4,6}(?:\.(?:SH|SZ|BJ|HK))?|[A-Za-z]{1,5}(?:\.US)?)",
                    candidate,
                    flags=re.IGNORECASE,
                )
            )
            if (
                len(candidate) >= 2
                and not candidate.isdigit()
                and not looks_like_symbol
            ):
                candidates.append(candidate)
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _to_yahoo_symbol(symbol: str) -> str:
        upper = symbol.upper()
        if upper.endswith(".SH"):
            return f"{upper[:-3]}.SS"
        if upper.endswith(".US"):
            return upper[:-3]
        return upper

    @staticmethod
    def _to_canonical_symbol(symbol: str) -> str:
        upper = symbol.upper()
        if upper.endswith(".SS"):
            return f"{upper[:-3]}.SH"
        if upper.endswith((".SZ", ".BJ", ".HK")):
            return upper
        return f"{upper}.US"

    @staticmethod
    def _market_for_symbol(symbol: str) -> str:
        if symbol.endswith((".SH", ".SZ", ".BJ")):
            return "A股"
        if symbol.endswith(".HK"):
            return "港股"
        if symbol.endswith(".US"):
            return "美股"
        return "其他"

    @staticmethod
    def _row_values(frame: pd.DataFrame, *names: str) -> list[float]:
        if frame.empty:
            return []
        for name in names:
            if name in frame.index:
                values = []
                for value in frame.loc[name].tolist():
                    parsed = YFinanceProvider._number(value)
                    if parsed is not None:
                        values.append(parsed)
                return values
        return []

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _first(cls, values: list[float]) -> float | None:
        return values[0] if values else None

    @classmethod
    def _growth(cls, values: list[float]) -> float | None:
        if len(values) < 2 or values[1] <= 0:
            return None
        return (values[0] / values[1] - 1) * 100

    @classmethod
    def _billions(cls, value: Any) -> float | None:
        number = cls._number(value)
        return number / 1_000_000_000 if number is not None else None

    @classmethod
    def _fraction_percent(cls, value: Any) -> float | None:
        number = cls._number(value)
        return number * 100 if number is not None else None

    @staticmethod
    def _news_url(content: dict[str, Any]) -> str:
        for key in ("canonicalUrl", "clickThroughUrl"):
            value = content.get(key)
            if isinstance(value, dict) and value.get("url"):
                return str(value["url"])
        return str(content.get("link") or "https://finance.yahoo.com/")

    @staticmethod
    def _news_datetime(content: dict[str, Any]) -> datetime:
        iso_value = content.get("pubDate") or content.get("displayTime")
        if iso_value:
            try:
                return datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
            except ValueError:
                pass
        epoch = content.get("providerPublishTime")
        if epoch:
            try:
                return datetime.fromtimestamp(float(epoch), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _credibility(source: str) -> float:
        trusted = (
            "Reuters",
            "Bloomberg",
            "SEC",
            "Exchange",
            "公司公告",
            "Business Wire",
        )
        established = (
            "Yahoo Finance",
            "CNBC",
            "Forbes",
            "MarketWatch",
            "财联社",
            "证券时报",
        )
        if any(name.casefold() in source.casefold() for name in trusted):
            return 0.92
        if any(name.casefold() in source.casefold() for name in established):
            return 0.80
        return 0.68

    @staticmethod
    def _sentiment(text: str) -> str:
        lowered = text.casefold()
        negative = (
            "下滑",
            "下降",
            "亏损",
            "处罚",
            "调查",
            "recall",
            "decline",
            "loss",
            "lawsuit",
        )
        positive = (
            "增长",
            "提升",
            "扩张",
            "中标",
            "growth",
            "record",
            "expansion",
            "beats",
        )
        if any(word in lowered for word in negative):
            return "negative"
        if any(word in lowered for word in positive):
            return "positive"
        return "neutral"
