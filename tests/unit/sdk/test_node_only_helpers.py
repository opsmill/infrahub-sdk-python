from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.exceptions import FieldNotFoundError, FieldNotLoadedError, FieldSelectionConflictError
from infrahub_sdk.node._only import (  # noqa: PLC2701  # the helpers under test are private to the package
    HfidFields,
    OnlyMarker,
    check_only_conflict,
    check_only_names,
    check_only_names_on_every_kind,
    expand_hfid,
    field_names,
)
from infrahub_sdk.schema import GenericSchemaAPI, NodeSchemaAPI

if TYPE_CHECKING:
    from infrahub_sdk.schema import MainSchemaTypesAPI

ANIMAL_ATTRIBUTES = [{"name": "name", "kind": "Text"}, {"name": "weight", "kind": "Number", "optional": True}]
ANIMAL_RELATIONSHIPS = [
    {"name": "owner", "peer": "TestingPerson", "cardinality": "one", "identifier": "person__animal"},
    {"name": "best_friend", "peer": "TestingPerson", "cardinality": "one", "optional": True},
]
ANIMAL_HFID = ["owner__name__value", "name__value"]
BREED_AND_COLOR = [{"name": "breed", "kind": "Text"}, {"name": "color", "kind": "Color", "optional": True}]
HIERARCHY_RELATIONSHIPS = [
    {"name": "parent", "peer": "LocationGeneric", "cardinality": "one", "kind": "Hierarchy", "optional": True},
    {"name": "children", "peer": "LocationGeneric", "cardinality": "many", "kind": "Hierarchy", "optional": True},
]

# Implementing kinds carry the generic's fields, as the server returns them.
ANIMAL = GenericSchemaAPI(
    name="Animal",
    namespace="Testing",
    human_friendly_id=ANIMAL_HFID,
    used_by=["TestingCat", "TestingDog"],
    attributes=ANIMAL_ATTRIBUTES,
    relationships=ANIMAL_RELATIONSHIPS,
)
CAT = NodeSchemaAPI(
    name="Cat",
    namespace="Testing",
    inherit_from=["TestingAnimal"],
    human_friendly_id=["owner__name__value", "name__value", "color__value"],
    attributes=ANIMAL_ATTRIBUTES + BREED_AND_COLOR,
    relationships=ANIMAL_RELATIONSHIPS,
)
DOG = NodeSchemaAPI(
    name="Dog",
    namespace="Testing",
    inherit_from=["TestingAnimal"],
    human_friendly_id=ANIMAL_HFID,
    attributes=ANIMAL_ATTRIBUTES + BREED_AND_COLOR,
    relationships=ANIMAL_RELATIONSHIPS,
)
PERSON = NodeSchemaAPI(
    name="Person",
    namespace="Testing",
    human_friendly_id=["name__value"],
    attributes=[{"name": "name", "kind": "Text"}, {"name": "height", "kind": "Number", "optional": True}],
    relationships=[{"name": "animals", "peer": "TestingAnimal", "cardinality": "many"}],
)
LOCATION_GENERIC = GenericSchemaAPI(
    name="Generic",
    namespace="Location",
    hierarchical=True,
    used_by=["LocationSite"],
    attributes=[{"name": "name", "kind": "Text"}],
    relationships=HIERARCHY_RELATIONSHIPS,
)
SITE = NodeSchemaAPI(
    name="Site",
    namespace="Location",
    inherit_from=["LocationGeneric"],
    hierarchy="LocationGeneric",
    attributes=[{"name": "name", "kind": "Text"}, {"name": "facility", "kind": "Text"}],
    relationships=HIERARCHY_RELATIONSHIPS,
)
PLACE = GenericSchemaAPI(
    name="Place",
    namespace="Infra",
    used_by=["LocationSite"],
    attributes=[{"name": "name", "kind": "Text"}],
)
HFID_PATHS = NodeSchemaAPI(
    name="Rack",
    namespace="Infra",
    human_friendly_id=[
        "location__name__value",
        "location__code__value",
        "location__name__value",
        "name__value",
        "name",
        "building",
        "missing__value",
    ],
    attributes=[{"name": "name", "kind": "Text"}],
    relationships=[
        {"name": "location", "peer": "InfraLocation", "cardinality": "one"},
        {"name": "building", "peer": "InfraBuilding", "cardinality": "one"},
    ],
)


