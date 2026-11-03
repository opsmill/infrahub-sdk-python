"""Ranges declared on create, on upsert and in an object file; numbers attached, detached and their provenance."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.constants import PoolAllocationProvenance
from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.spec.object import ObjectFile
from infrahub_sdk.testing.docker import TestInfrahubDockerClient, skip_version

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.node import InfrahubNode

VLAN_KIND = "TestingPoolVlan"
REFUSAL_MESSAGE = re.escape(
    "The peers of 'ranges' cannot be edited one at a time, because the mutation takes the fields of a "
    "CoreNumberPoolRange and not a reference to one. To set them, pass the complete list of 'ranges' to "
    "client.create() and save the node with allow_upsert=True, or create, update or delete the "
    "CoreNumberPoolRange node itself."
)
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


def _object_file(kind: str, data: list[dict[str, Any]]) -> ObjectFile:
    return ObjectFile(
        location=Path("inline"),
        content={"apiVersion": "infrahub.app/v1", "kind": "Object", "spec": {"kind": kind, "data": data}},
    )


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

    async def test_the_way_out_named_by_the_refusal_adds_the_range(
        self, client: InfrahubClient, load_vlan_schema: None
    ) -> None:
        """After the refusal, saving the pool again with the complete list adds the range."""
        pool = await client.create(
            kind="CoreNumberPool",
            name="Recovered Pool",
            node=VLAN_KIND,
            node_attribute="vlan_id",
            ranges=[{"start": 2000, "end": 2099}],
        )
        await pool.save()
        fetched = await client.get(kind="CoreNumberPool", id=pool.id)
        with pytest.raises(FeatureNotSupportedError, match=REFUSAL_MESSAGE):
            fetched.ranges.add({"start": 2100, "end": 2199})

        recovered = await client.create(
            kind="CoreNumberPool",
            name="Recovered Pool",
            node=VLAN_KIND,
            node_attribute="vlan_id",
            ranges=[{"start": 2000, "end": 2099}, {"start": 2100, "end": 2199}],
        )
        await recovered.save(allow_upsert=True)

        ranges = await client.filters(kind="CoreNumberPoolRange", pool__ids=[pool.id])
        assert _bounds(ranges) == [(2000, 2099, None), (2100, 2199, None)]

    async def test_a_range_node_is_added_changed_and_deleted_on_its_own(
        self, client: InfrahubClient, load_vlan_schema: None
    ) -> None:
        """The other way out the refusal names: work with the CoreNumberPoolRange node itself."""
        pool = await client.create(
            kind="CoreNumberPool",
            name="Range Node Pool",
            node=VLAN_KIND,
            node_attribute="vlan_id",
            ranges=[{"start": 4000, "end": 4099}],
        )
        await pool.save()

        added = await client.create(kind="CoreNumberPoolRange", start=4100, end=4199, pool=pool.id)
        await added.save()

        ranges = await client.filters(kind="CoreNumberPoolRange", pool__ids=[pool.id])
        assert _bounds(ranges) == [(4000, 4099, None), (4100, 4199, None)]

        fetched = await client.get(kind="CoreNumberPoolRange", id=added.id)
        fetched.end.value = 4149
        await fetched.save()

        ranges = await client.filters(kind="CoreNumberPoolRange", pool__ids=[pool.id])
        assert _bounds(ranges) == [(4000, 4099, None), (4100, 4149, None)]

        await fetched.delete()

        ranges = await client.filters(kind="CoreNumberPoolRange", pool__ids=[pool.id])
        assert _bounds(ranges) == [(4000, 4099, None)]

    async def test_an_object_file_sets_the_ranges_of_a_new_and_of_an_existing_pool(
        self, client: InfrahubClient, load_vlan_schema: None
    ) -> None:
        """Ranges declared in an object file travel with the pool, on a new pool and on one that exists."""
        obj = _object_file(
            kind="CoreNumberPool",
            data=[
                {
                    "name": "Object File Pool",
                    "node": VLAN_KIND,
                    "node_attribute": "vlan_id",
                    "ranges": {"data": [{"start": 3000, "end": 3099}]},
                }
            ],
        )
        await obj.validate_format(client=client)

        # Once against a pool that does not exist, once against the pool the first pass created.
        await obj.process(client=client)
        await obj.process(client=client)

        pool = await client.get(kind="CoreNumberPool", name__value="Object File Pool")
        ranges = await client.filters(kind="CoreNumberPoolRange", pool__ids=[pool.id])
        assert _bounds(ranges) == [(3000, 3099, None)]

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
