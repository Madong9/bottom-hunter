from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.schemas.agents import (
    FilteredNewsItem,
    NewsFilterInput,
    NewsFilterOutput,
    NewsFilterStats,
)
from app.schemas.common import SourceReference


class NewsFilterAgent(BaseAgent[NewsFilterInput, NewsFilterOutput]):
    name = "news_filter"
    minimum_credibility = 0.65
    minimum_relevance = 0.60
    maximum_age_days = 365

    def run(self, agent_input: NewsFilterInput) -> NewsFilterOutput:
        requested_symbols = set(agent_input.understanding.symbols)
        selected = []
        seen_titles: set[str] = set()
        duplicate_count = 0
        low_relevance_count = 0
        low_credibility_count = 0
        stale_count = 0
        now = datetime.now(timezone.utc)

        for item in sorted(
            agent_input.candidates, key=lambda news: news.published_at, reverse=True
        ):
            normalized_title = "".join(item.title.casefold().split())
            if normalized_title in seen_titles:
                duplicate_count += 1
                continue
            seen_titles.add(normalized_title)
            symbol_match = bool(requested_symbols.intersection(item.symbols))
            relevance = 0.95 if symbol_match else 0.25
            if relevance < self.minimum_relevance:
                low_relevance_count += 1
                continue
            if item.credibility < self.minimum_credibility:
                low_credibility_count += 1
                continue
            age_days = max(0, (now - item.published_at.astimezone(timezone.utc)).days)
            if age_days > self.maximum_age_days:
                stale_count += 1
                continue
            timeliness = self._timeliness_score(age_days)
            importance = self._importance_score(item.title)
            composite = round(
                relevance * 0.35
                + item.credibility * 0.30
                + timeliness * 0.20
                + importance * 0.15,
                2,
            )
            selected.append(
                FilteredNewsItem(
                    **item.model_dump(),
                    relevance_score=relevance,
                    timeliness_score=timeliness,
                    importance_score=importance,
                    composite_score=composite,
                    event_type=self._event_type(item.title),
                    retention_reason=(
                        f"股票主体匹配，来源可信度 {item.credibility:.0%}，"
                        f"发布于 {age_days} 天内，事件具备研究价值"
                    ),
                    attention_reason=self._attention_reason(item.title),
                )
            )

        retrieved_at = datetime.now(timezone.utc)
        sources = [
            SourceReference(
                source_id=item.news_id,
                name=f"{item.source} - {item.title}",
                source_type="news",
                retrieved_at=retrieved_at,
                as_of=item.published_at,
                url=item.url,
            )
            for item in selected
        ]
        return NewsFilterOutput(
            selected=selected,
            rejected_count=(
                duplicate_count
                + low_relevance_count
                + low_credibility_count
                + stale_count
            ),
            stats=NewsFilterStats(
                candidate_count=len(agent_input.candidates),
                duplicate_count=duplicate_count,
                low_relevance_count=low_relevance_count,
                low_credibility_count=low_credibility_count,
                stale_count=stale_count,
                selected_count=len(selected),
            ),
            sources=sources,
        )

    @staticmethod
    def _event_type(title: str) -> str:
        mapping = {
            "财报": "财报",
            "经营数据": "财报",
            "产线": "产能扩张",
            "发布": "产品发布",
            "价格": "行业竞争",
            "需求": "行业趋势",
        }
        return next((kind for keyword, kind in mapping.items() if keyword in title), "公司动态")

    @staticmethod
    def _timeliness_score(age_days: int) -> float:
        if age_days <= 30:
            return 1.0
        if age_days <= 90:
            return 0.8
        if age_days <= 180:
            return 0.6
        return 0.4

    @staticmethod
    def _importance_score(title: str) -> float:
        if any(keyword in title for keyword in ("财报", "经营数据", "处罚", "并购")):
            return 0.95
        if any(keyword in title for keyword in ("发布", "产线", "高管", "政策")):
            return 0.85
        if any(keyword in title for keyword in ("价格", "需求", "行业")):
            return 0.70
        return 0.60

    @staticmethod
    def _attention_reason(title: str) -> str:
        if any(keyword in title for keyword in ("财报", "经营数据")):
            return "经营数据能够帮助确认公司的收入、利润和经营趋势是否发生变化。"
        if any(keyword in title for keyword in ("价格竞争", "价格")):
            return "价格竞争可能影响行业利润率，因此需要持续观察公司的盈利能力。"
        if any(keyword in title for keyword in ("产线", "扩建", "产能")):
            return "产能变化可能影响未来供给、资本开支和业务增长节奏。"
        if any(keyword in title for keyword in ("产品", "发布")):
            return "产品变化可能影响用户需求和公司的竞争力，需要观察后续销售表现。"
        if any(keyword in title for keyword in ("需求", "动销", "库存")):
            return "需求与库存变化能够反映产品销售状况，并可能影响后续收入和利润率。"
        return "该事件与公司经营相关，后续影响仍需结合公告和财务数据确认。"
