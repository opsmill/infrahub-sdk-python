from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx
import pytest

from infrahub_sdk.task import manager
from infrahub_sdk.task.exceptions import TaskNotCompletedError, TaskNotFoundError
from infrahub_sdk.task.models import Task, TaskState

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

TASK_ID = "a60f4431-6a43-451e-8f42-9ec5db9a9370"


# --- Deterministic task-wait helpers ---
@dataclass
class PollClock:
    """Expose elapsed polling time without changing the event loop's clock."""

    elapsed: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, delay: float) -> None:
        assert delay > 0
        self.sleeps.append(delay)
        self.elapsed += delay

    async def asleep(self, delay: float) -> None:
        self.sleep(delay)


@pytest.fixture
def poll_clock(monkeypatch: pytest.MonkeyPatch) -> PollClock:
    clock = PollClock()
    monkeypatch.setattr(manager, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    monkeypatch.setattr(manager, "asyncio", SimpleNamespace(sleep=clock.asleep))
    return clock


def _task_response(state: TaskState | None) -> httpx.Response:
    nodes = []
    if state is not None:
        nodes.append(
            {
                "node": {
                    "id": TASK_ID,
                    "title": "Branch merge",
                    "state": state.value,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:01+00:00",
                }
            }
        )
    return httpx.Response(200, json={"data": {"InfrahubTask": {"edges": nodes, "count": len(nodes)}}})


async def _wait(clients: BothClients, client_type: str, interval: int, timeout: int) -> Task:
    if client_type == "standard":
        return await clients.standard.task.wait_for_completion(id=TASK_ID, interval=interval, timeout=timeout)
    return clients.sync.task.wait_for_completion(id=TASK_ID, interval=interval, timeout=timeout)


# --- End deterministic task-wait helpers ---


@pytest.mark.parametrize("client_type", ["standard", "sync"])
@pytest.mark.parametrize(
    ("state", "interval", "timeout"),
    [
        (TaskState.COMPLETED, 90, 60),
        (TaskState.FAILED, 1, 0),
        (TaskState.CANCELLED, 1, 60),
        (TaskState.CRASHED, 7, 60),
    ],
)
async def test_wait_observes_terminal_state_before_sleeping(
    clients: BothClients,
    httpx_mock: HTTPXMock,
    poll_clock: PollClock,
    client_type: str,
    state: TaskState,
    interval: int,
    timeout: int,
) -> None:
    httpx_mock.add_response(method="POST", json=_task_response(state).json(), is_optional=True)

    task = await _wait(clients, client_type, interval, timeout)

    assert task.id == TASK_ID
    assert task.state == state
    assert len(httpx_mock.get_requests()) == 1
    assert poll_clock.sleeps == []


@pytest.mark.parametrize("client_type", ["standard", "sync"])
@pytest.mark.parametrize(
    ("interval", "timeout", "query_duration", "elapsed"),
    [(90, 60, 0, 60), (7, 60, 0, 60), (7, 60, 2, 60), (1, 5, 2, 5), (1, 5, 9, 9)],
)
async def test_wait_accounts_for_requests_and_remaining_polling_time(
    clients: BothClients,
    httpx_mock: HTTPXMock,
    poll_clock: PollClock,
    client_type: str,
    interval: int,
    timeout: int,
    query_duration: int,
    elapsed: int,
) -> None:
    request_times: list[float] = []

    def pending_task(request: httpx.Request) -> httpx.Response:
        request_times.append(poll_clock.elapsed)
        poll_clock.elapsed += query_duration
        return _task_response(TaskState.RUNNING)

    httpx_mock.add_callback(pending_task, method="POST", is_reusable=True, is_optional=True)

    with pytest.raises(TaskNotCompletedError):
        await _wait(clients, client_type, interval, timeout)

    assert request_times
    assert all(start < timeout for start in request_times)
    assert poll_clock.elapsed == pytest.approx(elapsed)


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_wait_returns_task_that_finishes_after_an_initial_poll(
    clients: BothClients, httpx_mock: HTTPXMock, poll_clock: PollClock, client_type: str
) -> None:
    httpx_mock.add_response(method="POST", json=_task_response(TaskState.RUNNING).json())
    httpx_mock.add_response(method="POST", json=_task_response(TaskState.COMPLETED).json())

    task = await _wait(clients, client_type, interval=7, timeout=60)

    assert task.state == TaskState.COMPLETED
    assert len(httpx_mock.get_requests()) == 2
    assert poll_clock.sleeps == [7]


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_wait_propagates_task_lookup_failure(
    clients: BothClients, httpx_mock: HTTPXMock, poll_clock: PollClock, client_type: str
) -> None:
    httpx_mock.add_response(method="POST", json=_task_response(None).json())

    with pytest.raises(TaskNotFoundError):
        await _wait(clients, client_type, interval=1, timeout=60)

    assert len(httpx_mock.get_requests()) == 1
    assert poll_clock.sleeps == []


@pytest.mark.parametrize("client_type", ["standard", "sync"])
@pytest.mark.parametrize(
    ("interval", "timeout"),
    [
        (0, 60),
        (-1, 60),
        (1, -1),
        (float("nan"), 60),
        (float("inf"), 60),
        (-float("inf"), 60),
        (1, float("nan")),
        (1, float("inf")),
        (1, -float("inf")),
    ],
)
async def test_wait_rejects_invalid_timing_before_a_request(
    clients: BothClients, httpx_mock: HTTPXMock, poll_clock: PollClock, client_type: str, interval: int, timeout: int
) -> None:
    with pytest.raises(ValueError):
        await _wait(clients, client_type, interval, timeout)

    assert httpx_mock.get_requests() == []
    assert poll_clock.sleeps == []


async def test_wait_preserves_async_cancellation(
    clients: BothClients, httpx_mock: HTTPXMock, poll_clock: PollClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def cancel_wait(delay: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(manager, "asyncio", SimpleNamespace(sleep=cancel_wait))
    httpx_mock.add_response(method="POST", json=_task_response(TaskState.RUNNING).json())

    with pytest.raises(asyncio.CancelledError):
        await _wait(clients, "standard", interval=1, timeout=60)

    assert len(httpx_mock.get_requests()) == 1
