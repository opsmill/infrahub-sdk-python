from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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
