from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

if TYPE_CHECKING:
    from typing import Any

    from pytest_httpx import HTTPXMock

    from infrahub_sdk.protocols_base import CoreNode, CoreNodeSync
    from infrahub_sdk.schema import NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_allocate_next_ip_address(
    httpx_mock: HTTPXMock,
    mock_schema_query_ipam: HTTPXMock,
    clients: BothClients,
    ipaddress_pool_schema: NodeSchemaAPI,
    ipam_ipprefix_schema: NodeSchemaAPI,
    ipam_ipprefix_data: dict[str, Any],
    client_type: str,
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "InfrahubIPAddressPoolGetResource": {
                    "ok": True,
                    "node": {
                        "id": "17da1246-54f1-a9c0-2784-179f0ec5b128",
                        "kind": "IpamIPAddress",
                        "identifier": "test",
                        "display_label": "192.0.2.0/32",
                    },
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "allocate-ip-loopback"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "IpamIPAddress": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "17d9bd8d-8fc2-70b0-278a-179f425e25cb",
                                "__typename": "IpamIPAddress",
                                "address": {"value": "192.0.2.0/32"},
                                "description": {"value": "test"},
                            }
                        }
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-ipamipaddress-page1"},
        is_reusable=True,
    )

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
        ip_address = await clients.standard.allocate_next_ip_address(
            resource_pool=cast("CoreNode", ip_pool),
            identifier="test",
            prefix_length=32,
            address_type="IpamIPAddress",
            data={"description": "test"},
            tracker="allocate-ip-loopback",
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
        ip_address = clients.sync.allocate_next_ip_address(
            resource_pool=cast("CoreNodeSync", ip_pool),
            identifier="test",
            prefix_length=32,
            address_type="IpamIPAddress",
            data={"description": "test"},
            tracker="allocate-ip-loopback",
        )

    assert ip_address
    assert str(cast("InfrahubNodeSync", ip_address).address.value) == "192.0.2.0/32"
    assert cast("InfrahubNodeSync", ip_address).description.value == "test"


@pytest.mark.parametrize("client_type", client_types)
async def test_allocate_next_ip_prefix(
    httpx_mock: HTTPXMock,
    mock_schema_query_ipam: HTTPXMock,
    clients: BothClients,
    ipprefix_pool_schema: NodeSchemaAPI,
    ipam_ipprefix_schema: NodeSchemaAPI,
    ipam_ipprefix_data: dict[str, Any],
    client_type: str,
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "InfrahubIPPrefixPoolGetResource": {
                    "ok": True,
                    "node": {
                        "id": "7d9bd8d-8fc2-70b0-278a-179f425e25cb",
                        "kind": "IpamIPPrefix",
                        "identifier": "test",
                        "display_label": "192.0.2.0/31",
                    },
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "allocate-ip-interco"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "IpamIPPrefix": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "17d9bd8d-8fc2-70b0-278a-179f425e25cb",
                                "__typename": "IpamIPPrefix",
                                "prefix": {"value": "192.0.2.0/31"},
                                "description": {"value": "test"},
                            }
                        }
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-ipamipprefix-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        ip_prefix = InfrahubNode(client=clients.standard, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNode(
            client=clients.standard,
            schema=ipprefix_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core intercos",
                "default_prefix_type": "IpamIPPrefix",
                "default_prefix_length": 31,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        ip_prefix = await clients.standard.allocate_next_ip_prefix(
            resource_pool=cast("CoreNode", ip_pool),
            identifier="test",
            prefix_length=31,
            prefix_type="IpamIPPrefix",
            data={"description": "test"},
            tracker="allocate-ip-interco",
        )
    else:
        ip_prefix = InfrahubNodeSync(client=clients.sync, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNodeSync(
            client=clients.sync,
            schema=ipprefix_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core intercos",
                "default_prefix_type": "IpamIPPrefix",
                "default_prefix_length": 31,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        ip_prefix = clients.sync.allocate_next_ip_prefix(
            resource_pool=cast("CoreNodeSync", ip_pool),
            identifier="test",
            prefix_length=31,
            prefix_type="IpamIPPrefix",
            data={"description": "test"},
            tracker="allocate-ip-interco",
        )

    assert ip_prefix
    assert str(cast("InfrahubNodeSync", ip_prefix).prefix.value) == "192.0.2.0/31"  # type: ignore[unresolved-attribute]
    assert cast("InfrahubNodeSync", ip_prefix).description.value == "test"  # type: ignore[unresolved-attribute]
