"""Offline schema validation: with only the SDK installed (pydantic, no server).

Validates a schema payload against the generated write models and asserts the
field-level verdict, without importing the backend/server package. Values the user may not
set never reach the server, but they are reported: a read-only field -- one the read API
returns -- as a warning, and any other extra field as an error. Enum, constraint and
required-field violations are reported naming the field and the invalid value.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from infrahub_sdk.schema import InfrahubSchemaRead, InfrahubSchemaWrite, validate_schema
from infrahub_sdk.schema.validate import SchemaValidationResult


def _valid_schema() -> dict:
    return {
        "version": "1.0",
        "nodes": [
            {
                "name": "Device",
                "namespace": "Infra",
                "attributes": [
                    {"name": "hostname", "kind": "Text"},
                    {"name": "count", "kind": "Number", "optional": True},
                ],
                "relationships": [
                    {"name": "interfaces", "peer": "InfraInterface", "cardinality": "many", "optional": True},
                ],
            },
        ],
        "generics": [
            {"name": "Endpoint", "namespace": "Infra", "attributes": [{"name": "role", "kind": "Text"}]},
        ],
    }


def _fields_named(result: SchemaValidationResult) -> set[str]:
    return {error.field for error in result.errors}


def _extension_node_schema(node: dict) -> dict:
    return {"version": "1.0", "extensions": {"nodes": [node]}}


def _schema_with_computed_attribute(computed_attribute: dict) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["computed_attribute"] = computed_attribute
    return schema


def _schema_with_choices(choices: list[dict]) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["choices"] = choices
    return schema


def _schema_with_parameters(parameters: dict) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["parameters"] = parameters
    return schema


def _schema_with_kind_and_parameters(kind: str, parameters: dict) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = kind
    schema["nodes"][0]["attributes"][0]["parameters"] = parameters
    return schema


def _relationship_out_of_enum(field: str, value: str) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0][field] = value
    return schema


def _attribute_out_of_enum_kind(kind: str) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = kind
    return schema


def _schema_with_attribute_fields(**fields: object) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0].update(fields)
    return schema


def _schema_with_relationship_fields(**fields: object) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0].update(fields)
    return schema


def _schema_with_node_fields(**fields: object) -> dict:
    schema = _valid_schema()
    schema["nodes"][0].update(fields)
    return schema


def _schema_with_generic_fields(**fields: object) -> dict:
    schema = _valid_schema()
    schema["generics"][0].update(fields)
    return schema


def _schema_with_root_fields(**fields: object) -> dict:
    schema = _valid_schema()
    schema.update(fields)
    return schema


def test_schema_root_models_are_importable_with_nodes_and_generics() -> None:
    for root in (InfrahubSchemaWrite, InfrahubSchemaRead):
        assert "nodes" in root.model_fields
        assert "generics" in root.model_fields


def test_valid_payload_passes() -> None:
    result = validate_schema(schema=_valid_schema())
    assert isinstance(result, SchemaValidationResult)
    assert result.valid is True
    assert result.errors == []
    # raise_for_status must be a no-op for a valid payload
    result.raise_for_status()


def test_valid_payload_with_extensions_block_passes() -> None:
    schema = _valid_schema()
    schema["extensions"] = {
        "nodes": [
            {
                "kind": "InfraDevice",
                "attributes": [{"name": "extra", "kind": "Text"}],
                "relationships": [{"name": "peers", "peer": "InfraDevice", "cardinality": "many", "optional": True}],
            }
        ]
    }

    result = validate_schema(schema=schema)

    assert result.valid is True, result.messages


def test_enum_backed_relationship_cardinality_valid_value_passes() -> None:
    # A plain string for RelationshipCardinality is valid.
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0]["cardinality"] = "one"

    result = validate_schema(schema=schema)

    assert result.valid is True, result.messages


# ---------------------------------------------------------------------------
# Read-only fields are accepted with a warning
# ---------------------------------------------------------------------------


@dataclass
class ReadOnlyCase:
    name: str
    schema: dict
    # Exact dotted paths expected among the reported warnings.
    expected_fields: set[str]


READ_ONLY_CASES = [
    ReadOnlyCase(
        name="attribute-inherited",
        schema=_schema_with_attribute_fields(inherited=True),
        expected_fields={"nodes[0].attributes[0].inherited"},
    ),
    ReadOnlyCase(
        name="relationship-inherited-and-hierarchical",
        schema=_schema_with_relationship_fields(inherited=True, hierarchical="SomeGeneric"),
        expected_fields={
            "nodes[0].relationships[0].inherited",
            "nodes[0].relationships[0].hierarchical",
        },
    ),
    ReadOnlyCase(
        name="generic-used-by",
        schema=_schema_with_generic_fields(used_by=["InfraThing"]),
        expected_fields={"generics[0].used_by"},
    ),
    ReadOnlyCase(
        name="node-hierarchy",
        schema=_schema_with_node_fields(hierarchy="SomeGeneric"),
        expected_fields={"nodes[0].hierarchy"},
    ),
    ReadOnlyCase(
        name="node-derived-kind-and-hash",
        schema=_schema_with_node_fields(kind="InfraDevice", hash="abc123"),
        expected_fields={"nodes[0].kind", "nodes[0].hash"},
    ),
    ReadOnlyCase(
        name="extension-attribute-inherited",
        schema=_extension_node_schema(
            {"kind": "InfraDevice", "attributes": [{"name": "extra", "kind": "Text", "inherited": True}]}
        ),
        expected_fields={"extensions.nodes[0].attributes[0].inherited"},
    ),
    ReadOnlyCase(
        name="root-keys-of-a-read-api-response",
        schema=_schema_with_root_fields(main="abc123", profiles=[], templates=[], namespaces=[]),
        expected_fields={"main", "profiles", "templates", "namespaces"},
    ),
    # Every internal schema model carries `id` and `state`, so they appear on the nested value
    # models of a schema dumped from those models even though they are not settable there.
    ReadOnlyCase(
        name="parameters-bookkeeping-fields",
        schema=_schema_with_parameters({"min_length": 1, "id": None, "state": "present"}),
        expected_fields={
            "nodes[0].attributes[0].parameters.id",
            "nodes[0].attributes[0].parameters.state",
        },
    ),
    ReadOnlyCase(
        name="choice-bookkeeping-fields",
        schema=_schema_with_choices([{"name": "active", "id": None, "state": "present"}]),
        expected_fields={
            "nodes[0].attributes[0].choices[0].id",
            "nodes[0].attributes[0].choices[0].state",
        },
    ),
    # `transform` belongs to the TransformPython variant of the computed-attribute union, so it is
    # known at this location but not settable on a Jinja2 one.
    ReadOnlyCase(
        name="computed-attribute-sibling-variant-field",
        schema=_schema_with_computed_attribute({"kind": "Jinja2", "jinja2_template": "x", "transform": "t"}),
        expected_fields={"nodes[0].attributes[0].computed_attribute.transform"},
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in READ_ONLY_CASES])
def test_read_only_field_is_accepted_with_a_warning(case: ReadOnlyCase) -> None:
    # A payload read back from Infrahub carries read-only fields, so it must still load; the user
    # is told the value is ignored rather than having it dropped silently.
    result = validate_schema(schema=case.schema)

    assert result.valid is True, result.messages
    assert {warning.field for warning in result.warnings} == case.expected_fields


def test_read_only_warning_names_the_owning_kind_and_element() -> None:
    # Consumers render a warning as kind + field rather than as a path, so the owning schema kind
    # and the attribute/relationship carrying the field travel with the finding.
    schema = _schema_with_attribute_fields(inherited=True)

    result = validate_schema(schema=schema)

    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.name == "inherited"
    assert warning.kind == "InfraDevice"
    assert warning.element == "hostname"


def test_read_only_fields_are_dropped_on_round_trip() -> None:
    # A warning must not mean the value is kept: read-only fields are absent from the validated
    # model, so they never reach the server.
    schema = _valid_schema()
    schema["nodes"][0]["hierarchy"] = "SomeGeneric"
    schema["nodes"][0]["attributes"][0]["inherited"] = True

    assert validate_schema(schema=schema).valid is True

    dumped = InfrahubSchemaWrite.model_validate(schema).model_dump()
    node = dumped["nodes"][0]
    assert "hierarchy" not in node
    assert "inherited" not in node["attributes"][0]


# ---------------------------------------------------------------------------
# Any other extra field is rejected
# ---------------------------------------------------------------------------


@dataclass
class UnknownFieldCase:
    name: str
    schema: dict
    # Exact dotted paths expected among the reported error fields.
    expected_fields: set[str]


UNKNOWN_FIELD_CASES = [
    UnknownFieldCase(
        name="node-unknown-field",
        schema=_schema_with_node_fields(not_a_field="boom"),
        expected_fields={"nodes[0].not_a_field"},
    ),
    UnknownFieldCase(
        name="unknown-top-level-key",
        schema=_schema_with_root_fields(not_a_root_field="boom"),
        expected_fields={"not_a_root_field"},
    ),
    UnknownFieldCase(
        name="extension-attribute-unknown-field",
        schema=_extension_node_schema(
            {"kind": "InfraDevice", "attributes": [{"name": "extra", "kind": "Text", "not_a_field": "boom"}]}
        ),
        expected_fields={"extensions.nodes[0].attributes[0].not_a_field"},
    ),
    UnknownFieldCase(
        name="computed-attribute-unknown-field",
        schema=_schema_with_computed_attribute({"kind": "Jinja2", "jinja2_template": "x", "not_a_real_field": "x"}),
        expected_fields={"nodes[0].attributes[0].computed_attribute.not_a_real_field"},
    ),
    UnknownFieldCase(
        name="choice-unknown-field",
        schema=_schema_with_choices([{"name": "active", "not_a_real_field": "x"}]),
        expected_fields={"nodes[0].attributes[0].choices[0].not_a_real_field"},
    ),
    UnknownFieldCase(
        name="parameters-unknown-field",
        schema=_schema_with_parameters({"not_a_real_param": 1}),
        expected_fields={"nodes[0].attributes[0].parameters.not_a_real_param"},
    ),
    # Parameters only valid for a different attribute kind do nothing on this one, so naming them
    # is the only way the author learns the setting had no effect.
    UnknownFieldCase(
        name="number-attribute-number-pool-parameters",
        schema=_schema_with_kind_and_parameters("Number", {"start_range": 1, "end_range": 9}),
        expected_fields={
            "nodes[0].attributes[0].parameters.start_range",
            "nodes[0].attributes[0].parameters.end_range",
        },
    ),
    UnknownFieldCase(
        name="text-attribute-number-parameters",
        schema=_schema_with_kind_and_parameters("Text", {"min_value": 1}),
        expected_fields={"nodes[0].attributes[0].parameters.min_value"},
    ),
    UnknownFieldCase(
        name="generic-attribute-any-parameters",
        schema=_schema_with_kind_and_parameters("Dropdown", {"regex": "x"}),
        expected_fields={"nodes[0].attributes[0].parameters.regex"},
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in UNKNOWN_FIELD_CASES])
def test_unknown_field_is_rejected_naming_the_field(case: UnknownFieldCase) -> None:
    result = validate_schema(schema=case.schema)

    assert result.valid is False
    assert _fields_named(result) == case.expected_fields
    assert result.warnings == []


def test_unknown_fields_are_reported_at_every_nesting_level_at_once() -> None:
    # One pass must name every offending key rather than stopping at the first, so a payload is
    # corrected in a single round.
    schema = _valid_schema()
    schema["not_a_root_field"] = "boom"
    schema["nodes"][0]["not_a_node_field"] = "boom"
    schema["nodes"][0]["attributes"][0]["not_an_attribute_field"] = "boom"
    schema["nodes"][0]["relationships"][0]["not_a_relationship_field"] = "boom"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert _fields_named(result) == {
        "not_a_root_field",
        "nodes[0].not_a_node_field",
        "nodes[0].attributes[0].not_an_attribute_field",
        "nodes[0].relationships[0].not_a_relationship_field",
    }


def test_unknown_fields_are_not_reported_while_the_payload_is_otherwise_invalid() -> None:
    # The validated model is what resolves the contract at each location, so a payload that fails
    # validation reports that failure first and the extra fields once it is corrected.
    schema = _schema_with_node_fields(not_a_field="boom")
    schema["nodes"][0]["attributes"][0]["kind"] = "NotARealKind"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert _fields_named(result) == {"nodes[0].attributes[0]"}


# ---------------------------------------------------------------------------
# Value violations are still rejected naming the field and the invalid value
# ---------------------------------------------------------------------------


@dataclass
class OutOfEnumCase:
    name: str
    schema: dict
    # Exact dotted path expected among the reported error fields. For a discriminated union the
    # unknown discriminator is reported against the container (attribute), not a leaf field.
    expected_field: str
    invalid_value: str


OUT_OF_ENUM_CASES = [
    OutOfEnumCase(
        name="attribute-kind",
        schema=_attribute_out_of_enum_kind("NotARealKind"),
        expected_field="nodes[0].attributes[0]",
        invalid_value="NotARealKind",
    ),
    OutOfEnumCase(
        name="relationship-kind",
        schema=_relationship_out_of_enum("kind", "NotARealKind"),
        expected_field="nodes[0].relationships[0].kind",
        invalid_value="NotARealKind",
    ),
    OutOfEnumCase(
        name="relationship-cardinality",
        schema=_relationship_out_of_enum("cardinality", "both"),
        expected_field="nodes[0].relationships[0].cardinality",
        invalid_value="both",
    ),
    OutOfEnumCase(
        name="computed-attribute-kind",
        schema=_schema_with_computed_attribute({"kind": "NotARealKind"}),
        expected_field="nodes[0].attributes[0].Text.computed_attribute",
        invalid_value="NotARealKind",
    ),
    OutOfEnumCase(
        name="extension-attribute-kind",
        schema=_extension_node_schema(
            {"kind": "InfraDevice", "attributes": [{"name": "extra", "kind": "NotARealKind"}]}
        ),
        expected_field="extensions.nodes[0].attributes[0]",
        invalid_value="NotARealKind",
    ),
    OutOfEnumCase(
        name="extension-relationship-cardinality",
        schema=_extension_node_schema(
            {"kind": "InfraDevice", "relationships": [{"name": "peers", "peer": "InfraDevice", "cardinality": "both"}]}
        ),
        expected_field="extensions.nodes[0].relationships[0].cardinality",
        invalid_value="both",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in OUT_OF_ENUM_CASES])
def test_out_of_enum_value_is_rejected_naming_field_and_value(case: OutOfEnumCase) -> None:
    result = validate_schema(schema=case.schema)

    assert result.valid is False
    assert case.expected_field in _fields_named(result), result.messages
    assert any(case.invalid_value in message for message in result.messages), result.messages


def test_enum_backed_relationship_cardinality_out_of_enum_value_is_rejected() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0]["cardinality"] = "both"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert any("cardinality" in message for message in result.messages), result.messages


def test_missing_version_is_rejected() -> None:
    # The load endpoint requires ``version``, so a payload without it must be reported invalid
    # offline too instead of passing here and being rejected on submission.
    schema = _valid_schema()
    del schema["version"]

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert _fields_named(result) == {"version"}


def test_raise_on_error_raises_value_error_naming_field() -> None:
    # Exercises the raise_on_error path rather than the result verdict: an out-of-enum value must
    # raise a ValueError naming the offending field.
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = "NotARealKind"

    with pytest.raises(ValueError, match=r"kind"):
        validate_schema(schema=schema, raise_on_error=True)


def test_valid_computed_attribute_block_passes() -> None:
    result = validate_schema(
        schema=_schema_with_computed_attribute({"kind": "Jinja2", "jinja2_template": "{{ name }}"})
    )

    assert result.valid is True, result.messages


def test_computed_attribute_jinja2_without_template_is_rejected() -> None:
    result = validate_schema(schema=_schema_with_computed_attribute({"kind": "Jinja2"}))

    assert result.valid is False
    assert any("jinja2_template" in message for message in result.messages), result.messages


def test_computed_attribute_transform_python_without_transform_is_rejected() -> None:
    result = validate_schema(schema=_schema_with_computed_attribute({"kind": "TransformPython"}))

    assert result.valid is False
    assert any("transform" in message for message in result.messages), result.messages


def test_valid_choice_passes() -> None:
    result = validate_schema(schema=_schema_with_choices([{"name": "active", "color": "#aabbcc", "label": "Active"}]))

    assert result.valid is True, result.messages


def test_choice_bad_color_is_rejected() -> None:
    result = validate_schema(schema=_schema_with_choices([{"name": "active", "color": "not-a-color"}]))

    assert result.valid is False
    assert any("color" in message for message in result.messages), result.messages


def test_valid_text_parameters_pass() -> None:
    result = validate_schema(schema=_schema_with_parameters({"min_length": 1}))

    assert result.valid is True, result.messages


def test_number_attribute_accepts_number_parameters() -> None:
    result = validate_schema(schema=_schema_with_kind_and_parameters("Number", {"min_value": 1}))

    assert result.valid is True, result.messages


def test_number_pool_attribute_accepts_number_pool_parameters() -> None:
    result = validate_schema(schema=_schema_with_kind_and_parameters("NumberPool", {"start_range": 1, "end_range": 9}))

    assert result.valid is True, result.messages
