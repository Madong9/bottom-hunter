from __future__ import annotations

from datetime import UTC, date, datetime

from bottom_hunter.src import notify as bottom_hunter_notify
from bottom_hunter.src.models import (
    Alert,
    BottomState,
    EntryStage,
    ScoreBreakdown,
    SignalLevel,
    StockSignal,
)
from bottom_hunter.src.notify import (
    NotifyConfig,
    _wecom,
    _wecom_app_token,
    format_digest,
    load_notify_config,
    push,
)


def _alert() -> Alert:
    return Alert(date(2026, 8, 28), "A_SCORE_JUMP", "TEST.US", "测试提醒")


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self) -> dict:
        if self._payload:
            return self._payload
        raise ValueError("no json")


def test_push_disabled_is_noop(monkeypatch) -> None:
    def fail_post(*_args, **_kwargs):
        raise AssertionError("disabled config must not post")

    monkeypatch.setattr("bottom_hunter.src.notify.requests.post", fail_post)
    assert push([_alert()], [], NotifyConfig()) == []


def test_push_sends_to_wecom(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, json=None, timeout=8, **_kwargs):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(200, {"errcode": 0, "errmsg": "ok"})

    monkeypatch.setattr("bottom_hunter.src.notify.requests.post", fake_post)
    config = NotifyConfig(enabled=True, wecom_webhook="https://qy.example/webhook")
    errors = push([_alert()], [], config)
    assert errors == []
    assert captured["url"] == "https://qy.example/webhook"
    assert captured["json"]["msgtype"] == "markdown"
    assert "测试提醒" in captured["json"]["markdown"]["content"]


def test_wecom_reports_api_error(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs):
        return _FakeResponse(200, {"errcode": 93000, "errmsg": "invalid webhook"})

    monkeypatch.setattr("bottom_hunter.src.notify.requests.post", fake_post)
    error = _wecom("https://qy.example/x", "t", "b", 5)
    assert error and "93000" in error


def test_push_skips_low_value_alerts(monkeypatch) -> None:
    def fail_post(*_args, **_kwargs):
        raise AssertionError("non-selected alerts must not post")

    monkeypatch.setattr("bottom_hunter.src.notify.requests.post", fail_post)
    config = NotifyConfig(enabled=True, wecom_webhook="https://qy.example/webhook")
    quiet = Alert(date(2026, 8, 28), "OTHER_TYPE", "TEST.US", "不在默认推送范围")
    assert push([quiet], [], config) == []


def test_load_notify_config_reads_wecom(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "notify.yaml").write_text(
        "enabled: true\nchannels:\n  wecom:\n    webhook: https://qy.example/hook\n",
        encoding="utf-8",
    )
    config = load_notify_config(config_dir)
    assert config.enabled is True
    assert config.wecom_webhook == "https://qy.example/hook"
    assert config.has_channel is True


def test_push_wecom_app_reaches_personal_wechat(monkeypatch) -> None:
    captured: dict = {}

    def fake_get(url, params=None, timeout=8, **_kwargs):
        captured["get_url"] = url
        captured["get_params"] = params or {}
        return _FakeResponse(200, {"access_token": "TOK", "expires_in": 7200})

    def fake_post(url, json=None, params=None, timeout=8, **_kwargs):
        captured["post_url"] = url
        captured["post_json"] = json
        return _FakeResponse(200, {"errcode": 0, "errmsg": "ok"})

    monkeypatch.setattr("bottom_hunter.src.notify.requests.get", fake_get)
    monkeypatch.setattr("bottom_hunter.src.notify.requests.post", fake_post)
    config = NotifyConfig(
        enabled=True,
        wecom_corpid="ww1",
        wecom_corpsecret="sec",
        wecom_agentid="1000002",
        wecom_touser="@all",
    )
    assert push([_alert()], [], config) == []
    assert captured["get_url"].endswith("/gettoken")
    assert captured["post_json"]["msgtype"] == "markdown"
    assert captured["post_json"]["agentid"] == 1000002
    assert captured["post_json"]["touser"] == "@all"


def test_wecom_app_token_is_cached(monkeypatch) -> None:
    calls: list = []

    def fake_get(url, params=None, timeout=8, **_kwargs):
        calls.append(params)
        return _FakeResponse(200, {"access_token": "TOK", "expires_in": 7200})

    monkeypatch.setattr("bottom_hunter.src.notify.requests.get", fake_get)
    bottom_hunter_notify._WECOM_TOKEN.clear()
    _wecom_app_token("corp", "secret", 5)
    _wecom_app_token("corp", "secret", 5)
    assert len(calls) == 1


def test_push_sends_to_wxpusher(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, json=None, timeout=8, **_kwargs):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(200, {"success": True})

    monkeypatch.setattr("bottom_hunter.src.notify.requests.post", fake_post)
    config = NotifyConfig(enabled=True, wxpusher_app_token="AT_x", wxpusher_uid="UID_1")
    errors = push([_alert()], [], config)
    assert errors == []
    assert captured["json"]["uids"] == ["UID_1"]
    assert captured["json"]["contentType"] == 3


def test_digest_is_chinese_mobile_summary_for_new_entity() -> None:
    signal = StockSignal(
        date(2026, 8, 28),
        "TEST.US",
        "测试公司",
        "US",
        "technology",
        "信息技术",
        ScoreBreakdown(2, 2, 2, 1, 1, 0, 1),
        SignalLevel.BUY_CANDIDATE,
        BottomState.NO_NEW_LOW,
        EntryStage.ENTRY_STAGE_2,
        {"support_level": 98.0, "resistance_level": 112.0},
        ["RSI14 28.0", "恐慌低点后第2个交易日未明显创新低"],
        [],
        True,
        date(2026, 8, 26),
        95.0,
        "complete",
        "长桥",
        datetime(2026, 8, 28, tzinfo=UTC),
    )
    title, body = format_digest([_alert()], [signal])
    assert "08-28" in title
    assert "阶段2·拒绝新低" in body
    assert "观察位：支撑 98" in body
    assert "A_SCORE_JUMP" not in body
