from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from infrahub_sdk.exceptions import ValidationError
from infrahub_sdk.spec.object import ObjectFile, RelationshipDataFormat, get_relationship_info

if TYPE_CHECKING:
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


async def test_validate_object(client: InfrahubClient, schema_query_01_data: dict, location_mexico_01) -> None:
    client.schema.set_cache(schema=schema_query_01_data, branch="main")
    obj = ObjectFile(location="some/path", content=location_mexico_01)
    await obj.validate_format(client=client)

    assert obj.spec.kind == "BuiltinLocation"


async def test_validate_object_bad_syntax01(
    client: InfrahubClient, schema_query_01_data: dict, location_bad_syntax01
) -> None:
    client.schema.set_cache(schema=schema_query_01_data, branch="main")
    obj = ObjectFile(location="some/path", content=location_bad_syntax01)
    with pytest.raises(ValidationError) as exc:
        await obj.validate_format(client=client)

    assert "name" in str(exc.value)


async def test_validate_object_bad_syntax02(client_with_schema_01: InfrahubClient, location_bad_syntax02) -> None:
    obj = ObjectFile(location="some/path", content=location_bad_syntax02)
    with pytest.raises(ValidationError) as exc:
        await obj.validate_format(client=client_with_schema_01)

    assert "notvalidattribute" in str(exc.value)


async def test_validate_object_expansion(client_with_schema_01: InfrahubClient, location_expansion) -> None:
    obj = ObjectFile(location="some/path", content=location_expansion)
    await obj.validate_format(client=client_with_schema_01)

    assert obj.spec.kind == "BuiltinLocation"
    assert len(obj.spec.data) == 5
    assert obj.spec.data[0]["name"] == "AMS1"
    assert obj.spec.data[4]["name"] == "AMS5"


async def test_validate_no_object_expansion(client_with_schema_01: InfrahubClient, no_location_expansion) -> None:
    obj = ObjectFile(location="some/path", content=no_location_expansion)
    await obj.validate_format(client=client_with_schema_01)
    assert obj.spec.kind == "BuiltinLocation"
    assert not obj.spec.parameters.expand_range
    assert len(obj.spec.data) == 1
    assert obj.spec.data[0]["name"] == "AMS[1-5]"


async def test_validate_object_expansion_multiple_ranges(
    client_with_schema_01: InfrahubClient, location_expansion_multiple_ranges
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
    client_with_schema_01: InfrahubClient, location_expansion_multiple_ranges_bad_syntax
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


@pytest.mark.parametrize("data,is_valid,format", get_relationship_info_testdata)
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


async def test_parameters_top_level(client_with_schema_01: InfrahubClient, location_expansion) -> None:
    obj = ObjectFile(location="some/path", content=location_expansion)
    await obj.validate_format(client=client_with_schema_01)
    assert obj.spec.parameters.expand_range is True


async def test_parameters_missing(client_with_schema_01: InfrahubClient, location_mexico_01) -> None:
    obj = ObjectFile(location="some/path", content=location_mexico_01)
    await obj.validate_format(client=client_with_schema_01)
    assert hasattr(obj.spec.parameters, "expand_range")


async def test_parameters_empty_dict(client_with_schema_01: InfrahubClient, location_with_empty_parameters) -> None:
    obj = ObjectFile(location="some/path", content=location_with_empty_parameters)
    await obj.validate_format(client=client_with_schema_01)
    assert hasattr(obj.spec.parameters, "expand_range")


async def test_parameters_non_dict(client_with_schema_01: InfrahubClient, location_with_non_dict_parameters) -> None:
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
