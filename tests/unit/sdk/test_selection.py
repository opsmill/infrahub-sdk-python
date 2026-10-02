"""Tests for the selection record, ``only`` validation and the field-selection decision helpers."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any

import pytest

from infrahub_sdk.exceptions import SelectionConflictError, SelectionFieldNotFoundError
from infrahub_sdk.node.selection import (
    HIERARCHICAL_FIELD_NAMES,
    IDENTITY_FLOOR_NAMES,
    Selection,
    check_selection_conflict,
    implementing_kind_only,
    is_attribute_selected,
    is_hierarchical_selected,
    is_relationship_selected,
    should_expand_peer,
    validate_only,
)
from infrahub_sdk.schema import GenericSchemaAPI, NodeSchemaAPI, RelationshipSchemaAPI

GENERIC_DEVICE_ATTRIBUTES: list[dict[str, Any]] = [
    {"name": "name", "kind": "Text", "unique": True},
    {"name": "description", "kind": "Text", "optional": True},
]
GENERIC_DEVICE_RELATIONSHIPS: list[dict[str, Any]] = [
    {"name": "tags", "peer": "BuiltinTag", "kind": "Generic", "cardinality": "many", "optional": True},
]


def _implementing_device_schema(name: str, extra_attribute: dict[str, Any]) -> NodeSchemaAPI:
    return NodeSchemaAPI(
        namespace="Test",
        name=name,
        default_filter="name__value",
        inherit_from=["TestGenericDevice"],
        attributes=[{**attr, "inherited": True} for attr in GENERIC_DEVICE_ATTRIBUTES] + [extra_attribute],
        relationships=[{**rel, "inherited": True} for rel in GENERIC_DEVICE_RELATIONSHIPS],
    )


@pytest.fixture
def generic_device_schema() -> GenericSchemaAPI:
    return GenericSchemaAPI(
        namespace="Test",
        name="GenericDevice",
        default_filter="name__value",
        attributes=GENERIC_DEVICE_ATTRIBUTES,
        relationships=GENERIC_DEVICE_RELATIONSHIPS,
        used_by=["TestRouter", "TestSwitch"],
    )


@pytest.fixture
def implementing_device_schemas() -> list[NodeSchemaAPI]:
    return [
        _implementing_device_schema("Router", {"name": "role", "kind": "Text", "optional": True}),
        _implementing_device_schema("Switch", {"name": "ports", "kind": "Number", "optional": True}),
    ]


@pytest.fixture
def hierarchical_location_schema() -> NodeSchemaAPI:
    return NodeSchemaAPI(
        namespace="Infra",
        name="Location",
        default_filter="name__value",
        hierarchy="InfraLocation",
        attributes=[{"name": "name", "kind": "Text", "unique": True}],
        relationships=[],
    )


def _rel(name: str, cardinality: str, kind: str) -> RelationshipSchemaAPI:
    return RelationshipSchemaAPI.model_validate(
        {
            "name": name,
            "peer": "TestPeer",
            "cardinality": cardinality,
            "kind": kind,
        }
    )


SITE = _rel("site", "one", "Generic")
TAGS = _rel("tags", "many", "Generic")
INTERFACES = _rel("interfaces", "many", "Component")
GROUPS = _rel("member_of_groups", "many", "Group")
ATTRIBUTE_PEERS = _rel("attribute_peers", "many", "Attribute")
PARENT_PEERS = _rel("parent_peers", "many", "Parent")


def test_identity_floor_and_hierarchical_names() -> None:
    assert frozenset({"id", "hfid", "display_label"}) == IDENTITY_FLOOR_NAMES
    assert HIERARCHICAL_FIELD_NAMES == ("parent", "children", "ancestors", "descendants")


# ---------------------------------------------------------------------------
# check_selection_conflict
# ---------------------------------------------------------------------------


@dataclass
class ConflictCase:
    name: str
    include: list[str] | None
    exclude: list[str] | None
    expected_parameters: list[str]
    expected_message: str


CONFLICT_CASES = [
    ConflictCase(
        name="empty-include",
        include=[],
        exclude=None,
        expected_parameters=["only", "include"],
        expected_message="'only' cannot be combined with 'include'; pass 'only' on its own.",
    ),
    ConflictCase(
        name="include",
        include=["tags"],
        exclude=None,
        expected_parameters=["only", "include"],
        expected_message="'only' cannot be combined with 'include'; pass 'only' on its own.",
    ),
    ConflictCase(
        name="empty-exclude",
        include=None,
        exclude=[],
        expected_parameters=["only", "exclude"],
        expected_message="'only' cannot be combined with 'exclude'; pass 'only' on its own.",
    ),
    ConflictCase(
        name="exclude",
        include=None,
        exclude=["description"],
        expected_parameters=["only", "exclude"],
        expected_message="'only' cannot be combined with 'exclude'; pass 'only' on its own.",
    ),
    ConflictCase(
        name="include-and-exclude",
        include=["tags"],
        exclude=["description"],
        expected_parameters=["only", "include", "exclude"],
        expected_message="'only' cannot be combined with 'include' or 'exclude'; pass 'only' on its own.",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in CONFLICT_CASES])
def test_check_selection_conflict_rejects_only_with_include_or_exclude(case: ConflictCase) -> None:
    with pytest.raises(SelectionConflictError, match=f"^{re.escape(case.expected_message)}$") as excinfo:
        check_selection_conflict(include=case.include, exclude=case.exclude, only=["name"])

    assert excinfo.value.parameters == case.expected_parameters


@dataclass
class ValidCombinationCase:
    name: str
    include: list[str] | None
    exclude: list[str] | None
    only: list[str] | None


VALID_COMBINATION_CASES = [
    ValidCombinationCase(name="only", include=None, exclude=None, only=["name"]),
    ValidCombinationCase(name="empty-only", include=None, exclude=None, only=[]),
    ValidCombinationCase(name="include-and-exclude", include=["tags"], exclude=["description"], only=None),
    ValidCombinationCase(name="nothing", include=None, exclude=None, only=None),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in VALID_COMBINATION_CASES])
def test_check_selection_conflict_accepts_valid_combinations(case: ValidCombinationCase) -> None:
    assert check_selection_conflict(include=case.include, exclude=case.exclude, only=case.only) is None


# ---------------------------------------------------------------------------
# validate_only
# ---------------------------------------------------------------------------


@dataclass
class KnownNamesCase:
    name: str
    only: list[str]


KNOWN_NAMES_CASES = [
    KnownNamesCase(name="empty", only=[]),
    KnownNamesCase(name="attributes", only=["name", "description", "type"]),
    KnownNamesCase(name="relationships", only=["tags", "primary_tag", "member_of_groups"]),
    KnownNamesCase(name="floor", only=["id", "hfid", "display_label"]),
    KnownNamesCase(name="mixed", only=["name", "tags", "hfid"]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in KNOWN_NAMES_CASES])
def test_validate_only_accepts_known_names(location_schema: NodeSchemaAPI, case: KnownNamesCase) -> None:
    assert validate_only(case.only, location_schema, [], fragment=False, kind="BuiltinLocation") is None


def test_validate_only_accepts_hierarchical_names_on_hierarchical_kind(
    hierarchical_location_schema: NodeSchemaAPI,
) -> None:
    only = ["name", "parent", "children", "ancestors", "descendants"]

    assert validate_only(only, hierarchical_location_schema, [], fragment=False, kind="InfraLocation") is None


@pytest.mark.parametrize("field_name", HIERARCHICAL_FIELD_NAMES)
def test_validate_only_rejects_hierarchical_names_on_flat_kind(location_schema: NodeSchemaAPI, field_name: str) -> None:
    expected = f"'{field_name}' is not an attribute or relationship of BuiltinLocation."

    with pytest.raises(SelectionFieldNotFoundError, match=f"^{re.escape(expected)}$") as excinfo:
        validate_only([field_name], location_schema, [], fragment=False, kind="BuiltinLocation")

    assert excinfo.value.field == field_name
    assert excinfo.value.kind == "BuiltinLocation"
    assert excinfo.value.implementing_kinds == []


def test_validate_only_rejects_unknown_name(location_schema: NodeSchemaAPI) -> None:
    expected = "'colour' is not an attribute or relationship of BuiltinLocation."

    with pytest.raises(SelectionFieldNotFoundError, match=f"^{re.escape(expected)}$") as excinfo:
        validate_only(["name", "colour", "tags"], location_schema, [], fragment=False, kind="BuiltinLocation")

    assert excinfo.value.kind == "BuiltinLocation"
    assert excinfo.value.field == "colour"
    assert excinfo.value.implementing_kinds == []


@pytest.mark.parametrize("fragment", [True, False])
def test_validate_only_accepts_generic_names_with_or_without_fragment(
    generic_device_schema: GenericSchemaAPI, implementing_device_schemas: list[NodeSchemaAPI], fragment: bool
) -> None:
    only = ["name", "description", "tags", "id"]

    assert (
        validate_only(only, generic_device_schema, implementing_device_schemas, fragment, kind="TestGenericDevice")
        is None
    )


def test_validate_only_accepts_implementing_kind_names_with_fragment(
    generic_device_schema: GenericSchemaAPI, implementing_device_schemas: list[NodeSchemaAPI]
) -> None:
    only = ["name", "role", "ports"]

    assert (
        validate_only(only, generic_device_schema, implementing_device_schemas, fragment=True, kind="TestGenericDevice")
        is None
    )


def test_validate_only_rejects_implementing_kind_names_without_fragment(
    generic_device_schema: GenericSchemaAPI, implementing_device_schemas: list[NodeSchemaAPI]
) -> None:
    expected = (
        "'role' is not defined on TestGenericDevice, only on the kinds implementing it (TestRouter). "
        "Pass fragment=True to select it."
    )

    with pytest.raises(SelectionFieldNotFoundError, match=f"^{re.escape(expected)}$") as excinfo:
        validate_only(
            ["name", "role"],
            generic_device_schema,
            implementing_device_schemas,
            fragment=False,
            kind="TestGenericDevice",
        )

    assert excinfo.value.kind == "TestGenericDevice"
    assert excinfo.value.field == "role"
    assert excinfo.value.implementing_kinds == ["TestRouter"]


def test_validate_only_lists_every_implementing_kind_that_defines_the_name(
    generic_device_schema: GenericSchemaAPI, implementing_device_schemas: list[NodeSchemaAPI]
) -> None:
    firewall = _implementing_device_schema("Firewall", {"name": "role", "kind": "Text", "optional": True})

    with pytest.raises(SelectionFieldNotFoundError, match=re.escape("(TestRouter, TestFirewall)")) as excinfo:
        validate_only(
            ["role"],
            generic_device_schema,
            [*implementing_device_schemas, firewall],
            fragment=False,
            kind="TestGenericDevice",
        )

    assert excinfo.value.implementing_kinds == ["TestRouter", "TestFirewall"]


@pytest.mark.parametrize("fragment", [True, False])
def test_validate_only_rejects_name_unknown_to_generic_and_implementations(
    generic_device_schema: GenericSchemaAPI, implementing_device_schemas: list[NodeSchemaAPI], fragment: bool
) -> None:
    expected = "'colour' is not an attribute or relationship of TestGenericDevice."

    with pytest.raises(SelectionFieldNotFoundError, match=f"^{re.escape(expected)}$") as excinfo:
        validate_only(
            ["colour"], generic_device_schema, implementing_device_schemas, fragment, kind="TestGenericDevice"
        )

    assert excinfo.value.field == "colour"
    assert excinfo.value.implementing_kinds == []


def test_validate_only_ignores_implementing_schemas_for_a_node_kind(
    location_schema: NodeSchemaAPI, implementing_device_schemas: list[NodeSchemaAPI]
) -> None:
    expected = "'role' is not an attribute or relationship of BuiltinLocation."

    with pytest.raises(SelectionFieldNotFoundError, match=f"^{re.escape(expected)}$") as excinfo:
        validate_only(["role"], location_schema, implementing_device_schemas, fragment=True, kind="BuiltinLocation")

    assert excinfo.value.field == "role"
    assert excinfo.value.implementing_kinds == []


def test_implementing_kind_only_keeps_names_only_the_implementing_kind_defines(
    generic_device_schema: GenericSchemaAPI, implementing_device_schemas: list[NodeSchemaAPI]
) -> None:
    router, switch = implementing_device_schemas
    only = ["name", "role", "tags", "ports", "id", "hfid", "colour"]

    assert implementing_kind_only(only, generic_device_schema, router) == ["role"]
    assert implementing_kind_only(only, generic_device_schema, switch) == ["ports"]


def test_implementing_kind_only_keeps_fields_inherited_from_another_generic(
    generic_device_schema: GenericSchemaAPI,
) -> None:
    router = _implementing_device_schema(
        "Router", {"name": "serial", "kind": "Text", "optional": True, "inherited": True}
    )

    assert implementing_kind_only(["name", "serial"], generic_device_schema, router) == ["serial"]


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


@dataclass
class DescribeCase:
    name: str
    include: list[str] | None
    exclude: list[str] | None
    only: list[str] | None
    expected: str


DESCRIBE_CASES = [
    DescribeCase(name="only", include=None, exclude=None, only=["name"], expected="only=['name']"),
    DescribeCase(name="empty-only", include=None, exclude=None, only=[], expected="only=[]"),
    DescribeCase(name="exclude", include=None, exclude=["description"], only=None, expected="exclude=['description']"),
    DescribeCase(name="include", include=["tags"], exclude=None, only=None, expected="include=['tags']"),
    DescribeCase(
        name="include-and-exclude",
        include=["tags"],
        exclude=["description"],
        only=None,
        expected="include=['tags'], exclude=['description']",
    ),
    DescribeCase(name="default", include=None, exclude=None, only=None, expected="default selection"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in DESCRIBE_CASES])
def test_selection_describe(case: DescribeCase) -> None:
    selection = Selection.from_args(include=case.include, exclude=case.exclude, only=case.only)

    assert selection.describe() == case.expected


def test_selection_from_args_records_tuples_and_strictness() -> None:
    names = ["name"]
    selection = Selection.from_args(include=None, exclude=None, only=names)
    names.append("description")

    assert selection == Selection(only=("name",), include=None, exclude=None, strict=True)
    assert selection.peer_of is None
    assert selection.peer_floor is False

    default = Selection.from_args(include=["tags"], exclude=["description"], only=None)
    assert default == Selection(only=None, include=("tags",), exclude=("description",), strict=False)


def test_selection_is_frozen() -> None:
    selection = Selection.from_args(include=None, exclude=None, only=["name"])
    attribute = "strict"

    with pytest.raises(dataclasses.FrozenInstanceError, match="cannot assign to field 'strict'"):
        setattr(selection, attribute, False)


@dataclass
class PeerCase:
    name: str
    parent: Selection
    expected_label: str
    expected_strict: bool


PEER_CASES = [
    PeerCase(
        name="only",
        parent=Selection.from_args(include=None, exclude=None, only=["site"]),
        expected_label="peer of InfraDevice.site, fetched with only=['site']",
        expected_strict=True,
    ),
    PeerCase(
        name="include",
        parent=Selection.from_args(include=["site"], exclude=None, only=None),
        expected_label="peer of InfraDevice.site, fetched with include=['site']",
        expected_strict=False,
    ),
    PeerCase(
        name="default",
        parent=Selection.from_args(include=None, exclude=None, only=None),
        expected_label="peer of InfraDevice.site, fetched with default selection",
        expected_strict=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in PEER_CASES])
@pytest.mark.parametrize("peer_floor", [True, False])
def test_selection_for_peer(case: PeerCase, peer_floor: bool) -> None:
    peer = Selection.for_peer(parent=case.parent, parent_kind="InfraDevice", rel_name="site", peer_floor=peer_floor)

    assert peer.strict is case.expected_strict
    assert peer.peer_of == "InfraDevice.site"
    assert peer.peer_floor is peer_floor
    assert peer.describe() == case.expected_label
    assert case.parent.peer_of is None


# ---------------------------------------------------------------------------
# Decision helpers
# ---------------------------------------------------------------------------


@dataclass
class AttributeCase:
    name: str
    field: str
    include: list[str] | None
    exclude: list[str] | None
    only: list[str] | None
    expected: bool


ATTRIBUTE_CASES = [
    AttributeCase(name="default", field="description", include=None, exclude=None, only=None, expected=True),
    AttributeCase(
        name="include-does-not-narrow", field="description", include=["tags"], exclude=None, only=None, expected=True
    ),
    AttributeCase(
        name="excluded", field="description", include=None, exclude=["description"], only=None, expected=False
    ),
    AttributeCase(name="empty-exclude", field="description", include=None, exclude=[], only=None, expected=True),
    AttributeCase(name="other-excluded", field="description", include=None, exclude=["name"], only=None, expected=True),
    AttributeCase(name="only-named", field="name", include=None, exclude=None, only=["name"], expected=True),
    AttributeCase(
        name="only-not-named", field="description", include=None, exclude=None, only=["name"], expected=False
    ),
    AttributeCase(name="empty-only", field="description", include=None, exclude=None, only=[], expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in ATTRIBUTE_CASES])
def test_is_attribute_selected(case: AttributeCase) -> None:
    assert (
        is_attribute_selected(case.field, include=case.include, exclude=case.exclude, only=case.only) is case.expected
    )


@dataclass
class RelationshipCase:
    name: str
    rel_schema: RelationshipSchemaAPI
    include: list[str] | None
    exclude: list[str] | None
    only: list[str] | None
    expected: bool


RELATIONSHIP_CASES = [
    # Without only: today's rules.
    RelationshipCase(name="one-default", rel_schema=SITE, include=None, exclude=None, only=None, expected=True),
    RelationshipCase(name="one-excluded", rel_schema=SITE, include=None, exclude=["site"], only=None, expected=False),
    RelationshipCase(
        name="many-generic-default", rel_schema=TAGS, include=None, exclude=None, only=None, expected=False
    ),
    RelationshipCase(
        name="many-generic-included", rel_schema=TAGS, include=["tags"], exclude=None, only=None, expected=True
    ),
    RelationshipCase(
        name="many-generic-empty-include", rel_schema=TAGS, include=[], exclude=None, only=None, expected=False
    ),
    RelationshipCase(
        name="many-generic-other-included", rel_schema=TAGS, include=["site"], exclude=None, only=None, expected=False
    ),
    RelationshipCase(
        name="many-generic-included-and-excluded",
        rel_schema=TAGS,
        include=["tags"],
        exclude=["tags"],
        only=None,
        expected=False,
    ),
    RelationshipCase(
        name="many-component-default", rel_schema=INTERFACES, include=None, exclude=None, only=None, expected=False
    ),
    RelationshipCase(
        name="many-component-included",
        rel_schema=INTERFACES,
        include=["interfaces"],
        exclude=None,
        only=None,
        expected=True,
    ),
    RelationshipCase(
        name="many-group-default", rel_schema=GROUPS, include=None, exclude=None, only=None, expected=False
    ),
    RelationshipCase(
        name="many-attribute-default", rel_schema=ATTRIBUTE_PEERS, include=None, exclude=None, only=None, expected=True
    ),
    RelationshipCase(
        name="many-attribute-excluded",
        rel_schema=ATTRIBUTE_PEERS,
        include=None,
        exclude=["attribute_peers"],
        only=None,
        expected=False,
    ),
    RelationshipCase(
        name="many-parent-default", rel_schema=PARENT_PEERS, include=None, exclude=None, only=None, expected=True
    ),
    # Under only: selected iff named.
    RelationshipCase(name="only-one-named", rel_schema=SITE, include=None, exclude=None, only=["site"], expected=True),
    RelationshipCase(
        name="only-one-not-named", rel_schema=SITE, include=None, exclude=None, only=["name"], expected=False
    ),
    RelationshipCase(name="only-many-named", rel_schema=TAGS, include=None, exclude=None, only=["tags"], expected=True),
    RelationshipCase(
        name="only-many-attribute-not-named",
        rel_schema=ATTRIBUTE_PEERS,
        include=None,
        exclude=None,
        only=["name"],
        expected=False,
    ),
    RelationshipCase(name="only-empty", rel_schema=PARENT_PEERS, include=None, exclude=None, only=[], expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in RELATIONSHIP_CASES])
def test_is_relationship_selected(case: RelationshipCase) -> None:
    result = is_relationship_selected(case.rel_schema, include=case.include, exclude=case.exclude, only=case.only)

    assert result is case.expected


def test_is_relationship_selected_accepts_enum_valued_schema() -> None:
    # Fields left at their defaults hold enum members rather than strings.
    tags = RelationshipSchemaAPI(name="tags", peer="BuiltinTag")

    assert is_relationship_selected(tags, include=None, exclude=None, only=None) is False
    assert is_relationship_selected(tags, include=["tags"], exclude=None, only=None) is True


@dataclass
class ExpandPeerCase:
    name: str
    include: list[str] | None
    only: list[str] | None
    prefetch_relationships: bool
    expected: bool


EXPAND_PEER_CASES = [
    ExpandPeerCase(name="default", include=None, only=None, prefetch_relationships=False, expected=False),
    ExpandPeerCase(name="included", include=["site"], only=None, prefetch_relationships=False, expected=True),
    ExpandPeerCase(name="other-included", include=["tags"], only=None, prefetch_relationships=False, expected=False),
    ExpandPeerCase(name="empty-include", include=[], only=None, prefetch_relationships=False, expected=False),
    ExpandPeerCase(name="prefetch", include=None, only=None, prefetch_relationships=True, expected=True),
    ExpandPeerCase(
        name="only-named-without-prefetch", include=None, only=["site"], prefetch_relationships=False, expected=False
    ),
    ExpandPeerCase(
        name="only-named-with-prefetch", include=None, only=["site"], prefetch_relationships=True, expected=True
    ),
    ExpandPeerCase(
        name="only-ignores-include", include=["site"], only=["site"], prefetch_relationships=False, expected=False
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in EXPAND_PEER_CASES])
def test_should_expand_peer(case: ExpandPeerCase) -> None:
    result = should_expand_peer(
        "site", include=case.include, only=case.only, prefetch_relationships=case.prefetch_relationships
    )

    assert result is case.expected


@dataclass
class HierarchicalCase:
    name: str
    field: str
    include: list[str] | None
    exclude: list[str] | None
    only: list[str] | None
    prefetch_relationships: bool
    expected: bool


HIERARCHICAL_CASES = [
    # Without only: today's rules.
    HierarchicalCase(
        name="default",
        field="parent",
        include=None,
        exclude=None,
        only=None,
        prefetch_relationships=False,
        expected=False,
    ),
    HierarchicalCase(
        name="prefetch",
        field="parent",
        include=None,
        exclude=None,
        only=None,
        prefetch_relationships=True,
        expected=True,
    ),
    HierarchicalCase(
        name="included",
        field="parent",
        include=["parent"],
        exclude=None,
        only=None,
        prefetch_relationships=False,
        expected=True,
    ),
    HierarchicalCase(
        name="other-included",
        field="parent",
        include=["children"],
        exclude=None,
        only=None,
        prefetch_relationships=False,
        expected=False,
    ),
    HierarchicalCase(
        name="empty-include",
        field="parent",
        include=[],
        exclude=None,
        only=None,
        prefetch_relationships=False,
        expected=False,
    ),
    HierarchicalCase(
        name="excluded-beats-prefetch",
        field="parent",
        include=None,
        exclude=["parent"],
        only=None,
        prefetch_relationships=True,
        expected=False,
    ),
    HierarchicalCase(
        name="excluded-beats-include",
        field="parent",
        include=["parent"],
        exclude=["parent"],
        only=None,
        prefetch_relationships=False,
        expected=False,
    ),
    # Under only: selected iff named, whatever prefetch_relationships says.
    HierarchicalCase(
        name="only-named",
        field="parent",
        include=None,
        exclude=None,
        only=["parent"],
        prefetch_relationships=False,
        expected=True,
    ),
    HierarchicalCase(
        name="only-named-with-prefetch",
        field="parent",
        include=None,
        exclude=None,
        only=["parent"],
        prefetch_relationships=True,
        expected=True,
    ),
    HierarchicalCase(
        name="only-not-named-with-prefetch",
        field="children",
        include=None,
        exclude=None,
        only=["parent"],
        prefetch_relationships=True,
        expected=False,
    ),
    HierarchicalCase(
        name="only-empty",
        field="descendants",
        include=None,
        exclude=None,
        only=[],
        prefetch_relationships=True,
        expected=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in HIERARCHICAL_CASES])
def test_is_hierarchical_selected(case: HierarchicalCase) -> None:
    result = is_hierarchical_selected(
        case.field,
        include=case.include,
        exclude=case.exclude,
        only=case.only,
        prefetch_relationships=case.prefetch_relationships,
    )

    assert result is case.expected
