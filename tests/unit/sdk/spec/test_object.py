from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrahub_sdk.exceptions import ValidationError
from infrahub_sdk.node.related_node import RelatedNode
from infrahub_sdk.schema import GenericSchema, NodeSchema, SchemaRootAPI
from infrahub_sdk.spec.object import (
    InfrahubObjectFileData,
    ObjectFile,
    RelationshipDataFormat,
    get_relationship_info,
    normalize_hfid_reference,
    normalize_hfid_reference_mapping,
)

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
    input_data: str | list[str]
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


@pytest.fixture
async def client_with_generic_peer_schema(client: InfrahubClient) -> InfrahubClient:
    """Schema where a relationship points at a generic that has no HFID, while its nodes do."""
    owner_rel = {"name": "owner", "peer": "TestingPerson", "cardinality": "one", "identifier": "person__animal"}
    animal_data: dict[str, Any] = {
        "name": "Animal",
        "namespace": "Testing",
        "attributes": [{"name": "name", "kind": "Text"}],
        "relationships": [owner_rel],
    }
    animal = GenericSchema(**animal_data).convert_api()
    animal.used_by = ["TestingDog", "TestingCat"]

    def animal_node(name: str) -> NodeSchema:
        data: dict[str, Any] = {
            "name": name,
            "namespace": "Testing",
            "inherit_from": ["TestingAnimal"],
            "human_friendly_id": ["owner__name__value", "name__value"],
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": [owner_rel],
        }
        return NodeSchema(**data)

    person_data: dict[str, Any] = {
        "name": "Person",
        "namespace": "Testing",
        "human_friendly_id": ["name__value"],
        "attributes": [{"name": "name", "kind": "Text"}],
        "relationships": [
            {
                "name": "favorite_animal",
                "peer": "TestingAnimal",
                "cardinality": "one",
                "optional": True,
                "identifier": "favorite_animal",
            },
            {
                "name": "animals",
                "peer": "TestingAnimal",
                "cardinality": "many",
                "optional": True,
                "identifier": "person__animal",
            },
        ],
    }
    person = NodeSchema(**person_data)

    schema = SchemaRootAPI(
        generics=[animal],
        nodes=[animal_node("Dog").convert_api(), animal_node("Cat").convert_api(), person.convert_api()],
    )
    client.schema.set_cache(schema=schema, branch="main")
    return client


@dataclass
class HfidReferenceInfoCase:
    """Test case for relationship info of an HFID reference mapping."""

    name: str
    relationship: str
    value: Any
    is_valid: bool
    format: RelationshipDataFormat
    peer_kind: str
    reason: str | None = None


HFID_REFERENCE_INFO_CASES = [
    HfidReferenceInfoCase(
        name="one_with_kind",
        relationship="favorite_animal",
        value={"kind": "TestingDog", "hfid": ["Jane Smith", "Max"]},
        is_valid=True,
        format=RelationshipDataFormat.ONE_REF,
        peer_kind="TestingDog",
    ),
    HfidReferenceInfoCase(
        name="one_without_kind",
        relationship="favorite_animal",
        value={"hfid": ["Jane Smith", "Max"]},
        is_valid=True,
        format=RelationshipDataFormat.ONE_REF,
        peer_kind="TestingAnimal",
    ),
    HfidReferenceInfoCase(
        name="one_kind_not_implementing_generic",
        relationship="favorite_animal",
        value={"kind": "TestingPerson", "hfid": ["Jane Smith"]},
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="Kind TestingPerson is not a valid peer for relationship favorite_animal, expected TestingAnimal",
    ),
    HfidReferenceInfoCase(
        name="one_kind_unknown",
        relationship="favorite_animal",
        value={"kind": "TestingUnicorn", "hfid": ["Jane Smith", "Max"]},
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="Kind TestingUnicorn is not a valid peer for relationship favorite_animal, expected TestingAnimal",
    ),
    HfidReferenceInfoCase(
        name="one_kind_is_the_peer_itself",
        relationship="favorite_animal",
        value={"kind": "TestingAnimal", "hfid": ["Jane Smith", "Max"]},
        is_valid=True,
        format=RelationshipDataFormat.ONE_REF,
        peer_kind="TestingAnimal",
    ),
    HfidReferenceInfoCase(
        name="one_kind_not_a_string",
        relationship="favorite_animal",
        value={"kind": ["TestingDog"], "hfid": ["Jane Smith", "Max"]},
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="'kind' must be a string",
    ),
    HfidReferenceInfoCase(
        name="one_unexpected_key",
        relationship="favorite_animal",
        value={"kind": "TestingDog", "hfid": ["Jane Smith", "Max"], "name": "Max"},
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="HFID reference only accepts 'hfid' and 'kind', found ['name']",
    ),
    HfidReferenceInfoCase(
        name="one_hfid_not_a_list",
        relationship="favorite_animal",
        value={"kind": "TestingDog", "hfid": {"name": "Max"}},
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="'hfid' must be a string or a list of values",
    ),
    HfidReferenceInfoCase(
        name="one_kind_without_hfid_or_data",
        relationship="favorite_animal",
        value={"kind": "TestingDog"},
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="Relationship favorite_animal must be a dict with 'data' or 'hfid'",
    ),
    HfidReferenceInfoCase(
        name="many_bare_mapping",
        relationship="animals",
        value={"kind": "TestingDog", "hfid": ["Jane Smith", "Max"]},
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="Relationship animals has a cardinality of many, provide the HFID references as a list",
    ),
    HfidReferenceInfoCase(
        name="many_mixed_list",
        relationship="animals",
        value=[{"kind": "TestingDog", "hfid": ["Jane Smith", "Max"]}, {"kind": "TestingCat", "hfid": "Whiskers"}],
        is_valid=True,
        format=RelationshipDataFormat.MANY_REF,
        peer_kind="TestingAnimal",
    ),
    HfidReferenceInfoCase(
        name="many_list_with_invalid_mapping",
        relationship="animals",
        value=[["Jane Smith", "Max"], {"kind": "TestingPerson", "hfid": ["Jane Smith"]}],
        is_valid=False,
        format=RelationshipDataFormat.UNKNOWN,
        peer_kind="TestingAnimal",
        reason="Kind TestingPerson is not a valid peer for relationship animals, expected TestingAnimal",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in HFID_REFERENCE_INFO_CASES])
