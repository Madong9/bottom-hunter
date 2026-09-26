from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.schemas.agents import ReviewCheck, RiskReviewInput, RiskReviewOutput
from app.schemas.common import ReviewStatus, RiskLevel


class RiskReviewAgent(BaseAgent[RiskReviewInput, RiskReviewOutput]):
    name = "risk_review"
    prohibited_certainty_terms = ("保证收益", "稳赚", "必然上涨", "一定上涨")
    prohibited_advice_terms = (
        "建议买入",
        "建议卖出",
        "应该买",
        "应该卖",
        "可以买入",
        "抄底",
        "满仓",
    )

    def run(self, agent_input: RiskReviewInput) -> RiskReviewOutput:
        analysis = agent_input.analysis
        available_sources = set(agent_input.available_source_ids)
        fact_ids = {fact.fact_id for fact in analysis.facts}
        sourced_facts = [
            fact
            for fact in analysis.facts
            if fact.source_ids and set(fact.source_ids).issubset(available_sources)
        ]
        evidence_coverage = (
            len(sourced_facts) / len(analysis.facts) if analysis.facts else 0.0
        )

        report_text = analysis.model_dump_json()
        certainty_terms = [
            term for term in self.prohibited_certainty_terms if term in report_text
        ]
        advice_terms = [term for term in self.prohibited_advice_terms if term in report_text]
        inference_separated = bool(analysis.ai_analysis) and all(
            item.based_on_fact_ids
            and set(item.based_on_fact_ids).issubset(fact_ids)
            for item in analysis.ai_analysis
        )
        scenarios_conditional = all(
            item.condition.startswith("如果") and "可能" in item.possible_outcome
            for item in analysis.scenarios
        )

        checks = [
            ReviewCheck(
                check_id="fact_sources",
                label="核心事实存在来源",
                passed=bool(analysis.facts) and evidence_coverage == 1.0,
                detail=f"{len(sourced_facts)}/{len(analysis.facts)} 条事实可追溯",
            ),
            ReviewCheck(
                check_id="certainty_language",
                label="未发现确定性收益承诺",
                passed=not certainty_terms,
                detail="未发现违规表述" if not certainty_terms else f"发现：{', '.join(certainty_terms)}",
            ),
            ReviewCheck(
                check_id="inference_label",
                label="推断内容已标记",
                passed=inference_separated,
                detail="AI 分析与已确认事实分区展示",
            ),
            ReviewCheck(
                check_id="advice_boundary",
                label="投资建议边界检查通过",
                passed=not advice_terms,
                detail="未输出直接买卖建议" if not advice_terms else f"发现：{', '.join(advice_terms)}",
            ),
            ReviewCheck(
                check_id="scenario_language",
                label="未来情景采用条件式表达",
                passed=scenarios_conditional,
                detail="情景使用“如果……可能……”表述",
            ),
        ]

        issues = [check.detail for check in checks if not check.passed]
        revisions = [f"修正检查项：{check.label}" for check in checks if not check.passed]
        approved = all(check.passed for check in checks)
        return RiskReviewOutput(
            status=ReviewStatus.APPROVED if approved else ReviewStatus.REJECTED,
            risk_level=(
                RiskLevel.HIGH
                if not approved
                else RiskLevel.MEDIUM
                if analysis.negative_factors
                else RiskLevel.LOW
            ),
            issues=issues,
            required_revisions=revisions,
            disclaimer_required=True,
            evidence_coverage_rate=round(evidence_coverage, 2),
            checks=checks,
            reviewed_at=datetime.now(timezone.utc),
        )
