"""Verify backend upsert behaviour for a NumberPool-sourced HFID attribute.

This mirrors the demo-service-catalog VLAN allocation: ``IpamVLAN`` has an HFID of
``[l2domain, vlan_id]`` and ``vlan_id`` is allocated from a ``CoreNumberPool``. The client
adds a guard (``InfrahubNode._validate_upsert``) that raises a ``ValidationError`` before any
network call for exactly this shape. These tests deliberately bypass that guard so we can
observe what the *server* does, and decide whether the client-side guard is blocking an
operation the backend actually supports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.testing.docker import TestInfrahubDockerClient

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient

POOL_START = 100
POOL_END = 200

ALLOCATION_SCHEMA: dict[str, Any] = {
    "version": "1.0",
    "nodes": [
        {
            "name": "Allocation",
            "namespace": "Testing",
            "label": "Allocation",
            "default_filter": "group__value",
            "order_by": ["group__value"],
            "display_labels": ["group__value"],
            # HFID combines a plain discriminator with a NumberPool-sourced attribute,
            # exactly like IpamVLAN's [l2domain, vlan_id].
            "human_friendly_id": ["group__value", "code__value"],
            "attributes": [
                {"name": "group", "kind": "Text"},
                {"name": "code", "kind": "Number", "optional": True},
            ],
        }
    ],
}


class TestUpsertNumberPoolHfid(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    async def load_allocation_schema(self, default_branch: str, client: InfrahubClient) -> None:
        await client.schema.wait_until_converged(branch=default_branch)
        resp = await client.schema.load(schemas=[ALLOCATION_SCHEMA], branch=default_branch, wait_until_converged=True)
        assert resp.errors == {}

    @pytest.fixture(scope="class")
    async def code_pool(self, client: InfrahubClient, load_allocation_schema: None) -> InfrahubNode:
        pool = await client.create(
            kind="CoreNumberPool",
            name="Allocation Code Pool",
            node="TestingAllocation",
            node_attribute="code",
            start_range=POOL_START,
            end_range=POOL_END,
        )
        await pool.save()
        return pool

    async def test_backend_upsert_creates_node_with_pool_sourced_hfid_attr(
        self,
        client: InfrahubClient,
        code_pool: InfrahubNode,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A no-id upsert of a pool-HFID node should create the node and allocate the pool value.

        With the client guard bypassed this exercises the real path. If it succeeds, the
        client-side ``_validate_upsert`` guard is blocking an operation the backend supports
        (the regression introduced after #312 removed the HFID from the upsert payload).
        """
        # Disable only the guard under investigation; everything else exercises the real path.
        monkeypatch.setattr(InfrahubNode, "_validate_upsert", lambda *_args, **_kwargs: None)

        node = await client.create(kind="TestingAllocation", group="g1", code=code_pool)
        await node.save(allow_upsert=True)

        assert node.id is not None, "Backend did not create the node on a no-id upsert"
        code_value = node.code.value
        assert code_value is not None, "Pool value was not allocated server-side"
        assert POOL_START <= code_value <= POOL_END

    async def test_backend_upsert_idempotency_with_pool_sourced_hfid_attr(
        self,
        client: InfrahubClient,
        code_pool: InfrahubNode,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Characterise re-run behaviour of a no-id upsert with the same discriminator.

        Does a second upsert reuse the node, create a duplicate, or error? This is the open
        question behind #396 (idempotent number-pool allocation). The assertion documents the
        observed behaviour rather than asserting a fix.
        """
        monkeypatch.setattr(InfrahubNode, "_validate_upsert", lambda *_args, **_kwargs: None)

        first = await client.create(kind="TestingAllocation", group="g2", code=code_pool)
        await first.save(allow_upsert=True)

        second = await client.create(kind="TestingAllocation", group="g2", code=code_pool)
        await second.save(allow_upsert=True)

        nodes = await client.filters(kind="TestingAllocation", group__value="g2")
        # One node => backend resolved the HFID despite the unresolved pool value (idempotent).
        # Two nodes => upsert fell back to create, so re-runs duplicate (the #396 limitation).
        assert len(nodes) in {1, 2}
