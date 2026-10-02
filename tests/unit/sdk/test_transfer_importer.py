"""Tests for how the line-delimited JSON importer sets optional relationships aside before creating nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest

from infrahub_sdk.node import InfrahubNode, RelationshipManager
from infrahub_sdk.transfer.importer.json import LineDelimitedJSONImporter
from infrahub_sdk.transfer.schema_sorter import InfrahubSchemaTopologicalSorter
from tests.unit.sdk.test_node_field_access import (
    LOCATION_ID,
    PRIMARY_TAG_ID,
    TAG_ID,
    location_payload,
    no_field_warning,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI


@dataclass
class OptionalRelationshipCase:
    name: str
    omit: frozenset[str]
    expected_peer_ids: dict[str, dict[str, list[str]]]


OPTIONAL_RELATIONSHIP_CASES = [
    OptionalRelationshipCase(
        name="default-selection",
        omit=frozenset({"tags", "member_of_groups"}),
        expected_peer_ids={LOCATION_ID: {"primary_tag": [PRIMARY_TAG_ID]}},
    ),
    OptionalRelationshipCase(
        name="default-selection-without-primary-tag",
        omit=frozenset({"tags", "member_of_groups", "primary_tag"}),
        expected_peer_ids={},
    ),
    OptionalRelationshipCase(
        name="every-relationship-fetched",
        omit=frozenset(),
        expected_peer_ids={LOCATION_ID: {"tags": [TAG_ID], "primary_tag": [PRIMARY_TAG_ID]}},
    ),
]


def stored_peer_ids(importer: LineDelimitedJSONImporter) -> dict[str, dict[str, list[str]]]:
    """Return the peer ids of each relationship the importer set aside, by node id and relationship name."""
    return {
        node_id: {
            name: value.peer_ids if isinstance(value, RelationshipManager) else [value.id]
            for name, value in relationships.items()
        }
        for node_id, relationships in importer.optional_relationships_by_node.items()
    }


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in OPTIONAL_RELATIONSHIP_CASES])
async def test_remove_and_store_optional_relationships_skips_relationships_missing_from_the_export(
    client: InfrahubClient, location_schema: NodeSchemaAPI, case: OptionalRelationshipCase
) -> None:
    node = await InfrahubNode.from_graphql(
        client=client, branch="main", data=location_payload(omit=case.omit), schema=location_schema
    )
    importer = LineDelimitedJSONImporter(client=client, topological_sorter=InfrahubSchemaTopologicalSorter())
    importer.all_nodes = {LOCATION_ID: node}
    # The importer stores the API schemas that client.schema.get returns, whatever its annotation says.
    importer.schemas_by_kind = cast("Mapping[str, NodeSchema]", {location_schema.kind: location_schema})

    with no_field_warning():
        await importer.remove_and_store_optional_relationships()

        assert stored_peer_ids(importer) == case.expected_peer_ids
