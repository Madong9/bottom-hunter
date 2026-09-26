from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.agents import StockEntityResolverAgent
from app.core.exceptions import TaskNotFoundError
from app.orchestration.workflow import ResearchWorkflow, WorkflowAgentError
from app.providers.base import FinancialDataProvider
from app.repositories import InMemoryTaskRepository, TaskRepository
from app.schemas.common import TaskStatus
from app.schemas.research import (
    ResearchRequest,
    ResearchTask,
    ResearchTaskList,
    StockSearchItem,
)


class ResearchService:
    """Application service backed by a replaceable local task repository."""

    def __init__(
        self,
        workflow: ResearchWorkflow,
        provider: FinancialDataProvider,
        repository: TaskRepository | None = None,
        entity_resolver: StockEntityResolverAgent | None = None,
    ) -> None:
        self._workflow = workflow
        self._provider = provider
        self._repository = repository or InMemoryTaskRepository()
        self._entity_resolver = entity_resolver

    def create(self, request: ResearchRequest) -> ResearchTask:
        task_id = uuid4()
        task = ResearchTask(
            task_id=task_id,
            query=request.query,
            status=TaskStatus.RUNNING,
            created_at=datetime.now(timezone.utc),
        )
        self._save(task)

        try:
            result, agent_runs = self._workflow.run(request.query)
            task = task.model_copy(
                update={
                    "status": TaskStatus.COMPLETED,
                    "completed_at": datetime.now(timezone.utc),
                    "agent_runs": agent_runs,
                    "result": result,
                }
            )
        except WorkflowAgentError as exc:
            task = task.model_copy(
                update={
                    "status": TaskStatus.FAILED,
                    "completed_at": datetime.now(timezone.utc),
                    "agent_runs": exc.agent_runs,
                    "error": str(exc.cause),
                }
            )
        self._save(task)
        return task

    def get(self, task_id: UUID) -> ResearchTask:
        task = self._repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"研究任务 {task_id} 不存在")
        return task

    def list_tasks(self, limit: int = 20) -> ResearchTaskList:
        tasks, total = self._repository.list(limit)
        return ResearchTaskList(items=tasks, total=total)

    def search_stocks(self, query: str) -> list[StockSearchItem]:
        if self._entity_resolver is not None:
            return self._entity_resolver.search_stocks(query)
        return self._provider.search_stocks(query)

    def _save(self, task: ResearchTask) -> None:
        self._repository.save(task)
