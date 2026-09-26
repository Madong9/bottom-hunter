from fastapi import APIRouter

from app.api.routes import health, research, stocks

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(research.router, prefix="/research", tags=["research"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
