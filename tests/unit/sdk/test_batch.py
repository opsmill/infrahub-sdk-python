from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.batch import InfrahubBatch
from infrahub_sdk.exceptions import GraphQLError

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_batch_execution(clients: BothClients, client_type: str) -> None:
    r: list[int] = []
    tasks_number = 10

    if client_type == "standard":

        async def test_func() -> int:
            return 1

        batch = await clients.standard.create_batch()
        for _ in range(tasks_number):
            batch.add(task=test_func)

        assert batch.num_tasks == tasks_number
        async for _, result in batch.execute():
            r.append(result)
    else:

        def test_func() -> int:
            return 1

        batch = clients.sync.create_batch()
        for _ in range(tasks_number):
            batch.add(task=test_func)

        assert batch.num_tasks == tasks_number
        for _, result in batch.execute():
            r.append(result)

    assert r == [1] * tasks_number


@pytest.mark.parametrize("client_type", client_types)
async def test_batch_return_exception(
    httpx_mock: HTTPXMock,
    mock_query_mutation_location_create_failed: HTTPXMock,
    mock_schema_query_01: HTTPXMock,
    clients: BothClients,
    client_type: str,
) -> None:
    if client_type == "standard":
        batch = await clients.standard.create_batch(return_exceptions=True)
        locations = ["JFK1", "JFK1"]
        results = []
        for location_name in locations:
            data = {"name": {"value": location_name, "is_protected": True}}
            obj = await clients.standard.create(kind="BuiltinLocation", data=data)
            batch.add(task=obj.save, node=obj)
            results.append(obj)

        result_iter = batch.execute()
        # Assert first node success
        node, result = await anext(result_iter)
        assert node == results[0]
        assert not isinstance(result, Exception)

        # Assert second node failure
        node, result = await anext(result_iter)
        assert node == results[1]
        assert isinstance(result, GraphQLError)
        assert "An error occurred while executing the GraphQL Query" in str(result)
    else:
        batch = clients.sync.create_batch(return_exceptions=True)
        locations = ["JFK1", "JFK1"]
        results = []
        for location_name in locations:
            data = {"name": {"value": location_name, "is_protected": True}}
            obj = clients.sync.create(kind="BuiltinLocation", data=data)
            batch.add(task=obj.save, node=obj)
            results.append(obj)

        results = [r for _, r in batch.execute()]
        # Must have one exception and one graphqlerror
        assert len(results) == 2
        assert any(isinstance(r, Exception) for r in results)
        assert any(isinstance(r, GraphQLError) for r in results)


@pytest.mark.parametrize("client_type", client_types)
async def test_batch_exception(
    httpx_mock: HTTPXMock,
    mock_query_mutation_location_create_failed: HTTPXMock,
    mock_schema_query_01: HTTPXMock,
    clients: BothClients,
    client_type: str,
) -> None:
    if client_type == "standard":
        batch = await clients.standard.create_batch(return_exceptions=False)
        locations = ["JFK1", "JFK1"]
        for location_name in locations:
            data = {"name": {"value": location_name, "is_protected": True}}
            obj = await clients.standard.create(kind="BuiltinLocation", data=data)
            batch.add(task=obj.save, node=obj)

        with pytest.raises(GraphQLError) as exc:
            async for _, _ in batch.execute():
                pass
        assert "An error occurred while executing the GraphQL Query" in str(exc.value)
    else:
        batch = clients.sync.create_batch(return_exceptions=False)
        locations = ["JFK1", "JFK1"]
        for location_name in locations:
            data = {"name": {"value": location_name, "is_protected": True}}
            obj = clients.sync.create(kind="BuiltinLocation", data=data)
            batch.add(task=obj.save, node=obj)

        with pytest.raises(GraphQLError) as exc:
            for _, _ in batch.execute():
                pass
        assert "An error occurred while executing the GraphQL Query" in str(exc.value)


async def test_execute_does_not_orphan_inflight_tasks_when_raising() -> None:
    """When one batch task raises and return_exceptions=False, sibling tasks
    that are still in flight must not be left running. If they are orphaned,
    their work-in-progress side effects continue after the caller has been
    told the batch failed, and unretrieved exceptions surface later as
    "Task exception was never retrieved" in the asyncio log.
    """
    side_effects: list[str] = []

    async def raise_fast() -> None:
        # Yield once so siblings get scheduled, then fail before they finish.
        await asyncio.sleep(0)
        raise RuntimeError("fast failure")

    async def slow_side_effect(name: str) -> str:
        await asyncio.sleep(0.1)
        side_effects.append(name)
        return name

    batch = InfrahubBatch(max_concurrent_execution=10, return_exceptions=False)
    batch.add(task=raise_fast)
    for i in range(5):
        batch.add(task=slow_side_effect, name=f"slow-{i}")

    with pytest.raises(RuntimeError, match="fast failure"):
        async for _ in batch.execute():
            pass

    # Wait long enough that any orphan would have completed.
    await asyncio.sleep(0.3)

    assert side_effects == [], (
        f"sibling tasks were orphaned and ran to completion after execute() raised: {side_effects}"
    )


async def test_return_exceptions_yields_exceptions_indistinguishably_from_successes() -> None:
    """Pins down the current contract of ``execute()`` with ``return_exceptions=True``.

    Failures are yielded as ``(node, ExceptionInstance)`` using the same tuple
    shape as successes ``(node, result)``. The yielded ``node`` is whatever the
    caller passed via ``batch.add(..., node=...)`` regardless of outcome, so a
    consumer that does not ``isinstance``-check ``result`` cannot tell a failed
    task from a successful one and will silently treat both as "created".

    This test is expected to change when the API shape is reworked (e.g., a
    ``BatchResult`` dataclass with separate ``result``/``exception`` fields, or
    a split API where successes and failures are surfaced on different paths).
    """
    sentinel_a = object()
    sentinel_b = object()

    async def succeed() -> str:
        return "ok"

    async def fail() -> None:
        raise RuntimeError("boom")

    batch = InfrahubBatch(max_concurrent_execution=10, return_exceptions=True)
    batch.add(task=succeed, node=sentinel_a)
    batch.add(task=fail, node=sentinel_b)

    yielded: list[tuple[object, object]] = []
    async for node, result in batch.execute():
        yielded.append((node, result))

    by_node = {id(n): r for n, r in yielded}

    # Both tasks yield, and the tuple shape is identical.
    assert len(yielded) == 2
    assert {id(sentinel_a), id(sentinel_b)} == set(by_node.keys())

    # Successful yield: result is the task's return value.
    assert by_node[id(sentinel_a)] == "ok"

    # Failed yield: result is the exception instance, in the same slot. The
    # only way to distinguish failure from success is an isinstance check on
    # the result. The node slot is unchanged from what the caller supplied.
    failed_result = by_node[id(sentinel_b)]
    assert isinstance(failed_result, RuntimeError)
    assert str(failed_result) == "boom"

    # Demonstrate the silent-data-loss pitfall: a naive caller that records
    # ``node`` per yield treats the failed task as if it succeeded.
    naive_created = [n for n, _ in yielded]
    assert sentinel_b in naive_created  # node retained despite the underlying failure
