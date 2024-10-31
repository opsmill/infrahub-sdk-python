from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.exceptions import GraphQLError

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients


async def test_batch_return_exception(
    httpx_mock: HTTPXMock, mock_query_mutation_location_create_failed, mock_schema_query_01, clients: BothClients
):  # pylint: disable=unused-argument
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
    node, result = await result_iter.__anext__()
    assert node == results[0]
    assert not isinstance(result, Exception)

    # Assert second node failure
    node, result = await result_iter.__anext__()
    assert node == results[1]
    assert isinstance(result, GraphQLError)
    assert "An error occurred while executing the GraphQL Query" in str(result)


async def test_batch_exception(
    httpx_mock: HTTPXMock, mock_query_mutation_location_create_failed, mock_schema_query_01, clients: BothClients
):  # pylint: disable=unused-argument
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


async def test_batch_not_implemented_sync(clients: BothClients):
    with pytest.raises(NotImplementedError):
        clients.sync.create_batch()
