from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from infrahub_sdk.exceptions import ObjectValidationError, ValidationError
from infrahub_sdk.node.related_node import RelatedNode
from infrahub_sdk.spec.object import (
    InfrahubObjectFileData,
    ObjectFile,
    RelationshipDataFormat,
    get_relationship_info,
    normalize_hfid_reference,
)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.client import InfrahubClient
    from infrahub_sdk.node import InfrahubNode


@pytest.fixture
def root_location() -> dict:
    return {"apiVersion": "infrahub.app/v1", "kind": "Object", "spec": {"kind": "BuiltinLocation", "data": []}}


@pytest.fixture
def location_mexico_01(root_location: dict) -> dict:
    data = [{"name": "Mexico", "type": "Country"}]

    location = root_location.copy()
    location["spec"]["data"] = data
    return location


@pytest.fixture
def location_bad_syntax01(root_location: dict) -> dict:
    data = [{"notthename": "Mexico", "type": "Country"}]
    location = root_location.copy()
    location["spec"]["data"] = data
    return location


@pytest.fixture
def location_bad_syntax02(root_location: dict) -> dict:
    data = [{"name": "Mexico", "notvalidattribute": "notvalidattribute", "type": "Country"}]
    location = root_location.copy()
    location["spec"]["data"] = data
    location["spec"]["parameters"] = {"expand_range": True}
    return location


@pytest.fixture
def location_expansion(root_location: dict) -> dict:
    data = [
        {
            "name": "AMS[1-5]",
            "type": "Country",
        }
    ]
    location = root_location.copy()
    location["spec"]["data"] = data
    location["spec"]["parameters"] = {"expand_range": True}
    return location


@pytest.fixture
def no_location_expansion(root_location: dict) -> dict:
    data = [
        {
            "name": "AMS[1-5]",
            "type": "Country",
        }
    ]
    location = root_location.copy()
    location["spec"]["data"] = data
    location["spec"]["parameters"] = {"expand_range": False}
    return location


@pytest.fixture
def location_expansion_multiple_ranges(root_location: dict) -> dict:
    data = [
        {
            "name": "AMS[1-5]",
            "type": "Country",
            "description": "Amsterdam datacenter [a,e,i,o,u]",
        }
    ]
    location = root_location.copy()
    location["spec"]["data"] = data
    location["spec"]["parameters"] = {"expand_range": True}
    return location


@pytest.fixture
def location_expansion_multiple_ranges_bad_syntax(root_location: dict) -> dict:
    data = [
        {
            "name": "AMS[1-5]",
            "type": "Country",
            "description": "Amsterdam datacenter [10-15]",
        }
    ]
    location = root_location.copy()
    location["spec"]["data"] = data
    location["spec"]["parameters"] = {"expand_range": True}
    return location


@pytest.fixture
def location_with_non_dict_parameters(root_location: dict) -> dict:
    data = [{"name": "Mexico", "type": "Country"}]
    location = root_location.copy()
    location["spec"]["data"] = data
    location["spec"]["parameters"] = "not_a_dict"
    return location


@pytest.fixture
def location_with_empty_parameters(root_location: dict) -> dict:
    data = [{"name": "Mexico", "type": "Country"}]
    location = root_location.copy()
    location["spec"]["data"] = data
    location["spec"]["parameters"] = {}
    return location


def _attr(name: str, kind: str = "Text") -> dict[str, Any]:
    return {"name": name, "kind": kind, "optional": False}


def _rel(name: str, peer: str, cardinality: str = "one", identifier: str | None = None) -> dict[str, Any]:
    rel: dict[str, Any] = {"name": name, "peer": peer, "cardinality": cardinality, "optional": True}
    if identifier:
        rel["identifier"] = identifier
    return rel


def _interface_node(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "namespace": "Testing",
        "inherit_from": ["TestingSupportsSubintf"],
        "human_friendly_id": ["device__name__value", "name__value"],
        "attributes": [_attr("name")],
        "relationships": [
            {**_rel("device", "TestingDevice"), "optional": False},
            _rel("sub_interfaces", "TestingSubInterface", "many", "supports_subintf__subinterface"),
        ],
    }


