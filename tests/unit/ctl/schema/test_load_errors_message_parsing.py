# ruff: noqa: PLC2701
# Private imports are accepted here, since this a first step of a refactoring which will make this method part of
# dedicated components
"""Parsing of the schema-level error message an Infrahub 1.11.0+ server returns on `schema load`.

The message joins every write-contract violation as `<field path>: <message> (received: <value>)` separated
by `; `. These tests cover splitting it, telling a whole violation from one cut inside a received value, and
turning field paths and received values back into data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from infrahub_sdk.ctl.schema import (
    _format_field_path,
    _is_complete_violation,
    _is_schema_level_error,
    _is_whole_received_value,
    _parse_field_path,
    _parse_received_value,
    _split_contract_violations,
)

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
    FormatPathCase(name="capital-case-segment-kept", segments=["parameters", "Regex"], expected="parameters.Regex"),
    FormatPathCase(name="kind-like-segment-kept", segments=["Text", "name"], expected="Text.name"),
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
