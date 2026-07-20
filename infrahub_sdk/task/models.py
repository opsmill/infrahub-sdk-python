from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

WEBHOOK_SEND_WORKFLOW = "webhook-send"


class TaskState(str, Enum):
    SCHEDULED = "SCHEDULED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    CRASHED = "CRASHED"
    PAUSED = "PAUSED"
    CANCELLING = "CANCELLING"


class TaskActionName(str, Enum):
    RETRY = "RETRY"
    CANCEL = "CANCEL"


class TaskLog(BaseModel):
    message: str
    severity: str
    timestamp: datetime


class TaskAction(BaseModel):
    action: TaskActionName
    available: bool
    unavailability_reason: str | None = None


class TaskRelatedNode(BaseModel):
    id: str
    kind: str


class TaskError(BaseModel):
    """Classified failure reason with a remediation hint; set only when a task failed with one."""

    status_class: str
    message: str
    remediation: str


class HttpRequest(BaseModel):
    url: str
    headers: dict[str, Any] | None = None  # secret values are masked by the server


class HttpResponse(BaseModel):
    status_code: int | None = None
    body: str | None = None
    latency_ms: float | None = None


class Task(BaseModel):
    id: str
    title: str
    state: TaskState
    progress: float | None = None
    workflow: str | None = None
    branch: str | None = None
    # start_time: datetime # Is it still required
    created_at: datetime
    updated_at: datetime
    parameters: dict | None = None
    tags: list[str] | None = None
    related_nodes: list[TaskRelatedNode] = Field(default_factory=list)
    logs: list[TaskLog] = Field(default_factory=list)
    available_actions: list[TaskAction] = Field(default_factory=list)
    error: TaskError | None = None

    @property
    def can_retry(self) -> bool:
        """Whether this task can currently be retried."""
        return any(action.action is TaskActionName.RETRY and action.available for action in self.available_actions)

    @property
    def can_cancel(self) -> bool:
        """Whether this task can currently be cancelled."""
        return any(action.action is TaskActionName.CANCEL and action.available for action in self.available_actions)

    @classmethod
    def from_graphql(cls, data: dict) -> Task:
        data = dict(data)
        related_nodes: list[TaskRelatedNode] = []
        logs: list[TaskLog] = []
        available_actions: list[TaskAction] = []

        if "related_nodes" in data:
            if data.get("related_nodes"):
                related_nodes = [TaskRelatedNode(**item) for item in data["related_nodes"]]
            del data["related_nodes"]

        if "logs" in data:
            if data.get("logs"):
                logs = [TaskLog(**item["node"]) for item in data["logs"]["edges"]]
            del data["logs"]

        if "available_actions" in data:
            if data.get("available_actions"):
                available_actions = [TaskAction(**item) for item in data["available_actions"]]
            del data["available_actions"]

        # The workflow name selects the concrete type, mirroring the server's interface;
        # pydantic coerces the remaining error / http_* dicts in `data` into their models.
        target_cls = TASK_TYPES.get(data.get("workflow") or "", cls)
        return target_cls(
            **data,
            related_nodes=related_nodes,
            logs=logs,
            available_actions=available_actions,
        )


class WebhookDeliveryTask(Task):
    """Concrete task type for the ``webhook-send`` workflow, carrying delivery diagnostics."""

    http_request: HttpRequest | None = None
    http_response: HttpResponse | None = None


TASK_TYPES: dict[str, type[Task]] = {
    WEBHOOK_SEND_WORKFLOW: WebhookDeliveryTask,
}


class TaskFilter(BaseModel):
    ids: list[str] | None = None
    q: str | None = None
    branch: str | None = None
    state: list[TaskState] | None = None
    workflow: list[str] | None = None
    limit: int | None = None
    offset: int | None = None
    related_node__ids: list[str] | None = None

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)
