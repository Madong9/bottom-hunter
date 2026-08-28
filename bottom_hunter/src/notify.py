"""Push notifications for high-value alerts (ServerChan / Telegram).

Configuration lives in config/notify.yaml:

    enabled: true
    channels:
      serverchan:
        sendkey: SCTxxxxxxxx
      telegram:
        bot_token: "123456:ABC"
        chat_id: "10086"

Only alert types listed in `alert_types` are pushed (default: the
high-value A/B/C/E classes plus strong signals). Failures never break
the scan; they are logged as warnings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import PROJECT_DIR
from .models import Alert, SignalLevel, StockSignal

LOGGER = logging.getLogger(__name__)

DEFAULT_ALERT_TYPES = ("A_SCORE_JUMP", "B_ENTRY_STAGE", "C_SECTOR_SURGE", "E_SIGNAL_FAILED")


@dataclass(frozen=True)
class NotifyConfig:
    enabled: bool = False
    serverchan_sendkey: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    alert_types: tuple[str, ...] = DEFAULT_ALERT_TYPES

    @property
    def has_channel(self) -> bool:
        return bool(self.serverchan_sendkey or (self.telegram_bot_token and self.telegram_chat_id))


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
    return NotifyConfig(
        enabled=bool(payload.get("enabled")),
        serverchan_sendkey=str(channels.get("serverchan", {}).get("sendkey") or ""),
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


def _telegram(token: str, chat_id: str, title: str, body: str, timeout: int) -> str | None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": f"{title}\n\n{body}"},
        timeout=timeout,
    )
    if response.status_code != 200:
        return f"Telegram HTTP {response.status_code}: {response.text[:120]}"
    return None


def _format(alerts: list[Alert], signals: list[StockSignal]) -> tuple[str, str]:
    lines = [f"· {alert.alert_type}: {alert.message}" for alert in alerts[:10]]
    strong = [
        signal
        for signal in signals
        if signal.signal_level in (SignalLevel.BUY_CANDIDATE, SignalLevel.STRONG_REVERSAL)
        and not signal.breakout
    ]
    if strong:
        lines.append("")
        lines.append("高分信号：")
        lines.extend(
            f"· {signal.symbol} {signal.name} {signal.score.total}分 [{signal.signal_level.value}]"
            for signal in strong[:10]
        )
    return "Bottom Hunter 信号提醒", "\n".join(lines)


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
    if not selected and not any(
        signal.signal_level in (SignalLevel.BUY_CANDIDATE, SignalLevel.STRONG_REVERSAL)
        for signal in signals
    ):
        return []
    title, body = _format(selected, signals)
    errors: list[str] = []
    if config.serverchan_sendkey:
        try:
            error = _serverchan(config.serverchan_sendkey, title, body, timeout)
            if error:
                errors.append(error)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"ServerChan: {exc}")
    if config.telegram_bot_token and config.telegram_chat_id:
        try:
            error = _telegram(
                config.telegram_bot_token, config.telegram_chat_id, title, body, timeout
            )
            if error:
                errors.append(error)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"Telegram: {exc}")
    if errors:
        LOGGER.warning("推送失败：%s", "; ".join(errors))
    else:
        LOGGER.info("已推送 %d 条提醒", max(1, len(selected)))
    return errors
