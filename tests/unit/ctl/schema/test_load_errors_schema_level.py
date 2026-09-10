"""Rendering of the schema-level `schema load` errors an Infrahub 1.11.0+ server reports.

The last section builds the message with the SDK validator the server relies on, so any drift in its format
shows up here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from infrahub_sdk.schema import validate_schema
from tests.helpers.schema_load_errors import (
    DEVICE,
    EXTENSION_SCHEMA,
    HEADER,
    INVALID_SCHEMA,
    OTHER_SCHEMA,
    SCHEMA,
    SPEED_ATTRIBUTE,
    TAG_EXTENSION,
    VALID_NODE,
    field_level_error,
    render,
    schema_level_error,
)


def _server_message(schema: dict[str, Any]) -> str:
    """Build the message exactly as an Infrahub 1.11 server does: `validate_schema(...).raise_for_status()`."""
    with pytest.raises(ValueError, match=r".+: .+") as exc:
        validate_schema(schema=schema).raise_for_status()
    return f"Value error, {exc.value}"


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
    assert render([schema_level_error(case.message)], case.schema) == f"{HEADER}  {case.expected_line}\n"


def test_display_schema_level_violation_on_missing_node_reports_not_found() -> None:
    message = "Value error, nodes[4].name: bad (received: 'x')"
    assert render([schema_level_error(message)], SCHEMA) == f"{HEADER}Node data not found.\n"


def test_display_schema_level_error_uses_its_type_on_every_line() -> None:
    message = "a: Boom; nodes[0].namespace: bad (received: 1)"
    assert render([schema_level_error(message, err_type="value_error")], SCHEMA) == (
        f"{HEADER}"
        "  Schema: schema-0.yml | a: Boom (value_error)\n"
        "  Node: InfraDevice | namespace (1) | bad (value_error)\n"
    )


def test_display_schema_level_error_without_msg_prints_only_the_header() -> None:
    error = {"type": "value_error", "loc": ["body", "schemas", 0]}
    assert render([error], SCHEMA) == HEADER


def test_display_schema_level_error_with_empty_msg_prints_only_the_header() -> None:
    assert render([schema_level_error("")], SCHEMA) == HEADER


def test_display_schema_level_error_picks_the_schema_file_by_index() -> None:
    message = "Value error, nodes[0].namespace: bad (received: 'Test')"
    assert render([schema_level_error(message, schema_index=1)], SCHEMA, OTHER_SCHEMA) == (
        f"{HEADER}  Node: TestOther | namespace (Test) | bad (value_error)\n"
    )


def test_display_schema_level_verbatim_violation_names_the_right_schema_file() -> None:
    message = "Value error, version: Field required"
    assert render([schema_level_error(message, schema_index=1)], SCHEMA, SCHEMA) == (
        f"{HEADER}  Schema: schema-1.yml | version: Field required (value_error)\n"
    )


def test_display_schema_level_verbatim_violation_with_unknown_schema_index() -> None:
    message = "Value error, version: Field required"
    assert render([schema_level_error(message, schema_index=3)], SCHEMA) == (
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
    assert render([schema_level_error(message)], SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (infra) | first (value_error)\n"
        "  Node: InfraGeneric | name (Generic) | second (value_error)\n"
        "  Schema: schema-0.yml | version: third (value_error)\n"
        "  Node: InfraDevice | Attribute: serial | parameters.regex ([) | fourth (value_error)\n"
        "  Node: InfraDevice | Relationship: site | peer (x; y: z) | fifth (value_error)\n"
    )


def test_display_mixes_schema_level_and_field_level_errors() -> None:
    errors = [
        field_level_error(loc=["body", "schemas", 0, "nodes", 0, "namespace"], msg="field-level", input="infra"),
        schema_level_error("Value error, generics[0].name: schema-level (received: 'Generic')"),
        field_level_error(loc=["body", "branch"], msg="ignored"),
    ]
    assert render(errors, SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (infra) | field-level (value_error)\n"
        "  Node: InfraGeneric | name (Generic) | schema-level (value_error)\n"
    )


def test_display_one_schema_level_error_per_schema() -> None:
    errors = [
        schema_level_error("Value error, nodes[0].namespace: bad (received: 'infra')", schema_index=0),
        schema_level_error("Value error, nodes[0].name: bad (received: 'Other')", schema_index=1),
    ]
    assert render(errors, SCHEMA, OTHER_SCHEMA) == (
        f"{HEADER}"
        "  Node: InfraDevice | namespace (infra) | bad (value_error)\n"
        "  Node: TestOther | name (Other) | bad (value_error)\n"
    )


# ---------------------------------------------------------------------------------------------------------------------
# Contract with the server: the message is built by the SDK validator the server relies on
# ---------------------------------------------------------------------------------------------------------------------


def test_contract_invalid_namespace_and_short_attribute_name() -> None:
    assert render([schema_level_error(_server_message(INVALID_SCHEMA))], INVALID_SCHEMA) == (
        f"{HEADER}"
        "  Node: infraDevice | namespace (infra) | String should match pattern '^[A-Z][a-z0-9]+$' (value_error)\n"
        "  Node: infraDevice | Attribute: n | name (n) | String should have at least 3 characters (value_error)\n"
    )


def test_contract_unknown_field_on_extension_attribute_with_markup_in_value() -> None:
    attribute = {**SPEED_ATTRIBUTE, "made_up": "[red]x"}
    schema = {"version": "1.0", "extensions": {"nodes": [{**TAG_EXTENSION, "attributes": [attribute]}]}}
    assert render([schema_level_error(_server_message(schema))], schema) == (
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

    assert render([schema_level_error(message)], schema) == (
        f"{HEADER}  Node: infraDevice | namespace (infra) | String should match pattern '^[A-Z][a-z0-9]+$' (value_error)\n"
    )
    assert render([schema_level_error(long_message)], schema_with_bad_description).count("\n") == 3


def test_contract_missing_required_field_shows_no_value() -> None:
    node = {key: value for key, value in VALID_NODE.items() if key != "name"}
    schema = {"version": "1.0", "nodes": [node]}
    assert render([schema_level_error(_server_message(schema))], schema) == (
        f"{HEADER}  Node: InfraNone | name | Field required (value_error)\n"
    )


def test_contract_unknown_root_field_is_verbatim() -> None:
    schema = {"version": "1.0", "bogus": 1, "nodes": []}
    assert render([schema_level_error(_server_message(schema))], schema) == (
        f"{HEADER}  Schema: schema-0.yml | bogus: Unknown field, it is not part of the schema (received: 1) (value_error)\n"
    )


# ---------------------------------------------------------------------------------------------------------------------
# validate_schema_content_and_exit / _display_schema_warnings
