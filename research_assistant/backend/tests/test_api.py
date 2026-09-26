import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["data_provider"] == "mock"
    assert response.json()["real_data"] is False
    assert response.json()["qwen_configured"] is False


def test_create_and_get_research_task() -> None:
    response = client.post(
        "/api/v1/research",
        json={"query": "请分析宁德时代的基本面、新闻和风险"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert len(payload["agent_runs"]) == 7
    assert payload["agent_runs"][0]["agent"] == "query_router"
    assert payload["agent_runs"][1]["agent"] == "stock_entity_resolver"
    assert (
        payload["result"]["entity_resolution"]["entities"][0]["symbol"] == "300750.SZ"
    )
    assert payload["result"]["routing"]["category"] == "风险分析"
    assert payload["result"]["routing"]["output_requirements"]
    assert payload["result"]["understanding"]["symbols"] == ["300750.SZ"]
    assert payload["result"]["risk_review"]["status"] == "approved"
    analysis = payload["result"]["analysis"]
    assert analysis["facts"]
    assert analysis["ai_analysis"]
    assert analysis["scenarios"]
    assert analysis["uncertainties"]
    assert all(item["condition"].startswith("如果") for item in analysis["scenarios"])
    assert all("可能" in item["possible_outcome"] for item in analysis["scenarios"])

    serialized_result = str(payload["result"])
    assert "建议买入" not in serialized_result
    assert "建议卖出" not in serialized_result
    assert "confidence_score" not in payload["result"]["risk_review"]
    assert payload["result"]["risk_review"]["checks"]

    fetched = client.get(f"/api/v1/research/{payload['task_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["task_id"] == payload["task_id"]


def test_unsupported_stock_creates_auditable_failed_task() -> None:
    response = client.post(
        "/api/v1/research",
        json={"query": "分析一个不存在的股票"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["agent_runs"][0]["agent"] == "query_router"
    assert payload["agent_runs"][0]["status"] == "completed"
    assert payload["agent_runs"][1]["agent"] == "stock_entity_resolver"
    assert payload["agent_runs"][1]["status"] == "failed"


def test_stock_search() -> None:
    response = client.get("/api/v1/stocks/search", params={"query": "Apple"})
    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "AAPL.US"


def test_comparison_contains_structured_dimensions_and_warning() -> None:
    response = client.post(
        "/api/v1/research",
        json={"query": "比较贵州茅台和宁德时代"},
    )
    assert response.status_code == 201
    analysis = response.json()["result"]["analysis"]
    assert len(analysis["comparison"]) == 2
    first = analysis["comparison"][0]
    assert {
        "revenue_growth_percent",
        "net_profit_growth_percent",
        "roe_percent",
        "pe_ttm",
        "positive_factor",
        "main_risk",
        "business_characteristics",
    }.issubset(first)
    assert "不可直接等同" in analysis["comparison_notice"]
    assert "单一指标" in analysis["comparison_notice"]


def test_pe_question_returns_beginner_friendly_term_explanation() -> None:
    response = client.post(
        "/api/v1/research",
        json={"query": "茅台PE是什么意思？"},
    )
    assert response.status_code == 201
    explanations = response.json()["result"]["analysis"]["term_explanations"]
    pe = next(item for item in explanations if item["term"] == "PE")
    assert "市盈率" in pe["professional_definition"]
    assert "多少倍价格" in pe["plain_language_explanation"]


def test_catl_report_generates_future_watch_list() -> None:
    response = client.post(
        "/api/v1/research",
        json={"query": "分析宁德时代"},
    )
    assert response.status_code == 201
    analysis = response.json()["result"]["analysis"]
    assert analysis["future_watch"]
    assert any("储能" in item for item in analysis["future_watch"])
    assert analysis["investor_focus"]
    assert analysis["follow_up_questions"]


def test_all_demo_reports_avoid_direct_or_deterministic_investment_language() -> None:
    prohibited = ("建议买入", "建议卖出", "稳赚", "保证收益", "必然上涨")
    for query in ("分析贵州茅台", "分析宁德时代", "分析Apple"):
        response = client.post("/api/v1/research", json={"query": query})
        assert response.status_code == 201
        report_text = json.dumps(response.json()["result"], ensure_ascii=False)
        assert not any(term in report_text for term in prohibited)


def test_unknown_task_returns_404() -> None:
    response = client.get("/api/v1/research/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
