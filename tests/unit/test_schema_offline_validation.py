"""Offline schema validation: with only the SDK installed (pydantic, no server).

Validates a schema payload against the generated write models and asserts the
field-level verdict, without importing the backend/server package. The write models
set ``extra="ignore"``, so non-settable (read-level, internal) and unknown fields are
dropped silently rather than rejected; enum, constraint and required-field violations
are still reported naming the field and the invalid value.
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
# Non-write fields are tolerated and dropped, not rejected
# ---------------------------------------------------------------------------


@dataclass
class ToleratedCase:
    name: str
    schema: dict


TOLERATED_CASES = [
    # Read-level / internal fields the user may not set: dropped silently on validation.
    ToleratedCase(name="attribute-read-level-inherited", schema=_schema_with_attribute_fields(inherited=True)),
    ToleratedCase(
        name="relationship-read-level",
        schema=_schema_with_relationship_fields(inherited=True, hierarchical="SomeGeneric"),
    ),
    ToleratedCase(name="generic-read-level-used-by", schema=_schema_with_generic_fields(used_by=["InfraThing"])),
    ToleratedCase(name="node-read-level-hierarchy", schema=_schema_with_node_fields(hierarchy="SomeGeneric")),
    ToleratedCase(
        name="extension-attribute-read-level-inherited",
        schema=_extension_node_schema(
            {"kind": "InfraDevice", "attributes": [{"name": "extra", "kind": "Text", "inherited": True}]}
        ),
    ),
    # Genuinely unknown fields (typos, removed fields): also dropped silently.
    ToleratedCase(name="node-unknown-field", schema=_schema_with_node_fields(not_a_field="boom")),
    ToleratedCase(name="unknown-top-level-key", schema=_schema_with_root_fields(not_a_root_field="boom")),
    ToleratedCase(
        name="extension-attribute-unknown-field",
        schema=_extension_node_schema(
            {"kind": "InfraDevice", "attributes": [{"name": "extra", "kind": "Text", "not_a_field": "boom"}]}
        ),
    ),
    ToleratedCase(
        name="computed-attribute-unknown-field",
        schema=_schema_with_computed_attribute({"kind": "Jinja2", "jinja2_template": "x", "not_a_real_field": "x"}),
    ),
    ToleratedCase(
        name="choice-unknown-field",
        schema=_schema_with_choices([{"name": "active", "not_a_real_field": "x"}]),
    ),
    ToleratedCase(name="parameters-unknown-field", schema=_schema_with_parameters({"not_a_real_param": 1})),
    # Parameters valid only for a different attribute kind: dropped, not rejected.
    ToleratedCase(
        name="number-attribute-number-pool-parameters",
        schema=_schema_with_kind_and_parameters("Number", {"start_range": 1, "end_range": 9}),
    ),
    ToleratedCase(
        name="text-attribute-number-parameters",
        schema=_schema_with_kind_and_parameters("Text", {"min_value": 1}),
    ),
    ToleratedCase(
        name="generic-attribute-any-parameters",
        schema=_schema_with_kind_and_parameters("Dropdown", {"regex": "x"}),
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in TOLERATED_CASES])
def test_non_write_field_is_tolerated(case: ToleratedCase) -> None:
    # extra="ignore" on the write models drops the field silently, so validation passes.
    result = validate_schema(schema=case.schema)

    assert result.valid is True, result.messages


def test_non_write_fields_are_dropped_on_round_trip() -> None:
    # Tolerated fields must not round-trip into the payload: read-level and unknown fields are
    # absent from the validated model, so they never reach the server.
    schema = _valid_schema()
    schema["not_a_root_field"] = "boom"
    schema["nodes"][0]["hierarchy"] = "SomeGeneric"
    schema["nodes"][0]["attributes"][0]["inherited"] = True
    schema["nodes"][0]["attributes"][0]["not_a_field"] = "boom"

    assert validate_schema(schema=schema).valid is True

    dumped = InfrahubSchemaWrite.model_validate(schema).model_dump()
    assert "not_a_root_field" not in dumped
    node = dumped["nodes"][0]
    assert "hierarchy" not in node
    attribute = node["attributes"][0]
    assert "inherited" not in attribute
    assert "not_a_field" not in attribute


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