@pytest.fixture
def schema_generic_peer_data() -> dict[str, Any]:
    return {
        "main": "generic-peer",
        "generics": [
            {
                "name": "SupportsSubintf",
                "namespace": "Testing",
                "used_by": [
                    "TestingPhysicalInterface",
                    "TestingPortChannelInterface",
                    "TestingNoHfid",
                    "ProfileTestingPhysicalInterface",
                ],
                "attributes": [],
                "relationships": [
                    _rel("sub_interfaces", "TestingSubInterface", "many", "supports_subintf__subinterface")
                ],
            }
        ],
        "nodes": [
            _interface_node("PhysicalInterface"),
            _interface_node("PortChannelInterface"),
            {
                "name": "Device",
                "namespace": "Testing",
                "human_friendly_id": ["name__value"],
                "attributes": [_attr("name")],
                "relationships": [],
            },
            {
                "name": "SubInterface",
                "namespace": "Testing",
                "attributes": [_attr("name"), _attr("vlan_id", "Number")],
                "relationships": [
                    _rel("parent_interface", "TestingSupportsSubintf", identifier="supports_subintf__subinterface")
                ],
            },
            {
                "name": "Tunnel",
                "namespace": "Testing",
                "attributes": [_attr("name")],
                "relationships": [_rel("source_interfaces", "TestingSupportsSubintf", "many")],
            },
            {
                "name": "Other",
                "namespace": "Testing",
                "human_friendly_id": ["name__value"],
                "attributes": [_attr("name")],
                "relationships": [],
            },
            {
                "name": "NoHfid",
                "namespace": "Testing",
                "inherit_from": ["TestingSupportsSubintf"],
                "attributes": [_attr("name")],
                "relationships": [
                    _rel("sub_interfaces", "TestingSubInterface", "many", "supports_subintf__subinterface")
                ],
            },
        ],
        "profiles": [
            {
                "name": "TestingPhysicalInterface",
                "namespace": "Profile",
                "human_friendly_id": ["profile_name__value"],
                "attributes": [_attr("profile_name")],
                "relationships": [],
            }
        ],
    }


@pytest.fixture
def client_with_generic_peer_schema(client: InfrahubClient, schema_generic_peer_data: dict) -> InfrahubClient:
    client.schema.set_cache(schema=schema_generic_peer_data, branch="main")
    return client


async def test_validate_object(client: InfrahubClient, schema_query_01_data: dict, location_mexico_01: dict) -> None:
    client.schema.set_cache(schema=schema_query_01_data, branch="main")
    obj = ObjectFile(location="some/path", content=location_mexico_01)
    await obj.validate_format(client=client)

    assert obj.spec.kind == "BuiltinLocation"


async def test_validate_object_bad_syntax01(
    client: InfrahubClient, schema_query_01_data: dict, location_bad_syntax01: dict
) -> None:
    client.schema.set_cache(schema=schema_query_01_data, branch="main")
    obj = ObjectFile(location="some/path", content=location_bad_syntax01)
    with pytest.raises(ValidationError) as exc:
        await obj.validate_format(client=client)

    assert "name" in str(exc.value)


async def test_validate_object_bad_syntax02(client_with_schema_01: InfrahubClient, location_bad_syntax02: dict) -> None:
    obj = ObjectFile(location="some/path", content=location_bad_syntax02)
    with pytest.raises(ValidationError) as exc:
        await obj.validate_format(client=client_with_schema_01)

    assert "notvalidattribute" in str(exc.value)


async def test_validate_object_expansion(client_with_schema_01: InfrahubClient, location_expansion: dict) -> None:
    obj = ObjectFile(location="some/path", content=location_expansion)
    await obj.validate_format(client=client_with_schema_01)

    assert obj.spec.kind == "BuiltinLocation"
    assert len(obj.spec.data) == 5
    assert obj.spec.data[0]["name"] == "AMS1"
    assert obj.spec.data[4]["name"] == "AMS5"


async def test_validate_no_object_expansion(client_with_schema_01: InfrahubClient, no_location_expansion: dict) -> None:
    obj = ObjectFile(location="some/path", content=no_location_expansion)
    await obj.validate_format(client=client_with_schema_01)
    assert obj.spec.kind == "BuiltinLocation"
    assert not obj.spec.parameters.expand_range
    assert len(obj.spec.data) == 1
    assert obj.spec.data[0]["name"] == "AMS[1-5]"


async def test_validate_object_expansion_multiple_ranges(
    client_with_schema_01: InfrahubClient, location_expansion_multiple_ranges: dict
) -> None:
    obj = ObjectFile(location="some/path", content=location_expansion_multiple_ranges)
    await obj.validate_format(client=client_with_schema_01)

    assert obj.spec.kind == "BuiltinLocation"
    assert len(obj.spec.data) == 5
    assert obj.spec.data[0]["name"] == "AMS1"
    assert obj.spec.data[0]["description"] == "Amsterdam datacenter a"
    assert obj.spec.data[4]["name"] == "AMS5"
    assert obj.spec.data[4]["description"] == "Amsterdam datacenter u"


async def test_validate_object_expansion_multiple_ranges_bad_syntax(
    client_with_schema_01: InfrahubClient, location_expansion_multiple_ranges_bad_syntax: dict
) -> None:
    obj = ObjectFile(location="some/path", content=location_expansion_multiple_ranges_bad_syntax)
    with pytest.raises(ValidationError) as exc:
        await obj.validate_format(client=client_with_schema_01)

    assert "Range expansion mismatch" in str(exc.value)


