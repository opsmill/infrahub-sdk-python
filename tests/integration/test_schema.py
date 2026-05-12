from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from infrahub_sdk import InfrahubClient
from infrahub_sdk.ctl.schema import display_schema_load_errors
from infrahub_sdk.exceptions import BranchNotFoundError
from infrahub_sdk.schema import NodeSchemaAPI
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.yaml import SchemaFile


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


class TestInfrahubSchemaLoadErrorRendering(TestInfrahubDockerClient):
    """Render real server error responses through display_schema_load_errors.

    These exist as integration tests so we catch any drift between the server's
    validation error payload shape and the CLI renderer, particularly for
    `extensions` paths which previously went unhandled.
    """

    async def test_extension_top_level_field_error(self, client: InfrahubClient) -> None:
        broken_schema = {
            "version": "1.0",
            "extensions": {
                "nodes": [
                    {
                        "kind": "BuiltinTag",
                        "namespace": "Forbidden",
                    }
                ]
            },
        }

        response = await client.schema.load(schemas=[broken_schema])

        assert response.errors, "Server should reject a forbidden field on an extensions/nodes entry"
        assert "detail" in response.errors

        schemas_data = [SchemaFile(location=Path("broken.yml"), content=broken_schema)]
        buffer = StringIO()
        output = Console(file=buffer, width=1000, force_terminal=False)
        display_schema_load_errors(response=response.errors, schemas_data=schemas_data, output=output)
        rendered = buffer.getvalue()

        assert "Unable to load the schema" in rendered
        assert "BuiltinTag" in rendered
        assert "extensions/nodes" in rendered

    async def test_extension_nested_attribute_error(self, client: InfrahubClient) -> None:
        broken_schema = {
            "version": "1.0",
            "extensions": {
                "nodes": [
                    {
                        "kind": "BuiltinTag",
                        "attributes": [
                            {"name": "speed", "kind": "Number", "made_up": True},
                        ],
                    }
                ]
            },
        }

        response = await client.schema.load(schemas=[broken_schema])

        assert response.errors, "Server should reject a forbidden field on an extensions attribute entry"
        assert "detail" in response.errors

        schemas_data = [SchemaFile(location=Path("broken.yml"), content=broken_schema)]
        buffer = StringIO()
        output = Console(file=buffer, width=1000, force_terminal=False)
        display_schema_load_errors(response=response.errors, schemas_data=schemas_data, output=output)
        rendered = buffer.getvalue()

        assert "Unable to load the schema" in rendered
        assert "BuiltinTag" in rendered
        assert "extensions/nodes" in rendered
        assert "speed" in rendered
