from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

if TYPE_CHECKING:
    from typing import Any

    from infrahub_sdk.schema import NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_resource_pool_relationship(
    clients: BothClients,
    ipaddress_pool_schema: NodeSchemaAPI,
    ipam_ipprefix_schema: NodeSchemaAPI,
    simple_device_schema: NodeSchemaAPI,
    ipam_ipprefix_data: dict[str, Any],
    client_type: str,
) -> None:
    if client_type == "standard":
        ip_prefix = InfrahubNode(client=clients.standard, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNode(
            client=clients.standard,
            schema=ipaddress_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core loopbacks",
                "default_address_type": "IpamIPAddress",
                "default_prefix_length": 32,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        device = InfrahubNode(
            client=clients.standard,
            schema=simple_device_schema,
            data={"name": "device-01", "primary_address": ip_pool, "ip_address_pool": ip_pool},
        )
    else:
        ip_prefix = InfrahubNodeSync(client=clients.sync, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNodeSync(
            client=clients.sync,
            schema=ipaddress_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core loopbacks",
                "default_address_type": "IpamIPAddress",
                "default_prefix_length": 32,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        device = InfrahubNodeSync(
            client=clients.sync,
            schema=simple_device_schema,
            data={"name": "device-01", "primary_address": ip_pool, "ip_address_pool": ip_pool},
        )

    assert device._generate_input_data()["data"] == {
        "data": {
            "name": {"value": "device-01"},
            "primary_address": {"from_pool": {"id": "pppppppp-pppp-pppp-pppp-pppppppppppp"}},
            "ip_address_pool": {"id": "pppppppp-pppp-pppp-pppp-pppppppppppp"},
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_create_mutation_query_with_resource_pool_relationship(
    clients: BothClients,
    ipaddress_pool_schema: NodeSchemaAPI,
    ipam_ipprefix_schema: NodeSchemaAPI,
    simple_device_schema: NodeSchemaAPI,
    ipam_ipprefix_data: dict[str, Any],
    client_type: str,
) -> None:
    if client_type == "standard":
        ip_prefix = InfrahubNode(client=clients.standard, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNode(
            client=clients.standard,
            schema=ipaddress_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core loopbacks",
                "default_address_type": "IpamIPAddress",
                "default_prefix_length": 32,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        device = InfrahubNode(
            client=clients.standard,
            schema=simple_device_schema,
            data={"name": "device-01", "primary_address": ip_pool, "ip_address_pool": ip_pool},
        )
    else:
        ip_prefix = InfrahubNodeSync(client=clients.sync, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNodeSync(
            client=clients.sync,
            schema=ipaddress_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core loopbacks",
                "default_address_type": "IpamIPAddress",
                "default_prefix_length": 32,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        device = InfrahubNodeSync(
            client=clients.sync,
            schema=simple_device_schema,
            data={"name": "device-01", "primary_address": ip_pool, "ip_address_pool": ip_pool},
        )

    assert device._generate_mutation_query() == {
        "object": {
            "id": None,
            "primary_address": {"node": {"__typename": None, "display_label": None, "id": None}},
            "ip_address_pool": {"node": {"__typename": None, "display_label": None, "id": None}},
        },
        "ok": None,
    }
