from __future__ import annotations

from datetime import date

from bottom_hunter.src.models import Alert
from bottom_hunter.src.notify import (
    NotifyConfig,
    _wecom,
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
        "enabled: true\n"
        "channels:\n"
        "  wecom:\n"
        "    webhook: https://qy.example/hook\n",
        encoding="utf-8",
    )
    config = load_notify_config(config_dir)
    assert config.enabled is True
    assert config.wecom_webhook == "https://qy.example/hook"
    assert config.has_channel is True
