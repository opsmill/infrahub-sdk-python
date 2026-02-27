from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

if TYPE_CHECKING:
    from typing import Any

    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_get_pool_allocated_resources(
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
                "InfrahubResourcePoolAllocated": {
                    "count": 2,
                    "edges": [
                        {
                            "node": {
                                "id": "17d9bd8d-8fc2-70b0-278a-179f425e25cb",
                                "kind": "IpamIPAddress",
                                "branch": "main",
                                "identifier": "ip-1",
                            }
                        },
                        {
                            "node": {
                                "id": "17d9bd8e-31ee-acf0-2786-179fb76f2f67",
                                "kind": "IpamIPAddress",
                                "branch": "main",
                                "identifier": "ip-2",
                            }
                        },
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "get-allocated-resources-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "IpamIPAddress": {
                    "count": 2,
                    "edges": [
                        {"node": {"id": "17d9bd8d-8fc2-70b0-278a-179f425e25cb", "__typename": "IpamIPAddress"}},
                        {"node": {"id": "17d9bd8e-31ee-acf0-2786-179fb76f2f67", "__typename": "IpamIPAddress"}},
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-ipamipaddress-page1"},
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

        resources = await ip_pool.get_pool_allocated_resources(resource=ip_prefix)
        assert len(resources) == 2
        assert [resource.id for resource in resources] == [
            "17d9bd8d-8fc2-70b0-278a-179f425e25cb",
            "17d9bd8e-31ee-acf0-2786-179fb76f2f67",
        ]
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

        resources = ip_pool.get_pool_allocated_resources(resource=ip_prefix)
        assert len(resources) == 2
        assert [resource.id for resource in resources] == [
            "17d9bd8d-8fc2-70b0-278a-179f425e25cb",
            "17d9bd8e-31ee-acf0-2786-179fb76f2f67",
        ]


@pytest.mark.parametrize("client_type", client_types)
async def test_get_pool_resources_utilization(
    httpx_mock: HTTPXMock,
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
                "InfrahubResourcePoolUtilization": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "17d9bd86-3471-a020-2782-179ff078e58f",
                                "utilization": 93.75,
                                "utilization_branches": 0,
                                "utilization_default_branch": 93.75,
                            }
                        }
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "get-pool-utilization"},
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

        utilizations = await ip_pool.get_pool_resources_utilization()
        assert len(utilizations) == 1
        assert utilizations[0]["utilization"] == 93.75
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

        utilizations = ip_pool.get_pool_resources_utilization()
        assert len(utilizations) == 1
        assert utilizations[0]["utilization"] == 93.75
