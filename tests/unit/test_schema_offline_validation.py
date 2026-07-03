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
