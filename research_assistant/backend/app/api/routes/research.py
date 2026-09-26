from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_research_service
from app.schemas.research import ResearchRequest, ResearchTask, ResearchTaskList
from app.services import ResearchService

router = APIRouter()
ServiceDependency = Annotated[ResearchService, Depends(get_research_service)]


@router.post("", response_model=ResearchTask, status_code=status.HTTP_201_CREATED)
def create_research(
    request: ResearchRequest,
    service: ServiceDependency,
) -> ResearchTask:
    return service.create(request)


@router.get("", response_model=ResearchTaskList)
def list_research(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResearchTaskList:
    return service.list_tasks(limit=limit)


@router.get("/{task_id}", response_model=ResearchTask)
def get_research(task_id: UUID, service: ServiceDependency) -> ResearchTask:
    return service.get(task_id)
