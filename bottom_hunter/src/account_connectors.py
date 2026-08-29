from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from .config import PROJECT_DIR
from .longbridge_adapter import (
    DEFAULT_HTTP_URL,
    DEFAULT_QUOTE_WS_URL,
    LongbridgeClient,
    LongbridgeError,
)

LOGGER = logging.getLogger(__name__)


SERVICE_NAME = "bottom-hunter-account"


class AccountConnectionError(RuntimeError):
    pass


class UnsafeApiPermission(AccountConnectionError):
    pass


class RestrictedLocationError(AccountConnectionError):
    pass


@dataclass(frozen=True)
class ConnectionResult:
    source: str
    account_id: str
    account_label: str
    permissions: str
    verified_at: str
    persisted_in_keyring: bool
    detail: str


class CredentialVault:
    """Persist secrets only in the desktop OS keyring, never in project files."""

    def __init__(self) -> None:
        self._session_values: dict[str, dict[str, str]] = {}

    @staticmethod
    def _keyring():
        try:
            import keyring
            from keyring.backend import KeyringBackend

            backend = keyring.get_keyring()
            if not isinstance(backend, KeyringBackend) or backend.priority <= 0:
                return None
            return keyring
        except Exception:
            return None

    def save(self, source: str, values: dict[str, str]) -> bool:
        cleaned = {key: str(value) for key, value in values.items() if str(value)}
        self._session_values[source] = cleaned
        keyring = self._keyring()
        if keyring is None:
            return False
        try:
            keyring.set_password(SERVICE_NAME, source, json.dumps(cleaned))
            return True
        except Exception as exc:
            LOGGER.warning("凭据写入系统钥匙串失败 (%s)：%s", source, exc)
            return False

    def load(self, source: str) -> dict[str, str]:
        if source in self._session_values:
            return dict(self._session_values[source])
        keyring = self._keyring()
        if keyring is None:
            return {}
        try:
            value = keyring.get_password(SERVICE_NAME, source)
            payload = json.loads(value) if value else {}
            if isinstance(payload, dict):
                result = {str(key): str(item) for key, item in payload.items()}
                self._session_values[source] = result
                return result
        except Exception as exc:
            LOGGER.warning("凭据读取系统钥匙串失败 (%s)：%s", source, exc)
        return {}

    def delete(self, source: str) -> None:
        self._session_values.pop(source, None)
        keyring = self._keyring()
        if keyring is None:
            return
        try:
            keyring.delete_password(SERVICE_NAME, source)
        except Exception as exc:
            LOGGER.warning("凭据从系统钥匙串删除失败 (%s)：%s", source, exc)


