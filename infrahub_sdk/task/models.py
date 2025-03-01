from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


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


class TaskLog(BaseModel):
    message: str
    severity: str
    timestamp: datetime


class TaskRelatedNode(BaseModel):
    id: str
    kind: str


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

    @classmethod
    def from_graphql(cls, data: dict) -> Task:
        related_nodes: list[TaskRelatedNode] = []
        logs: list[TaskLog] = []

        if data.get("related_nodes"):
            related_nodes = [TaskRelatedNode(**item) for item in data["related_nodes"]]
            del data["related_nodes"]

        if data.get("logs"):
            logs = [TaskLog(**item["node"]) for item in data["logs"]["edges"]]
            del data["logs"]

        return cls(**data, related_nodes=related_nodes, logs=logs)


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
