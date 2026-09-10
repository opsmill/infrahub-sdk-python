"""Rendering of `schema load` errors located on the failing field, as every Infrahub version reports them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from infrahub_sdk.ctl.schema import display_schema_load_errors, handle_non_detail_errors
from tests.helpers.schema_load_errors import (
    EXTENSION_SCHEMA,
    HEADER,
    SCHEMA,
    capture_console,
    field_level_error,
    make_console,
    render,
)

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
    console, output = make_console()
    handle_non_detail_errors(response=case.response, output=console)
    assert output.getvalue() == case.expected


def test_handle_non_detail_errors_defaults_to_module_console(monkeypatch: pytest.MonkeyPatch) -> None:
    output = capture_console(monkeypatch)
    handle_non_detail_errors(response={"error": "written on the module console"})
    assert output.getvalue() == "  written on the module console\n"


# ---------------------------------------------------------------------------------------------------------------------
# display_schema_load_errors: response shapes
# ---------------------------------------------------------------------------------------------------------------------


def test_display_no_detail_delegates_to_non_detail_rendering() -> None:
    console, output = make_console()
    display_schema_load_errors(response={"error": "Boom"}, schemas_data=[], output=console)
    assert output.getvalue() == f"{HEADER}  Boom\n"


def test_display_empty_detail_prints_only_the_header() -> None:
    assert render([], SCHEMA) == HEADER


def test_display_defaults_to_module_console(monkeypatch: pytest.MonkeyPatch) -> None:
    output = capture_console(monkeypatch)
    display_schema_load_errors(response={"detail": []}, schemas_data=[])
    assert output.getvalue() == HEADER


@dataclass
class SkippedErrorCase:
    name: str
    error: dict[str, Any]


SKIPPED_ERROR_CASES = [
    SkippedErrorCase(name="missing-loc", error={"type": "value_error", "msg": "no loc"}),
    SkippedErrorCase(name="not-a-schema-location", error=field_level_error(loc=["body", "branch"])),
    SkippedErrorCase(
        name="root-field-not-schema-level-type", error=field_level_error(loc=["body", "schemas", 0, "version"])
    ),
    SkippedErrorCase(name="node-without-field", error=field_level_error(loc=["body", "schemas", 0, "nodes", 0])),
    SkippedErrorCase(
        name="unknown-container", error=field_level_error(loc=["body", "schemas", 0, "relationships", 0, "peer"])
    ),
    SkippedErrorCase(
        name="schema-level-wrong-type", error=field_level_error(loc=["body", "schemas", 0], err_type="missing")
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in SKIPPED_ERROR_CASES])
def test_display_skips_locations_it_cannot_attribute(case: SkippedErrorCase) -> None:
    assert render([case.error], SCHEMA) == HEADER


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
        name="attribute-capital-case-key-is-not-a-union-tag",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 0, "Made_up"],
        extra={"input": True},
        expected_line="Node: InfraDevice | Attribute: serial | Made_up (True) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="attribute-nested-capital-case-key-kept",
        loc=["body", "schemas", 0, "nodes", 0, "attributes", 0, "parameters", "Regex"],
        extra={"input": "a"},
        expected_line="Node: InfraDevice | Attribute: serial | parameters.Regex (a) | Boom (value_error)",
    ),
    FieldLevelCase(
        name="relationship-kind-named-key-kept",
        loc=["body", "schemas", 0, "nodes", 0, "relationships", 0, "Text"],
        extra={"input": 1},
        expected_line="Node: InfraDevice | Relationship: site | Text (1) | Boom (value_error)",
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
    error = field_level_error(loc=case.loc, **case.extra)
    assert render([error], case.schema) == f"{HEADER}  {case.expected_line}\n"


def test_display_field_level_error_without_msg_or_type() -> None:
    error = {"loc": ["body", "schemas", 0, "nodes", 0, "namespace"], "input": "x"}
    assert render([error], SCHEMA) == f"{HEADER}  Node: InfraDevice | namespace (x) | No error message (unknown)\n"


def test_display_field_level_error_type_is_echoed() -> None:
    error = field_level_error(loc=["body", "schemas", 0, "nodes", 0, "namespace"], err_type="string_pattern_mismatch")
    assert render([error], SCHEMA) == (f"{HEADER}  Node: InfraDevice | namespace | Boom (string_pattern_mismatch)\n")


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
    assert render([field_level_error(loc=case.loc)], *case.schemas) == f"{HEADER}Node data not found.\n"


def test_display_several_field_level_errors_keep_their_order() -> None:
    errors = [
        field_level_error(loc=["body", "schemas", 0, "nodes", 0, "namespace"], msg="first", input=1),
        field_level_error(loc=["body", "schemas", 0, "nodes", 5, "namespace"], msg="lost"),
        field_level_error(loc=["body", "schemas", 0, "nodes", 0, "attributes", 1, "kind"], msg="second", input=2),
    ]
    assert render(errors, SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (1) | first (value_error)\n"
        "Node data not found.\n"
        "  Node: InfraDevice | Attribute: status | kind (2) | second (value_error)\n"
    )


# ---------------------------------------------------------------------------------------------------------------------
# display_schema_load_errors: schema-level errors (Infrahub 1.11.0+)