@pytest.fixture
def schemas(
    location_schema: NodeSchemaAPI, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> dict[str, MainSchemaTypesAPI]:
    return {
        "location": location_schema,
        "location-with-hfid": schema_with_hfid["location"],
        "rack": schema_with_hfid["rack"],
        "animal": ANIMAL,
        "cat": CAT,
        "dog": DOG,
        "person": PERSON,
        "location-generic": LOCATION_GENERIC,
        "site": SITE,
        "place": PLACE,
        "hfid-paths": HFID_PATHS,
    }


@dataclass
class ConflictCase:
    name: str
    only: list[str] | None
    include: list[str] | None
    exclude: list[str] | None


CONFLICT_CASES = [
    ConflictCase(name="only-and-include", only=["name"], include=["tags"], exclude=None),
    ConflictCase(name="only-and-exclude", only=["name"], include=None, exclude=["tags"]),
    ConflictCase(name="only-and-empty-include", only=["name"], include=[], exclude=None),
    ConflictCase(name="only-and-empty-exclude", only=["name"], include=None, exclude=[]),
    ConflictCase(name="empty-only-and-include", only=[], include=["tags"], exclude=None),
    ConflictCase(name="only-and-both", only=["name"], include=["tags"], exclude=["description"]),
]

NO_CONFLICT_CASES = [
    ConflictCase(name="nothing", only=None, include=None, exclude=None),
    ConflictCase(name="include-and-exclude-without-only", only=None, include=["tags"], exclude=["description"]),
    ConflictCase(name="empty-include-without-only", only=None, include=[], exclude=None),
    ConflictCase(name="only-alone", only=["name"], include=None, exclude=None),
    ConflictCase(name="empty-only-alone", only=[], include=None, exclude=None),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in CONFLICT_CASES])
def test_conflict_check_raises_when_only_meets_include_or_exclude(case: ConflictCase) -> None:
    with pytest.raises(
        FieldSelectionConflictError, match=re.escape("only cannot be combined with include or exclude.")
    ):
        check_only_conflict(only=case.only, include=case.include, exclude=case.exclude)


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in NO_CONFLICT_CASES])
def test_conflict_check_passes_when_one_side_is_none(case: ConflictCase) -> None:
    assert check_only_conflict(only=case.only, include=case.include, exclude=case.exclude) is None


@dataclass
class FieldNamesCase:
    name: str
    schema: str
    expected: set[str]


FIELD_NAMES_CASES = [
    FieldNamesCase(
        name="plain-node",
        schema="location",
        expected={"name", "description", "type", "tags", "primary_tag", "member_of_groups"},
    ),
    FieldNamesCase(
        name="hierarchical-node",
        schema="site",
        expected={"name", "facility", "parent", "children", "ancestors", "descendants"},
    ),
    FieldNamesCase(
        name="hierarchical-generic",
        schema="location-generic",
        expected={"name", "parent", "children", "ancestors", "descendants"},
    ),
    FieldNamesCase(name="plain-generic", schema="animal", expected={"name", "weight", "owner", "best_friend"}),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in FIELD_NAMES_CASES])
def test_field_names_of_one_kind(case: FieldNamesCase, schemas: dict[str, MainSchemaTypesAPI]) -> None:
    assert field_names(schemas[case.schema]) == case.expected


@dataclass
class NameCheckCase:
    name: str
    only: list[str]
    schema: str
    implementing: list[str]
    unknown_field: str | None


