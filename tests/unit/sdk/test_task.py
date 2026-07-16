from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.graphql import Mutation
from infrahub_sdk.task.exceptions import TaskNotFoundError, TooManyTasksError
from infrahub_sdk.task.manager import MUTATION_TASK_QUERY, InfraHubTaskManagerBase
from infrahub_sdk.task.models import Task, TaskFilter, TaskState

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all(clients: BothClients, mock_query_tasks_01: HTTPXMock, client_type: str) -> None:
    if client_type == "standard":
        tasks = await clients.standard.task.all()
    else:
        tasks = clients.sync.task.all()

    assert len(tasks) == 5
    assert isinstance(tasks[0], Task)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all_full(clients: BothClients, mock_query_tasks_01: HTTPXMock, client_type: str) -> None:
    if client_type == "standard":
        tasks = await clients.standard.task.all(include_logs=True, include_related_nodes=True)
    else:
        tasks = clients.sync.task.all(include_logs=True, include_related_nodes=True)

    assert len(tasks) == 5
    assert isinstance(tasks[0], Task)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_retry(clients: BothClients, httpx_mock: HTTPXMock, client_type: str) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubTaskRetry": {"ok": True, "task": {"id": "b71f5542-7b54-562f-9053-8fd6ec0b0481"}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-task-retry"},
    )

    if client_type == "standard":
        new_id = await clients.standard.task.retry(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
    else:
        new_id = clients.sync.task.retry(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")

    assert new_id == "b71f5542-7b54-562f-9053-8fd6ec0b0481"
    sent_query = json.loads(httpx_mock.get_requests()[-1].content)["query"]
    assert "InfrahubTaskRetry(" in sent_query
    assert 'id: "a60f4431-6a43-451e-8f42-9ec5db9a9370"' in sent_query


@pytest.mark.parametrize("client_type", client_types)
async def test_method_cancel(clients: BothClients, httpx_mock: HTTPXMock, client_type: str) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubTaskCancel": {"ok": True, "task": {"id": "a60f4431-6a43-451e-8f42-9ec5db9a9370"}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-task-cancel"},
    )

    if client_type == "standard":
        cancelled = await clients.standard.task.cancel(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
    else:
        cancelled = clients.sync.task.cancel(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")

    assert cancelled is True
    sent_query = json.loads(httpx_mock.get_requests()[-1].content)["query"]
    assert "InfrahubTaskCancel(" in sent_query
    assert 'id: "a60f4431-6a43-451e-8f42-9ec5db9a9370"' in sent_query


@pytest.mark.parametrize("client_type", client_types)
async def test_filter_limit_forwards_include_actions(
    clients: BothClients, mock_query_tasks_03: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        await clients.standard.task.filter(limit=5, include_actions=True)
    else:
        clients.sync.task.filter(limit=5, include_actions=True)

    sent_query = json.loads(mock_query_tasks_03.get_requests()[-1].content)["query"]
    assert "available_actions" in sent_query


async def test_action_mutation_render() -> None:
    query = Mutation(
        mutation="InfrahubTaskRetry",
        input_data={"data": {"id": "a60f4431-6a43-451e-8f42-9ec5db9a9370"}},
        query=MUTATION_TASK_QUERY,
    )
    assert (
        query.render()
        == """
mutation {
    InfrahubTaskRetry(
        data: {
            id: "a60f4431-6a43-451e-8f42-9ec5db9a9370"
        }
    ){
        ok
        task {
            id
        }
    }
}
"""
    )


async def test_generate_count_query() -> None:
    query = InfraHubTaskManagerBase._generate_count_query()
    assert query
    assert (
        query.render()
        == """
query {
    InfrahubTask {
        count
    }
}
"""
    )

    query2 = InfraHubTaskManagerBase._generate_count_query(
        filters=TaskFilter(ids=["azerty", "qwerty"], state=[TaskState.COMPLETED])
    )
    assert query2
    assert (
        query2.render()
        == """
query {
    InfrahubTask(ids: ["azerty", "qwerty"], state: [COMPLETED]) {
        count
    }
}
"""
    )


@pytest.mark.parametrize("client_type", client_types)
async def test_method_filters(clients: BothClients, mock_query_tasks_02_main: HTTPXMock, client_type: str) -> None:
    if client_type == "standard":
        tasks = await clients.standard.task.filter(filter=TaskFilter(branch="main"))
    else:
        tasks = clients.sync.task.filter(filter=TaskFilter(branch="main"))

    assert len(tasks) == 2
    assert isinstance(tasks[0], Task)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_too_many(clients: BothClients, mock_query_tasks_02_main: HTTPXMock, client_type: str) -> None:
    with pytest.raises(TooManyTasksError):
        if client_type == "standard":
            await clients.standard.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
        else:
            clients.sync.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_not_found(clients: BothClients, mock_query_tasks_empty: HTTPXMock, client_type: str) -> None:
    with pytest.raises(TaskNotFoundError):
        if client_type == "standard":
            await clients.standard.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
        else:
            clients.sync.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get(clients: BothClients, mock_query_tasks_03: HTTPXMock, client_type: str) -> None:
    if client_type == "standard":
        task = await clients.standard.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
    else:
        task = clients.sync.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")

    assert task
    assert task.id == "a60f4431-6a43-451e-8f42-9ec5db9a9370"


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_full(clients: BothClients, mock_query_tasks_05: HTTPXMock, client_type: str) -> None:
    if client_type == "standard":
        task = await clients.standard.task.get(id="32116fcd-9071-43a7-9f14-777901020b5b")
    else:
        task = clients.sync.task.get(id="32116fcd-9071-43a7-9f14-777901020b5b")

    assert task
    assert task.id == "32116fcd-9071-43a7-9f14-777901020b5b"
    assert len(task.logs) == 4
    assert len(task.related_nodes) == 2
    assert task.model_dump() == {
        "available_actions": [],
        "branch": "main",
        "created_at": datetime(2025, 1, 18, 22, 12, 20, 228112, tzinfo=timezone.utc),
        "id": "32116fcd-9071-43a7-9f14-777901020b5b",
        "logs": [
            {
                "message": "Found 1 check definitions in the repository",
                "severity": "info",
                "timestamp": datetime(2025, 1, 18, 22, 12, 20, 371699, tzinfo=timezone.utc),
            },
            {
                "message": "Found 3 Python transforms in the repository",
                "severity": "info",
                "timestamp": datetime(2025, 1, 18, 22, 12, 20, 603709, tzinfo=timezone.utc),
            },
            {
                "message": "Found 4 generator definitions in the repository",
                "severity": "info",
                "timestamp": datetime(2025, 1, 18, 22, 12, 21, 259186, tzinfo=timezone.utc),
            },
            {
                "message": "Processing generator update_upstream_interfaces_description (generators/upstream_interfaces.py)",
                "severity": "info",
                "timestamp": datetime(2025, 1, 18, 22, 12, 21, 259692, tzinfo=timezone.utc),
            },
        ],
        "parameters": None,
        "progress": None,
        "related_nodes": [
            {
                "id": "1808d478-e51e-7504-d0ef-c513f1cd69a5",
                "kind": "CoreReadOnlyRepository",
            },
            {"id": "1808d478-e51e-7504-aaaa-c513f1cd69a5", "kind": "TestMyKind"},
        ],
        "state": TaskState.COMPLETED,
        "tags": None,
        "title": "Import Python file",
        "updated_at": datetime(2025, 1, 18, 22, 12, 22, 44921, tzinfo=timezone.utc),
        "workflow": "import-python-files",
    }


def _base_task_data() -> dict:
    return {
        "id": "a60f4431-6a43-451e-8f42-9ec5db9a9370",
        "title": "Webhook delivery",
        "state": "COMPLETED",
        "created_at": "2025-01-18T22:12:20.228112+00:00",
        "updated_at": "2025-01-18T22:12:22.044921+00:00",
    }


async def test_available_actions_parsed() -> None:
    task = Task.from_graphql(
        {
            **_base_task_data(),
            "available_actions": [
                {"action": "RETRY", "available": True, "unavailability_reason": None},
                {"action": "CANCEL", "available": False, "unavailability_reason": "the task has already settled"},
            ],
        }
    )

    assert task.can_retry is True
    assert task.can_cancel is False
    assert task.available_actions[1].unavailability_reason == "the task has already settled"


async def test_available_actions_absent_defaults_empty() -> None:
    task = Task.from_graphql(_base_task_data())

    assert task.available_actions == []
    assert task.can_retry is False
    assert task.can_cancel is False
