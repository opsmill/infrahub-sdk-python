"""Number pool ranges declared on create and upsert, attaching and detaching numbers, and allocation provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.constants import PoolAllocationProvenance
from infrahub_sdk.testing.docker import TestInfrahubDockerClient, skip_version

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.node import InfrahubNode

VLAN_KIND = "TestingPoolVlan"
VLAN_SCHEMA: dict[str, Any] = {
    "version": "1.0",
    "nodes": [
        {
            "name": "PoolVlan",
            "namespace": "Testing",
            "human_friendly_id": ["name__value"],
            "display_label": "{{ name__value }}",
            "attributes": [
                {"name": "name", "kind": "Text", "unique": True},
                {"name": "vlan_id", "kind": "Number", "optional": True},
            ],
        }
    ],
}


def _bounds(range_nodes: list[Any]) -> list[tuple[int | None, int | None, int | None]]:
    return sorted((r.start.value, r.end.value, r.allocation_weight.value) for r in range_nodes)


@pytest.mark.skipif(skip_version(min_infrahub_version="1.12"), reason="Requires Infrahub 1.12 or later")
class TestNumberPoolAttachRanges(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    async def load_vlan_schema(self, default_branch: str, client: InfrahubClient) -> None:
        await client.schema.wait_until_converged(branch=default_branch)
        resp = await client.schema.load(schemas=[VLAN_SCHEMA], branch=default_branch, wait_until_converged=True)
        assert resp.errors == {}

    @pytest.fixture(scope="class")
    async def vlan_pool(self, client: InfrahubClient, load_vlan_schema: None) -> InfrahubNode:
        pool = await client.create(
            kind="CoreNumberPool",
            name="VLAN ID Pool",
            node=VLAN_KIND,
            node_attribute="vlan_id",
            ranges=[{"start": 100, "end": 199, "allocation_weight": 10}, {"start": 200, "end": 299}],
        )
        await pool.save()
        return pool

    async def test_create_stores_declared_ranges(self, client: InfrahubClient, vlan_pool: InfrahubNode) -> None:
        ranges = await client.filters(kind="CoreNumberPoolRange", pool__ids=[vlan_pool.id])

        assert _bounds(ranges) == [(100, 199, 10), (200, 299, None)]

    async def test_upsert_sets_declared_ranges(self, client: InfrahubClient, load_vlan_schema: None) -> None:
        pool = await client.create(
            kind="CoreNumberPool",
            name="Upserted Pool",
            node=VLAN_KIND,
            node_attribute="vlan_id",
            ranges=[{"start": 1000, "end": 1099, "allocation_weight": 10}, {"start": 1100, "end": 1199}],
        )
        await pool.save()
        upsert = await client.create(
            kind="CoreNumberPool",
            name="Upserted Pool",
            node=VLAN_KIND,
            node_attribute="vlan_id",
            ranges=[{"start": 1000, "end": 1099, "allocation_weight": 20}, {"start": 1200}],
        )

        await upsert.save(allow_upsert=True)

        ranges = await client.filters(kind="CoreNumberPoolRange", pool__ids=[pool.id])
        assert _bounds(ranges) == [(1000, 1099, 20), (1200, None, None)]

    async def test_attach_detach_and_provenance(self, client: InfrahubClient, vlan_pool: InfrahubNode) -> None:
        allocated = await client.create(kind=VLAN_KIND, name="allocated", vlan_id={"from_pool": {"id": vlan_pool.id}})
        await allocated.save()
        provided = await client.create(
            kind=VLAN_KIND, name="provided", vlan_id={"value": 150, "from_pool": {"id": vlan_pool.id}}
        )
        await provided.save()
        plain = await client.create(kind=VLAN_KIND, name="plain", vlan_id=160)
        await plain.save()
        fetched_plain = await client.get(kind=VLAN_KIND, id=plain.id)
        fetched_plain.vlan_id.attach_to_pool(vlan_pool)
        await fetched_plain.save()

        allocations = {a.node_id: a for a in await vlan_pool.get_pool_allocations(resource=vlan_pool)}
        assert allocations[allocated.id].provenance == PoolAllocationProvenance.ALLOCATED
        assert allocations[allocated.id].display_label == str(allocated.vlan_id.value)
        assert allocations[provided.id].provenance == PoolAllocationProvenance.PROVIDED
        assert allocations[plain.id].provenance == PoolAllocationProvenance.PROVIDED
        with_properties = await client.get(kind=VLAN_KIND, id=provided.id, property=True)
        assert with_properties.vlan_id.source is not None
        assert with_properties.vlan_id.source.id == vlan_pool.id

        to_detach = await client.get(kind=VLAN_KIND, id=provided.id)
        to_detach.vlan_id.detach_from_pool()
        await to_detach.save()

        allocations = {a.node_id: a for a in await vlan_pool.get_pool_allocations(resource=vlan_pool)}
        assert provided.id not in allocations
        assert (await client.get(kind=VLAN_KIND, id=provided.id)).vlan_id.value == 150

    async def test_detach_before_first_save_keeps_the_number(
        self, client: InfrahubClient, vlan_pool: InfrahubNode
    ) -> None:
        vlan = await client.create(
            kind=VLAN_KIND, name="detached-before-save", vlan_id={"value": 180, "from_pool": {"id": vlan_pool.id}}
        )
        vlan.vlan_id.detach_from_pool()

        await vlan.save()

        assert (await client.get(kind=VLAN_KIND, id=vlan.id)).vlan_id.value == 180
        assert vlan.id not in {a.node_id for a in await vlan_pool.get_pool_allocations(resource=vlan_pool)}

    def test_attach_detach_sync(self, client_sync: InfrahubClientSync, vlan_pool: InfrahubNode) -> None:
        vlan = client_sync.create(kind=VLAN_KIND, name="sync", vlan_id=170)
        vlan.save()
        vlan.vlan_id.attach_to_pool(vlan_pool.id)
        vlan.save()
        pool = client_sync.get(kind="CoreNumberPool", id=vlan_pool.id)

        assert vlan.id in {a.node_id for a in pool.get_pool_allocations(resource=pool)}

        vlan.vlan_id.detach_from_pool()
        vlan.save()

        assert vlan.id not in {a.node_id for a in pool.get_pool_allocations(resource=pool)}
