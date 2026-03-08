"""Templates store pool references without allocating values.

When a template node is saved, _process_mutation_result should NOT overwrite
pool-sourced attributes or relationships with server-allocated values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema import AttributeSchemaAPI, RelationshipSchemaAPI, TemplateSchemaAPI
from infrahub_sdk.schema.main import AttributeKind, RelationshipKind

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.schema import NodeSchemaAPI

POOL_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
NODE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

VLAN_MUTATION = "TemplateIpamVLANCreate"
DEVICE_MUTATION = "TemplateInfraDeviceCreate"


class TestTemplateAttributeSkipsPoolAllocation:
    async def test_async_template_preserves_pool_reference_on_attribute(
        self,
        client: InfrahubClient,
        vlan_template_schema: TemplateSchemaAPI,
    ) -> None:
        """After save, a template's from_pool attribute should keep the pool reference, not the allocated value."""
        node = InfrahubNode(client=client, schema=vlan_template_schema, data=_vlan_data_with_pool())

        # Act
        await node._process_mutation_result(VLAN_MUTATION, _vlan_mutation_response())

        assert node.vlan_id.value != 42
        assert node.id == NODE_ID

    async def test_sync_template_preserves_pool_reference_on_attribute(
        self,
        client_sync: InfrahubClientSync,
        vlan_template_schema: TemplateSchemaAPI,
    ) -> None:
        """After save, a template's from_pool attribute should keep the pool reference, not the allocated value."""
        node = InfrahubNodeSync(client=client_sync, schema=vlan_template_schema, data=_vlan_data_with_pool())

        # Act
        node._process_mutation_result(VLAN_MUTATION, _vlan_mutation_response())

        assert node.vlan_id.value != 42
        assert node.id == NODE_ID

    async def test_async_regular_node_does_allocate_from_pool(
        self,
        client: InfrahubClient,
        vlan_schema: NodeSchemaAPI,
    ) -> None:
        """Contrast: a regular node SHOULD update its attribute with the allocated value."""
        node = InfrahubNode(client=client, schema=vlan_schema, data=_vlan_data_with_pool())

        # Act
        await node._process_mutation_result("InfraVLANCreate", _node_vlan_mutation_response())

        assert node.vlan_id.value == 42
        assert node.id == NODE_ID

    async def test_sync_regular_node_does_allocate_from_pool(
        self,
        client_sync: InfrahubClientSync,
        vlan_schema: NodeSchemaAPI,
    ) -> None:
        """Contrast: a regular node SHOULD update its attribute with the allocated value."""
        node = InfrahubNodeSync(client=client_sync, schema=vlan_schema, data=_vlan_data_with_pool())

        # Act
        node._process_mutation_result("InfraVLANCreate", _node_vlan_mutation_response())

        assert node.vlan_id.value == 42
        assert node.id == NODE_ID


class TestTemplateRelationshipSkipsPoolAllocation:
    async def test_async_template_preserves_pool_reference_on_relationship(
        self,
        client: InfrahubClient,
        device_template_schema: TemplateSchemaAPI,
        ipaddress_pool_schema: NodeSchemaAPI,
        ipam_ipprefix_schema: NodeSchemaAPI,
        ipam_ipprefix_data: dict[str, Any],
    ) -> None:
        """After save, a template's pool relationship should not be replaced with the allocated resource."""
        ip_prefix = InfrahubNode(client=client, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNode(client=client, schema=ipaddress_pool_schema, data=_pool_node_data(ip_prefix))
        node = InfrahubNode(
            client=client, schema=device_template_schema, data={"name": "device-template", "primary_address": ip_pool}
        )
        original_rel = node.primary_address

        # Act
        await node._process_mutation_result(DEVICE_MUTATION, _device_mutation_response())

        assert node.primary_address is original_rel
        assert node.id == NODE_ID

    async def test_sync_template_preserves_pool_reference_on_relationship(
        self,
        client_sync: InfrahubClientSync,
        device_template_schema: TemplateSchemaAPI,
        ipaddress_pool_schema: NodeSchemaAPI,
        ipam_ipprefix_schema: NodeSchemaAPI,
        ipam_ipprefix_data: dict[str, Any],
    ) -> None:
        """After save, a template's pool relationship should not be replaced with the allocated resource."""
        ip_prefix = InfrahubNodeSync(client=client_sync, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNodeSync(client=client_sync, schema=ipaddress_pool_schema, data=_pool_node_data(ip_prefix))
        node = InfrahubNodeSync(
            client=client_sync,
            schema=device_template_schema,
            data={"name": "device-template", "primary_address": ip_pool},
        )
        original_rel = node.primary_address

        # Act
        node._process_mutation_result(DEVICE_MUTATION, _device_mutation_response())

        assert node.primary_address is original_rel
        assert node.id == NODE_ID


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _vlan_data_with_pool() -> dict[str, Any]:
    return {"name": "Standard VLAN", "vlan_id": {"from_pool": {"id": POOL_ID, "identifier": "vlan-id"}}}


def _vlan_mutation_response() -> dict[str, Any]:
    return {VLAN_MUTATION: {"ok": True, "object": {"id": NODE_ID, "vlan_id": {"value": 42}}}}


def _node_vlan_mutation_response() -> dict[str, Any]:
    return {"InfraVLANCreate": {"ok": True, "object": {"id": NODE_ID, "vlan_id": {"value": 42}}}}


def _device_mutation_response() -> dict[str, Any]:
    return {
        DEVICE_MUTATION: {
            "ok": True,
            "object": {
                "id": NODE_ID,
                "primary_address": {
                    "node": {
                        "__typename": "IpamIPAddress",
                        "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                        "display_label": "10.0.0.1/32",
                    },
                },
            },
        },
    }


def _pool_node_data(ip_prefix: InfrahubNode | InfrahubNodeSync) -> dict[str, Any]:
    return {
        "id": POOL_ID,
        "name": "Core loopbacks",
        "default_address_type": "IpamIPAddress",
        "default_prefix_length": 32,
        "ip_namespace": "ip_namespace",
        "resources": [ip_prefix],
    }


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
async def vlan_template_schema() -> TemplateSchemaAPI:
    return TemplateSchemaAPI(
        name="VLAN",
        namespace="TemplateIpam",
        attributes=[
            AttributeSchemaAPI(name="name", kind=AttributeKind.TEXT, unique=True),
            AttributeSchemaAPI(name="vlan_id", kind=AttributeKind.NUMBER),
        ],
        relationships=[],
    )


@pytest.fixture
async def device_template_schema() -> TemplateSchemaAPI:
    return TemplateSchemaAPI(
        name="Device",
        namespace="TemplateInfra",
        attributes=[
            AttributeSchemaAPI(name="name", kind=AttributeKind.TEXT, unique=True),
        ],
        relationships=[
            RelationshipSchemaAPI(
                name="primary_address",
                peer="IpamIPAddress",
                label="Primary IP Address",
                optional=True,
                cardinality="one",
                kind=RelationshipKind.ATTRIBUTE,
            ),
        ],
    )
