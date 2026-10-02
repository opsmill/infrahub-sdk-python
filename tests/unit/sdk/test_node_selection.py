"""Tests for the fields a node query selects, including exclusive selection with ``only``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.schema import GenericSchemaAPI, NodeSchemaAPI

if TYPE_CHECKING:
    from infrahub_sdk.schema import MainSchemaTypesAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

GENERIC_DEVICE_ATTRIBUTES: list[dict[str, Any]] = [
    {"name": "name", "kind": "Text", "unique": True},
    {"name": "description", "kind": "Text", "optional": True},
]
GENERIC_DEVICE_RELATIONSHIPS: list[dict[str, Any]] = [
    {"name": "tags", "peer": "BuiltinTag", "kind": "Generic", "cardinality": "many", "optional": True},
]


def _implementing_device_schema(name: str, extra_attribute: dict[str, Any]) -> NodeSchemaAPI:
    # The server repeats inherited fields on each implementing kind, flagged with ``inherited``.
    return NodeSchemaAPI(
        namespace="Test",
        name=name,
        default_filter="name__value",
        inherit_from=["TestGenericDevice"],
        attributes=[{**attr, "inherited": True} for attr in GENERIC_DEVICE_ATTRIBUTES] + [extra_attribute],
        relationships=[{**rel, "inherited": True} for rel in GENERIC_DEVICE_RELATIONSHIPS],
    )


@pytest.fixture
async def generic_device_schema() -> GenericSchemaAPI:
    return GenericSchemaAPI(
        namespace="Test",
        name="GenericDevice",
        default_filter="name__value",
        attributes=GENERIC_DEVICE_ATTRIBUTES,
        relationships=GENERIC_DEVICE_RELATIONSHIPS,
        used_by=["TestRouter", "TestSwitch"],
    )


@pytest.fixture
async def router_schema() -> NodeSchemaAPI:
    return _implementing_device_schema("Router", {"name": "role", "kind": "Text", "optional": True})


@pytest.fixture
async def switch_schema() -> NodeSchemaAPI:
    return _implementing_device_schema("Switch", {"name": "ports", "kind": "Number", "optional": True})


@pytest.fixture
async def generic_family_clients(
    clients: BothClients,
    generic_device_schema: GenericSchemaAPI,
    router_schema: NodeSchemaAPI,
    switch_schema: NodeSchemaAPI,
    tag_schema: NodeSchemaAPI,
    location_schema: NodeSchemaAPI,
) -> BothClients:
    cache_data = {
        "version": "1.0",
        "generics": [generic_device_schema.model_dump()],
        "nodes": [
            router_schema.model_dump(),
            switch_schema.model_dump(),
            tag_schema.model_dump(),
            location_schema.model_dump(),
        ],
    }
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)
    return clients


@pytest.mark.parametrize("client_type", client_types)
async def test_generic_family_resolves_from_schema_cache(generic_family_clients: BothClients, client_type: str) -> None:
    kinds = ["TestGenericDevice", "TestRouter", "TestSwitch", "BuiltinTag", "BuiltinLocation"]
    schemas: dict[str, MainSchemaTypesAPI]
    if client_type == "standard":
        schemas = {kind: await generic_family_clients.standard.schema.get(kind=kind) for kind in kinds}
    else:
        schemas = {kind: generic_family_clients.sync.schema.get(kind=kind) for kind in kinds}

    generic = schemas["TestGenericDevice"]
    assert isinstance(generic, GenericSchemaAPI)
    assert generic.used_by == ["TestRouter", "TestSwitch"]
    assert generic.attribute_names == ["name", "description"]
    assert generic.relationship_names == ["tags"]
    assert generic.get_relationship(name="tags").kind == "Generic"

    for kind, own_attribute in (("TestRouter", "role"), ("TestSwitch", "ports")):
        implementing = schemas[kind]
        assert isinstance(implementing, NodeSchemaAPI)
        assert implementing.inherit_from == ["TestGenericDevice"]
        assert implementing.attribute_names == ["name", "description", own_attribute]
        assert [attr.name for attr in implementing.attributes if not attr.inherited] == [own_attribute]
        assert implementing.relationship_names == ["tags"]

    assert isinstance(schemas["BuiltinTag"], NodeSchemaAPI)
    assert isinstance(schemas["BuiltinLocation"], NodeSchemaAPI)
    assert schemas["BuiltinLocation"].relationship_names == ["tags", "primary_tag", "member_of_groups"]
