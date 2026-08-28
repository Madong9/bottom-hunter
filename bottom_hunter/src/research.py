from __future__ import annotations

import csv
import html
import io
import json
import re
import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import PROJECT_DIR
from .models import FundamentalResult, Instrument
from .network_config import apply_requests_session
from .research_models import (
    FinancialFact,
    MacroObservation,
    ResearchItem,
    ResearchKind,
    ResearchSnapshot,
    SourceTier,
)
from .research_storage import ResearchStore

USER_AGENT = "BottomHunter/0.1 research client (local desktop application)"
POSITIVE_WORDS = (
    "超预期", "增长", "盈利", "增持", "回购", "中标", "突破", "上调",
    "beat", "growth", "upgrade", "profit", "buyback",
)
NEGATIVE_WORDS = (
    "低于预期", "亏损", "减持", "问询", "处罚", "诉讼", "下调", "风险",
    "miss", "loss", "downgrade", "lawsuit", "warning",
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_datetime(value: Any, fallback: datetime | None = None) -> datetime:
    fallback = fallback or datetime.now(UTC)
    if isinstance(value, datetime):
        return _aware(value)
    cleaned = str(value or "").strip()
    if not cleaned:
        return fallback
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        # Eastmoney sometimes emits milliseconds as HH:MM:SS:mmm.
        cleaned = re.sub(r"(\d{2}:\d{2}:\d{2}):(\d{3})$", r"\1.\2", cleaned)
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            try:
                parsed = parsedate_to_datetime(cleaned)
            except (TypeError, ValueError):
                return fallback
    return _aware(parsed)


def _strip_html(value: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def classify_sentiment(text: str) -> tuple[str, float]:
    normalized = text.casefold()
    positive = sum(word.casefold() in normalized for word in POSITIVE_WORDS)
    negative = sum(word.casefold() in normalized for word in NEGATIVE_WORDS)
    if positive > negative:
        return "bullish", min(0.85, 0.55 + 0.08 * (positive - negative))
    if negative > positive:
        return "bearish", min(0.85, 0.55 + 0.08 * (negative - positive))
    return "neutral", 0.5


def build_session(timeout_retries: int = 2) -> requests.Session:
    session = requests.Session()
    apply_requests_session(session)
    retry = Retry(
        total=max(0, timeout_retries),
        connect=max(0, timeout_retries),
        read=max(0, timeout_retries),
        backoff_factor=0.35,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,text/*,*/*"})
    return session


@dataclass(frozen=True)
class MacroSeriesDefinition:
    series_id: str
    name: str
    dimension: str
    unit: str
    favorable_direction: int = 0


@dataclass(frozen=True)
class ResearchConfig:
    timeout: int
    retries: int
    max_news_items: int
    news_enabled: bool
    language: str
    region: str
    community_sites: tuple[str, ...]
    macro_series: tuple[MacroSeriesDefinition, ...]
    macro_impact: Mapping[str, Mapping[str, tuple[str, ...]]]
    refresh: Mapping[str, int]

    @classmethod
    def load(cls, path: str | Path | None = None) -> ResearchConfig:
        config_path = Path(path) if path else PROJECT_DIR / "config" / "research.yaml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        network = payload.get("network") or {}
        news = payload.get("news") or {}
        definitions = tuple(
            MacroSeriesDefinition(
                series_id=str(item["id"]),
                name=str(item.get("name") or item["id"]),
                dimension=str(item.get("dimension") or "其他"),
                unit=str(item.get("unit") or ""),
                favorable_direction=max(-1, min(1, int(item.get("favorable_direction", 0)))),
            )
            for item in payload.get("macro_series") or []
        )
        macro_impact = {
            str(dimension): {
                "positive": tuple(str(value) for value in (mapping or {}).get("positive") or ()),
                "negative": tuple(str(value) for value in (mapping or {}).get("negative") or ()),
            }
            for dimension, mapping in (payload.get("macro_impact") or {}).items()
        }
        return cls(
            timeout=max(3, min(60, int(network.get("timeout_seconds", 12)))),
            retries=max(0, min(5, int(network.get("retries", 2)))),
            max_news_items=max(5, min(100, int(news.get("max_items", 30)))),
            news_enabled=bool(news.get("enabled", True)),
            language=str(news.get("language", "zh-CN")),
            region=str(news.get("region", "CN")),
            community_sites=tuple(str(value) for value in news.get("community_sites") or ()),
            macro_series=definitions,
            macro_impact=macro_impact,
            refresh={str(key): int(value) for key, value in (payload.get("refresh") or {}).items()},
        )


class EastmoneyResearchProvider:
    FINANCIAL_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew"
    ANNOUNCEMENT_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    METRICS = {
        "TOTALOPERATEREVE": ("营业收入", "CNY"),
        "PARENTNETPROFIT": ("归母净利润", "CNY"),
        "KCFJCXSYJLR": ("扣非净利润", "CNY"),
        "FCFF_FORWARD": ("自由现金流", "CNY"),
        "EPSJB": ("基本每股收益", "CNY/股"),
        "ROEJQ": ("ROE", "%"),
        "XSMLL": ("毛利率", "%"),
        "XSJLL": ("净利率", "%"),
        "ZCFZL": ("资产负债率", "%"),
        "TOTALOPERATEREVETZ": ("营收同比", "%"),
        "PARENTNETPROFITTZ": ("净利润同比", "%"),
    }

    def __init__(self, session: requests.Session, timeout: int = 12):
        self.session = session
        self.timeout = timeout

    @staticmethod
    def _code(symbol: str) -> str:
        code = symbol.split(".", 1)[0]
        prefix = "SH" if symbol.upper().endswith(".SS") else "SZ"
        return prefix + code

    def financial_facts(self, asset: Mapping[str, Any]) -> list[FinancialFact]:
        if str(asset.get("market")) != "CN":
            return []
        response = self.session.get(
            self.FINANCIAL_URL,
            params={"type": "0", "code": self._code(str(asset["symbol"]))},
            timeout=self.timeout,
            headers={"Referer": "https://quote.eastmoney.com/"},
        )
        response.raise_for_status()
        rows = response.json().get("data") or []
        result: list[FinancialFact] = []
        source_url = f"https://emweb.securities.eastmoney.com/PC_HSF10/FinanceAnalysis/index?code={self._code(str(asset['symbol']))}"
        for row in rows[:12]:
            try:
                period_end = date.fromisoformat(str(row["REPORT_DATE"])[:10])
                filed_at = _parse_datetime(row.get("NOTICE_DATE"))
            except (KeyError, ValueError):
                continue
            for field, (metric, unit) in self.METRICS.items():
                value = row.get(field)
                if value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                result.append(
                    FinancialFact(
                        symbol=str(asset["symbol"]), market="CN", period_end=period_end,
                        filed_at=filed_at, available_at=filed_at, metric=metric, value=numeric,
                        unit=unit, currency=str(row.get("CURRENCY") or "CNY"),
                        source="东方财富财务数据", source_url=source_url,
                        period_type=str(row.get("REPORT_DATE_NAME") or row.get("REPORT_TYPE") or ""),
                        extra={"provider_field": field},
                    )
                )
        return result

    def filings(self, asset: Mapping[str, Any]) -> list[ResearchItem]:
        if str(asset.get("market")) != "CN":
            return []
        code = str(asset["symbol"]).split(".", 1)[0]
        response = self.session.get(
            self.ANNOUNCEMENT_URL,
            params={
                "sr": "-1", "page_size": "40", "page_index": "1",
                "ann_type": "A", "client_source": "web", "stock_list": code,
            },
            timeout=self.timeout,
            headers={"Referer": "https://data.eastmoney.com/"},
        )
        response.raise_for_status()
        rows = (response.json().get("data") or {}).get("list") or []
        result: list[ResearchItem] = []
        for row in rows:
            article_code = str(row.get("art_code") or "")
            title = str(row.get("title") or "").strip()
            if not article_code or not title:
                continue
            published = _parse_datetime(row.get("display_time") or row.get("notice_date"))
            columns = ", ".join(
                str(item.get("column_name") or "") for item in row.get("columns") or []
            ).strip(", ")
            result.append(
                ResearchItem(
                    item_id=article_code, kind=ResearchKind.FILING, tier=SourceTier.OFFICIAL,
                    symbol=str(asset["symbol"]), market="CN", title=title,
                    published_at=published, available_at=published,
                    report_date=(date.fromisoformat(str(row["notice_date"])[:10]) if row.get("notice_date") else None),
                    source="上市公司公告（东财索引）",
                    url=f"https://data.eastmoney.com/notices/detail/{code}/{article_code}.html",
                    summary=columns, sentiment="neutral", confidence=0.98,
                    extra={"article_code": article_code},
                )
            )
        return result


class SecEdgarProvider:
    TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
    FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    TAGS = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": "营业收入",
        "Revenues": "营业收入",
        "GrossProfit": "毛利润",
        "NetIncomeLoss": "净利润",
        "NetCashProvidedByUsedInOperatingActivities": "经营现金流",
        "Assets": "总资产",
        "Liabilities": "总负债",
        "StockholdersEquity": "股东权益",
        "EarningsPerShareDiluted": "稀释每股收益",
    }

    def __init__(self, session: requests.Session, cache_dir: Path, timeout: int = 12):
        self.session = session
        self.cache_path = cache_dir / "sec_company_tickers.json"
        self.timeout = timeout
        self._ticker_cache: dict[str, dict[str, Any]] | None = None
        self._ticker_lock = threading.Lock()

    def _ticker_map(self) -> dict[str, dict[str, Any]]:
        with self._ticker_lock:
            if self._ticker_cache is not None:
                return self._ticker_cache
            payload: dict[str, Any] = {}
            fresh = False
            try:
                fresh = datetime.now().timestamp() - self.cache_path.stat().st_mtime < 86400
                if fresh:
                    payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            if not fresh:
                response = self.session.get(self.TICKERS_URL, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(payload), encoding="utf-8")
                temporary.replace(self.cache_path)
            self._ticker_cache = {
                str(item.get("ticker", "")).upper(): item for item in payload.values()
            }
            return self._ticker_cache

    def _cik(self, asset: Mapping[str, Any]) -> str:
        if str(asset.get("market")) != "US":
            return ""
        ticker = str(asset["symbol"]).split(".", 1)[0].upper().replace("-", ".")
        item = self._ticker_map().get(ticker) or self._ticker_map().get(ticker.replace(".", "-"))
        return f"{int(item['cik_str']):010d}" if item else ""

    def financial_facts(self, asset: Mapping[str, Any]) -> list[FinancialFact]:
        cik = self._cik(asset)
        if not cik:
            return []
        response = self.session.get(self.FACTS_URL.format(cik=cik), timeout=self.timeout)
        response.raise_for_status()
        us_gaap = (response.json().get("facts") or {}).get("us-gaap") or {}
        result: list[FinancialFact] = []
        seen: set[tuple[str, str, str]] = set()
        for tag, metric in self.TAGS.items():
            fact = us_gaap.get(tag) or {}
            for unit, records in (fact.get("units") or {}).items():
                for record in sorted(records, key=lambda item: str(item.get("filed") or ""), reverse=True):
                    form = str(record.get("form") or "")
                    if form not in {"10-K", "10-Q", "20-F", "40-F"}:
                        continue
                    end = str(record.get("end") or "")
                    key = (metric, end, form)
                    if not end or key in seen or record.get("val") is None:
                        continue
                    seen.add(key)
                    filed_at = _parse_datetime(record.get("filed"))
                    accession = str(record.get("accn") or "")
                    accession_plain = accession.replace("-", "")
                    document_url = (
                        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_plain}/"
                        if accession else f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
                    )
                    result.append(
                        FinancialFact(
                            symbol=str(asset["symbol"]), market="US",
                            period_end=date.fromisoformat(end), filed_at=filed_at,
                            available_at=filed_at, metric=metric, value=float(record["val"]),
                            unit=unit, currency="USD" if unit == "USD" else "",
                            source="SEC XBRL", source_url=document_url, period_type=form,
                            extra={"tag": tag, "accession": accession, "frame": record.get("frame")},
                        )
                    )
                    if sum(item.metric == metric for item in result) >= 12:
                        break
                if sum(item.metric == metric for item in result) >= 12:
                    break
        return result

    def filings(self, asset: Mapping[str, Any]) -> list[ResearchItem]:
        cik = self._cik(asset)
        if not cik:
            return []
        response = self.session.get(self.SUBMISSIONS_URL.format(cik=cik), timeout=self.timeout)
        response.raise_for_status()
        recent = (response.json().get("filings") or {}).get("recent") or {}
        keys = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument", "primaryDocDescription")
        columns = list(zip(*(recent.get(key) or [] for key in keys), strict=True))
        records = [dict(zip(keys, values, strict=True)) for values in columns]
        result: list[ResearchItem] = []
        for record in records[:60]:
            accession = str(record["accessionNumber"])
            primary = str(record["primaryDocument"])
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{primary}"
            form = str(record["form"])
            description = str(record["primaryDocDescription"] or "").strip()
            filed_at = _parse_datetime(record["filingDate"])
            result.append(
                ResearchItem(
                    item_id=accession, kind=ResearchKind.FILING, tier=SourceTier.OFFICIAL,
                    symbol=str(asset["symbol"]), market="US",
                    title=f"{form} · {description or primary}", published_at=filed_at,
                    available_at=filed_at, source="SEC EDGAR", url=url,
                    report_date=(date.fromisoformat(record["reportDate"]) if record["reportDate"] else None),
                    summary=f"申报类型 {form}", confidence=1.0,
                    extra={"accession": accession, "form": form},
                )
            )
        return result


class GoogleNewsRssProvider:
    URL = "https://news.google.com/rss/search"

    def __init__(self, session: requests.Session, config: ResearchConfig):
        self.session = session
        self.config = config

    def _fetch(
        self,
        asset: Mapping[str, Any],
        query: str,
        *,
        kind: ResearchKind,
        tier: SourceTier,
    ) -> list[ResearchItem]:
        ceid = f"{self.config.region}:{self.config.language.split('-')[0]}"
        response = self.session.get(
            self.URL,
            params={"q": query, "hl": self.config.language, "gl": self.config.region, "ceid": ceid},
            timeout=self.config.timeout,
            headers={"Accept": "application/rss+xml,application/xml,text/xml"},
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        result: list[ResearchItem] = []
        for node in root.findall("./channel/item")[: self.config.max_news_items]:
            title = str(node.findtext("title") or "").strip()
            link = str(node.findtext("link") or "").strip()
            if not title or not link:
                continue
            source_node = node.find("source")
            source = (source_node.text or "").strip() if source_node is not None else "Google News"
            published = _parse_datetime(node.findtext("pubDate"))
            summary = _strip_html(str(node.findtext("description") or ""))[:600]
            sentiment, confidence = classify_sentiment(f"{title} {summary}")
            result.append(
                ResearchItem(
                    kind=kind, tier=tier, symbol=str(asset["symbol"]),
                    market=str(asset.get("market") or ""), title=title,
                    published_at=published, available_at=published, source=source or "Google News",
                    url=link, summary=summary, sentiment=sentiment,
                    confidence=min(confidence, 0.65 if tier == SourceTier.COMMUNITY else 0.75),
                    extra={"aggregator": "Google News RSS", "query": query},
                )
            )
        return result

    def news(self, asset: Mapping[str, Any]) -> list[ResearchItem]:
        if not self.config.news_enabled:
            return []
        name = str(asset.get("name") or "").strip()
        symbol = str(asset["symbol"]).split(".", 1)[0]
        query = f'"{name}" {symbol} 股票' if name and name != symbol else f"{symbol} 股票"
        return self._fetch(asset, query, kind=ResearchKind.NEWS, tier=SourceTier.PROFESSIONAL)

    def media_opinions(self, asset: Mapping[str, Any]) -> list[ResearchItem]:
        if not self.config.news_enabled:
            return []
        name = str(asset.get("name") or asset["symbol"])
        symbol = str(asset["symbol"]).split(".", 1)[0]
        query = f'"{name}" {symbol} (分析 OR 观点 OR 评论 OR 研报)'
        return self._fetch(
            asset,
            query,
            kind=ResearchKind.MEDIA_OPINION,
            tier=SourceTier.PROFESSIONAL,
        )

    def community(self, asset: Mapping[str, Any]) -> list[ResearchItem]:
        if not self.config.news_enabled:
            return []
        name = str(asset.get("name") or asset["symbol"])
        result: list[ResearchItem] = []
        for site in self.config.community_sites:
            query = f'site:{site} "{name}"'
            result.extend(
                self._fetch(
                    asset, query, kind=ResearchKind.COMMUNITY_OPINION,
                    tier=SourceTier.COMMUNITY,
                )
            )
        return result[: self.config.max_news_items]


class FredMacroProvider:
    URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def __init__(self, session: requests.Session, timeout: int = 12):
        self.session = session
        self.timeout = timeout

    def observation(self, definition: MacroSeriesDefinition) -> MacroObservation:
        response = self.session.get(self.URL, params={"id": definition.series_id}, timeout=self.timeout)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        values: list[tuple[date, float]] = []
        for row in reader:
            raw = row.get(definition.series_id)
            if raw in {None, "", "."}:
                continue
            try:
                values.append((date.fromisoformat(str(row["observation_date"])), float(raw)))
            except (KeyError, ValueError, TypeError):
                continue
        if not values:
            raise ValueError(f"FRED {definition.series_id} 没有可用观测值")
        observation_date, value = values[-1]
        previous = values[-2][1] if len(values) > 1 else None
        change = value - previous if previous is not None else None
        change_pct = change / abs(previous) if change is not None and previous else None
        signal = 0
        if definition.favorable_direction and change_pct is not None:
            magnitude = 2 if abs(change_pct) >= 0.02 else (1 if abs(change_pct) >= 0.002 else 0)
            direction = 1 if change_pct > 0 else (-1 if change_pct < 0 else 0)
            signal = magnitude * direction * definition.favorable_direction
        now = datetime.now(UTC)
        return MacroObservation(
            series_id=definition.series_id, name=definition.name,
            dimension=definition.dimension, observation_date=observation_date,
            value=value, previous=previous, change=change, change_pct=change_pct,
            signal=max(-2, min(2, signal)), unit=definition.unit, source="FRED",
            source_url=f"https://fred.stlouisfed.org/series/{definition.series_id}",
            release_at=now, vintage_at=now,
            extra={"note": "release_at 为本机获取时间；回测需另行导入当时 vintage"},
        )


def macro_regime(observations: Iterable[MacroObservation]) -> dict[str, Any]:
    grouped: dict[str, list[int]] = {}
    for item in observations:
        grouped.setdefault(item.dimension, []).append(item.signal)
    dimensions = {
        dimension: round(sum(values) / len(values), 2)
        for dimension, values in grouped.items() if values
    }
    scored = list(dimensions.values())
    overall = sum(scored) / len(scored) if scored else 0.0
    label = "risk-on" if overall >= 0.5 else ("risk-off" if overall <= -0.5 else "neutral")
    return {"label": label, "score": round(overall, 2), "dimensions": dimensions}


def macro_sector_impact(
    regime: Mapping[str, Any],
    mapping: Mapping[str, Mapping[str, tuple[str, ...]]],
) -> dict[str, list[str]]:
    benefiting: list[str] = []
    pressured: list[str] = []
    for dimension, raw_score in (regime.get("dimensions") or {}).items():
        score = float(raw_score)
        if abs(score) < 0.5:
            continue
        rules = mapping.get(str(dimension)) or {}
        positive = list(rules.get("positive") or ())
        negative = list(rules.get("negative") or ())
        benefiting.extend(positive if score > 0 else negative)
        pressured.extend(negative if score > 0 else positive)
    return {
        "benefiting": list(dict.fromkeys(benefiting)),
        "pressured": list(dict.fromkeys(pressured)),
    }


class ResearchService:
    def __init__(
        self,
        project_dir: str | Path = PROJECT_DIR,
        *,
        store: ResearchStore | None = None,
        config: ResearchConfig | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.config = config or ResearchConfig.load(self.project_dir / "config" / "research.yaml")
        self.store = store or ResearchStore(self.project_dir / "state" / "signals.db")
        self.session = session or build_session(self.config.retries)
        cache_dir = self.project_dir / "state" / "research_cache"
        self.eastmoney = EastmoneyResearchProvider(self.session, self.config.timeout)
        self.sec = SecEdgarProvider(self.session, cache_dir, self.config.timeout)
        self.news_provider = GoogleNewsRssProvider(self.session, self.config)
        self.macro_provider = FredMacroProvider(self.session, self.config.timeout)

    def cached_asset(self, asset: Mapping[str, Any]) -> ResearchSnapshot:
        return self.store.snapshot(str(asset["symbol"]), str(asset.get("market") or ""))

    def refresh_due(self, scope: str) -> bool:
        status = self.store.refresh_status(scope)
        if not status:
            return True
        refreshed_at = _parse_datetime(status.get("refreshed_at"))
        if scope == "macro":
            minutes = int(self.config.refresh.get("macro_minutes", 30))
        else:
            minutes = int(self.config.refresh.get("news_minutes", 15))
        return datetime.now(UTC) - refreshed_at >= timedelta(minutes=max(1, minutes))

    def refresh_asset(self, asset: Mapping[str, Any]) -> ResearchSnapshot:
        symbol = str(asset["symbol"])
        market = str(asset.get("market") or "")
        tasks: dict[str, Callable[[], list[Any]]] = {
            "news": lambda: self.news_provider.news(asset),
            "media_opinions": lambda: self.news_provider.media_opinions(asset),
            "community": lambda: self.news_provider.community(asset),
        }
        if market == "CN":
            tasks.update({
                "financials": lambda: self.eastmoney.financial_facts(asset),
                "filings": lambda: self.eastmoney.filings(asset),
            })
        elif market == "US":
            tasks.update({
                "financials": lambda: self.sec.financial_facts(asset),
                "filings": lambda: self.sec.filings(asset),
            })
        errors: dict[str, str] = {}
        facts: list[FinancialFact] = []
        items: list[ResearchItem] = []
        with ThreadPoolExecutor(max_workers=min(5, len(tasks))) as executor:
            futures = {executor.submit(task): name for name, task in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    values = future.result()
                except Exception as exc:
                    errors[name] = str(exc)
                    continue
                if name == "financials":
                    facts.extend(values)
                else:
                    items.extend(values)
        self.store.save_financial_facts(facts)
        self.store.save_items(items)
        self.store.mark_refresh(f"asset:{symbol}", "partial" if errors else "ok", errors)
        snapshot = self.store.snapshot(symbol, market)
        snapshot.errors = errors
        return snapshot

    def refresh_macro(self) -> tuple[list[MacroObservation], dict[str, Any], dict[str, str]]:
        observations: list[MacroObservation] = []
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(6, max(1, len(self.config.macro_series)))) as executor:
            futures = {
                executor.submit(self.macro_provider.observation, definition): definition
                for definition in self.config.macro_series
            }
            for future in as_completed(futures):
                definition = futures[future]
                try:
                    observations.append(future.result())
                except Exception as exc:
                    errors[definition.series_id] = str(exc)
        self.store.save_macro(observations)
        self.store.mark_refresh("macro", "partial" if errors else "ok", errors)
        cached = self.store.macro_latest()
        regime = macro_regime(cached)
        regime["sector_impact"] = macro_sector_impact(regime, self.config.macro_impact)
        return cached, regime, errors

    def cached_macro(self) -> tuple[list[MacroObservation], dict[str, Any]]:
        observations = self.store.macro_latest()
        regime = macro_regime(observations)
        regime["sector_impact"] = macro_sector_impact(regime, self.config.macro_impact)
        return observations, regime

    def import_items(self, path: str | Path, default_symbol: str = "") -> int:
        file_path = Path(path)
        if file_path.suffix.casefold() == ".json":
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("items") or []
        else:
            rows = list(csv.DictReader(file_path.read_text(encoding="utf-8-sig").splitlines()))
        items: list[ResearchItem] = []
        for row in rows:
            kind_text = str(row.get("kind") or "community_opinion")
            tier_text = str(row.get("tier") or ("community" if "community" in kind_text else "professional"))
            try:
                kind = ResearchKind(kind_text)
                tier = SourceTier(tier_text)
            except ValueError as exc:
                raise ValueError(f"不支持的 kind/tier：{kind_text}/{tier_text}") from exc
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            summary = str(row.get("summary") or "").strip()
            sentiment = str(row.get("sentiment") or "").strip()
            confidence = row.get("confidence")
            if not sentiment:
                sentiment, detected_confidence = classify_sentiment(f"{title} {summary}")
            else:
                detected_confidence = 0.5
            items.append(
                ResearchItem(
                    kind=kind, tier=tier, symbol=str(row.get("symbol") or default_symbol),
                    market=str(row.get("market") or ""), title=title,
                    published_at=_parse_datetime(row.get("published_at")),
                    source=str(row.get("source") or "手工导入"),
                    url=str(row.get("url") or ""), author=str(row.get("author") or ""),
                    summary=summary, sentiment=sentiment,
                    confidence=float(confidence) if confidence not in {None, ""} else detected_confidence,
                    extra={"import_file": str(file_path)},
                )
            )
        return self.store.save_items(items)

    @staticmethod
    def analyse(snapshot: ResearchSnapshot) -> dict[str, Any]:
        items = snapshot.news + snapshot.opinions
        bullish = [item for item in items if item.sentiment == "bullish"]
        bearish = [item for item in items if item.sentiment == "bearish"]
        official = snapshot.filings
        confidence = min(
            1.0,
            0.25 + min(len(official), 3) * 0.15 + min(len(items), 10) * 0.035,
        )
        return {
            "bullish": len(bullish),
            "bearish": len(bearish),
            "neutral": len(items) - len(bullish) - len(bearish),
            "confidence": round(confidence, 2),
            "latest_bullish": [item.title for item in bullish[:3]],
            "latest_bearish": [item.title for item in bearish[:3]],
            "warning": "情绪分类是关键词辅助结果，社区观点不参与基本面评分。",
        }


class CachedResearchFundamentalProvider:
    """Conservative score from cached, point-in-time financial facts only.

    News and opinions are deliberately excluded. A manual fundamentals.csv row
    should take precedence when the operator has reviewed primary disclosures.
    """

    def __init__(self, store: ResearchStore):
        self.store = store

    def get_fundamental_data(
        self, instrument: Instrument, as_of: date
    ) -> FundamentalResult:
        facts = [
            item
            for item in self.store.financial_facts(instrument.symbol, limit=240)
            if (item.available_at or item.filed_at).date() <= as_of
        ]
        if not facts:
            return FundamentalResult(
                None, "研究中心尚无该日期前可用的财报数据。", None, None
            )
        latest_by_metric: dict[str, FinancialFact] = {}
        history_by_metric: dict[str, list[FinancialFact]] = {}
        for item in sorted(facts, key=lambda value: (value.period_end, value.filed_at), reverse=True):
            latest_by_metric.setdefault(item.metric, item)
            history_by_metric.setdefault(item.metric, []).append(item)

        positives: list[str] = []
        risks: list[str] = []

        def value(metric: str) -> float | None:
            item = latest_by_metric.get(metric)
            return item.value if item else None

        revenue_yoy = value("营收同比")
        profit_yoy = value("净利润同比")
        roe = value("ROE")
        debt_ratio = value("资产负债率")
        net_profit = value("净利润") or value("归母净利润")
        cash_flow = value("经营现金流") or value("自由现金流")

        # SEC facts do not expose ratios directly, so derive a current debt ratio.
        assets = value("总资产")
        liabilities = value("总负债")
        if debt_ratio is None and assets and liabilities is not None:
            debt_ratio = liabilities / assets * 100

        # Derive growth when the provider does not expose a point-in-time YoY field.
        if revenue_yoy is None:
            revenue_yoy = self._derived_growth(history_by_metric.get("营业收入") or [])
        if profit_yoy is None:
            profit_history = history_by_metric.get("净利润") or history_by_metric.get("归母净利润") or []
            profit_yoy = self._derived_growth(profit_history)

        if revenue_yoy is not None:
            (positives if revenue_yoy > 0 else risks).append(f"营收增速 {revenue_yoy:.1f}%")
        if profit_yoy is not None:
            (positives if profit_yoy > 0 else risks).append(f"净利润增速 {profit_yoy:.1f}%")
        if roe is not None:
            (positives if roe >= 8 else risks).append(f"ROE {roe:.1f}%")
        if debt_ratio is not None:
            (positives if debt_ratio < 70 else risks).append(f"资产负债率 {debt_ratio:.1f}%")
        if net_profit is not None:
            (positives if net_profit > 0 else risks).append("净利润为正" if net_profit > 0 else "净利润为负")
        if cash_flow is not None:
            (positives if cash_flow > 0 else risks).append(
                "现金流为正" if cash_flow > 0 else "现金流为负"
            )

        evidence_count = len(positives) + len(risks)
        if evidence_count < 3:
            return FundamentalResult(
                None,
                f"已有财报但可用指标仅 {evidence_count} 项，不足以自动评分。",
                facts[0].source,
                max(item.period_end for item in facts),
            )
        severe = sum(
            (
                net_profit is not None and net_profit < 0,
                cash_flow is not None and cash_flow < 0,
                debt_ratio is not None and debt_ratio >= 85,
                profit_yoy is not None and profit_yoy <= -30,
            )
        )
        if severe >= 2:
            score = 0
        elif len(positives) >= 3 and severe == 0:
            score = 2
        else:
            score = 1
        reason_parts = positives[:4] + risks[:4]
        return FundamentalResult(
            score,
            "；".join(reason_parts) + "。仅基于已缓存财报，未使用新闻/社区情绪。",
            facts[0].source,
            max(item.period_end for item in facts),
        )

    @staticmethod
    def _derived_growth(history: list[FinancialFact]) -> float | None:
        if len(history) < 2:
            return None
        latest = history[0]
        comparable = next(
            (
                item
                for item in history[1:]
                if item.period_type == latest.period_type
                and 300 <= (latest.period_end - item.period_end).days <= 430
            ),
            None,
        )
        if comparable is None or comparable.value == 0:
            return None
        return (latest.value / abs(comparable.value) - 1) * 100


def official_portal_url(asset: Mapping[str, Any]) -> str:
    market = str(asset.get("market") or "")
    symbol = str(asset.get("symbol") or "")
    code = symbol.split(".", 1)[0]
    if market == "CN":
        return f"https://www.cninfo.com.cn/new/disclosure/stock?stockCode={code}"
    if market == "HK":
        return "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=zh"
    if market == "US":
        return f"https://www.sec.gov/edgar/browse/?CIK={quote_plus(code)}&owner=exclude"
    return ""