get_relationship_info_testdata = [
    pytest.param(
        [
            {"data": {"name": "Blue"}},
            {"data": {"name": "Red"}},
        ],
        True,
        RelationshipDataFormat.MANY_OBJ_LIST_DICT,
        id="many_obj_list_dict",
    ),
    pytest.param(
        {
            "data": [
                {"name": "Blue"},
                {"name": "Red"},
            ],
        },
        True,
        RelationshipDataFormat.MANY_OBJ_DICT_LIST,
        id="many_obj_dict_list",
    ),
    pytest.param(
        ["blue", "red"],
        True,
        RelationshipDataFormat.MANY_REF,
        id="many_ref",
    ),
    pytest.param(
        [
            {"name": "Blue"},
            {"name": "Red"},
        ],
        False,
        RelationshipDataFormat.UNKNOWN,
        id="many_invalid_list_dict",
    ),
]


@pytest.mark.parametrize(("data", "is_valid", "format"), get_relationship_info_testdata)
async def test_get_relationship_info_tags(
    client_with_schema_01: InfrahubClient,
    data: dict | list,
    is_valid: bool,
    format: RelationshipDataFormat,
) -> None:
    location_schema = await client_with_schema_01.schema.get(kind="BuiltinLocation")

    rel_info = await get_relationship_info(client_with_schema_01, location_schema, "tags", data)
    assert rel_info.is_valid == is_valid
    assert rel_info.format == format


async def test_get_relationship_info_generic_peer_without_hfid(client_with_generic_peer_schema: InfrahubClient) -> None:
    schema = await client_with_generic_peer_schema.schema.get(kind="TestingSubInterface")

    rel_info = await get_relationship_info(
        client_with_generic_peer_schema, schema, "parent_interface", ["router1", "Gi0/0/3"]
    )
    assert rel_info.format == RelationshipDataFormat.ONE_REF
    assert rel_info.peer_has_hfid is False
    assert rel_info.peer_is_generic_without_hfid is True
    assert rel_info.peer_used_by == [
        "TestingPhysicalInterface",
        "TestingPortChannelInterface",
        "TestingNoHfid",
        "ProfileTestingPhysicalInterface",
    ]


@dataclass
class KindHfidReferenceCase:
    name: str
    kind: str
    relationship: str
    data: dict | list
    format: RelationshipDataFormat


KIND_HFID_REFERENCE_CASES = [
    KindHfidReferenceCase(
        name="one_kind_hfid",
        kind="TestingSubInterface",
        relationship="parent_interface",
        data={"kind": "TestingPhysicalInterface", "hfid": ["router1", "Gi0/0/3"]},
        format=RelationshipDataFormat.ONE_REF,
    ),
    KindHfidReferenceCase(
        name="many_kind_hfid",
        kind="TestingTunnel",
        relationship="source_interfaces",
        data=[
            {"kind": "TestingPhysicalInterface", "hfid": ["router1", "Gi0/0/3"]},
            {"kind": "TestingPortChannelInterface", "hfid": ["router1", "Po1"]},
        ],
        format=RelationshipDataFormat.MANY_REF,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in KIND_HFID_REFERENCE_CASES])
async def test_get_relationship_info_kind_hfid_reference(
    client_with_generic_peer_schema: InfrahubClient, case: KindHfidReferenceCase
) -> None:
    schema = await client_with_generic_peer_schema.schema.get(kind=case.kind)

    rel_info = await get_relationship_info(client_with_generic_peer_schema, schema, case.relationship, case.data)
    assert rel_info.is_valid
    assert rel_info.format == case.format
    assert rel_info.peer_is_generic_without_hfid is True


@dataclass
class NestedObjectKindCase:
    name: str
    nested_kind: str


NESTED_OBJECT_KIND_CASES = [
    NestedObjectKindCase(name="kind_in_used_by", nested_kind="TestingPhysicalInterface"),
    NestedObjectKindCase(name="kind_outside_used_by", nested_kind="TestingOther"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in NESTED_OBJECT_KIND_CASES])
async def test_get_relationship_info_nested_object_uses_named_kind_schema(
    client_with_generic_peer_schema: InfrahubClient, case: NestedObjectKindCase
) -> None:
    schema = await client_with_generic_peer_schema.schema.get(kind="TestingSubInterface")
    named_schema = await client_with_generic_peer_schema.schema.get(kind=case.nested_kind)

    rel_info = await get_relationship_info(
        client_with_generic_peer_schema,
        schema,
        "parent_interface",
        {"kind": case.nested_kind, "data": {"name": "Gi0/0/9"}},
    )
    assert rel_info.format == RelationshipDataFormat.ONE_OBJ
    assert rel_info.peer_kind == case.nested_kind
    assert rel_info.peer_human_friendly_id == named_schema.human_friendly_id