class AccountConnectionService:
    def __init__(
        self,
        metadata_path: str | Path | None = None,
        *,
        timeout: int = 10,
        vault: CredentialVault | None = None,
        session: requests.Session | None = None,
        longbridge_client_factory: Callable[[dict[str, str]], Any] | None = None,
    ) -> None:
        self.metadata_path = (
            Path(metadata_path).resolve() if metadata_path else PROJECT_DIR / "state" / "account_connections.json"
        )
        self.timeout = timeout
        self.vault = vault or CredentialVault()
        self.session = session or requests.Session()
        self.longbridge_client_factory = longbridge_client_factory
        self.session.headers.update({"User-Agent": "BottomHunter/0.3 account-watchlist"})

    def _metadata(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_metadata(self, source: str, result: ConnectionResult) -> None:
        payload = self._metadata()
        values = asdict(result)
        values.pop("persisted_in_keyring", None)
        payload[source] = values
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.metadata_path)

    def status(self, source: str) -> dict[str, Any]:
        metadata = self._metadata().get(source, {})
        return {
            **metadata,
            "source": source,
            "connected": bool(metadata),
            "credential_available": bool(self.vault.load(source)),
        }

    @staticmethod
    def _safe_response(response: requests.Response, platform: str) -> Any:
        response_text = str(getattr(response, "text", "") or "")
        restricted_markers = ("restricted location", "b. eligibility")
        if platform == "币安" and any(marker in response_text.casefold() for marker in restricted_markers):
            raise RestrictedLocationError(
                "币安区域限制：官方账号接口拒绝当前网络位置；这不是 API Key 填写错误。"
                "系统不会绕过平台限制。你仍可不验证账号，直接导入币安自选文件；"
                "行情不可用时会自动转用欧易或本地缓存。"
            )
        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise AccountConnectionError(f"{platform} 返回了非 JSON 响应") from exc
        if response.status_code >= 400:
            if isinstance(payload, dict):
                message = payload.get("msg") or payload.get("message") or payload.get("code")
            else:
                message = response.status_code
            if platform == "币安" and any(marker in str(message).casefold() for marker in restricted_markers):
                raise RestrictedLocationError(
                    "币安区域限制：官方账号接口拒绝当前网络位置；这不是 API Key 填写错误。"
                    "系统不会绕过平台限制。你仍可不验证账号，直接导入币安自选文件；"
                    "行情不可用时会自动转用欧易或本地缓存。"
                )
            raise AccountConnectionError(f"{platform} 验证失败：{message}")
        return payload

    def connect_binance(
        self,
        api_key: str,
        secret_key: str,
        *,
        account_label: str = "",
        base_url: str = "https://api.binance.com",
    ) -> ConnectionResult:
        api_key = api_key.strip()
        secret_key = secret_key.strip()
        if not api_key or not secret_key:
            raise ValueError("币安 API Key 和 Secret Key 不能为空")
        base_url = base_url.rstrip("/")
        restrictions = self._binance_signed_get(base_url, "/sapi/v1/account/apiRestrictions", api_key, secret_key)
        if not bool(restrictions.get("enableReading", False)):
            raise AccountConnectionError("币安 API Key 没有读取权限")
        unsafe = [
            key
            for key in (
                "enableWithdrawals",
                "enableInternalTransfer",
                "enableSpotAndMarginTrading",
                "enableMargin",
                "enableFutures",
                "enableVanillaOptions",
            )
            if bool(restrictions.get(key, False))
        ]
        if unsafe:
            raise UnsafeApiPermission(f"拒绝关联：请新建仅启用读取权限的币安 API Key；当前开启了 {', '.join(unsafe)}")

        account = self._binance_signed_get(
            base_url,
            "/api/v3/account",
            api_key,
            secret_key,
            extra={"omitZeroBalances": "true"},
        )
        account_id = str(
            account.get("uid")
            or account.get("accountAlias")
            or hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
        )
        persisted = self.vault.save(
            "binance",
            {"api_key": api_key, "secret_key": secret_key, "base_url": base_url},
        )
        result = ConnectionResult(
            source="binance",
            account_id=account_id,
            account_label=account_label.strip() or f"币安 {account_id}",
            permissions="read_only",
            verified_at=datetime.now(UTC).isoformat(),
            persisted_in_keyring=persisted,
            detail=(
                "已验证只读 API Key；官方 API 不提供 App 自选读取"
                + ("" if persisted else "；系统密钥环不可用，本次凭据仅在内存中保留")
            ),
        )
        self._save_metadata("binance", result)
        return result

    def _binance_signed_get(
        self,
        base_url: str,
        path: str,
        api_key: str,
        secret_key: str,
        extra: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        params = {"timestamp": str(int(time.time() * 1000)), "recvWindow": "5000"}
        params.update(extra or {})
        query = urlencode(params)
        signature = hmac.new(secret_key.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        try:
            response = self.session.get(
                f"{base_url}{path}?{query}&signature={signature}",
                headers={"X-MBX-APIKEY": api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AccountConnectionError(f"币安连接失败：{exc}") from exc
        payload = self._safe_response(response, "币安")
        if not isinstance(payload, dict):
            raise AccountConnectionError("币安账号响应结构无效")
        return payload

    def connect_okx(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        *,
        account_label: str = "",
        base_url: str = "https://www.okx.com",
    ) -> ConnectionResult:
        api_key, secret_key, passphrase = (
            api_key.strip(),
            secret_key.strip(),
            passphrase.strip(),
        )
        if not api_key or not secret_key or not passphrase:
            raise ValueError("欧易 API Key、Secret Key 和 Passphrase 不能为空")
        base_url = base_url.rstrip("/")
        path = "/api/v5/account/config"
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        signature = base64.b64encode(
            hmac.new(
                secret_key.encode("utf-8"),
                f"{timestamp}GET{path}".encode(),
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        headers = {
            "OK-ACCESS-KEY": api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": passphrase,
        }
        try:
            response = self.session.get(f"{base_url}{path}", headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AccountConnectionError(f"欧易连接失败：{exc}") from exc
        payload = self._safe_response(response, "欧易")
        if not isinstance(payload, dict) or str(payload.get("code", "0")) != "0":
            message = payload.get("msg") if isinstance(payload, dict) else "响应结构无效"
            raise AccountConnectionError(f"欧易验证失败：{message}")
        values = payload.get("data") or []
        if not values or not isinstance(values[0], dict):
            raise AccountConnectionError("欧易账号配置响应为空")
        config = values[0]
        permissions = {item.strip().casefold() for item in str(config.get("perm") or "").split(",") if item.strip()}
        unsafe = permissions.intersection({"trade", "withdraw"})
        if unsafe or "read_only" not in permissions:
            raise UnsafeApiPermission(
                f"拒绝关联：请新建仅包含 Read 权限的欧易 API Key；当前权限为 {', '.join(sorted(permissions)) or '未知'}"
            )
        account_id = str(config.get("uid") or hashlib.sha256(api_key.encode()).hexdigest()[:12])
        persisted = self.vault.save(
            "okx",
            {
                "api_key": api_key,
                "secret_key": secret_key,
                "passphrase": passphrase,
                "base_url": base_url,
            },
        )
        result = ConnectionResult(
            source="okx",
            account_id=account_id,
            account_label=account_label.strip() or f"欧易 {account_id}",
            permissions="read_only",
            verified_at=datetime.now(UTC).isoformat(),
            persisted_in_keyring=persisted,
            detail=(
                "已验证只读 API Key；官方 API 不提供 App 自选读取"
                + ("" if persisted else "；系统密钥环不可用，本次凭据仅在内存中保留")
            ),
        )
        self._save_metadata("okx", result)
        return result

    def connect_longbridge(
        self,
        app_key: str,
        app_secret: str,
        access_token: str,
        *,
        account_label: str = "",
        http_url: str = DEFAULT_HTTP_URL,
        quote_ws_url: str = DEFAULT_QUOTE_WS_URL,
    ) -> ConnectionResult:
        """Verify a Longbridge quote connection without creating a trade context."""

        credentials = {
            "app_key": app_key.strip(),
            "app_secret": app_secret.strip(),
            "access_token": access_token.strip(),
            "http_url": http_url.strip().rstrip("/") or DEFAULT_HTTP_URL,
            "quote_ws_url": quote_ws_url.strip().rstrip("/") or DEFAULT_QUOTE_WS_URL,
        }
        if not all(credentials[key] for key in ("app_key", "app_secret", "access_token")):
            raise ValueError("长桥 App Key、App Secret 和 Access Token 不能为空")
        client = (
            self.longbridge_client_factory(credentials)
            if self.longbridge_client_factory is not None
            else LongbridgeClient(credentials)
        )
        try:
            verification = client.verify()
        except LongbridgeError as exc:
            raise AccountConnectionError(str(exc)) from exc
        account_id = verification.member_id or hashlib.sha256(credentials["app_key"].encode("utf-8")).hexdigest()[:12]
        persisted = self.vault.save("longbridge", credentials)
        package_detail = f"；行情套餐：{', '.join(verification.packages)}" if verification.packages else ""
        result = ConnectionResult(
            source="longbridge",
            account_id=account_id,
            account_label=account_label.strip() or f"长桥 {account_id}",
            permissions="quote_only",
            verified_at=datetime.now(UTC).isoformat(),
            persisted_in_keyring=persisted,
            detail=(
                f"已验证长桥只读行情连接；行情等级：{verification.quote_level or '未知'}"
                f"{package_detail}；本程序只创建 QuoteContext，不创建交易接口"
                + ("" if persisted else "；系统密钥环不可用，本次凭据仅在内存中保留")
            ),
        )
        self._save_metadata("longbridge", result)
        return result

    def disconnect(self, source: str) -> None:
        self.vault.delete(source)
        payload = self._metadata()
        payload.pop(source, None)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.metadata_path)
