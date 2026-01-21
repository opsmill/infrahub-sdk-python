from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.schema import NodeSchemaAPI

    from .conftest import BothClients

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_node_artifact_generate_raise_featurenotsupported(
    client: InfrahubClient, client_type: str, location_schema: NodeSchemaAPI, location_data01: dict[str, Any]
) -> None:
    # node does not inherit from CoreArtifactTarget
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=location_data01)
        with pytest.raises(FeatureNotSupportedError):
            await node.artifact_generate("artifact_definition")
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=location_data01)
        with pytest.raises(FeatureNotSupportedError):
            node.artifact_generate("artifact_definition")


@pytest.mark.parametrize("client_type", client_types)
async def test_node_artifact_fetch_raise_featurenotsupported(
    client: InfrahubClient, client_type: str, location_schema: NodeSchemaAPI, location_data01: dict[str, Any]
) -> None:
    # node does not inherit from CoreArtifactTarget
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=location_data01)
        with pytest.raises(FeatureNotSupportedError):
            await node.artifact_fetch("artifact_definition")
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=location_data01)
        with pytest.raises(FeatureNotSupportedError):
            node.artifact_fetch("artifact_definition")


@pytest.mark.parametrize("client_type", client_types)
async def test_node_generate_raise_featurenotsupported(
    client: InfrahubClient, client_type: str, location_schema: NodeSchemaAPI, location_data01: dict[str, Any]
) -> None:
    # node not of kind CoreArtifactDefinition
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=location_data01)
        with pytest.raises(FeatureNotSupportedError):
            await node.generate("artifact_definition")
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=location_data01)
        with pytest.raises(FeatureNotSupportedError):
            node.generate("artifact_definition")


@pytest.mark.parametrize("client_type", client_types)
async def test_node_artifact_definition_generate(
    clients: BothClients,
    client_type: str,
    mock_rest_api_artifact_definition_generate: HTTPXMock,
    artifact_definition_schema: NodeSchemaAPI,
    artifact_definition_data: dict[str, Any],
) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=artifact_definition_schema, data=artifact_definition_data)
        await node.generate()
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=artifact_definition_schema, data=artifact_definition_data)
        node.generate()


@pytest.mark.parametrize("client_type", client_types)
async def test_node_artifact_fetch(
    clients: BothClients,
    client_type: str,
    mock_rest_api_artifact_fetch: HTTPXMock,
    device_schema: NodeSchemaAPI,
    device_data: dict[str, Any],
) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=device_schema, data=device_data)
        artifact_content = await node.artifact_fetch("startup-config")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=device_schema, data=device_data)
        artifact_content = node.artifact_fetch("startup-config")

    assert (
        artifact_content
        == """!device startup config
ip name-server 1.1.1.1
"""
    )


@pytest.mark.parametrize("client_type", client_types)
async def test_node_artifact_generate(
    clients: BothClients,
    client_type: str,
    mock_rest_api_artifact_generate: HTTPXMock,
    device_schema: NodeSchemaAPI,
    device_data: dict[str, Any],
) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=device_schema, data=device_data)
        await node.artifact_generate("startup-config")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=device_schema, data=device_data)
        node.artifact_generate("startup-config")
