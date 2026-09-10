# ruff: noqa: PLC2701
"""Locating a `schema load` error in the submitted schema files from its `loc` path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from infrahub_sdk.ctl.schema import _resolve_attribute_label, get_node, valid_error_path
from tests.helpers.schema_load_errors import DEVICE, EXTENSION_SCHEMA, SCHEMA, TAG_EXTENSION, schema_files

# ---------------------------------------------------------------------------------------------------------------------
# valid_error_path / get_node / _resolve_attribute_label
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class LocPathCase:
    name: str
    loc_path: list[Any]
    expected: bool


LOC_PATH_CASES = [
    LocPathCase(name="node-field", loc_path=["body", "schemas", 0, "nodes", 0, "name"], expected=True),
    LocPathCase(
        name="node-attribute-field", loc_path=["body", "schemas", 0, "nodes", 0, "attributes", 0, "kind"], expected=True
    ),
    LocPathCase(name="generic-field", loc_path=["body", "schemas", 0, "generics", 0, "name"], expected=True),
    LocPathCase(
        name="extension-node", loc_path=["body", "schemas", 0, "extensions", "nodes", 0, "kind"], expected=True
    ),
    LocPathCase(
        name="extension-generic", loc_path=["body", "schemas", 0, "extensions", "generics", 0, "kind"], expected=True
    ),
    LocPathCase(
        name="extension-rel", loc_path=["body", "schemas", 0, "extensions", "relationships", 0, "peer"], expected=True
    ),
    LocPathCase(name="node-without-field", loc_path=["body", "schemas", 0, "nodes", 0], expected=False),
    LocPathCase(
        name="extension-node-without-field", loc_path=["body", "schemas", 0, "extensions", "nodes", 0], expected=False
    ),
    LocPathCase(
        name="top-level-relationships", loc_path=["body", "schemas", 0, "relationships", 0, "peer"], expected=False
    ),
    LocPathCase(name="string-node-index", loc_path=["body", "schemas", 0, "nodes", "0", "name"], expected=False),
    LocPathCase(
        name="string-extension-index",
        loc_path=["body", "schemas", 0, "extensions", "nodes", "0", "name"],
        expected=False,
    ),
    LocPathCase(name="root-field", loc_path=["body", "schemas", 0, "version"], expected=False),
    LocPathCase(name="schema-level", loc_path=["body", "schemas", 0], expected=False),
    LocPathCase(name="empty", loc_path=[], expected=False),
    LocPathCase(name="string-schema-index", loc_path=["body", "schemas", "x", "nodes", 0, "name"], expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in LOC_PATH_CASES])
def test_valid_error_path(case: LocPathCase) -> None:
    assert valid_error_path(loc_path=case.loc_path) is case.expected


def test_get_node_top_level_containers() -> None:
    files = schema_files(SCHEMA)
    assert get_node(schemas_data=files, schema_index=0, node_index=0) == DEVICE
    assert get_node(schemas_data=files, schema_index=0, node_index=0, container="generics") == {
        "name": "Generic",
        "namespace": "Infra",
    }


def test_get_node_extension_containers() -> None:
    files = schema_files(EXTENSION_SCHEMA)
    assert get_node(schemas_data=files, schema_index=0, node_index=0, is_extension=True) == TAG_EXTENSION
    generic = get_node(schemas_data=files, schema_index=0, node_index=0, container="generics", is_extension=True)
    assert generic == {"kind": "CoreNode", "label": 1}
    rel = get_node(schemas_data=files, schema_index=0, node_index=0, container="relationships", is_extension=True)
    assert rel == {"name": "site", "peer": 1}


@dataclass
class MissingNodeCase:
    name: str
    kwargs: dict[str, Any]
    schemas: list[dict[str, Any]]


MISSING_NODE_CASES = [
    MissingNodeCase(name="schema-index-out-of-range", kwargs={"schema_index": 1, "node_index": 0}, schemas=[SCHEMA]),
    MissingNodeCase(name="node-index-out-of-range", kwargs={"schema_index": 0, "node_index": 5}, schemas=[SCHEMA]),
    MissingNodeCase(
        name="no-extensions-key", kwargs={"schema_index": 0, "node_index": 0, "is_extension": True}, schemas=[SCHEMA]
    ),
    MissingNodeCase(
        name="no-container",
        kwargs={"schema_index": 0, "node_index": 0, "container": "generics"},
        schemas=[{"nodes": [DEVICE]}],
    ),
    MissingNodeCase(name="no-schemas", kwargs={"schema_index": 0, "node_index": 0}, schemas=[]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in MISSING_NODE_CASES])
def test_get_node_returns_none_when_missing(case: MissingNodeCase) -> None:
    assert get_node(schemas_data=schema_files(*case.schemas), **case.kwargs) is None


ELEMENTS: list[Any] = [
    {"name": "a", "kind": "Text", "min_value": 0},
    {"name": "b", "kind": "Number"},
    "not-a-dict",
    {"kind": "X"},
]


@dataclass
class LabelCase:
    name: str
    attribute: Any
    expected: str | None


LABEL_CASES = [
    LabelCase(name="index-first", attribute=0, expected="a"),
    LabelCase(name="index-second", attribute=1, expected="b"),
    LabelCase(name="index-on-non-dict-item", attribute=2, expected=None),
    LabelCase(name="index-on-element-without-name", attribute=3, expected=None),
    LabelCase(name="index-out-of-range", attribute=4, expected=None),
    LabelCase(name="negative-index", attribute=-1, expected=None),
    LabelCase(name="field-name-found-on-first", attribute="min_value", expected="a"),
    LabelCase(name="field-name-found-on-several-returns-first", attribute="kind", expected="a"),
    LabelCase(name="field-name-not-found", attribute="optional", expected=None),
    LabelCase(name="field-name-is-name", attribute="name", expected="a"),
    LabelCase(name="unsupported-type", attribute=None, expected=None),
    LabelCase(name="float-index", attribute=1.0, expected=None),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in LABEL_CASES])
def test_resolve_attribute_label(case: LabelCase) -> None:
    assert _resolve_attribute_label(error_data=ELEMENTS, attribute=case.attribute) == case.expected


def test_resolve_attribute_label_empty_collection() -> None:
    assert _resolve_attribute_label(error_data=[], attribute=0) is None
    assert _resolve_attribute_label(error_data=[], attribute="kind") is None


def test_resolve_attribute_label_field_name_skips_none_values() -> None:
    elements = [{"name": "a", "optional": None}, {"name": "b", "optional": False}]
    assert _resolve_attribute_label(error_data=elements, attribute="optional") == "b"