ACCEPTED_NAME_CASES = [
    NameCheckCase(
        name="attributes-and-relationships",
        only=["name", "description", "tags", "primary_tag"],
        schema="location",
        implementing=[],
        unknown_field=None,
    ),
    NameCheckCase(
        name="identifiers",
        only=["id", "display_label", "hfid"],
        schema="location",
        implementing=[],
        unknown_field=None,
    ),
    NameCheckCase(name="empty", only=[], schema="location", implementing=[], unknown_field=None),
    NameCheckCase(name="duplicates", only=["name", "name"], schema="location", implementing=[], unknown_field=None),
    NameCheckCase(
        name="hierarchy-on-a-hierarchical-node",
        only=["parent", "children", "ancestors", "descendants"],
        schema="site",
        implementing=[],
        unknown_field=None,
    ),
    NameCheckCase(
        name="generic-own-fields",
        only=["name", "owner"],
        schema="animal",
        implementing=["cat", "dog"],
        unknown_field=None,
    ),
    NameCheckCase(
        name="generic-fields-of-implementing-kinds",
        only=["breed", "color"],
        schema="animal",
        implementing=["cat", "dog"],
        unknown_field=None,
    ),
    NameCheckCase(
        name="hierarchy-on-a-hierarchical-generic",
        only=["ancestors", "descendants"],
        schema="location-generic",
        implementing=[],
        unknown_field=None,
    ),
    NameCheckCase(
        name="hierarchy-through-a-hierarchical-implementing-kind",
        only=["parent", "descendants"],
        schema="place",
        implementing=["site"],
        unknown_field=None,
    ),
]

REJECTED_NAME_CASES = [
    NameCheckCase(name="misspelt", only=["nmae"], schema="location", implementing=[], unknown_field="nmae"),
    NameCheckCase(
        name="first-unknown-in-order",
        only=["name", "descriptin", "tgas"],
        schema="location",
        implementing=[],
        unknown_field="descriptin",
    ),
    NameCheckCase(
        name="parent-on-a-plain-node", only=["parent"], schema="location", implementing=[], unknown_field="parent"
    ),
    NameCheckCase(
        name="children-on-a-plain-node", only=["children"], schema="location", implementing=[], unknown_field="children"
    ),
    NameCheckCase(
        name="ancestors-on-a-plain-node",
        only=["ancestors"],
        schema="location",
        implementing=[],
        unknown_field="ancestors",
    ),
    NameCheckCase(
        name="descendants-on-a-plain-node",
        only=["descendants"],
        schema="location",
        implementing=[],
        unknown_field="descendants",
    ),
    NameCheckCase(
        name="generic-without-implementing-kinds",
        only=["breed"],
        schema="animal",
        implementing=[],
        unknown_field="breed",
    ),
    NameCheckCase(
        name="generic-name-on-no-kind",
        only=["name", "height"],
        schema="animal",
        implementing=["cat", "dog"],
        unknown_field="height",
    ),
    NameCheckCase(
        name="hierarchy-on-a-plain-generic",
        only=["ancestors"],
        schema="animal",
        implementing=["cat", "dog"],
        unknown_field="ancestors",
    ),
    NameCheckCase(
        name="hierarchy-on-a-plain-generic-without-implementing-kinds",
        only=["descendants"],
        schema="place",
        implementing=[],
        unknown_field="descendants",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in ACCEPTED_NAME_CASES])
def test_name_check_accepts(case: NameCheckCase, schemas: dict[str, MainSchemaTypesAPI]) -> None:
    implementing = [schemas[kind] for kind in case.implementing]

    assert check_only_names(only=case.only, schema=schemas[case.schema], implementing_schemas=implementing) is None


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in REJECTED_NAME_CASES])
def test_name_check_rejects(case: NameCheckCase, schemas: dict[str, MainSchemaTypesAPI]) -> None:
    schema = schemas[case.schema]
    implementing = [schemas[kind] for kind in case.implementing]
    expected_message = f"'{case.unknown_field}' is not an attribute or relationship of {schema.kind}."

    with pytest.raises(FieldNotFoundError, match=re.escape(expected_message)) as exc_info:
        check_only_names(only=case.only, schema=schema, implementing_schemas=implementing)

    assert (exc_info.value.kind, exc_info.value.field) == (schema.kind, case.unknown_field)


@dataclass
class PeerCheckCase:
    name: str
    only: list[str]
    peer_kinds: list[str]
    unknown_kind: str | None
    unknown_field: str | None


