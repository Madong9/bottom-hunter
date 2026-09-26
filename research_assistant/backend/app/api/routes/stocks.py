from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_research_service
from app.schemas.research import StockSearchItem
from app.services import ResearchService

router = APIRouter()
ServiceDependency = Annotated[ResearchService, Depends(get_research_service)]


@router.get("/search", response_model=list[StockSearchItem])
def search_stocks(
    service: ServiceDependency,
    query: Annotated[str, Query(max_length=100)] = "",
) -> list[StockSearchItem]:
    return service.search_stocks(query)