async def test_get_relationship_info_hfid_reference(
    client_with_generic_peer_schema: InfrahubClient, case: HfidReferenceInfoCase
) -> None:
    person_schema = await client_with_generic_peer_schema.schema.get(kind="TestingPerson")

    rel_info = await get_relationship_info(
        client_with_generic_peer_schema, person_schema, case.relationship, case.value
    )

    assert rel_info.is_valid == case.is_valid
    assert rel_info.format == case.format
    assert rel_info.peer_kind == case.peer_kind
    assert rel_info.reason_relationship_not_valid == case.reason


async def test_validate_format_reports_invalid_hfid_reference(client_with_generic_peer_schema: InfrahubClient) -> None:
    content = {
        "apiVersion": "infrahub.app/v1",
        "kind": "Object",
        "spec": {
            "kind": "TestingPerson",
            "data": [{"name": "Olivia", "favorite_animal": {"kind": "TestingPerson", "hfid": ["Jane Smith"]}}],
        },
    }
    obj = ObjectFile(location="some/path", content=content)

    with pytest.raises(
        ValidationError, match="Kind TestingPerson is not a valid peer for relationship favorite_animal"
    ):
        await obj.validate_format(client=client_with_generic_peer_schema)


async def test_hfid_reference_in_object_loading(
    client_with_generic_peer_schema: InfrahubClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reference mapping is sent as hfid plus kind, and a string hfid is wrapped as a single-component HFID."""
    content = {
        "apiVersion": "infrahub.app/v1",
        "kind": "Object",
        "spec": {
            "kind": "TestingPerson",
            "data": [
                {
                    "name": "Olivia",
                    "favorite_animal": {"kind": "TestingDog", "hfid": ["Jane Smith", "Max"]},
                    "animals": [
                        {"kind": "TestingCat", "hfid": "Whiskers"},
                        {"hfid": ["Jane Smith", "Max"]},
                        "550e8400-e29b-41d4-a716-446655440000",
                    ],
                }
            ],
        },
    }
    obj = ObjectFile(location="some/path", content=content)
    await obj.validate_format(client=client_with_generic_peer_schema)

    create_calls: list[dict[str, Any]] = []
    original_create = client_with_generic_peer_schema.create

    async def capture_create(kind: str, branch: str | None = None, data: dict | None = None, **kwargs: Any) -> Any:  # noqa: ANN401
        create_calls.append({"kind": kind, "data": data})
        return await original_create(kind=kind, branch=branch, data=data, **kwargs)

    async def skip_save(self: InfrahubNode, **kwargs: Any) -> None:  # noqa: ANN401
        return None

    monkeypatch.setattr(client_with_generic_peer_schema, "create", capture_create)
    monkeypatch.setattr("infrahub_sdk.node.InfrahubNode.save", skip_save)

    await obj.process(client=client_with_generic_peer_schema)

    assert len(create_calls) == 1
    assert create_calls[0]["data"]["favorite_animal"] == {"hfid": ["Jane Smith", "Max"], "kind": "TestingDog"}
    assert create_calls[0]["data"]["animals"] == [
        {"hfid": ["Whiskers"], "kind": "TestingCat"},
        {"hfid": ["Jane Smith", "Max"]},
        "550e8400-e29b-41d4-a716-446655440000",
    ]


def test_normalize_hfid_reference_mapping() -> None:
    assert normalize_hfid_reference_mapping({"hfid": "Max", "kind": "TestingDog"}) == {
        "hfid": ["Max"],
        "kind": "TestingDog",
    }
    assert normalize_hfid_reference_mapping({"hfid": ["Jane Smith", "Max"]}) == {"hfid": ["Jane Smith", "Max"]}


def test_related_node_graphql_payload_with_kind() -> None:
    """A related node built from hfid and kind sends both in the mutation input."""
    related_node = RelatedNode(
        schema=MagicMock(),
        name="favorite_animal",
        branch="main",
        client=MagicMock(),
        data={"hfid": ["Jane Smith", "Max"], "kind": "TestingDog"},
    )

    assert related_node._generate_input_data() == {"hfid": ["Jane Smith", "Max"], "kind": "TestingDog"}