ACCEPTED_PEER_CASES = [
    PeerCheckCase(
        name="every-kind-has-every-name",
        only=["name", "breed", "color"],
        peer_kinds=["cat", "dog"],
        unknown_kind=None,
        unknown_field=None,
    ),
    PeerCheckCase(
        name="identifiers-on-every-kind",
        only=["id", "display_label", "hfid"],
        peer_kinds=["cat", "person"],
        unknown_kind=None,
        unknown_field=None,
    ),
    PeerCheckCase(name="no-peer-kinds", only=["anything"], peer_kinds=[], unknown_kind=None, unknown_field=None),
]

REJECTED_PEER_CASES = [
    PeerCheckCase(
        name="missing-on-the-second-kind",
        only=["name", "weight"],
        peer_kinds=["cat", "person"],
        unknown_kind="TestingPerson",
        unknown_field="weight",
    ),
    PeerCheckCase(
        name="missing-on-the-first-kind",
        only=["name", "height"],
        peer_kinds=["cat", "person"],
        unknown_kind="TestingCat",
        unknown_field="height",
    ),
    PeerCheckCase(
        name="on-an-implementing-kind-but-not-on-the-other-peer",
        only=["breed"],
        peer_kinds=["dog", "person"],
        unknown_kind="TestingPerson",
        unknown_field="breed",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in ACCEPTED_PEER_CASES])
def test_peer_check_accepts(case: PeerCheckCase, schemas: dict[str, MainSchemaTypesAPI]) -> None:
    peer_schemas = [schemas[kind] for kind in case.peer_kinds]

    assert check_only_names_on_every_kind(only=case.only, schemas=peer_schemas) is None


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in REJECTED_PEER_CASES])
def test_peer_check_rejects_a_name_missing_on_one_kind(
    case: PeerCheckCase, schemas: dict[str, MainSchemaTypesAPI]
) -> None:
    peer_schemas = [schemas[kind] for kind in case.peer_kinds]
    expected_message = f"'{case.unknown_field}' is not an attribute or relationship of {case.unknown_kind}."

    with pytest.raises(FieldNotFoundError, match=re.escape(expected_message)) as exc_info:
        check_only_names_on_every_kind(only=case.only, schemas=peer_schemas)

    assert (exc_info.value.kind, exc_info.value.field) == (case.unknown_kind, case.unknown_field)


@dataclass
class HfidCase:
    name: str
    schema: str
    expected: HfidFields


HFID_CASES = [
    HfidCase(
        name="attribute-path",
        schema="location-with-hfid",
        expected=HfidFields(attributes=("name",), relationships={}),
    ),
    HfidCase(
        name="relationship-path",
        schema="rack",
        expected=HfidFields(attributes=("facility_id",), relationships={"location": ("name",)}),
    ),
    HfidCase(name="no-hfid", schema="location", expected=HfidFields(attributes=(), relationships={})),
    HfidCase(
        name="implementing-kind-with-its-own-hfid",
        schema="cat",
        expected=HfidFields(attributes=("name", "color"), relationships={"owner": ("name",)}),
    ),
    HfidCase(
        name="implementing-kind-with-the-generic-hfid",
        schema="dog",
        expected=HfidFields(attributes=("name",), relationships={"owner": ("name",)}),
    ),
    HfidCase(
        name="every-path-form-once-each",
        schema="hfid-paths",
        expected=HfidFields(attributes=("name",), relationships={"location": ("name", "code"), "building": ()}),
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in HFID_CASES])
def test_hfid_expansion(case: HfidCase, schemas: dict[str, MainSchemaTypesAPI]) -> None:
    assert expand_hfid(schemas[case.schema]) == case.expected


def test_marker_builds_the_error_for_a_queried_node() -> None:
    marker = OnlyMarker(only=("name",))

    error = marker.not_loaded_error(kind="InfraDevice", field="description")

    assert isinstance(error, FieldNotLoadedError)
    assert (error.kind, error.field, error.only, error.peer_of) == ("InfraDevice", "description", ["name"], None)


def test_marker_builds_the_error_for_a_peer() -> None:
    marker = OnlyMarker(only=("site",), peer_of="InfraDevice.site")

    error = marker.not_loaded_error(kind="InfraSite", field="description")

    assert (error.kind, error.field, error.only, error.peer_of) == (
        "InfraSite",
        "description",
        ["site"],
        "InfraDevice.site",
    )
