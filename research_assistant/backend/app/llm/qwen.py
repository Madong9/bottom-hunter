import json
from typing import Any

import httpx

from app.llm.base import AnalysisEnhancer
from app.schemas.agents import AnalysisOutput
from app.schemas.llm import AnalysisNarrative


class QwenAnalysisEnhancer(AnalysisEnhancer):
    """Uses Qwen only for the interpretive layer; evidence remains deterministic."""

    _forbidden_phrases = (
        "建议买入",
        "建议卖出",
        "应该买入",
        "应该卖出",
        "抄底",
        "满仓",
        "稳赚",
        "必然上涨",
        "必然下跌",
    )

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout_seconds: float = 60,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    def enhance(self, question: str, draft: AnalysisOutput) -> AnalysisOutput:
        response_schema = self._response_schema(draft)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._user_prompt(question, draft)},
            ],
            "temperature": 0.2,
            "enable_thinking": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "analysis_narrative",
                    "strict": True,
                    "schema": response_schema,
                },
            },
        }
        response = self._post(payload)
        try:
            content = response["choices"][0]["message"]["content"]
            narrative = AnalysisNarrative.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("千问返回结构无法通过报告 Schema 校验") from exc

        self._validate_narrative(narrative, draft)
        return draft.model_copy(
            update={
                "summary": narrative.summary,
                "ai_analysis": narrative.ai_analysis,
                "scenarios": narrative.scenarios,
                "uncertainties": narrative.uncertainties,
                "future_watch": narrative.future_watch,
                "analysis_method": f"qwen:{self._model}",
                "analysis_warnings": [],
            }
        )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            response = self._client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
        else:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是普通投资者的公司认知助手。只能使用输入中的已确认事实，"
            "不得新增数字或事实，不预测涨跌，不给出买卖建议。"
            "AI分析必须原样复制输入中的 fact_id，不得自创或改写 ID；"
            "情景必须使用‘如果…可能…’。"
            "用面向金融小白的中文。输出必须是一个 JSON 对象，不要 Markdown。"
        )

    @staticmethod
    def _user_prompt(question: str, draft: AnalysisOutput) -> str:
        facts = [
            {
                "fact_id": item.fact_id,
                "content": item.content[:500],
            }
            for item in draft.facts[:10]
        ]
        context = {
            "question": question,
            "task_type": draft.title,
            "visible_modules": draft.visible_modules,
            "facts": facts,
            "companies": [
                {
                    "company_name": item.company_name,
                    "industry": item.industry,
                    "business_characteristics": item.business_characteristics[:300],
                }
                for item in draft.company_portraits
            ],
            "draft": {
                "summary": draft.summary,
                "ai_analysis": [item.model_dump() for item in draft.ai_analysis],
                "scenarios": [item.model_dump() for item in draft.scenarios],
                "uncertainties": draft.uncertainties,
                "future_watch": draft.future_watch,
            },
        }
        return (
            "请在不改变事实层的前提下，精简优化下列解释层。"
            "必须保持任务类型差异：风险分析聚焦下行因素、触发条件和待验证项；"
            "同行比较必须比较至少两家公司的同口径指标、业务差异和各自风险。"
            "每项尽量不超过120个中文字，AI分析1至3项，未来情景2至3项。"
            f"\n输入：{json.dumps(context, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _response_schema(draft: AnalysisOutput) -> dict[str, Any]:
        schema = AnalysisNarrative.model_json_schema()
        allowed_ids = [item.fact_id for item in draft.facts[:10]]
        definitions = schema.get("$defs", {})
        for definition_name in ("AIAnalysisItem", "FutureScenario"):
            definition = definitions.get(definition_name, {})
            properties = definition.get("properties", {})
            references = properties.get("based_on_fact_ids", {})
            references.get("items", {})["enum"] = allowed_ids
        return schema

    def _validate_narrative(
        self, narrative: AnalysisNarrative, draft: AnalysisOutput
    ) -> None:
        allowed_fact_ids = {item.fact_id for item in draft.facts}
        referenced_ids = {
            fact_id
            for item in [*narrative.ai_analysis, *narrative.scenarios]
            for fact_id in item.based_on_fact_ids
        }
        if not referenced_ids.issubset(allowed_fact_ids):
            raise ValueError("千问分析引用了不存在的事实 ID")
        for scenario in narrative.scenarios:
            if (
                not scenario.condition.startswith("如果")
                or "可能" not in scenario.possible_outcome
            ):
                raise ValueError("未来情景未使用‘如果…可能…’的非确定性表达")
        rendered = json.dumps(narrative.model_dump(), ensure_ascii=False)
        if any(phrase in rendered for phrase in self._forbidden_phrases):
            raise ValueError("千问返回包含直接交易建议或确定性收益表达")
