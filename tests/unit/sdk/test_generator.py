from __future__ import annotations

import json
from typing import TYPE_CHECKING

from infrahub_sdk import Config, InfrahubClient
from infrahub_sdk.context import ContextAccount, RequestContext
from infrahub_sdk.generator import InfrahubGenerator
from infrahub_sdk.node import InfrahubNode

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI

GENERATOR_GROUP_SCHEMA = {
    "generics": [{"name": "Node", "namespace": "Core"}],
    "nodes": [
        {
            "name": "GeneratorGroup",
            "namespace": "Core",
            "attributes": [
                {"name": "name", "kind": "Text", "unique": True},
                {"name": "description", "kind": "Text", "optional": True},
            ],
            "relationships": [{"name": "members", "peer": "CoreNode", "cardinality": "many", "optional": True}],
        }
    ],
}


class LocationGenerator(InfrahubGenerator):
    location_schema: NodeSchemaAPI

    async def generate(self, data: dict) -> None:
        location = InfrahubNode(
            client=self.client,
            schema=self.location_schema,
            data={"name": {"value": "JFK1"}, "type": {"value": "SITE"}},
        )
        await location.save(update_group_context=False)


async def test_generator_writes_carry_the_client_request_context(
    location_schema: NodeSchemaAPI, httpx_mock: HTTPXMock
) -> None:
    """A generator sends its writes with the account of the client it was given."""
    httpx_mock.add_response(
        method="POST", url="http://mock/api/query/locations?branch=main&update_group=true", json={"data": {}}
    )
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={
            "data": {"BuiltinLocationCreate": {"ok": True, "object": {"id": "17aec828-9814-ce00-3f20-1a053670f1c8"}}}
        },
    )
    httpx_mock.add_response(method="GET", url="http://mock/api/schema?branch=main", json=GENERATOR_GROUP_SCHEMA)
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {"CoreGeneratorGroup": {"count": 0, "edges": []}}},
    )
    client = InfrahubClient(config=Config(address="http://mock"))
    client.request_context = RequestContext(account=ContextAccount(id="account-1"))

    generator = LocationGenerator(query="locations", client=client, branch="main", infrahub_node=InfrahubNode)
    generator.location_schema = location_schema
    await generator.run(identifier="location-generator")

    mutation = httpx_mock.get_requests(url="http://mock/graphql/main")[0]
    query = " ".join(json.loads(mutation.content)["query"].split())
    assert "BuiltinLocationCreate" in query
    assert 'context: { account: { id: "account-1" } }' in query
