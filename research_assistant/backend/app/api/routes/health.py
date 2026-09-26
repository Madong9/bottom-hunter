from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "ai-investment-research-backend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_provider": settings.data_provider,
        "real_data": settings.data_provider == "yfinance",
        "qwen_enabled": settings.qwen_enabled,
        "qwen_configured": bool(settings.qwen_enabled and settings.qwen_api_key),
        "qwen_model": settings.qwen_model,
        "history_persistence": settings.database_path != ":memory:",
    }
