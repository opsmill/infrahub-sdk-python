from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.exceptions import ValidationError
from infrahub_sdk.spec.object import ObjectFile, RelationshipDataFormat, get_relationship_info

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.client import InfrahubClient


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
    return location


async def test_validate_object(client: InfrahubClient, mock_schema_query_01: HTTPXMock, location_mexico_01):
    obj = ObjectFile(location="some/path", content=location_mexico_01)
    await obj.validate_format(client=client)

    assert obj.spec.kind == "BuiltinLocation"


async def test_validate_object_bad_syntax01(
    client: InfrahubClient, mock_schema_query_01: HTTPXMock, location_bad_syntax01
):
    obj = ObjectFile(location="some/path", content=location_bad_syntax01)
    with pytest.raises(ValidationError) as exc:
        await obj.validate_format(client=client)

    assert "name" in str(exc.value)


async def test_validate_object_bad_syntax02(
    client: InfrahubClient, mock_schema_query_01: HTTPXMock, location_bad_syntax02
):
    obj = ObjectFile(location="some/path", content=location_bad_syntax02)
    with pytest.raises(ValidationError) as exc:
        await obj.validate_format(client=client)

    assert "notvalidattribute" in str(exc.value)


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
    client: InfrahubClient,
    mock_schema_query_01: HTTPXMock,
    data: dict | list,
    is_valid: bool,
    format: RelationshipDataFormat,
):
    location_schema = await client.schema.get(kind="BuiltinLocation")

    rel_info = await get_relationship_info(client, location_schema, "tags", data)
    assert rel_info.is_valid == is_valid
    assert rel_info.format == format
