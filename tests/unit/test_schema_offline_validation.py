"""Offline schema validation: with only the SDK installed (pydantic, no server).

Validates a schema payload against the generated write models and asserts the
field-level verdict, without importing the backend/server package.
"""

from __future__ import annotations

import pytest

from infrahub_sdk.schema import validate_schema
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


def test_out_of_enum_value_is_rejected_naming_field_and_value() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = "NotARealKind"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert any("nodes[0].attributes[0].kind" in message for message in result.messages), result.messages
    # The invalid value is echoed back to the caller.
    assert any("NotARealKind" in message for message in result.messages), result.messages


def test_unknown_field_on_node_is_rejected() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["not_a_field"] = "boom"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert any("not_a_field" in message for message in result.messages), result.messages


def test_raise_on_error_raises_value_error_naming_field() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["attributes"][0]["kind"] = "NotARealKind"

    with pytest.raises(ValueError, match=r"kind"):
        validate_schema(schema=schema, raise_on_error=True)


def _fields_named(result: SchemaValidationResult) -> set[str]:
    return {error.field for error in result.errors}


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
    assert "extensions.nodes[0].attributes[0].inherited" in _fields_named(result), result.messages


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
    assert "extensions.nodes[0].attributes[0].not_a_field" in _fields_named(result), result.messages


def test_extension_attribute_out_of_enum_kind_is_rejected_naming_field_and_value() -> None:
    schema = {
        "version": "1.0",
        "extensions": {
            "nodes": [
                {
                    "kind": "InfraDevice",
                    "attributes": [{"name": "extra", "kind": "NotARealKind"}],
                }
            ]
        },
    }

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert "extensions.nodes[0].attributes[0].kind" in _fields_named(result), result.messages
    assert any("NotARealKind" in message for message in result.messages), result.messages


def test_extension_relationship_out_of_enum_cardinality_is_rejected_with_dotted_location() -> None:
    schema = {
        "version": "1.0",
        "extensions": {
            "nodes": [
                {
                    "kind": "InfraDevice",
                    "relationships": [{"name": "peers", "peer": "InfraDevice", "cardinality": "both"}],
                }
            ]
        },
    }

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert "extensions.nodes[0].relationships[0].cardinality" in _fields_named(result), result.messages
    assert any("both" in message for message in result.messages), result.messages


def test_relationship_out_of_enum_cardinality_is_rejected_naming_field_and_value() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0]["cardinality"] = "both"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert "nodes[0].relationships[0].cardinality" in _fields_named(result), result.messages
    assert any("both" in message for message in result.messages), result.messages


def test_relationship_out_of_enum_kind_is_rejected_naming_field_and_value() -> None:
    schema = _valid_schema()
    schema["nodes"][0]["relationships"][0]["kind"] = "NotARealKind"

    result = validate_schema(schema=schema)

    assert result.valid is False
    assert "nodes[0].relationships[0].kind" in _fields_named(result), result.messages
    assert any("NotARealKind" in message for message in result.messages), result.messages


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
