"""When using from_pool on a number attribute (e.g. vlan_id), the SDK should generate:
    vlan_id: { from_pool: { id: "...", identifier: "..." } }

There are two ways to request a pool allocation:
1. Dict-based:  {"from_pool": {"id": "...", "identifier": "..."}}
2. Node-based:  pass an InfrahubNode pool object as the attribute value
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import ValidationError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.schema import NodeSchemaAPI


POOL_ID = "185b9728-1b76-dda7-d13d-106529b1bcd9"


# ──────────────────────────────────────────────
# Dict-based from_pool - async client
# ──────────────────────────────────────────────


async def test_number_attribute_from_pool_with_identifier(
    client: InfrahubClient,
    vlan_schema: NodeSchemaAPI,
) -> None:
    """A number attribute with from_pool and identifier should NOT be wrapped in value."""
    data: dict[str, Any] = {
        "name": "Example VLAN",
        "vlan_id": {"from_pool": {"id": POOL_ID, "identifier": "test"}},
        "role": "user",
        "status": "active",
    }
    node = InfrahubNode(client=client, schema=vlan_schema, data=data)

    # Act
    input_data = node._generate_input_data()["data"]["data"]

    assert input_data["name"] == {"value": "Example VLAN"}
    assert input_data["role"] == {"value": "user"}
    assert input_data["status"] == {"value": "active"}
    assert input_data["vlan_id"] == {"from_pool": {"id": POOL_ID, "identifier": "test"}}
    assert "value" not in input_data["vlan_id"]


async def test_number_attribute_regular_value(
    client: InfrahubClient,
    vlan_schema: NodeSchemaAPI,
) -> None:
    """Regular number values should still be wrapped in value as before."""
    data: dict[str, Any] = {
        "name": "Example VLAN",
        "vlan_id": 100,
    }
    node = InfrahubNode(client=client, schema=vlan_schema, data=data)

    # Act
    input_data = node._generate_input_data()["data"]["data"]

    assert input_data["name"] == {"value": "Example VLAN"}
    assert input_data["vlan_id"] == {"value": 100}


async def test_number_attribute_from_pool_mutation_query(
    client: InfrahubClient,
    vlan_schema: NodeSchemaAPI,
) -> None:
    """A from_pool dict attribute should request value back in the mutation query."""
    data: dict[str, Any] = {
        "name": "Example VLAN",
        "vlan_id": {"from_pool": {"id": POOL_ID, "identifier": "test"}},
    }
    node = InfrahubNode(client=client, schema=vlan_schema, data=data)

    # Act
    mutation_query = node._generate_mutation_query()

    assert mutation_query["object"]["vlan_id"] == {"value": None}


# ──────────────────────────────────────────────
# Dict-based from_pool - sync client
# ──────────────────────────────────────────────


async def test_sync_number_attribute_from_pool_with_identifier(
    client_sync: InfrahubClientSync,
    vlan_schema: NodeSchemaAPI,
) -> None:
    """A number attribute with from_pool and identifier should NOT be wrapped in value (sync client)."""
    data: dict[str, Any] = {
        "name": "Example VLAN",
        "vlan_id": {"from_pool": {"id": POOL_ID, "identifier": "test"}},
        "role": "user",
        "status": "active",
    }
    node = InfrahubNodeSync(client=client_sync, schema=vlan_schema, data=data)

    # Act
    input_data = node._generate_input_data()["data"]["data"]

    assert input_data["name"] == {"value": "Example VLAN"}
    assert input_data["role"] == {"value": "user"}
    assert input_data["status"] == {"value": "active"}
    assert input_data["vlan_id"] == {"from_pool": {"id": POOL_ID, "identifier": "test"}}
    assert "value" not in input_data["vlan_id"]


async def test_sync_number_attribute_regular_value(
    client_sync: InfrahubClientSync,
    vlan_schema: NodeSchemaAPI,
) -> None:
    """Regular number values should still be wrapped in value as before (sync client)."""
    data: dict[str, Any] = {
        "name": "Example VLAN",
        "vlan_id": 100,
    }
    node = InfrahubNodeSync(client=client_sync, schema=vlan_schema, data=data)

    # Act
    input_data = node._generate_input_data()["data"]["data"]

    assert input_data["name"] == {"value": "Example VLAN"}
    assert input_data["vlan_id"] == {"value": 100}


# ──────────────────────────────────────────────
# Node-based from_pool - async client
# ──────────────────────────────────────────────

NODE_POOL_ID = "185b9728-1b56-dda7-d13d-106535b1bcd9"


async def test_attribute_with_pool_node_generates_from_pool(
    client: InfrahubClient,
    vlan_schema: NodeSchemaAPI,
    ipaddress_pool_schema: NodeSchemaAPI,
    ipam_ipprefix_schema: NodeSchemaAPI,
    ipam_ipprefix_data: dict[str, Any],
) -> None:
    """When an attribute value is a CoreNodeBase pool node, _generate_input_data should produce from_pool."""
    ip_prefix = InfrahubNode(client=client, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
    ip_pool = InfrahubNode(
        client=client,
        schema=ipaddress_pool_schema,
        data={
            "id": NODE_POOL_ID,
            "name": "Core loopbacks",
            "default_address_type": "IpamIPAddress",
            "default_prefix_length": 32,
            "ip_namespace": "ip_namespace",
            "resources": [ip_prefix],
        },
    )
    vlan = InfrahubNode(
        client=client,
        schema=vlan_schema,
        data={"name": "Example VLAN", "vlan_id": ip_pool},
    )

    # Act
    input_data = vlan._generate_input_data()["data"]["data"]

    assert input_data["vlan_id"] == {"from_pool": {"id": NODE_POOL_ID}}
    assert "value" not in input_data["vlan_id"]


async def test_attribute_with_pool_node_generates_mutation_query(
    client: InfrahubClient,
    vlan_schema: NodeSchemaAPI,
    ipaddress_pool_schema: NodeSchemaAPI,
    ipam_ipprefix_schema: NodeSchemaAPI,
    ipam_ipprefix_data: dict[str, Any],
) -> None:
    """When an attribute value is a CoreNodeBase pool node, _generate_mutation_query should request value back."""
    ip_prefix = InfrahubNode(client=client, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
    ip_pool = InfrahubNode(
        client=client,
        schema=ipaddress_pool_schema,
        data={
            "id": NODE_POOL_ID,
            "name": "Core loopbacks",
            "default_address_type": "IpamIPAddress",
            "default_prefix_length": 32,
            "ip_namespace": "ip_namespace",
            "resources": [ip_prefix],
        },
    )
    vlan = InfrahubNode(
        client=client,
        schema=vlan_schema,
        data={"name": "Example VLAN", "vlan_id": ip_pool},
    )

    # Act
    mutation_query = vlan._generate_mutation_query()

    assert mutation_query["object"]["vlan_id"] == {"value": None}


UPSERT_MOCK_RESPONSE = {
    "data": {
        "InfraVLANUpsert": {
            "ok": True,
            "object": {"id": "mock-vlan-uuid", "vlan_id": {"value": 100}},
        }
    }
}


async def test_save_upsert_raises_when_numberpool_attr_in_hfid(
    client: InfrahubClient,
    vlan_schema_with_pool_hfid: NodeSchemaAPI,
) -> None:
    """save(allow_upsert=True) raises ValidationError naming the pool-sourced HFID attribute."""
    node = InfrahubNode(
        client=client,
        schema=vlan_schema_with_pool_hfid,
        data={"name": "Test VLAN", "vlan_id": {"from_pool": {"id": POOL_ID}}},
    )

    with pytest.raises(ValidationError, match=re.escape("Attribute 'vlan_id' is sourced from a CoreNumberPool")):
        await node.save(allow_upsert=True)


async def test_save_upsert_proceeds_when_explicit_id_set(
    client: InfrahubClient,
    vlan_schema_with_pool_hfid: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    """Upsert proceeds when an explicit node id is already set."""
    httpx_mock.add_response(method="POST", json=UPSERT_MOCK_RESPONSE)
    node = InfrahubNode(
        client=client,
        schema=vlan_schema_with_pool_hfid,
        data={"name": "Test VLAN", "vlan_id": {"from_pool": {"id": POOL_ID}}},
    )
    node.id = "existing-node-uuid"

    await node.save(allow_upsert=True)

    assert node.id == "mock-vlan-uuid"


async def test_save_upsert_proceeds_when_numberpool_attr_not_in_hfid(
    client: InfrahubClient,
    vlan_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    """Upsert proceeds when the pool-sourced attribute is not part of the HFID."""
    httpx_mock.add_response(method="POST", json=UPSERT_MOCK_RESPONSE)
    node = InfrahubNode(
        client=client,
        schema=vlan_schema,
        data={"name": "Test VLAN", "vlan_id": {"from_pool": {"id": POOL_ID}}},
    )

    await node.save(allow_upsert=True)

    assert node.id == "mock-vlan-uuid"


async def test_save_upsert_raises_when_pool_node_object_in_hfid(
    client: InfrahubClient,
    vlan_schema_with_pool_hfid: NodeSchemaAPI,
    ipaddress_pool_schema: NodeSchemaAPI,
    ipam_ipprefix_schema: NodeSchemaAPI,
    ipam_ipprefix_data: dict[str, Any],
) -> None:
    """save(allow_upsert=True) raises ValidationError when vlan_id is set to a pool node object (not a from_pool dict)."""
    ip_prefix = InfrahubNode(client=client, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
    ip_pool = InfrahubNode(
        client=client,
        schema=ipaddress_pool_schema,
        data={
            "id": NODE_POOL_ID,
            "name": "Core loopbacks",
            "default_address_type": "IpamIPAddress",
            "default_prefix_length": 32,
            "ip_namespace": "ip_namespace",
            "resources": [ip_prefix],
        },
    )
    node = InfrahubNode(
        client=client,
        schema=vlan_schema_with_pool_hfid,
        data={"name": "Test VLAN", "vlan_id": ip_pool},
    )

    with pytest.raises(ValidationError, match=re.escape("Attribute 'vlan_id' is sourced from a CoreNumberPool")):
        await node.save(allow_upsert=True)


async def test_create_upsert_raises_when_numberpool_attr_in_hfid(
    client: InfrahubClient,
    vlan_schema_with_pool_hfid: NodeSchemaAPI,
) -> None:
    """create(allow_upsert=True) raises ValidationError directly, not only through save()."""
    node = InfrahubNode(
        client=client,
        schema=vlan_schema_with_pool_hfid,
        data={"name": "Test VLAN", "vlan_id": {"from_pool": {"id": POOL_ID}}},
    )

    with pytest.raises(ValidationError, match=re.escape("Attribute 'vlan_id' is sourced from a CoreNumberPool")):
        await node.create(allow_upsert=True)


def test_create_upsert_raises_when_numberpool_attr_in_hfid_sync(
    client_sync: InfrahubClientSync,
    vlan_schema_with_pool_hfid: NodeSchemaAPI,
) -> None:
    """Sync create(allow_upsert=True) raises ValidationError directly, not only through save()."""
    node = InfrahubNodeSync(
        client=client_sync,
        schema=vlan_schema_with_pool_hfid,
        data={"name": "Test VLAN", "vlan_id": {"from_pool": {"id": POOL_ID}}},
    )

    with pytest.raises(ValidationError, match=re.escape("Attribute 'vlan_id' is sourced from a CoreNumberPool")):
        node.create(allow_upsert=True)
