# ruff: noqa: PLC2701
"""Rendering of the errors returned by `POST /api/schema/load` and `/api/schema/check`.

Two payload shapes are covered:

- field-level: one entry per failing field, located on that field (`body/schemas/0/nodes/0/namespace`);
- schema-level (Infrahub 1.11.0+): one `value_error` entry per schema, located on the schema entry
  (`body/schemas/0`), whose message joins every violation as `<field path>: <message> (received: <value>)`
  separated by `; `.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import typer
from rich.console import Console

from infrahub_sdk.ctl import schema as schema_module
from infrahub_sdk.ctl.schema import (
    _display_schema_warnings,
    _format_field_path,
    _is_complete_violation,
    _is_schema_level_error,
    _is_whole_received_value,
    _parse_field_path,
    _parse_received_value,
    _resolve_attribute_label,
    _split_contract_violations,
    display_schema_load_errors,
    get_node,
    handle_non_detail_errors,
    valid_error_path,
    validate_schema_content_and_exit,
)
from infrahub_sdk.schema import SchemaWarning, SchemaWarningKind, SchemaWarningType, validate_schema
from infrahub_sdk.yaml import SchemaFile

HEADER = "Unable to load the schema:\n"

# ---------------------------------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------------------------------


def _schema_files(*schemas: dict[str, Any]) -> list[SchemaFile]:
    return [SchemaFile(location=Path(f"schema-{index}.yml"), content=schema) for index, schema in enumerate(schemas)]


def _schema_level_error(message: str, schema_index: int = 0, err_type: str = "value_error") -> dict[str, Any]:
    return {"type": err_type, "loc": ["body", "schemas", schema_index], "msg": message, "input": {}}


def _field_level_error(
    loc: list[Any], msg: str = "Boom", err_type: str = "value_error", **extra: object
) -> dict[str, Any]:
    return {"type": err_type, "loc": loc, "msg": msg, **extra}


def _console() -> tuple[Console, StringIO]:
    output = StringIO()
    return Console(file=output, width=1000), output


def _render(errors: list[dict[str, Any]], *schemas: dict[str, Any]) -> str:
    console, output = _console()
    display_schema_load_errors(response={"detail": errors}, schemas_data=_schema_files(*schemas), output=console)
    return output.getvalue()


def _server_message(schema: dict[str, Any]) -> str:
    """Build the message exactly as an Infrahub 1.11 server does: `validate_schema(...).raise_for_status()`."""
    with pytest.raises(ValueError, match=r".+: .+") as exc:
        validate_schema(schema=schema).raise_for_status()
    return f"Value error, {exc.value}"


def _capture_console(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    """Replace the module console and return the buffer it writes to."""
    console, output = _console()
    monkeypatch.setattr(schema_module, "console", console)
    return output


DEVICE = {
    "name": "Device",
    "namespace": "Infra",
    "attributes": [
        {"name": "serial", "kind": "Text", "parameters": {"regex": "["}},
        {"name": "status", "kind": "Dropdown", "choices": [{"name": "active"}, {"name": "x", "label": 1}]},
    ],
    "relationships": [{"name": "site", "peer": "LocationSite"}, {"name": "tags", "peer": "BuiltinTag"}],
    "display_labels": ["name__value"],
}
SPEED_ATTRIBUTE = {"name": "speed", "kind": "Number", "made_up": True}
TAG_EXTENSION = {"kind": "BuiltinTag", "attributes": [SPEED_ATTRIBUTE]}
SCHEMA = {"version": "1.0", "nodes": [DEVICE], "generics": [{"name": "Generic", "namespace": "Infra"}]}
EXTENSION_SCHEMA = {
    "version": "1.0",
    "extensions": {
        "nodes": [TAG_EXTENSION],
        "generics": [{"kind": "CoreNode", "label": 1}],
        "relationships": [{"name": "site", "peer": 1}],
    },
}
VALID_NODE = {"name": "Device", "namespace": "Infra", "attributes": [{"name": "name", "kind": "Text"}]}
VALID_SCHEMA = {"version": "1.0", "nodes": [VALID_NODE]}
OTHER_SCHEMA = {"version": "1.0", "nodes": [{"name": "Other", "namespace": "Test"}]}
# Rejected offline by `validate_schema`: lowercase namespace and a too-short attribute name.
INVALID_SCHEMA = {
    "version": "1.0",
    "nodes": [{"name": "Device", "namespace": "infra", "attributes": [{"name": "n", "kind": "Text"}]}],
}


# ---------------------------------------------------------------------------------------------------------------------
# _split_contract_violations
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class SplitCase:
    name: str
    message: str
    expected: list[str]


SPLIT_CASES = [
    SplitCase(name="empty", message="", expected=[]),
    SplitCase(name="prefix-only", message="Value error, ", expected=[]),
    SplitCase(
        name="single-no-received", message="nodes[0].name: Field required", expected=["nodes[0].name: Field required"]
    ),
    SplitCase(
        name="prefix-stripped",
        message="Value error, nodes[0].name: Field required",
        expected=["nodes[0].name: Field required"],
    ),
    SplitCase(
        name="single-received",
        message="nodes[0].namespace: bad (received: 'x')",
        expected=["nodes[0].namespace: bad (received: 'x')"],
    ),
    SplitCase(
        name="two",
        message="a: m1 (received: 1); b: m2 (received: 2)",
        expected=["a: m1 (received: 1)", "b: m2 (received: 2)"],
    ),
    SplitCase(
        name="three-nested-path",
        message="a: m1 (received: 1); b: m2 (received: 2); c.d[3].e: m3 (received: 3)",
        expected=["a: m1 (received: 1)", "b: m2 (received: 2)", "c.d[3].e: m3 (received: 3)"],
    ),
    SplitCase(name="two-without-received-values", message="a: m1; b: m2", expected=["a: m1", "b: m2"]),
    SplitCase(
        name="missing-then-value",
        message="a: Field required; b: m2 (received: 2)",
        expected=["a: Field required", "b: m2 (received: 2)"],
    ),
    SplitCase(
        name="value-then-missing",
        message="a: m1 (received: 1); b: Field required",
        expected=["a: m1 (received: 1)", "b: Field required"],
    ),
    SplitCase(
        name="separator-inside-received-string",
        message="a: m (received: 'x; y: z'); b: m (received: 1)",
        expected=["a: m (received: 'x; y: z')", "b: m (received: 1)"],
    ),
    SplitCase(
        name="closing-paren-and-separator-inside-received-string",
        message="a: m (received: 'x); y: z'); b: m (received: 1)",
        expected=["a: m (received: 'x); y: z')", "b: m (received: 1)"],
    ),
    SplitCase(
        name="received-marker-inside-received-string",
        message="a: m (received: 'x (received: 1); y: z'); b: m (received: 1)",
        expected=["a: m (received: 'x (received: 1); y: z')", "b: m (received: 1)"],
    ),
    SplitCase(
        name="separator-inside-received-dict",
        message="a: m (received: {'d': 'x; y: z'}); b: m (received: 1)",
        expected=["a: m (received: {'d': 'x; y: z'})", "b: m (received: 1)"],
    ),
    SplitCase(
        name="two-separators-inside-received-list",
        message="a: m (received: ['x; y: z', 'w; v: u']); b: m (received: 1)",
        expected=["a: m (received: ['x; y: z', 'w; v: u'])", "b: m (received: 1)"],
    ),
    SplitCase(
        name="double-quoted-received-string",
        message='a: m (received: "it\'s; y: z"); b: m (received: 1)',
        expected=['a: m (received: "it\'s; y: z")', "b: m (received: 1)"],
    ),
    SplitCase(
        name="separator-inside-two-consecutive-received-strings",
        message="a: m (received: 'x; y: z'); b: m (received: 'p; q: r'); c: m (received: 3)",
        expected=["a: m (received: 'x; y: z')", "b: m (received: 'p; q: r')", "c: m (received: 3)"],
    ),
    SplitCase(
        name="unquoted-literals",
        message="a: m (received: None); b: m (received: True); c: m (received: -1.5)",
        expected=["a: m (received: None)", "b: m (received: True)", "c: m (received: -1.5)"],
    ),
    SplitCase(
        name="unquoted-non-literal-still-splits",
        message="a: m (received: nan); b: m (received: 1)",
        expected=["a: m (received: nan)", "b: m (received: 1)"],
    ),
    SplitCase(name="separator-not-followed-by-a-field-path", message="a: m; b", expected=["a: m; b"]),
    SplitCase(name="separator-without-space", message="a: m;b: m2", expected=["a: m;b: m2"]),
    SplitCase(name="semicolon-without-colon", message="a: m (received: 'x; y')", expected=["a: m (received: 'x; y')"]),
    SplitCase(
        name="multiline-message", message="a: line one\nline two; b: m", expected=["a: line one\nline two", "b: m"]
    ),
    SplitCase(
        name="unicode-received-string",
        message="a: m (received: 'é; ü: ñ'); b: m (received: 'ok')",
        expected=["a: m (received: 'é; ü: ñ')", "b: m (received: 'ok')"],
    ),
    SplitCase(
        name="rich-markup-inside-received-string",
        message="a: m (received: '[red]x[/red]; b: y'); b: m (received: 1)",
        expected=["a: m (received: '[red]x[/red]; b: y')", "b: m (received: 1)"],
    ),
    SplitCase(
        name="quoted-non-literal-degrades-to-one-entry",
        message="a: m (received: {'k': nan}); b: m (received: 1)",
        expected=["a: m (received: {'k': nan}); b: m (received: 1)"],
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in SPLIT_CASES])
def test_split_contract_violations(case: SplitCase) -> None:
    assert _split_contract_violations(message=case.message) == case.expected


def test_split_contract_violations_never_loses_text() -> None:
    """Whatever the split decisions, joining the parts back gives the original message."""
    message = "a: m (received: 'x; y: z'); b: m (received: {'k': 'v; w: u'}); c: Field required; d: m (received: 1)"
    parts = _split_contract_violations(message=message)
    assert "; ".join(parts) == message
    assert len(parts) == 4


# ---------------------------------------------------------------------------------------------------------------------
# _is_complete_violation / _is_whole_received_value
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class PredicateCase:
    name: str
    text: str
    expected: bool


COMPLETE_VIOLATION_CASES = [
    PredicateCase(name="no-received", text="a: Field required", expected=True),
    PredicateCase(name="int", text="a: m (received: 1)", expected=True),
    PredicateCase(name="string", text="a: m (received: 'x')", expected=True),
    PredicateCase(name="cut-inside-string", text="a: m (received: 'x", expected=False),
    PredicateCase(name="cut-inside-string-after-paren", text="a: m (received: 'x); y", expected=False),
    PredicateCase(name="dict", text="a: m (received: {'k': 'v'})", expected=True),
    PredicateCase(name="cut-inside-dict", text="a: m (received: {'k': 'v", expected=False),
    PredicateCase(name="unquoted-non-literal", text="a: m (received: nan)", expected=True),
    PredicateCase(name="no-field-path", text="not a violation", expected=False),
    PredicateCase(name="empty", text="", expected=False),
    PredicateCase(name="text-after-received-value-is-a-cut", text="a: m (received: 1) trailing", expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in COMPLETE_VIOLATION_CASES])
def test_is_complete_violation(case: PredicateCase) -> None:
    assert _is_complete_violation(text=case.text) is case.expected


WHOLE_RECEIVED_CASES = [
    PredicateCase(name="int", text="1", expected=True),
    PredicateCase(name="none", text="None", expected=True),
    PredicateCase(name="unquoted-non-literal", text="nan", expected=True),
    PredicateCase(name="string", text="'x'", expected=True),
    PredicateCase(name="double-quoted-string", text='"x"', expected=True),
    PredicateCase(name="unterminated-string", text="'x", expected=False),
    PredicateCase(name="two-values-glued", text="'x'); b: m (received: 'y'", expected=False),
    PredicateCase(name="list-of-strings", text="['a', 'b']", expected=True),
    PredicateCase(name="unterminated-list", text="['a', 'b'", expected=False),
    PredicateCase(name="quoted-non-literal", text="{'k': nan}", expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in WHOLE_RECEIVED_CASES])
def test_is_whole_received_value(case: PredicateCase) -> None:
    assert _is_whole_received_value(received=case.text) is case.expected


# ---------------------------------------------------------------------------------------------------------------------
# _parse_field_path / _format_field_path
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class ParsePathCase:
    name: str
    field: str
    expected: list[Any]


PARSE_PATH_CASES = [
    ParsePathCase(name="empty", field="", expected=[]),
    ParsePathCase(name="root-field", field="version", expected=["version"]),
    ParsePathCase(name="index", field="nodes[0]", expected=["nodes", 0]),
    ParsePathCase(name="multi-digit-index", field="nodes[12].name", expected=["nodes", 12, "name"]),
    ParsePathCase(
        name="nested",
        field="extensions.nodes[0].attributes[1].kind",
        expected=["extensions", "nodes", 0, "attributes", 1, "kind"],
    ),
    ParsePathCase(
        name="double-index",
        field="nodes[0].uniqueness_constraints[0][1]",
        expected=["nodes", 0, "uniqueness_constraints", 0, 1],
    ),
    ParsePathCase(name="leading-index", field="[0].name", expected=[0, "name"]),
    ParsePathCase(
        name="union-tag-kept",
        field="nodes[0].attributes[0].Text.name",
        expected=["nodes", 0, "attributes", 0, "Text", "name"],
    ),
    ParsePathCase(name="underscores", field="a_b.c_d", expected=["a_b", "c_d"]),
    ParsePathCase(name="digits-in-names", field="field2.sub3", expected=["field2", "sub3"]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in PARSE_PATH_CASES])
def test_parse_field_path(case: ParsePathCase) -> None:
    assert _parse_field_path(field=case.field) == case.expected


@dataclass
class FormatPathCase:
    name: str
    segments: list[Any]
    expected: str


FORMAT_PATH_CASES = [
    FormatPathCase(name="empty", segments=[], expected=""),
    FormatPathCase(name="single", segments=["name"], expected="name"),
    FormatPathCase(name="index", segments=["choices", 1], expected="choices[1]"),
    FormatPathCase(name="index-then-field", segments=["choices", 1, "label"], expected="choices[1].label"),
    FormatPathCase(name="dotted", segments=["parameters", "regex"], expected="parameters.regex"),
    FormatPathCase(name="bare-index", segments=[0], expected="[0]"),
    FormatPathCase(name="two-bare-indexes", segments=[0, 1], expected="[0][1]"),
    FormatPathCase(name="leading-union-tag-dropped", segments=["Text", "name"], expected="name"),
    FormatPathCase(name="trailing-union-tag-dropped", segments=["name", "Text"], expected="name"),
    FormatPathCase(name="only-union-tag", segments=["Text"], expected=""),
    FormatPathCase(
        name="acronym-union-tag-dropped", segments=["IPHost", "parameters", "regex"], expected="parameters.regex"
    ),
    FormatPathCase(
        name="union-tag-between-segments", segments=["choices", "Dropdown", 1, "label"], expected="choices[1].label"
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in FORMAT_PATH_CASES])
def test_format_field_path(case: FormatPathCase) -> None:
    assert _format_field_path(segments=case.segments) == case.expected


@pytest.mark.parametrize(
    "path", ["name", "nodes[0].name", "extensions.nodes[3].attributes[2].choices[1].label", "a[0][1].b"]
)
def test_field_path_round_trips_through_parse_and_format(path: str) -> None:
    assert _format_field_path(segments=_parse_field_path(field=path)) == path


# ---------------------------------------------------------------------------------------------------------------------
# _parse_received_value
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class ParseValueCase:
    name: str
    received: str
    expected: Any


PARSE_VALUE_CASES = [
    ParseValueCase(name="int", received="1", expected=1),
    ParseValueCase(name="negative-int", received="-1", expected=-1),
    ParseValueCase(name="float", received="1.5", expected=1.5),
    ParseValueCase(name="bool", received="True", expected=True),
    ParseValueCase(name="none", received="None", expected=None),
    ParseValueCase(name="string", received="'x'", expected="x"),
    ParseValueCase(name="double-quoted-string", received='"it\'s"', expected="it's"),
    ParseValueCase(name="empty-string", received="''", expected=""),
    ParseValueCase(name="list", received="[1, 'a']", expected=[1, "a"]),
    ParseValueCase(name="nested-dict", received="{'a': {'b': [1]}}", expected={"a": {"b": [1]}}),
    ParseValueCase(name="tuple", received="(1, 2)", expected=(1, 2)),
    ParseValueCase(name="non-literal-kept-verbatim", received="not a literal", expected="not a literal"),
    ParseValueCase(name="syntax-error-kept-verbatim", received="'unterminated", expected="'unterminated"),
    ParseValueCase(name="empty", received="", expected=""),
    ParseValueCase(name="enum-repr-kept-verbatim", received="<Kind.TEXT: 'Text'>", expected="<Kind.TEXT: 'Text'>"),
    ParseValueCase(name="nan-kept-verbatim", received="nan", expected="nan"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in PARSE_VALUE_CASES])
def test_parse_received_value(case: ParseValueCase) -> None:
    assert _parse_received_value(received=case.received) == case.expected


# ---------------------------------------------------------------------------------------------------------------------
# _is_schema_level_error
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class SchemaLevelCase:
    name: str
    error: dict[str, Any]
    loc_path: list[Any]
    expected: bool


SCHEMA_LEVEL_CASES = [
    SchemaLevelCase(
        name="match-first-schema", error={"type": "value_error"}, loc_path=["body", "schemas", 0], expected=True
    ),
    SchemaLevelCase(
        name="match-later-schema", error={"type": "value_error"}, loc_path=["body", "schemas", 7], expected=True
    ),
    SchemaLevelCase(
        name="wrong-type", error={"type": "extra_forbidden"}, loc_path=["body", "schemas", 0], expected=False
    ),
    SchemaLevelCase(name="no-type", error={}, loc_path=["body", "schemas", 0], expected=False),
    SchemaLevelCase(
        name="too-long", error={"type": "value_error"}, loc_path=["body", "schemas", 0, "nodes"], expected=False
    ),
    SchemaLevelCase(name="too-short", error={"type": "value_error"}, loc_path=["body", "schemas"], expected=False),
    SchemaLevelCase(name="empty-loc", error={"type": "value_error"}, loc_path=[], expected=False),
    SchemaLevelCase(
        name="string-index", error={"type": "value_error"}, loc_path=["body", "schemas", "0"], expected=False
    ),
    SchemaLevelCase(name="wrong-root", error={"type": "value_error"}, loc_path=["query", "schemas", 0], expected=False),
    SchemaLevelCase(
        name="wrong-container", error={"type": "value_error"}, loc_path=["body", "branch", 0], expected=False
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in SCHEMA_LEVEL_CASES])
def test_is_schema_level_error(case: SchemaLevelCase) -> None:
    assert _is_schema_level_error(error=case.error, loc_path=case.loc_path) is case.expected


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
    files = _schema_files(SCHEMA)
    assert get_node(schemas_data=files, schema_index=0, node_index=0) == DEVICE
    assert get_node(schemas_data=files, schema_index=0, node_index=0, container="generics") == {
        "name": "Generic",
        "namespace": "Infra",
    }


def test_get_node_extension_containers() -> None:
    files = _schema_files(EXTENSION_SCHEMA)
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
    assert get_node(schemas_data=_schema_files(*case.schemas), **case.kwargs) is None


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


# ---------------------------------------------------------------------------------------------------------------------
# handle_non_detail_errors
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class NonDetailCase:
    name: str
    response: dict[str, Any]
    expected: str


NON_DETAIL_CASES = [
    NonDetailCase(name="error-key", response={"error": "Boom"}, expected="  Boom\n"),
    NonDetailCase(
        name="errors-list", response={"errors": [{"message": "one"}, {"message": "two"}]}, expected="  one\n  two\n"
    ),
    NonDetailCase(name="empty-errors-list", response={"errors": []}, expected=""),
    NonDetailCase(name="errors-without-message", response={"errors": [{"no_message": 1}]}, expected="  None\n"),
    NonDetailCase(name="unknown-shape", response={"something": "else"}, expected="  '{'something': 'else'}'\n"),
    NonDetailCase(name="empty-response", response={}, expected="  '{}'\n"),
    NonDetailCase(
        name="error-wins-over-errors",
        response={"error": "Boom", "errors": [{"message": "ignored"}]},
        expected="  Boom\n",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in NON_DETAIL_CASES])
def test_handle_non_detail_errors(case: NonDetailCase) -> None:
    console, output = _console()
    handle_non_detail_errors(response=case.response, output=console)
    assert output.getvalue() == case.expected


def test_handle_non_detail_errors_defaults_to_module_console(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _capture_console(monkeypatch)
    handle_non_detail_errors(response={"error": "Boom"})
    assert output.getvalue() == "  Boom\n"


# ---------------------------------------------------------------------------------------------------------------------
# display_schema_load_errors: response shapes
# ---------------------------------------------------------------------------------------------------------------------


def test_display_no_detail_delegates_to_non_detail_rendering() -> None:
    console, output = _console()
    display_schema_load_errors(response={"error": "Boom"}, schemas_data=[], output=console)
    assert output.getvalue() == f"{HEADER}  Boom\n"


def test_display_empty_detail_prints_only_the_header() -> None:
    assert _render([], SCHEMA) == HEADER


def test_display_defaults_to_module_console(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _capture_console(monkeypatch)
    display_schema_load_errors(response={"detail": []}, schemas_data=[])
    assert output.getvalue() == HEADER


@dataclass
class SkippedErrorCase:
    name: str
    error: dict[str, Any]


SKIPPED_ERROR_CASES = [
    SkippedErrorCase(name="missing-loc", error={"type": "value_error", "msg": "no loc"}),
    SkippedErrorCase(name="not-a-schema-location", error=_field_level_error(loc=["body", "branch"])),
    SkippedErrorCase(
        name="root-field-not-schema-level-type", error=_field_level_error(loc=["body", "schemas", 0, "version"])
    ),
    SkippedErrorCase(name="node-without-field", error=_field_level_error(loc=["body", "schemas", 0, "nodes", 0])),
    SkippedErrorCase(
        name="unknown-container", error=_field_level_error(loc=["body", "schemas", 0, "relationships", 0, "peer"])
    ),
    SkippedErrorCase(
        name="schema-level-wrong-type", error=_field_level_error(loc=["body", "schemas", 0], err_type="missing")
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in SKIPPED_ERROR_CASES])
def test_display_skips_locations_it_cannot_attribute(case: SkippedErrorCase) -> None:
    assert _render([case.error], SCHEMA) == HEADER


# ---------------------------------------------------------------------------------------------------------------------
# display_schema_load_errors: field-level errors (every server version)
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class FieldLevelCase:
    name: str
    loc: list[Any]
    expected_line: str
    extra: dict[str, Any] = field(default_factory=dict)
    schema: dict[str, Any] = field(default_factory=lambda: SCHEMA)


FIELD_LEVEL_CASES = [
    FieldLevelCase(
        name="node-direct-field",
        loc=["body", "schemas", 0, "nodes", 0, "namespace"],
        extra={"input": "infra"},
        expected_line="Node: InfraDevice | namespace (infra) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="attribute-as-a-whole",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 0],
        extra={"input": {"name": "serial"}},
        expected_line="Node: InfraDevice | Attribute: serial ({'name': 'serial'}) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="attribute-field",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 1, "kind"],
        extra={"input": "Dropdown"},
        expected_line="Node: InfraDevice | Attribute: status | kind (Dropdown) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="attribute-nested-field",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 0, "parameters", "regex"],
        extra={"input": "["},
        expected_line="Node: InfraDevice | Attribute: serial | parameters.regex ([) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="attribute-choice-field",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 1, "choices", 1, "label"],
        extra={"input": 1},
        expected_line="Node: InfraDevice | Attribute: status | choices[1].label (1) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="attribute-union-tag-dropped",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 0, "Text", "name"],
        extra={"input": "serial"},
        expected_line="Node: InfraDevice | Attribute: serial | name (serial) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="legacy-attribute-located-by-field-name",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", "parameters"],
        extra={"input": {"regex": "["}},
        expected_line="Node: InfraDevice | Attribute: serial ({'regex': '['}) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="attribute-index-out-of-range",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 5, "kind"],
        extra={"input": "X"},
        expected_line="Node: InfraDevice | Attribute: None | kind (X) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="relationship-field",
        loc=["body", "schemas", 0, "nodes", 0, "relationships", 1, "peer"],
        extra={"input": "BuiltinTag"},
        expected_line="Node: InfraDevice | Relationship: tags | peer (BuiltinTag) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="relationship-as-a-whole",
        loc=["body", "schemas", 0, "nodes", 0, "relationships", 0],
        extra={"input": {}},
        expected_line="Node: InfraDevice | Relationship: site ({}) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="scalar-list-item",
        loc=["body", "schemas", 0, "nodes", 0, "display_labels", 0],
        extra={"input": 1},
        expected_line="Node: InfraDevice | display_labels[0] (1) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="nested-list-item",
        loc=["body", "schemas", 0, "nodes", 0, "uniqueness_constraints", 0, 1],
        extra={"input": 1},
        expected_line="Node: InfraDevice | uniqueness_constraints[0][1] (1) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="generic-direct-field",
        loc=["body", "schemas", 0, "generics", 0, "name"],
        extra={"input": "Generic"},
        expected_line="Node: InfraGeneric | name (Generic) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="explicit-null-input-is-shown",
        loc=["body", "schemas", 0, "nodes", 0, "namespace"],
        extra={"input": None},
        expected_line="Node: InfraDevice | namespace (None) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="no-input-key-shows-no-value",
        loc=["body", "schemas", 0, "nodes", 0, "namespace"],
        expected_line="Node: InfraDevice | namespace | Boom (value_error)",
    ),
    FieldLevelCase(
        name="rich-markup-in-input-is-literal",
        loc=["body", "schemas", 0, "nodes", 0, "namespace"],
        extra={"input": "[red]x[/red]"},
        expected_line="Node: InfraDevice | namespace ([red]x[/red]) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="extension-node-attribute-field",
        loc=["body", "schemas", 0, "extensions", "nodes", 0, "attributes", 0, "made_up"],
        extra={"input": True},
        schema=EXTENSION_SCHEMA,
        expected_line="Node: BuiltinTag (extensions/nodes) | Attribute: speed | made_up (True) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="extension-generic-field",
        loc=["body", "schemas", 0, "extensions", "generics", 0, "label"],
        extra={"input": 1},
        schema=EXTENSION_SCHEMA,
        expected_line="Node: CoreNode (extensions/generics) | label (1) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="extension-relationship-labelled-by-name",
        loc=["body", "schemas", 0, "extensions", "relationships", 0, "peer"],
        extra={"input": 1},
        schema=EXTENSION_SCHEMA,
        expected_line="Node: site (extensions/relationships) | peer (1) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="extension-without-kind-or-name-has-empty-label",
        loc=["body", "schemas", 0, "extensions", "nodes", 0, "namespace"],
        extra={"input": "X"},
        schema={"extensions": {"nodes": [{"namespace": "X"}]}},
        expected_line="Node:  (extensions/nodes) | namespace (X) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="node-without-namespace-or-name-renders-none",
        loc=["body", "schemas", 0, "nodes", 0, "label"],
        extra={"input": "x"},
        schema={"nodes": [{"label": "x"}]},
        expected_line="Node: NoneNone | label (x) | Boom (value_error)",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in FIELD_LEVEL_CASES])
def test_display_field_level_error(case: FieldLevelCase) -> None:
    error = _field_level_error(loc=case.loc, **case.extra)
    assert _render([error], case.schema) == f"{HEADER}  {case.expected_line}\n"


def test_display_field_level_error_without_msg_or_type() -> None:
    error = {"loc": ["body", "schemas", 0, "nodes", 0, "namespace"], "input": "x"}
    assert _render([error], SCHEMA) == f"{HEADER}  Node: InfraDevice | namespace (x) | No error message (unknown)\n"


def test_display_field_level_error_type_is_echoed() -> None:
    error = _field_level_error(loc=["body", "schemas", 0, "nodes", 0, "namespace"], err_type="string_pattern_mismatch")
    assert _render([error], SCHEMA) == (f"{HEADER}  Node: InfraDevice | namespace | Boom (string_pattern_mismatch)\n")


@dataclass
class NotFoundCase:
    name: str
    loc: list[Any]
    schemas: list[dict[str, Any]]


NOT_FOUND_CASES = [
    NotFoundCase(name="node-index-out-of-range", loc=["body", "schemas", 0, "nodes", 3, "name"], schemas=[SCHEMA]),
    NotFoundCase(name="schema-index-out-of-range", loc=["body", "schemas", 1, "nodes", 0, "name"], schemas=[SCHEMA]),
    NotFoundCase(name="no-schema-files", loc=["body", "schemas", 0, "nodes", 0, "name"], schemas=[]),
    NotFoundCase(name="no-extensions", loc=["body", "schemas", 0, "extensions", "nodes", 0, "kind"], schemas=[SCHEMA]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in NOT_FOUND_CASES])
def test_display_node_not_found(case: NotFoundCase) -> None:
    assert _render([_field_level_error(loc=case.loc)], *case.schemas) == f"{HEADER}Node data not found.\n"


def test_display_several_field_level_errors_keep_their_order() -> None:
    errors = [
        _field_level_error(loc=["body", "schemas", 0, "nodes", 0, "namespace"], msg="first", input=1),
        _field_level_error(loc=["body", "schemas", 0, "nodes", 5, "namespace"], msg="lost"),
        _field_level_error(loc=["body", "schemas", 0, "nodes", 0, "attributes", 1, "kind"], msg="second", input=2),
    ]
    assert _render(errors, SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (1) | first (value_error)\n"
        "Node data not found.\n"
        "  Node: InfraDevice | Attribute: status | kind (2) | second (value_error)\n"
    )


# ---------------------------------------------------------------------------------------------------------------------
# display_schema_load_errors: schema-level errors (Infrahub 1.11.0+)
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class SchemaLevelRenderCase:
    name: str
    message: str
    expected_line: str
    schema: dict[str, Any] = field(default_factory=lambda: SCHEMA)


SCHEMA_LEVEL_RENDER_CASES = [
    SchemaLevelRenderCase(
        name="node-direct-field",
        message="Value error, nodes[0].namespace: bad (received: 'infra')",
        expected_line="Node: InfraDevice | namespace (infra) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="without-value-error-prefix",
        message="nodes[0].namespace: bad (received: 'infra')",
        expected_line="Node: InfraDevice | namespace (infra) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="missing-field-has-no-value",
        message="Value error, nodes[0].name: Field required",
        expected_line="Node: InfraDevice | name | Field required (value_error)",
    ),
    SchemaLevelRenderCase(
        name="attribute-field",
        message="Value error, nodes[0].attributes[1].kind: bad (received: 'Dropdown')",
        expected_line="Node: InfraDevice | Attribute: status | kind (Dropdown) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="attribute-nested-field",
        message="Value error, nodes[0].attributes[0].parameters.regex: bad (received: '[')",
        expected_line="Node: InfraDevice | Attribute: serial | parameters.regex ([) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="attribute-choice-field",
        message="Value error, nodes[0].attributes[1].choices[1].label: bad (received: 1)",
        expected_line="Node: InfraDevice | Attribute: status | choices[1].label (1) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="attribute-union-tag-dropped",
        message="Value error, nodes[0].attributes[0].Text.name: bad (received: 'serial')",
        expected_line="Node: InfraDevice | Attribute: serial | name (serial) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="attribute-as-a-whole",
        message="Value error, nodes[0].attributes[1]: bad (received: {'name': 'status'})",
        expected_line="Node: InfraDevice | Attribute: status ({'name': 'status'}) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="attribute-list-field",
        message="Value error, nodes[0].attributes[1].choices: bad (received: [{'name': 'active'}])",
        expected_line="Node: InfraDevice | Attribute: status | choices ([{'name': 'active'}]) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="relationship-field",
        message="Value error, nodes[0].relationships[1].peer: bad (received: 'BuiltinTag')",
        expected_line="Node: InfraDevice | Relationship: tags | peer (BuiltinTag) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="scalar-list-item",
        message="Value error, nodes[0].display_labels[0]: bad (received: 1)",
        expected_line="Node: InfraDevice | display_labels[0] (1) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="explicit-null-value",
        message="Value error, nodes[0].namespace: bad (received: None)",
        expected_line="Node: InfraDevice | namespace (None) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="empty-string-value",
        message="Value error, nodes[0].namespace: bad (received: '')",
        expected_line="Node: InfraDevice | namespace () | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="separator-inside-value",
        message="Value error, nodes[0].namespace: bad (received: 'a; b: c')",
        expected_line="Node: InfraDevice | namespace (a; b: c) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="received-marker-inside-value",
        message="Value error, nodes[0].namespace: bad (received: 'x (received: 1)')",
        expected_line="Node: InfraDevice | namespace (x (received: 1)) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="rich-markup-in-value-is-literal",
        message="Value error, nodes[0].namespace: bad (received: '[red]x[/red]')",
        expected_line="Node: InfraDevice | namespace ([red]x[/red]) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="unicode-value",
        message="Value error, nodes[0].namespace: bad (received: 'Ünïcødé')",
        expected_line="Node: InfraDevice | namespace (Ünïcødé) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="message-with-quotes-and-brackets",
        message="Value error, nodes[0].namespace: String should match pattern '^[A-Z][a-z0-9]+$' (received: 'infra')",
        expected_line=(
            "Node: InfraDevice | namespace (infra) | String should match pattern '^[A-Z][a-z0-9]+$' (value_error)"
        ),
    ),
    SchemaLevelRenderCase(
        name="non-literal-value-shown-verbatim",
        message="Value error, nodes[0].namespace: bad (received: <Kind.TEXT: 'Text'>)",
        expected_line="Node: InfraDevice | namespace (<Kind.TEXT: 'Text'>) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="generic-field",
        message="Value error, generics[0].name: bad (received: 'Generic')",
        expected_line="Node: InfraGeneric | name (Generic) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="attribute-index-out-of-range",
        message="Value error, nodes[0].attributes[5].kind: bad (received: 'X')",
        expected_line="Node: InfraDevice | Attribute: None | kind (X) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="extension-node-attribute-field",
        message="Value error, extensions.nodes[0].attributes[0].made_up: bad (received: True)",
        schema=EXTENSION_SCHEMA,
        expected_line="Node: BuiltinTag (extensions/nodes) | Attribute: speed | made_up (True) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="extension-node-direct-field",
        message="Value error, extensions.nodes[0].namespace: bad (received: 'X')",
        schema=EXTENSION_SCHEMA,
        expected_line="Node: BuiltinTag (extensions/nodes) | namespace (X) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="extension-generic-field",
        message="Value error, extensions.generics[0].label: bad (received: 1)",
        schema=EXTENSION_SCHEMA,
        expected_line="Node: CoreNode (extensions/generics) | label (1) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="extension-relationship-field",
        message="Value error, extensions.relationships[0].peer: bad (received: 1)",
        schema=EXTENSION_SCHEMA,
        expected_line="Node: site (extensions/relationships) | peer (1) | bad (value_error)",
    ),
    SchemaLevelRenderCase(
        name="second-node-of-the-same-schema",
        message="Value error, nodes[1].bogus: Unknown field (received: 1)",
        schema={"version": "1.0", "nodes": [DEVICE, {"name": "Site", "namespace": "Location", "bogus": 1}]},
        expected_line="Node: LocationSite | bogus (1) | Unknown field (value_error)",
    ),
    # Violations that do not sit on a node are printed verbatim with their schema file.
    SchemaLevelRenderCase(
        name="verbatim-root-missing-field",
        message="Value error, version: Field required",
        expected_line="Schema: schema-0.yml | version: Field required (value_error)",
    ),
    SchemaLevelRenderCase(
        name="verbatim-root-unknown-field",
        message="Value error, bogus: Unknown field (received: 1)",
        expected_line="Schema: schema-0.yml | bogus: Unknown field (received: 1) (value_error)",
    ),
    SchemaLevelRenderCase(
        name="verbatim-container-level-field",
        message="Value error, extensions.generics: Unknown field (received: [{'kind': 'CoreNode'}])",
        expected_line=(
            "Schema: schema-0.yml | extensions.generics: Unknown field (received: [{'kind': 'CoreNode'}]) (value_error)"
        ),
    ),
    SchemaLevelRenderCase(
        name="verbatim-node-without-field",
        message="Value error, nodes[0]: Boom (received: {})",
        expected_line="Schema: schema-0.yml | nodes[0]: Boom (received: {}) (value_error)",
    ),
    SchemaLevelRenderCase(
        name="verbatim-container-not-a-list",
        message="Value error, nodes: Input should be a valid list (received: 'x')",
        expected_line="Schema: schema-0.yml | nodes: Input should be a valid list (received: 'x') (value_error)",
    ),
    SchemaLevelRenderCase(
        name="verbatim-message-without-field-path",
        message="Value error, Something went wrong",
        expected_line="Schema: schema-0.yml | Something went wrong (value_error)",
    ),
    SchemaLevelRenderCase(
        name="verbatim-rich-markup",
        message="Value error, [bold]markup[/bold] stays literal",
        expected_line="Schema: schema-0.yml | [bold]markup[/bold] stays literal (value_error)",
    ),
    SchemaLevelRenderCase(
        name="verbatim-top-level-relationships-is-not-a-node-container",
        message="Value error, relationships[0].peer: bad (received: 'X')",
        expected_line="Schema: schema-0.yml | relationships[0].peer: bad (received: 'X') (value_error)",
    ),
    SchemaLevelRenderCase(
        name="verbatim-bare-index-path",
        message="Value error, [0].name: bad (received: 'x')",
        expected_line="Schema: schema-0.yml | [0].name: bad (received: 'x') (value_error)",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in SCHEMA_LEVEL_RENDER_CASES])
def test_display_schema_level_violation(case: SchemaLevelRenderCase) -> None:
    assert _render([_schema_level_error(case.message)], case.schema) == f"{HEADER}  {case.expected_line}\n"


def test_display_schema_level_violation_on_missing_node_reports_not_found() -> None:
    message = "Value error, nodes[4].name: bad (received: 'x')"
    assert _render([_schema_level_error(message)], SCHEMA) == f"{HEADER}Node data not found.\n"


def test_display_schema_level_error_uses_its_type_on_every_line() -> None:
    message = "a: Boom; nodes[0].namespace: bad (received: 1)"
    assert _render([_schema_level_error(message, err_type="value_error")], SCHEMA) == (
        f"{HEADER}"
        "  Schema: schema-0.yml | a: Boom (value_error)\n"
        "  Node: InfraDevice | namespace (1) | bad (value_error)\n"
    )


def test_display_schema_level_error_without_msg_prints_only_the_header() -> None:
    error = {"type": "value_error", "loc": ["body", "schemas", 0]}
    assert _render([error], SCHEMA) == HEADER


def test_display_schema_level_error_with_empty_msg_prints_only_the_header() -> None:
    assert _render([_schema_level_error("")], SCHEMA) == HEADER


def test_display_schema_level_error_picks_the_schema_file_by_index() -> None:
    message = "Value error, nodes[0].namespace: bad (received: 'Test')"
    assert _render([_schema_level_error(message, schema_index=1)], SCHEMA, OTHER_SCHEMA) == (
        f"{HEADER}  Node: TestOther | namespace (Test) | bad (value_error)\n"
    )


def test_display_schema_level_verbatim_violation_names_the_right_schema_file() -> None:
    message = "Value error, version: Field required"
    assert _render([_schema_level_error(message, schema_index=1)], SCHEMA, SCHEMA) == (
        f"{HEADER}  Schema: schema-1.yml | version: Field required (value_error)\n"
    )


def test_display_schema_level_verbatim_violation_with_unknown_schema_index() -> None:
    message = "Value error, version: Field required"
    assert _render([_schema_level_error(message, schema_index=3)], SCHEMA) == (
        f"{HEADER}  Schema: schema 3 | version: Field required (value_error)\n"
    )


def test_display_schema_level_violations_are_rendered_in_order_across_nodes() -> None:
    message = (
        "Value error, nodes[0].namespace: first (received: 'infra'); "
        "generics[0].name: second (received: 'Generic'); "
        "version: third; "
        "nodes[0].attributes[0].parameters.regex: fourth (received: '['); "
        "nodes[0].relationships[0].peer: fifth (received: 'x; y: z')"
    )
    assert _render([_schema_level_error(message)], SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (infra) | first (value_error)\n"
        "  Node: InfraGeneric | name (Generic) | second (value_error)\n"
        "  Schema: schema-0.yml | version: third (value_error)\n"
        "  Node: InfraDevice | Attribute: serial | parameters.regex ([) | fourth (value_error)\n"
        "  Node: InfraDevice | Relationship: site | peer (x; y: z) | fifth (value_error)\n"
    )


def test_display_mixes_schema_level_and_field_level_errors() -> None:
    errors = [
        _field_level_error(loc=["body", "schemas", 0, "nodes", 0, "namespace"], msg="field-level", input="infra"),
        _schema_level_error("Value error, generics[0].name: schema-level (received: 'Generic')"),
        _field_level_error(loc=["body", "branch"], msg="ignored"),
    ]
    assert _render(errors, SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (infra) | field-level (value_error)\n"
        "  Node: InfraGeneric | name (Generic) | schema-level (value_error)\n"
    )


def test_display_one_schema_level_error_per_schema() -> None:
    errors = [
        _schema_level_error("Value error, nodes[0].namespace: bad (received: 'infra')", schema_index=0),
        _schema_level_error("Value error, nodes[0].name: bad (received: 'Other')", schema_index=1),
    ]
    assert _render(errors, SCHEMA, OTHER_SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (infra) | bad (value_error)\n"
        "  Node: TestOther | name (Other) | bad (value_error)\n"
    )


# ---------------------------------------------------------------------------------------------------------------------
# Contract with the server: the message is built by the SDK validator the server relies on
# ---------------------------------------------------------------------------------------------------------------------


def test_contract_invalid_namespace_and_short_attribute_name() -> None:
    assert _render([_schema_level_error(_server_message(INVALID_SCHEMA))], INVALID_SCHEMA) == (
        f"{HEADER}"
        "  Node: infraDevice | namespace (infra) | String should match pattern '^[A-Z][a-z0-9]+$' (value_error)\n"
        "  Node: infraDevice | Attribute: n | name (n) | String should have at least 3 characters (value_error)\n"
    )


def test_contract_unknown_field_on_extension_attribute_with_markup_in_value() -> None:
    attribute = {**SPEED_ATTRIBUTE, "made_up": "[red]x"}
    schema = {"version": "1.0", "extensions": {"nodes": [{**TAG_EXTENSION, "attributes": [attribute]}]}}
    assert _render([_schema_level_error(_server_message(schema))], schema) == (
        f"{HEADER}"
        "  Node: BuiltinTag (extensions/nodes) | Attribute: speed | made_up ([red]x) | "
        "Unknown field, it is not part of the schema (value_error)\n"
    )


def test_contract_description_containing_a_separator_is_kept_whole() -> None:
    node = {**VALID_NODE, "namespace": "infra", "description": "Uplinks; note: keep"}
    schema = {"version": "1.0", "nodes": [node]}
    message = _server_message(schema)
    schema_with_bad_description = {"version": "1.0", "nodes": [{**node, "description": "x" * 300}]}
    long_message = _server_message(schema_with_bad_description)

    assert _render([_schema_level_error(message)], schema) == (
        f"{HEADER}  Node: infraDevice | namespace (infra) | String should match pattern '^[A-Z][a-z0-9]+$' (value_error)\n"
    )
    assert _render([_schema_level_error(long_message)], schema_with_bad_description).count("\n") == 3


def test_contract_missing_required_field_shows_no_value() -> None:
    node = {key: value for key, value in VALID_NODE.items() if key != "name"}
    schema = {"version": "1.0", "nodes": [node]}
    assert _render([_schema_level_error(_server_message(schema))], schema) == (
        f"{HEADER}  Node: InfraNone | name | Field required (value_error)\n"
    )


def test_contract_unknown_root_field_is_verbatim() -> None:
    schema = {"version": "1.0", "bogus": 1, "nodes": []}
    assert _render([_schema_level_error(_server_message(schema))], schema) == (
        f"{HEADER}  Schema: schema-0.yml | bogus: Unknown field, it is not part of the schema (received: 1) (value_error)\n"
    )


# ---------------------------------------------------------------------------------------------------------------------
# validate_schema_content_and_exit / _display_schema_warnings
# ---------------------------------------------------------------------------------------------------------------------


def test_validate_schema_content_valid_schemas_print_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _capture_console(monkeypatch)
    validate_schema_content_and_exit(schemas=_schema_files(VALID_SCHEMA, VALID_SCHEMA))
    assert not output.getvalue()


def test_validate_schema_content_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _capture_console(monkeypatch)
    validate_schema_content_and_exit(schemas=[])
    assert not output.getvalue()


def test_validate_schema_content_reports_every_error_of_every_invalid_file_then_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markup = {"version": "1.0", "bogus": "[red]x[/red]", "nodes": []}
    output = _capture_console(monkeypatch)

    with pytest.raises(typer.Exit) as exc:
        validate_schema_content_and_exit(schemas=_schema_files(VALID_SCHEMA, INVALID_SCHEMA, markup))

    assert exc.value.exit_code == 1
    assert output.getvalue() == (
        "Schema not valid, found '2' error(s) in schema-1.yml\n"
        "  nodes[0].namespace: String should match pattern '^[A-Z][a-z0-9]+$' (received: 'infra')\n"
        "  nodes[0].attributes[0].Text.name: String should have at least 3 characters (received: 'n')\n"
        "Schema not valid, found '1' error(s) in schema-2.yml\n"
        "  bogus: Unknown field, it is not part of the schema (received: '[red]x[/red]')\n"
    )


@dataclass
class WarningCase:
    name: str
    warning: SchemaWarning
    expected: str


WARNING_CASES = [
    WarningCase(
        name="no-kind",
        warning=SchemaWarning(type=SchemaWarningType.DEPRECATION, message="gone soon"),
        expected=" deprecation: gone soon\n",
    ),
    WarningCase(
        name="one-kind",
        warning=SchemaWarning(
            type=SchemaWarningType.DEPRECATION, message="gone soon", kinds=[SchemaWarningKind(kind="InfraDevice")]
        ),
        expected=" deprecation: gone soon [InfraDevice]\n",
    ),
    WarningCase(
        name="kinds-with-field",
        warning=SchemaWarning(
            type=SchemaWarningType.DEPRECATION,
            message="gone soon",
            kinds=[SchemaWarningKind(kind="InfraDevice", field="serial"), SchemaWarningKind(kind="InfraSite")],
        ),
        expected=" deprecation: gone soon [InfraDevice.serial, InfraSite]\n",
    ),
    WarningCase(
        name="markup-in-message-is-escaped",
        warning=SchemaWarning(type=SchemaWarningType.DEPRECATION, message="[bold]x[/bold] stays literal"),
        expected=" deprecation: [bold]x[/bold] stays literal\n",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in WARNING_CASES])
def test_display_schema_warnings(case: WarningCase) -> None:
    console, output = _console()
    _display_schema_warnings(console=console, warnings=[case.warning])
    assert output.getvalue() == case.expected


def test_display_schema_warnings_none() -> None:
    console, output = _console()
    _display_schema_warnings(console=console, warnings=[])
    assert not output.getvalue()