@dataclass
class InvalidKindHfidCase:
    name: str
    kind: str
    item: dict[str, Any]
    expected: str


PHYSICAL_GI003 = {"kind": "TestingPhysicalInterface", "hfid": ["router1", "Gi0/0/3"]}

INVALID_KIND_HFID_CASES = [
    InvalidKindHfidCase(
        name="kind_not_inheriting",
        kind="TestingSubInterface",
        item={"vlan_id": 10, "parent_interface": {"kind": "TestingOther", "hfid": ["Gi0/0/3"]}},
        expected="1.parent_interface: TestingOther is not TestingSupportsSubintf and does not inherit from it",
    ),
    InvalidKindHfidCase(
        name="kind_unknown",
        kind="TestingSubInterface",
        item={"vlan_id": 10, "parent_interface": {"kind": "TestingMissing", "hfid": ["Gi0/0/3"]}},
        expected="1.parent_interface: TestingMissing is not TestingSupportsSubintf and does not inherit from it",
    ),
    InvalidKindHfidCase(
        name="kind_without_hfid",
        kind="TestingSubInterface",
        item={"vlan_id": 10, "parent_interface": {"kind": "TestingNoHfid", "hfid": ["Gi0/0/3"]}},
        expected="1.parent_interface: TestingNoHfid has no human_friendly_id",
    ),
    InvalidKindHfidCase(
        name="wrong_hfid_length",
        kind="TestingSubInterface",
        item={"vlan_id": 10, "parent_interface": {"kind": "TestingPhysicalInterface", "hfid": ["Gi0/0/3"]}},
        expected="1.parent_interface: expected 2 values for TestingPhysicalInterface",
    ),
    InvalidKindHfidCase(
        name="extra_key",
        kind="TestingSubInterface",
        item={"vlan_id": 10, "parent_interface": {**PHYSICAL_GI003, "id": "abc"}},
        expected="1.parent_interface: only `kind` and `hfid` are allowed",
    ),
    InvalidKindHfidCase(
        name="missing_kind",
        kind="TestingSubInterface",
        item={"vlan_id": 10, "parent_interface": {"hfid": ["router1", "Gi0/0/3"]}},
        expected="1.parent_interface: only `kind` and `hfid` are allowed in a peer reference, and both are required, got hfid",
    ),
    InvalidKindHfidCase(
        name="missing_hfid",
        kind="TestingSubInterface",
        item={"vlan_id": 10, "parent_interface": {"kind": "TestingPhysicalInterface"}},
        expected="1.parent_interface: only `kind` and `hfid` are allowed in a peer reference, and both are required, got kind",
    ),
    InvalidKindHfidCase(
        name="many_ref_item",
        kind="TestingTunnel",
        item={"source_interfaces": [PHYSICAL_GI003, {"kind": "TestingOther", "hfid": ["Gi0/0/3"]}]},
        expected="1.source_interfaces.2: TestingOther is not TestingSupportsSubintf",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in INVALID_KIND_HFID_CASES])
async def test_validate_format_invalid_kind_hfid_reference(
    client_with_generic_peer_schema: InfrahubClient, case: InvalidKindHfidCase
) -> None:
    content = {
        "apiVersion": "infrahub.app/v1",
        "kind": "Object",
        "spec": {"kind": case.kind, "data": [{"name": "Gi0/0/3.10", **case.item}]},
    }
    obj = ObjectFile(location="some/path", content=content)

    with pytest.raises(ValidationError, match=re.escape(case.expected)):
        await obj.validate_format(client=client_with_generic_peer_schema)


async def test_validate_format_valid_kind_hfid_reference(client_with_generic_peer_schema: InfrahubClient) -> None:
    content = {
        "apiVersion": "infrahub.app/v1",
        "kind": "Object",
        "spec": {
            "kind": "TestingTunnel",
            "data": [{"name": "t1", "source_interfaces": [PHYSICAL_GI003, ["router1", "Po1"]]}],
        },
    }
    await ObjectFile(location="some/path", content=content).validate_format(client=client_with_generic_peer_schema)


async def test_parameters_top_level(client_with_schema_01: InfrahubClient, location_expansion: dict) -> None:
    obj = ObjectFile(location="some/path", content=location_expansion)
    await obj.validate_format(client=client_with_schema_01)
    assert obj.spec.parameters.expand_range is True


