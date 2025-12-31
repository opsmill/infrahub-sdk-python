from typing import Any

import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.exceptions import BranchNotFoundError
from infrahub_sdk.schema import NodeSchemaAPI
from infrahub_sdk.testing.docker import TestInfrahubDockerClient


class TestInfrahubSchema(TestInfrahubDockerClient):
    async def test_query_schema_for_branch_not_found(self, client: InfrahubClient) -> None:
        with pytest.raises(BranchNotFoundError) as exc:
            await client.all(kind="BuiltinTag", branch="I-do-not-exist")

        assert str(exc.value) == "The requested branch was not found on the server [I-do-not-exist]"

    async def test_schema_all(self, client: InfrahubClient) -> None:
        schema_nodes = await client.schema.all()

        assert [node for node in schema_nodes.values() if node.namespace == "Profile"]

        assert "BuiltinTag" in schema_nodes
        assert isinstance(schema_nodes["BuiltinTag"], NodeSchemaAPI)

    async def test_schema_get(self, client: InfrahubClient) -> None:
        schema_node = await client.schema.get(kind="BuiltinTag")

        assert isinstance(schema_node, NodeSchemaAPI)
        assert client.default_branch in client.schema.cache


class TestInfrahubSchemaLoad(TestInfrahubDockerClient):
    async def test_schema_load_many(
        self, client: InfrahubClient, schema_extension_01: dict[str, Any], schema_extension_02: dict[str, Any]
    ) -> None:
        response = await client.schema.load(
            schemas=[schema_extension_01, schema_extension_02], wait_until_converged=True
        )

        assert response.schema_updated

        schema_nodes = await client.schema.all(refresh=True)
        assert "InfraRack" in schema_nodes
        assert "ProcurementContract" in schema_nodes
