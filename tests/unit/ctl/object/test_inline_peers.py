"""Unit tests for ``infrahub_sdk.ctl.object.inline_peers``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pytest

from infrahub_sdk.ctl.object.inline_peers import (
    raise_if_set_edits_inline_peers,
    raise_if_set_names_inline_peers_by_reference,
)
from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI


def _pool_schema(relationship: dict[str, Any]) -> NodeSchemaAPI:
    data: dict[str, Any] = {
        "name": "NumberPool",
        "namespace": "Core",
        "attributes": [{"name": "name", "kind": "Text", "unique": True}],
        "relationships": [relationship],
    }
    return NodeSchema(**data).convert_api()


CREATE_REFUSAL = re.escape(
    "'ranges' cannot be set with --set to a reference, because the mutation takes the fields of a "
    "CoreNumberPoolRange and not a reference to one. Pass the fields of every CoreNumberPoolRange "
    "instead, as a JSON list of objects."
)

UPDATE_REFUSAL = re.escape(
    "'ranges' cannot be changed with --set, because the mutation takes the fields of a CoreNumberPoolRange "
    "and not a reference to one. To set the complete list, run infrahubctl object create with it, which "
    "upserts the node. To add, change or delete one, run infrahubctl object create, update or delete on the "
    "CoreNumberPoolRange node itself."
)


def _ranges_schema() -> NodeSchemaAPI:
    return _pool_schema(
        {"name": "ranges", "peer": "CoreNumberPoolRange", "cardinality": "many", "identifier": "numberpool__range"}
    )


def _allowed_ranges_schema() -> NodeSchemaAPI:
    return _pool_schema(
        {
            "name": "allowed_ranges",
            "peer": "CoreNumberPoolRange",
            "cardinality": "many",
            "identifier": "numberpool__allowed_range",
        }
    )


@dataclass
class ReferenceCase:
    name: str
    value: Any


REFERENCE_CASES = [
    ReferenceCase(name="single-hfid", value="range-1"),
    ReferenceCase(name="list-of-hfids", value=["range-1", "range-2"]),
    ReferenceCase(name="list-of-hfid-parts", value=[["Core", "range-1"]]),
    ReferenceCase(name="uuid", value="550e8400-e29b-41d4-a716-446655440000"),
    ReferenceCase(name="object-holding-an-id", value=[{"id": "550e8400-e29b-41d4-a716-446655440000"}]),
    ReferenceCase(name="object-holding-an-hfid", value=[{"hfid": ["range-1"]}]),
    ReferenceCase(name="object-holding-a-node", value=[{"node": {"start": 1}}]),
    ReferenceCase(name="fields-and-a-reference", value=[{"start": 1, "end": 10}, {"id": "range-2"}]),
]

FIELDS_CASES = [
    ReferenceCase(name="one-range", value=[{"start": 1, "end": 10}]),
    ReferenceCase(name="two-ranges", value=[{"start": 1, "end": 10}, {"start": 20}]),
    ReferenceCase(name="no-range", value=[]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in REFERENCE_CASES])
def test_create_refuses_a_reference_to_a_peer_the_mutation_takes_as_fields(case: ReferenceCase) -> None:
    """The reference never reaches Infrahub, so the command says so instead of sending it."""
    with pytest.raises(FeatureNotSupportedError, match=CREATE_REFUSAL):
        raise_if_set_names_inline_peers_by_reference({"name": "VLAN IDs", "ranges": case.value}, _ranges_schema())


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in FIELDS_CASES])
def test_create_takes_the_fields_of_the_peers(case: ReferenceCase) -> None:
    """The fields are what the mutation takes, so --set carries them as they are."""
    raise_if_set_names_inline_peers_by_reference({"name": "VLAN IDs", "ranges": case.value}, _ranges_schema())


def test_create_takes_a_reference_for_another_relationship_to_the_same_peer() -> None:
    """Only the relationship Infrahub takes as fields is concerned, not every relationship to a range."""
    raise_if_set_names_inline_peers_by_reference({"allowed_ranges": "range-1"}, _allowed_ranges_schema())


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in REFERENCE_CASES + FIELDS_CASES])
def test_update_refuses_every_value_for_such_a_relationship(case: ReferenceCase) -> None:
    """An update sends the peers the node was fetched with, so any value given here is dropped."""
    with pytest.raises(FeatureNotSupportedError, match=UPDATE_REFUSAL):
        raise_if_set_edits_inline_peers({"name": "VLAN IDs", "ranges": case.value}, _ranges_schema())


def test_update_takes_another_relationship_to_the_same_peer() -> None:
    raise_if_set_edits_inline_peers({"allowed_ranges": "range-1"}, _allowed_ranges_schema())


def test_neither_guard_reads_the_schema_of_an_attribute() -> None:
    """An attribute has no relationship schema to read, and asking for one raises."""
    schema = _ranges_schema()

    raise_if_set_names_inline_peers_by_reference({"name": "VLAN IDs"}, schema)
    raise_if_set_edits_inline_peers({"name": "VLAN IDs"}, schema)