async def test_parameters_missing(client_with_schema_01: InfrahubClient, location_mexico_01: dict) -> None:
    obj = ObjectFile(location="some/path", content=location_mexico_01)
    await obj.validate_format(client=client_with_schema_01)
    assert hasattr(obj.spec.parameters, "expand_range")


async def test_parameters_empty_dict(
    client_with_schema_01: InfrahubClient, location_with_empty_parameters: dict
) -> None:
    obj = ObjectFile(location="some/path", content=location_with_empty_parameters)
    await obj.validate_format(client=client_with_schema_01)
    assert hasattr(obj.spec.parameters, "expand_range")


async def test_parameters_non_dict(
    client_with_schema_01: InfrahubClient, location_with_non_dict_parameters: dict
) -> None:
    obj = ObjectFile(location="some/path", content=location_with_non_dict_parameters)
    with pytest.raises(ValidationError):
        await obj.validate_format(client=client_with_schema_01)


@dataclass
class HfidLoadTestCase:
    """Test case for HFID normalization in object loading."""

    name: str
    data: list[dict[str, Any]]
    expected_primary_tag: str | list[str] | None
    expected_tags: list[str] | list[list[str]] | None


HFID_NORMALIZATION_TEST_CASES = [
    HfidLoadTestCase(
        name="cardinality_one_string_hfid_normalized",
        data=[{"name": "Mexico", "type": "Country", "primary_tag": "Important"}],
        expected_primary_tag=["Important"],
        expected_tags=None,
    ),
    HfidLoadTestCase(
        name="cardinality_one_list_hfid_unchanged",
        data=[{"name": "Mexico", "type": "Country", "primary_tag": ["Important"]}],
        expected_primary_tag=["Important"],
        expected_tags=None,
    ),
    HfidLoadTestCase(
        name="cardinality_one_uuid_unchanged",
        data=[{"name": "Mexico", "type": "Country", "primary_tag": "550e8400-e29b-41d4-a716-446655440000"}],
        expected_primary_tag="550e8400-e29b-41d4-a716-446655440000",
        expected_tags=None,
    ),
    HfidLoadTestCase(
        name="cardinality_many_string_hfids_normalized",
        data=[{"name": "Mexico", "type": "Country", "tags": ["Important", "Active"]}],
        expected_primary_tag=None,
        expected_tags=[["Important"], ["Active"]],
    ),
    HfidLoadTestCase(
        name="cardinality_many_list_hfids_unchanged",
        data=[{"name": "Mexico", "type": "Country", "tags": [["Important"], ["Active"]]}],
        expected_primary_tag=None,
        expected_tags=[["Important"], ["Active"]],
    ),
    HfidLoadTestCase(
        name="cardinality_many_mixed_hfids_normalized",
        data=[{"name": "Mexico", "type": "Country", "tags": ["Important", ["namespace", "name"]]}],
        expected_primary_tag=None,
        expected_tags=[["Important"], ["namespace", "name"]],
    ),
    HfidLoadTestCase(
        name="cardinality_many_uuids_unchanged",
        data=[
            {
                "name": "Mexico",
                "type": "Country",
                "tags": ["550e8400-e29b-41d4-a716-446655440000", "6ba7b810-9dad-11d1-80b4-00c04fd430c8"],
            }
        ],
        expected_primary_tag=None,
        expected_tags=["550e8400-e29b-41d4-a716-446655440000", "6ba7b810-9dad-11d1-80b4-00c04fd430c8"],
    ),
]


