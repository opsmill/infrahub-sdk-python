from datetime import datetime, timezone

import pytest

from infrahub_sdk.task.exceptions import TaskNotFoundError, TooManyTasksError
from infrahub_sdk.task.manager import InfraHubTaskManagerBase
from infrahub_sdk.task.models import Task, TaskFilter, TaskState

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all(clients, mock_query_tasks_01, client_type) -> None:
    if client_type == "standard":
        tasks = await clients.standard.task.all()
    else:
        tasks = clients.sync.task.all()

    assert len(tasks) == 5
    assert isinstance(tasks[0], Task)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all_full(clients, mock_query_tasks_01, client_type) -> None:
    if client_type == "standard":
        tasks = await clients.standard.task.all(include_logs=True, include_related_nodes=True)
    else:
        tasks = clients.sync.task.all(include_logs=True, include_related_nodes=True)

    assert len(tasks) == 5
    assert isinstance(tasks[0], Task)


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
async def test_method_filters(clients, mock_query_tasks_02_main, client_type) -> None:
    if client_type == "standard":
        tasks = await clients.standard.task.filter(filter=TaskFilter(branch="main"))
    else:
        tasks = clients.sync.task.filter(filter=TaskFilter(branch="main"))

    assert len(tasks) == 2
    assert isinstance(tasks[0], Task)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_too_many(clients, mock_query_tasks_02_main, client_type) -> None:
    with pytest.raises(TooManyTasksError):
        if client_type == "standard":
            await clients.standard.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
        else:
            clients.sync.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_not_found(clients, mock_query_tasks_empty, client_type) -> None:
    with pytest.raises(TaskNotFoundError):
        if client_type == "standard":
            await clients.standard.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
        else:
            clients.sync.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get(clients, mock_query_tasks_03, client_type) -> None:
    if client_type == "standard":
        task = await clients.standard.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")
    else:
        task = clients.sync.task.get(id="a60f4431-6a43-451e-8f42-9ec5db9a9370")

    assert task
    assert task.id == "a60f4431-6a43-451e-8f42-9ec5db9a9370"


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_full(clients, mock_query_tasks_05, client_type) -> None:
    if client_type == "standard":
        task = await clients.standard.task.get(id="32116fcd-9071-43a7-9f14-777901020b5b")
    else:
        task = clients.sync.task.get(id="32116fcd-9071-43a7-9f14-777901020b5b")

    assert task
    assert task.id == "32116fcd-9071-43a7-9f14-777901020b5b"
    assert len(task.logs) == 4
    assert len(task.related_nodes) == 2
    assert task.model_dump() == {
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
