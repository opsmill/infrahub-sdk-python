from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.constants import PoolAllocationProvenance
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync, PoolAllocation

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

    # Servers older than 1.12 reject the provenance field.
    allocated_request = httpx_mock.get_request(match_headers={"X-Infrahub-Tracker": "get-allocated-resources-page1"})
    assert allocated_request is not None
    assert b"provenance" not in allocated_request.content


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
        assert utilizations[0]["utilization"] == pytest.approx(93.75)
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
        assert utilizations[0]["utilization"] == pytest.approx(93.75)


NUMBER_POOL_ID = "nnnnnnnn-nnnn-nnnn-nnnn-nnnnnnnnnnnn"


def _allocation_row(node_id: str, number: int, provenance: str | None) -> dict[str, Any]:
    return {
        "node": {
            "id": node_id,
            "kind": "InfraVLAN",
            "branch": "main",
            "display_label": str(number),
            "identifier": None,
            "provenance": provenance,
        }
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_get_pool_allocations(
    httpx_mock: HTTPXMock,
    clients: BothClients,
    number_pool_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "InfrahubResourcePoolAllocated": {
                    "count": 4,
                    "edges": [
                        _allocation_row(node_id="vlan-1", number=100, provenance="ALLOCATED"),
                        _allocation_row(node_id="vlan-2", number=101, provenance="PROVIDED"),
                        _allocation_row(node_id="vlan-3", number=102, provenance="ALLOCATED"),
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "get-pool-allocations-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "InfrahubResourcePoolAllocated": {
                    "count": 4,
                    "edges": [_allocation_row(node_id="vlan-4", number=103, provenance=None)],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "get-pool-allocations-page2"},
    )
    pool_data = {"id": NUMBER_POOL_ID, "name": "VLAN IDs", "node": "InfraVLAN", "node_attribute": "vlan_id"}

    if client_type == "standard":
        pool = InfrahubNode(client=clients.standard, schema=number_pool_schema, data=pool_data)
        allocations = await pool.get_pool_allocations(resource=pool)
    else:
        pool_sync = InfrahubNodeSync(client=clients.sync, schema=number_pool_schema, data=pool_data)
        allocations = pool_sync.get_pool_allocations(resource=pool_sync)

    assert allocations == [
        PoolAllocation(
            node_id="vlan-1",
            kind="InfraVLAN",
            branch="main",
            display_label="100",
            identifier=None,
            provenance=PoolAllocationProvenance.ALLOCATED,
        ),
        PoolAllocation(
            node_id="vlan-2",
            kind="InfraVLAN",
            branch="main",
            display_label="101",
            identifier=None,
            provenance=PoolAllocationProvenance.PROVIDED,
        ),
        PoolAllocation(
            node_id="vlan-3",
            kind="InfraVLAN",
            branch="main",
            display_label="102",
            identifier=None,
            provenance=PoolAllocationProvenance.ALLOCATED,
        ),
        PoolAllocation(
            node_id="vlan-4", kind="InfraVLAN", branch="main", display_label="103", identifier=None, provenance=None
        ),
    ]
    first_request = httpx_mock.get_request(match_headers={"X-Infrahub-Tracker": "get-pool-allocations-page1"})
    assert first_request is not None
    assert b"provenance" in first_request.content


@pytest.mark.parametrize("client_type", client_types)
async def test_get_pool_allocations_requires_a_pool(
    clients: BothClients,
    vlan_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    if client_type == "standard":
        vlan = InfrahubNode(client=clients.standard, schema=vlan_schema, data={"id": "vlan-1", "name": "VLAN 1"})
        with pytest.raises(ValueError, match="can only be fetched from resource pool nodes"):
            await vlan.get_pool_allocations(resource=vlan)
    else:
        vlan_sync = InfrahubNodeSync(client=clients.sync, schema=vlan_schema, data={"id": "vlan-1", "name": "VLAN 1"})
        with pytest.raises(ValueError, match="can only be fetched from resource pool nodes"):
            vlan_sync.get_pool_allocations(resource=vlan_sync)