@pytest.mark.parametrize("test_case", HFID_NORMALIZATION_TEST_CASES, ids=lambda tc: tc.name)
async def test_hfid_normalization_in_object_loading(
    client_with_schema_01: InfrahubClient, test_case: HfidLoadTestCase
) -> None:
    """Test that HFIDs are normalized correctly based on cardinality and format."""
    root_location = {"apiVersion": "infrahub.app/v1", "kind": "Object", "spec": {"kind": "BuiltinLocation", "data": []}}
    location = {
        "apiVersion": root_location["apiVersion"],
        "kind": root_location["kind"],
        "spec": {"kind": root_location["spec"]["kind"], "data": test_case.data},
    }

    obj = ObjectFile(location="some/path", content=location)
    await obj.validate_format(client=client_with_schema_01)

    create_calls: list[dict[str, Any]] = []

    async def mock_create(
        kind: str,
        branch: str | None = None,
        data: dict | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> InfrahubNode:
        create_calls.append({"kind": kind, "data": data})
        original_create = client_with_schema_01.__class__.create
        return await original_create(client_with_schema_01, kind=kind, branch=branch, data=data, **kwargs)

    client_with_schema_01.create = mock_create

    with patch("infrahub_sdk.node.InfrahubNode.save", new_callable=AsyncMock):
        await obj.process(client=client_with_schema_01)

    assert len(create_calls) == 1
    if test_case.expected_primary_tag is not None:
        assert create_calls[0]["data"]["primary_tag"] == test_case.expected_primary_tag
    if test_case.expected_tags is not None:
        assert create_calls[0]["data"]["tags"] == test_case.expected_tags


@dataclass
class KindHfidLoadCase:
    name: str
    kind: str
    data: dict[str, Any]
    relationship: str
    expected: dict[str, Any] | list[dict[str, Any]]


KIND_HFID_LOAD_CASES = [
    KindHfidLoadCase(
        name="one_physical_interface",
        kind="TestingSubInterface",
        data={
            "name": "Gi0/0/3.100",
            "vlan_id": 100,
            "parent_interface": {"kind": "TestingPhysicalInterface", "hfid": ["router1", "Gi0/0/3"]},
        },
        relationship="parent_interface",
        expected={"hfid": ["router1", "Gi0/0/3"], "kind": "TestingPhysicalInterface"},
    ),
    KindHfidLoadCase(
        name="one_port_channel_interface",
        kind="TestingSubInterface",
        data={
            "name": "Po1.100",
            "vlan_id": 100,
            "parent_interface": {"kind": "TestingPortChannelInterface", "hfid": ["router1", "Po1"]},
        },
        relationship="parent_interface",
        expected={"hfid": ["router1", "Po1"], "kind": "TestingPortChannelInterface"},
    ),
    KindHfidLoadCase(
        name="many_mixed_kinds",
        kind="TestingTunnel",
        data={
            "name": "tunnel1",
            "source_interfaces": [
                {"kind": "TestingPhysicalInterface", "hfid": ["router1", "Gi0/0/3"]},
                {"kind": "TestingPortChannelInterface", "hfid": ["router1", "Po1"]},
            ],
        },
        relationship="source_interfaces",
        expected=[
            {"hfid": ["router1", "Gi0/0/3"], "kind": "TestingPhysicalInterface"},
            {"hfid": ["router1", "Po1"], "kind": "TestingPortChannelInterface"},
        ],
    ),
    KindHfidLoadCase(
        name="one_string_hfid_becomes_list",
        kind="TestingPhysicalInterface",
        data={"name": "Gi0/0/3", "device": {"kind": "TestingDevice", "hfid": "router1"}},
        relationship="device",
        expected={"hfid": ["router1"], "kind": "TestingDevice"},
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in KIND_HFID_LOAD_CASES])
async def test_kind_hfid_reference_in_object_loading(
    client_with_generic_peer_schema: InfrahubClient, case: KindHfidLoadCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_with_generic_peer_schema
    content = {"apiVersion": "infrahub.app/v1", "kind": "Object", "spec": {"kind": case.kind, "data": [case.data]}}
    obj = ObjectFile(location="some/path", content=content)
    await obj.validate_format(client=client)

    create_calls: list[dict[str, Any]] = []
    original_create = client.create

    async def capture_create(kind: str, data: dict | None = None, **kwargs: Any) -> InfrahubNode:  # noqa: ANN401
        create_calls.append({"kind": kind, "data": data})
        return await original_create(kind=kind, data=data, **kwargs)

    async def skip_save(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        return None

    monkeypatch.setattr(client, "create", capture_create)
    monkeypatch.setattr("infrahub_sdk.node.InfrahubNode.save", skip_save)

    await obj.process(client=client)

    assert len(create_calls) == 1
    assert create_calls[0]["data"][case.relationship] == case.expected


def _mock_hfid_lookup(
    client: InfrahubClient, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock, matching_kinds: set[str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Answer GraphQL lookups with a node only for ``matching_kinds``, and capture ``client.create`` calls."""
    queried_kinds: list[str] = []
    create_calls: list[dict[str, Any]] = []
    original_create = client.create

    def lookup(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        kind = payload["operationName"].removeprefix("Get_")
        queried_kinds.append(kind)
        assert "hfid: " in payload["query"]
        edges = [{"node": {"id": f"{kind}-id", "__typename": kind}}] if kind in matching_kinds else []
        return httpx.Response(200, json={"data": {kind: {"count": len(edges), "edges": edges}}})

    async def capture_create(kind: str, data: dict | None = None, **kwargs: Any) -> InfrahubNode:  # noqa: ANN401
        create_calls.append({"kind": kind, "data": data})
        return await original_create(kind=kind, data=data, **kwargs)

    async def skip_save(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        return None

    httpx_mock.add_callback(
        lookup, method="POST", url=re.compile(r".*/graphql/main"), is_optional=True, is_reusable=True
    )
    monkeypatch.setattr(client, "create", capture_create)
    monkeypatch.setattr("infrahub_sdk.node.InfrahubNode.save", skip_save)
    return queried_kinds, create_calls


def _sub_interface_file(parent_interface: Any) -> ObjectFile:  # noqa: ANN401
    data = {"name": "Gi0/0/3.20", "vlan_id": 20, "parent_interface": parent_interface}
    content = {
        "apiVersion": "infrahub.app/v1",
        "kind": "Object",
        "spec": {"kind": "TestingSubInterface", "data": [data]},
    }
    return ObjectFile(location="some/path", content=content)


async def test_hfid_only_reference_to_generic_peer_resolves_single_match(
    client_with_generic_peer_schema: InfrahubClient, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    client = client_with_generic_peer_schema
    obj = _sub_interface_file(["router2", "Gi0/0/3"])
    await obj.validate_format(client=client)
    queried_kinds, create_calls = _mock_hfid_lookup(
        client, monkeypatch, httpx_mock, matching_kinds={"TestingPhysicalInterface"}
    )

    await obj.process(client=client)

    assert create_calls[0]["data"]["parent_interface"] == {"id": "TestingPhysicalInterface-id"}
    assert queried_kinds == ["TestingPhysicalInterface", "TestingPortChannelInterface"]


async def test_hfid_only_reference_to_generic_peer_ambiguous(
    client_with_generic_peer_schema: InfrahubClient, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    client = client_with_generic_peer_schema
    obj = _sub_interface_file(["router2", "Gi0/0/3"])
    await obj.validate_format(client=client)
    _mock_hfid_lookup(
        client, monkeypatch, httpx_mock, matching_kinds={"TestingPhysicalInterface", "TestingPortChannelInterface"}
    )

    with pytest.raises(ObjectValidationError, match="parent_interface") as exc:
        await obj.process(client=client)

    for expected in ("TestingPhysicalInterface", "TestingPortChannelInterface", "kind:"):
        assert expected in str(exc.value)


@dataclass
class HfidOnlyNoMatchCase:
    name: str
    parent_interface: str | list[str]
    expected_get_calls: int
    expected_message: str


HFID_ONLY_NO_MATCH_CASES = [
    HfidOnlyNoMatchCase(
        name="two_parts",
        parent_interface=["router9", "Gi0/0/3"],
        expected_get_calls=2,
        expected_message="['router9', 'Gi0/0/3'] among TestingPhysicalInterface, TestingPortChannelInterface",
    ),
    HfidOnlyNoMatchCase(
        name="one_part_no_candidate",
        parent_interface="router9",
        expected_get_calls=0,
        expected_message="no kind that inherits from it has an HFID with 1 values",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in HFID_ONLY_NO_MATCH_CASES])
async def test_hfid_only_reference_to_generic_peer_no_match(
    client_with_generic_peer_schema: InfrahubClient,
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
    case: HfidOnlyNoMatchCase,
) -> None:
    """The profile kind in the generic's used_by has a 1-part HFID, but is never queried."""
    client = client_with_generic_peer_schema
    obj = _sub_interface_file(case.parent_interface)
    await obj.validate_format(client=client)
    queried_kinds, _ = _mock_hfid_lookup(client, monkeypatch, httpx_mock, matching_kinds=set())

    with pytest.raises(ObjectValidationError, match="no TestingSupportsSubintf with HFID") as exc:
        await obj.process(client=client)

    assert case.expected_message in str(exc.value)
    assert len(queried_kinds) == case.expected_get_calls


async def test_hfid_only_reference_error_names_list_item(
    client_with_generic_peer_schema: InfrahubClient, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    client = client_with_generic_peer_schema
    data = {
        "name": "tun1",
        "source_interfaces": [{"kind": "TestingPhysicalInterface", "hfid": ["r1", "Gi1"]}, ["router9", "Gi0/0/3"]],
    }
    content = {"apiVersion": "infrahub.app/v1", "kind": "Object", "spec": {"kind": "TestingTunnel", "data": [data]}}
    obj = ObjectFile(location="some/path", content=content)
    await obj.validate_format(client=client)
    _mock_hfid_lookup(client, monkeypatch, httpx_mock, matching_kinds=set())

    with pytest.raises(ObjectValidationError) as exc:
        await obj.process(client=client)

    assert exc.value.position == [1, "source_interfaces", 2]


async def test_string_reference_to_generic_peer_with_default_filter_is_sent_as_id(
    client: InfrahubClient, schema_generic_peer_data: dict, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    schema_generic_peer_data["generics"][0]["default_filter"] = "name__value"
    client.schema.set_cache(schema=schema_generic_peer_data, branch="main")
    obj = _sub_interface_file("Gi0/0/3")
    await obj.validate_format(client=client)
    queried_kinds, create_calls = _mock_hfid_lookup(client, monkeypatch, httpx_mock, matching_kinds=set())

    await obj.process(client=client)

    assert create_calls[0]["data"]["parent_interface"] == "Gi0/0/3"
    assert queried_kinds == []


async def test_nested_object_without_data_key_error_mentions_data(
    client_with_generic_peer_schema: InfrahubClient,
) -> None:
    parent = {"kind": "TestingPhysicalInterface", "name": "Gi0/0/3", "device": "router1"}
    obj = _sub_interface_file(parent)

    with pytest.raises(ValidationError, match="under `data:`"):
        await obj.validate_format(client=client_with_generic_peer_schema)


def test_normalize_hfid_reference_function() -> None:
    """Test the normalize_hfid_reference function directly.

    This tests the normalization logic in isolation:
    - Non-UUID strings get wrapped in a list (for HFID lookup)
    - UUID strings stay as strings (for ID lookup)
    - Lists stay unchanged
    """
    # Non-UUID string becomes list
    assert normalize_hfid_reference("Important") == ["Important"]

    # UUID string stays as string
    uuid_value = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_hfid_reference(uuid_value) == uuid_value

    # List stays unchanged
    assert normalize_hfid_reference(["namespace", "name"]) == ["namespace", "name"]
    assert normalize_hfid_reference(["single"]) == ["single"]


@dataclass
class RelatedNodePayloadTestCase:
    """Test case for verifying the actual GraphQL payload structure from RelatedNode."""

    name: str
    input_data: str | list[str] | dict[str, Any]
    expected_payload: dict[str, Any]


RELATED_NODE_PAYLOAD_TEST_CASES = [
    # String (UUID) → {"id": "uuid"}
    RelatedNodePayloadTestCase(
        name="uuid_string_becomes_id_payload",
        input_data="550e8400-e29b-41d4-a716-446655440000",
        expected_payload={"id": "550e8400-e29b-41d4-a716-446655440000"},
    ),
    # List (HFID) → {"hfid": [...]}
    RelatedNodePayloadTestCase(
        name="list_becomes_hfid_payload",
        input_data=["Important"],
        expected_payload={"hfid": ["Important"]},
    ),
    # Multi-component HFID list → {"hfid": [...]}
    RelatedNodePayloadTestCase(
        name="multi_component_hfid_payload",
        input_data=["namespace", "name"],
        expected_payload={"hfid": ["namespace", "name"]},
    ),
    RelatedNodePayloadTestCase(
        name="kind_hfid_dict_payload",
        input_data={"hfid": ["router1", "Gi0/0/3"], "kind": "TestingPhysicalInterface"},
        expected_payload={"hfid": ["router1", "Gi0/0/3"], "kind": "TestingPhysicalInterface"},
    ),
]


@pytest.mark.parametrize("test_case", RELATED_NODE_PAYLOAD_TEST_CASES, ids=lambda tc: tc.name)
def test_related_node_graphql_payload(test_case: RelatedNodePayloadTestCase) -> None:
    """Test that RelatedNode produces the correct GraphQL payload structure.

    This test verifies the actual {"id": ...} or {"hfid": ...} payload
    that gets sent in GraphQL mutations.
    """
    # Create mock dependencies
    mock_client = MagicMock()
    mock_schema = MagicMock()

    # Create RelatedNode with the input data
    related_node = RelatedNode(
        schema=mock_schema,
        name="test_rel",
        branch="main",
        client=mock_client,
        data=test_case.input_data,
    )

    # Generate the input data that would go into GraphQL mutation
    payload = related_node._generate_input_data()

    # Verify the payload structure
    assert payload == test_case.expected_payload, f"Expected payload {test_case.expected_payload}, got {payload}"


async def test_validate_object_skips_mandatory_check_with_object_template(
    client_with_schema_01: InfrahubClient,
) -> None:
    """When object_template is present, mandatory field validation should be skipped."""
    schema = await client_with_schema_01.schema.get(kind="BuiltinLocation")

    data = {"name": "Site1", "object_template": "Standard Site"}
    errors = await InfrahubObjectFileData.validate_object(
        client=client_with_schema_01, position=[1], schema=schema, data=data
    )

    mandatory_errors = [e for e in errors if e.message == "type is mandatory"]
    assert mandatory_errors == []


async def test_validate_object_skips_mandatory_check_with_object_profile(
    client_with_schema_01: InfrahubClient,
) -> None:
    """When object_profile is present, mandatory field validation should be skipped."""
    schema = await client_with_schema_01.schema.get(kind="BuiltinLocation")

    data = {"name": "Site1", "object_profile": "Standard Site"}
    errors = await InfrahubObjectFileData.validate_object(
        client=client_with_schema_01, position=[1], schema=schema, data=data
    )

    mandatory_errors = [e for e in errors if e.message == "type is mandatory"]
    assert mandatory_errors == []
