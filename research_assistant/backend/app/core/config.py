import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    api_v1_prefix: str
    cors_origins: str
    data_provider: str
    database_path: str
    qwen_enabled: bool
    qwen_api_key: str | None
    qwen_model: str
    qwen_base_url: str
    qwen_timeout_seconds: float

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "AI 投研助手 Demo"),
        app_env=os.getenv("APP_ENV", "development"),
        api_v1_prefix=os.getenv("API_V1_PREFIX", "/api/v1"),
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173"),
        data_provider=os.getenv("DATA_PROVIDER", "mock").strip().lower(),
        database_path=os.getenv("DATABASE_PATH", ":memory:"),
        qwen_enabled=_env_bool("QWEN_ENABLED", False),
        qwen_api_key=os.getenv("DASHSCOPE_API_KEY") or None,
        qwen_model=os.getenv("QWEN_MODEL", "qwen-plus"),
        qwen_base_url=os.getenv(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/"),
        qwen_timeout_seconds=float(os.getenv("QWEN_TIMEOUT_SECONDS", "30")),
    )
