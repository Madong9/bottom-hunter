"""Push notifications for high-value alerts (ServerChan / WeCom / WxPusher / Telegram).

Configuration lives in config/notify.yaml:

    enabled: true
    channels:
      serverchan:            # Server酱：推送到微信「方糖」服务号
        sendkey: SCTxxxxxxxx
      wecom:                 # 企业微信群机器人：仅内部群
        webhook: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx
      wecom_app:             # 企业微信自建应用：经微信插件直达个人微信
        corpid: "ww1234"
        corpsecret: "xxxx"
        agentid: 1000002
        touser: "@all"
      wxpusher:              # WxPusher：关注公众号即收，免费
        app_token: "AT_xxx"
        uid: "UID_xxx"
      telegram:
        bot_token: "123456:ABC"
        chat_id: "10086"

Only alert types listed in `alert_types` are pushed (default: the
high-value A/B/C/E classes plus strong signals). Failures never break
the scan; they are logged as warnings.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import PROJECT_DIR
from .models import Alert, StockSignal

LOGGER = logging.getLogger(__name__)

DEFAULT_ALERT_TYPES = ("A_SCORE_JUMP", "B_ENTRY_STAGE", "C_SECTOR_SURGE", "E_SIGNAL_FAILED")

ALERT_LABELS = {
    "A_SCORE_JUMP": "评分跃升",
    "B_ENTRY_STAGE": "阶段变化",
    "C_SECTOR_SURGE": "板块升温",
    "D_RELATIVE_DIVERGENCE": "相对强度拐点",
    "E_SIGNAL_FAILED": "结构失效",
}
STAGE_LABELS = {
    "ENTRY_STAGE_1": "阶段1·恐慌反转",
    "ENTRY_STAGE_2": "阶段2·拒绝新低",
    "ENTRY_STAGE_3": "阶段3·宽度确认",
}
STATE_LABELS = {
    "NORMAL": "正常",
    "SELL_OFF": "下跌释放",
    "CAPITULATION": "恐慌释放",
    "REVERSAL_DAY": "反转日",
    "NO_NEW_LOW": "拒绝创新低",
    "BREADTH_CONFIRM": "宽度确认",
    "TREND_CONFIRM": "趋势确认",
    "FAILED": "结构失效",
}


@dataclass(frozen=True)
class NotifyConfig:
    enabled: bool = False
    serverchan_sendkey: str = ""
    wecom_webhook: str = ""
    wecom_corpid: str = ""
    wecom_corpsecret: str = ""
    wecom_agentid: str = ""
    wecom_touser: str = "@all"
    wxpusher_app_token: str = ""
    wxpusher_uid: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    alert_types: tuple[str, ...] = DEFAULT_ALERT_TYPES

    @property
    def wecom_app_ready(self) -> bool:
        return bool(self.wecom_corpid and self.wecom_corpsecret and self.wecom_agentid)

    @property
    def has_channel(self) -> bool:
        return bool(
            self.serverchan_sendkey
            or self.wecom_webhook
            or self.wecom_app_ready
            or self.wxpusher_app_token
            or (self.telegram_bot_token and self.telegram_chat_id)
        )


def load_notify_config(config_dir: Path | None = None) -> NotifyConfig:
    path = (config_dir or PROJECT_DIR / "config") / "notify.yaml"
    if not path.exists():
        return NotifyConfig()
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        LOGGER.warning("读取通知配置失败：%s", exc)
        return NotifyConfig()
    channels = payload.get("channels") or {}
    alert_types = payload.get("alert_types") or DEFAULT_ALERT_TYPES
    wecom_app = channels.get("wecom_app", {}) or {}
    wxpusher = channels.get("wxpusher", {}) or {}
    return NotifyConfig(
        enabled=bool(payload.get("enabled")),
        serverchan_sendkey=str(channels.get("serverchan", {}).get("sendkey") or ""),
        wecom_webhook=str(channels.get("wecom", {}).get("webhook") or ""),
        wecom_corpid=str(wecom_app.get("corpid") or ""),
        wecom_corpsecret=str(wecom_app.get("corpsecret") or ""),
        wecom_agentid=str(wecom_app.get("agentid") or ""),
        wecom_touser=str(wecom_app.get("touser") or "@all"),
        wxpusher_app_token=str(wxpusher.get("app_token") or ""),
        wxpusher_uid=str(wxpusher.get("uid") or ""),
        telegram_bot_token=str(channels.get("telegram", {}).get("bot_token") or ""),
        telegram_chat_id=str(channels.get("telegram", {}).get("chat_id") or ""),
        alert_types=tuple(str(item) for item in alert_types),
    )


def _serverchan(sendkey: str, title: str, body: str, timeout: int) -> str | None:
    response = requests.post(
        f"https://sctapi.ftqq.com/{sendkey}.send",
        data={"title": title[:32], "desp": body},
        timeout=timeout,
    )
    if response.status_code != 200:
        return f"ServerChan HTTP {response.status_code}"
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    code = payload.get("code")
    if code not in (0, None):
        return f"ServerChan code={code}: {payload.get('message', '')}"
    return None


def _wecom(webhook: str, title: str, body: str, timeout: int) -> str | None:
    """WeCom group robot webhook; markdown body is capped at 4096 bytes."""
    content = f"**{title}**\n{body}"
    while content and len(content.encode("utf-8")) > 4000:
        content = content[: len(content) - 200]
    response = requests.post(
        webhook,
        json={"msgtype": "markdown", "markdown": {"content": content}},
        timeout=timeout,
    )
    if response.status_code != 200:
        return f"企业微信 HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError as exc:
        return f"企业微信响应不是有效 JSON: {exc}"
    if int(payload.get("errcode", -1)) != 0:
        return f"企业微信 errcode={payload.get('errcode')}: {payload.get('errmsg', '')}"
    return None


def _wecom_app(config: NotifyConfig, title: str, body: str, timeout: int) -> str | None:
    """Self-built WeCom app message; reaches personal WeChat via the WeChat plugin."""
    token = _wecom_app_token(config.wecom_corpid, config.wecom_corpsecret, timeout)
    content = f"**{title}**\n{body}"
    while content and len(content.encode("utf-8")) > 1900:
        content = content[: len(content) - 200]
    response = requests.post(
        "https://qyapi.weixin.qq.com/cgi-bin/message/send",
        params={"access_token": token},
        json={
            "touser": config.wecom_touser or "@all",
            "msgtype": "markdown",
            "agentid": int(config.wecom_agentid or 0),
            "markdown": {"content": content},
        },
        timeout=timeout,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        return f"企业微信应用响应不是有效 JSON: {exc}"
    if int(payload.get("errcode", -1)) != 0:
        return f"企业微信应用 errcode={payload.get('errcode')}: {payload.get('errmsg', '')}"
    return None


_WECOM_TOKEN: dict[str, tuple[str, float]] = {}


def _wecom_app_token(corpid: str, corpsecret: str, timeout: int) -> str:
    key = f"{corpid}:{corpsecret}"
    cached = _WECOM_TOKEN.get(key)
    if cached and cached[1] > time.time():
        return cached[0]
    response = requests.get(
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        params={"corpid": corpid, "corpsecret": corpsecret},
        timeout=timeout,
    )
    payload = response.json()
    token = str(payload.get("access_token") or "")
    if not token:
        raise ValueError(f"获取 access_token 失败: errcode={payload.get('errcode')}")
    expires = time.time() + max(60, int(payload.get("expires_in", 7200)) - 120)
    _WECOM_TOKEN[key] = (token, expires)
    return token


def _wxpusher(config: NotifyConfig, title: str, body: str, timeout: int) -> str | None:
    """WxPusher公众号通道: users follow a service account, no daily cap."""
    payload: dict[str, Any] = {
        "appToken": config.wxpusher_app_token,
        "summary": title[:99],
        "content": f"## {title}\n\n{body}",
        "contentType": 3,
    }
    if config.wxpusher_uid:
        payload["uids"] = [config.wxpusher_uid]
    response = requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=timeout)
    try:
        data = response.json()
    except ValueError as exc:
        return f"WxPusher 响应不是有效 JSON: {exc}"
    if not data.get("success", False):
        return f"WxPusher: {data.get('msg') or response.status_code}"
    return None


def _telegram(token: str, chat_id: str, title: str, body: str, timeout: int) -> str | None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": f"{title}\n\n{body}"},
        timeout=timeout,
    )
    if response.status_code != 200:
        return f"Telegram HTTP {response.status_code}: {response.text[:120]}"
    return None


def format_digest(alerts: list[Alert], signals: list[StockSignal]) -> tuple[str, str]:
    """Mobile-first Chinese digest containing only newly alerted entities."""
    if not alerts:
        return "Bottom Hunter｜今日无新增提醒", "今日无新增高优先级提醒。"
    alert_entities = {alert.entity for alert in alerts}
    signal_map = {signal.symbol: signal for signal in signals if signal.symbol in alert_entities}
    signal_map.update(
        {
            f"{signal.symbol}:{signal.sector_id}": signal
            for signal in signals
            if f"{signal.symbol}:{signal.sector_id}" in alert_entities
        }
    )
    ordered = sorted(
        {id(signal): signal for signal in signal_map.values()}.values(),
        key=lambda signal: (
            signal.state.value == "FAILED",
            signal.score.total,
            signal.score.rejection,
        ),
        reverse=True,
    )[:3]
    target = max(alert.date for alert in alerts)
    markets = sorted({signal.market for signal in ordered})
    market_text = "/".join(markets) if markets else "多市场"
    title = f"底部狩猎 {target:%m-%d}｜{len(alerts)}条新提醒｜{market_text}"
    lines: list[str] = []
    for index, signal in enumerate(ordered, 1):
        state = STATE_LABELS.get(signal.state.value, signal.state.value)
        stage = STAGE_LABELS.get(signal.entry_stage.value if signal.entry_stage else "", "仅观察")
        lines.extend(
            [
                f"### {index}. {signal.name}（{signal.symbol}）",
                f"状态：{state}｜{stage}｜{signal.score.total}/{signal.score.available_max}",
            ]
        )
        reasons = [reason for reason in signal.reasons if "仓位框架" not in reason][:2]
        if reasons:
            lines.append("触发：" + "；".join(reasons))
        support = signal.metrics.get("support_level")
        resistance = signal.metrics.get("resistance_level")
        levels = []
        if support is not None:
            levels.append(f"支撑 {float(support):,.4g}")
        if resistance is not None:
            levels.append(f"压力 {float(resistance):,.4g}")
        if levels:
            lines.append("观察位：" + "｜".join(levels))
        if signal.capitulation_low is not None:
            lines.append(f"失效参考：跌破恐慌低点 {signal.capitulation_low:,.4g}")
        lines.append(f"数据：{signal.date.isoformat()}｜{signal.provider}｜{signal.data_quality}")
        lines.append("")
    rendered_entities = {signal.symbol for signal in ordered}
    remaining = [
        alert
        for alert in alerts
        if alert.entity not in rendered_entities
        and not any(alert.entity.startswith(f"{symbol}:") for symbol in rendered_entities)
    ]
    if remaining:
        lines.append("其他变化：")
        lines.extend(
            f"- {ALERT_LABELS.get(alert.alert_type, alert.alert_type)}：{alert.message}" for alert in remaining[:5]
        )
        lines.append("")
    lines.append("风险：当前策略仍在滚动验证，仅供研究观察，不构成投资建议。")
    return title, "\n".join(lines).strip()


_format = format_digest


def push(
    alerts: list[Alert],
    signals: list[StockSignal],
    config: NotifyConfig,
    timeout: int = 8,
) -> list[str]:
    """Push a digest; returns a list of error strings (empty means success)."""
    if not config.enabled or not config.has_channel:
        return []
    selected = [alert for alert in alerts if alert.alert_type in config.alert_types]
    if not selected:
        return []
    title, body = format_digest(selected, signals)
    errors: list[str] = []
    if config.serverchan_sendkey:
        try:
            error = _serverchan(config.serverchan_sendkey, title, body, timeout)
            if error:
                errors.append(error)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"ServerChan: {exc}")
    if config.wecom_webhook:
        try:
            error = _wecom(config.wecom_webhook, title, body, timeout)
            if error:
                errors.append(error)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"企业微信: {exc}")
    if config.wecom_app_ready:
        try:
            error = _wecom_app(config, title, body, timeout)
            if error:
                errors.append(error)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"企业微信应用: {exc}")
    if config.wxpusher_app_token:
        try:
            error = _wxpusher(config, title, body, timeout)
            if error:
                errors.append(error)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"WxPusher: {exc}")
    if config.telegram_bot_token and config.telegram_chat_id:
        try:
            error = _telegram(config.telegram_bot_token, config.telegram_chat_id, title, body, timeout)
            if error:
                errors.append(error)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"Telegram: {exc}")
    if errors:
        LOGGER.warning("推送失败：%s", "; ".join(errors))
    else:
        LOGGER.info("已推送 %d 条提醒", max(1, len(selected)))
    return errors
