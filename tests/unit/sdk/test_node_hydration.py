"""Tests for hydrating relationship peers with a chosen set of fields."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.schema import (
    GenericSchemaAPI,
    NodeSchemaAPI,
    RelationshipCardinality,
    RelationshipKind,
    RelationshipSchemaAPI,
)

if TYPE_CHECKING:
    from infrahub_sdk.schema import MainSchemaTypesAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.fixture
async def core_node_schema() -> GenericSchemaAPI:
    return GenericSchemaAPI(namespace="Core", name="Node", used_by=["TestDevice", "TestCable"])


@pytest.fixture
async def group_with_members_schema(std_group_schema: NodeSchemaAPI) -> NodeSchemaAPI:
    members = RelationshipSchemaAPI(
        name="members",
        peer="CoreNode",
        kind=RelationshipKind.GENERIC,
        cardinality=RelationshipCardinality.MANY,
        optional=True,
        identifier="group_member",
    )
    return std_group_schema.model_copy(update={"relationships": [*std_group_schema.relationships, members]})


@pytest.fixture
async def named_member_schema() -> NodeSchemaAPI:
    return NodeSchemaAPI(
        namespace="Test",
        name="Device",
        default_filter="name__value",
        inherit_from=["CoreNode"],
        attributes=[
            {"name": "name", "kind": "Text", "unique": True},
            {"name": "description", "kind": "Text", "optional": True},
        ],
    )


@pytest.fixture
async def nameless_member_schema() -> NodeSchemaAPI:
    return NodeSchemaAPI(
        namespace="Test",
        name="Cable",
        default_filter="serial__value",
        inherit_from=["CoreNode"],
        attributes=[{"name": "serial", "kind": "Text", "unique": True}],
    )


@pytest.fixture
async def hydration_clients(
    clients: BothClients,
    core_node_schema: GenericSchemaAPI,
    group_with_members_schema: NodeSchemaAPI,
    named_member_schema: NodeSchemaAPI,
    nameless_member_schema: NodeSchemaAPI,
) -> BothClients:
    cache_data = {
        "version": "1.0",
        "generics": [core_node_schema.model_dump()],
        "nodes": [
            group_with_members_schema.model_dump(),
            named_member_schema.model_dump(),
            nameless_member_schema.model_dump(),
        ],
    }
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)
    return clients


@pytest.mark.parametrize("client_type", client_types)
async def test_group_members_resolve_from_schema_cache(hydration_clients: BothClients, client_type: str) -> None:
    kinds = ["CoreStandardGroup", "CoreNode", "TestDevice", "TestCable"]
    schemas: dict[str, MainSchemaTypesAPI]
    if client_type == "standard":
        schemas = {kind: await hydration_clients.standard.schema.get(kind=kind) for kind in kinds}
    else:
        schemas = {kind: hydration_clients.sync.schema.get(kind=kind) for kind in kinds}

    group = schemas["CoreStandardGroup"]
    assert isinstance(group, NodeSchemaAPI)
    assert group.attribute_names == ["name", "description"]
    members = group.get_relationship(name="members")
    assert (members.peer, members.kind, members.cardinality) == ("CoreNode", "Generic", "many")

    core_node = schemas["CoreNode"]
    assert isinstance(core_node, GenericSchemaAPI)
    assert core_node.used_by == ["TestDevice", "TestCable"]

    for kind, attribute_names in (("TestDevice", ["name", "description"]), ("TestCable", ["serial"])):
        member = schemas[kind]
        assert isinstance(member, NodeSchemaAPI)
        assert member.inherit_from == ["CoreNode"]
        assert member.attribute_names == attribute_names
