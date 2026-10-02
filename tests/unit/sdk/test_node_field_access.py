"""Tests for reading node attributes and relationships whose value the SDK may not know."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

if TYPE_CHECKING:
    from collections.abc import Collection

    from infrahub_sdk.schema import MainSchemaTypesAPI, NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

LOCATION_ID = "llllllll-llll-llll-llll-llllllllllll"
PRIMARY_TAG_ID = "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr"
TAG_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def location_payload(omit: Collection[str] = ()) -> dict[str, Any]:
    """Return a GraphQL edge for ``location_schema`` carrying every field except the keys in ``omit``.

    Raises:
        ValueError: If ``omit`` names a key the payload does not carry.

    """
    node: dict[str, Any] = {
        "__typename": "BuiltinLocation",
        "id": LOCATION_ID,
        "hfid": None,
        "display_label": "dfw1",
        "name": {"value": "DFW"},
        "description": {"value": "Dallas data center"},
        "type": {"value": "SITE"},
        "primary_tag": {
            "node": {"id": PRIMARY_TAG_ID, "hfid": None, "display_label": "red", "__typename": "BuiltinTag"},
        },
        "tags": {
            "count": 1,
            "edges": [{"node": {"id": TAG_ID, "hfid": None, "display_label": "blue", "__typename": "BuiltinTag"}}],
        },
        "member_of_groups": {"count": 0, "edges": []},
    }
    # Fail loudly on a typo so a test never runs against a payload it did not mean to build.
    unknown = set(omit) - node.keys()
    if unknown:
        raise ValueError(f"Cannot omit keys that the location payload does not carry: {sorted(unknown)}")
    return {"node": {key: value for key, value in node.items() if key not in omit}}


def make_node(
    client_type: str, clients: BothClients, schema: MainSchemaTypesAPI, data: dict[str, Any] | None
) -> InfrahubNode | InfrahubNodeSync:
    if client_type == "standard":
        return InfrahubNode(client=clients.standard, schema=schema, data=data)
    return InfrahubNodeSync(client=clients.sync, schema=schema, data=data)


@pytest.mark.parametrize("client_type", client_types)
async def test_location_payload_builds_full_and_partial_nodes(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    expected_class = InfrahubNode if client_type == "standard" else InfrahubNodeSync

    full = make_node(client_type, clients, location_schema, location_payload(omit=set()))
    assert type(full) is expected_class
    assert full.id == LOCATION_ID
    assert full.name.value == "DFW"
    assert full.description.value == "Dallas data center"
    assert full.primary_tag.id == PRIMARY_TAG_ID
    assert [peer.id for peer in full.tags.peers] == [TAG_ID]

    partial_payload = location_payload(omit={"description", "primary_tag", "tags"})
    assert sorted(partial_payload["node"]) == [
        "__typename",
        "display_label",
        "hfid",
        "id",
        "member_of_groups",
        "name",
        "type",
    ]
    partial = make_node(client_type, clients, location_schema, partial_payload)
    assert type(partial) is expected_class
    assert partial.id == LOCATION_ID
    assert partial.name.value == "DFW"
    assert partial.tags.initialized is False

    with pytest.raises(ValueError, match=r"\['descripton'\]"):
        location_payload(omit={"descripton"})
