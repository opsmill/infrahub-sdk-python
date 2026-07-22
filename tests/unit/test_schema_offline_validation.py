"""Offline schema validation: with only the SDK installed (pydantic, no server).

Validates a schema payload against the generated write models and asserts the
field-level verdict, without importing the backend/server package.
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


def test_non_settable_field_is_rejected_and_named() -> None:
    schema = _valid_schema()
    # `inherited` is a read-level attribute field; a user must not be able to set it.
    schema["nodes"][0]["attributes"][0]["inherited"] = True

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert any("inherited" in message for message in result.messages), result.messages
    # The message must locate the offending field within the payload.
    assert any("nodes[0].attributes[0]" in message for message in result.messages), result.messages


def test_enum_backed_relationship_cardinality_valid_value_passes() -> None:
    # cardinality is typed with the RelationshipCardinality enum (use_enum_values keeps the runtime
    # value a plain string); "one" is a valid RelationshipCardinality string and must validate.
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0]["cardinality"] = "one"

    result = validate_schema(schema=schema)

    assert result.valid is True, result.messages


def test_enum_backed_relationship_cardinality_out_of_enum_value_is_rejected() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0]["cardinality"] = "both"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert any("cardinality" in message for message in result.messages), result.messages


def test_unknown_field_on_node_is_rejected() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["not_a_field"] = "boom"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert any("not_a_field" in message for message in result.messages), result.messages


def test_raise_on_error_raises_value_error_naming_field() -> None:
    # Reuses the out-of-enum setup on purpose, but exercises the raise_on_error path rather than the
    # result verdict: an invalid payload must raise a ValueError naming the offending field.
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = "NotARealKind"

    with pytest.raises(ValueError, match=r"kind"):
        validate_schema(schema=schema, raise_on_error=True)


def _fields_named(result: SchemaValidationResult) -> set[str]:
    return {error.field for error in result.errors}


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


def test_unknown_top_level_key_is_rejected() -> None:
    schema = _valid_schema()
    schema["not_a_root_field"] = "boom"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert any("not_a_root_field" in message for message in result.messages), result.messages


def test_extension_attribute_read_level_field_is_rejected_with_dotted_location() -> None:
    schema = {
        "version": "1.0",
        "extensions": {
            "nodes": [
                {
                    "kind": "InfraDevice",
                    "attributes": [{"name": "extra", "kind": "Text", "inherited": True}],
                }
            ]
        },
    }

    result = validate_schema(schema=schema)

    assert result.valid is False
    # The matched variant's tag (the attribute kind) is part of the discriminated-union error path.
    assert "extensions.nodes[0].attributes[0].Text.inherited" in _fields_named(result), result.messages


def test_extension_attribute_unknown_field_is_rejected_with_dotted_location() -> None:
    schema = {
        "version": "1.0",
        "extensions": {
            "nodes": [
                {
                    "kind": "InfraDevice",
                    "attributes": [{"name": "extra", "kind": "Text", "not_a_field": "boom"}],
                }
            ]
        },
    }

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert "extensions.nodes[0].attributes[0].Text.not_a_field" in _fields_named(result), result.messages


def test_relationship_read_level_fields_are_rejected() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0]["inherited"] = True
    schema["nodes"][0]["relationships"][0]["hierarchical"] = "SomeGeneric"

    result = validate_schema(schema=schema)

    assert result.valid is False
    named = _fields_named(result)
    assert "nodes[0].relationships[0].inherited" in named, result.messages
    assert "nodes[0].relationships[0].hierarchical" in named, result.messages


def test_generic_read_level_field_used_by_is_rejected() -> None:
    schema = _valid_schema()
    schema["generics"][0]["used_by"] = ["InfraThing"]

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert "generics[0].used_by" in _fields_named(result), result.messages


def test_node_read_level_field_hierarchy_is_rejected() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["hierarchy"] = "SomeGeneric"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert "nodes[0].hierarchy" in _fields_named(result), result.messages


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


def test_computed_attribute_unknown_field_is_rejected() -> None:
    result = validate_schema(
        schema=_schema_with_computed_attribute({"kind": "Jinja2", "jinja2_template": "x", "not_a_real_field": "x"})
    )

    assert result.valid is False
    assert any("not_a_real_field" in message for message in result.messages), result.messages


def test_valid_choice_passes() -> None:
    result = validate_schema(schema=_schema_with_choices([{"name": "active", "color": "#aabbcc", "label": "Active"}]))

    assert result.valid is True, result.messages


def test_choice_unknown_field_is_rejected() -> None:
    result = validate_schema(schema=_schema_with_choices([{"name": "active", "not_a_real_field": "x"}]))

    assert result.valid is False
    assert any("not_a_real_field" in message for message in result.messages), result.messages


def test_choice_bad_color_is_rejected() -> None:
    result = validate_schema(schema=_schema_with_choices([{"name": "active", "color": "not-a-color"}]))

    assert result.valid is False
    assert any("color" in message for message in result.messages), result.messages


def test_valid_text_parameters_pass() -> None:
    result = validate_schema(schema=_schema_with_parameters({"min_length": 1}))

    assert result.valid is True, result.messages


def test_parameters_unknown_field_is_rejected() -> None:
    result = validate_schema(schema=_schema_with_parameters({"not_a_real_param": 1}))

    assert result.valid is False
    assert any("not_a_real_param" in message for message in result.messages), result.messages


def _schema_with_kind_and_parameters(kind: str, parameters: dict) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = kind
    schema["nodes"][0]["attributes"][0]["parameters"] = parameters
    return schema


def test_number_attribute_accepts_number_parameters() -> None:
    result = validate_schema(schema=_schema_with_kind_and_parameters("Number", {"min_value": 1}))

    assert result.valid is True, result.messages


def test_number_attribute_rejects_number_pool_parameters() -> None:
    # NumberPool-only parameters must not validate against a Number attribute.
    result = validate_schema(schema=_schema_with_kind_and_parameters("Number", {"start_range": 1, "end_range": 9}))

    assert result.valid is False
    assert any("start_range" in message for message in result.messages), result.messages


def test_text_attribute_rejects_number_parameters() -> None:
    # A Number-only parameter must not validate against a Text attribute.
    result = validate_schema(schema=_schema_with_kind_and_parameters("Text", {"min_value": 1}))

    assert result.valid is False
    assert any("min_value" in message for message in result.messages), result.messages


def test_generic_attribute_rejects_any_parameters() -> None:
    # A kind that maps to the plain parameters model accepts no parameter fields at all.
    result = validate_schema(schema=_schema_with_kind_and_parameters("Dropdown", {"regex": "x"}))

    assert result.valid is False
    assert any("regex" in message for message in result.messages), result.messages


def test_number_pool_attribute_accepts_number_pool_parameters() -> None:
    result = validate_schema(schema=_schema_with_kind_and_parameters("NumberPool", {"start_range": 1, "end_range": 9}))

    assert result.valid is True, result.messages


def _extension_node_schema(node: dict) -> dict:
    return {"version": "1.0", "extensions": {"nodes": [node]}}


@dataclass
class OutOfEnumCase:
    name: str
    schema: dict
    # Exact dotted path expected among the reported error fields. For a discriminated union the
    # unknown discriminator is reported against the container (attribute), not a leaf field.
    expected_field: str
    invalid_value: str


def _relationship_out_of_enum(field: str, value: str) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0][field] = value
    return schema


def _attribute_out_of_enum_kind(kind: str) -> dict:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = kind
    return schema


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
