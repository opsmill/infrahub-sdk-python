from __future__ import annotations

import pytest
from pydantic import ValidationError

from infrahub_sdk.convert_object_type import ConversionFieldInput, ConversionFieldValue


class TestConversionFieldValue:
    def test_attribute_value_with_value(self) -> None:
        """Test ConversionFieldValue with a normal attribute value."""
        value = ConversionFieldValue(attribute_value="test_value")
        assert value.attribute_value == "test_value"
        assert value.peer_id is None
        assert value.peers_ids is None

    def test_attribute_value_with_none(self) -> None:
        """Test ConversionFieldValue with explicit null attribute value.

        This is the bug case from the issue - when UI sends {"attribute_value": null},
        it should be accepted as a valid way to set an attribute to null.
        """
        value = ConversionFieldValue(attribute_value=None)
        assert value.attribute_value is None
        assert value.peer_id is None
        assert value.peers_ids is None
        assert "attribute_value" in value.model_fields_set

    def test_peer_id(self) -> None:
        """Test ConversionFieldValue with peer_id."""
        value = ConversionFieldValue(peer_id="some-uuid")
        assert value.attribute_value is None
        assert value.peer_id == "some-uuid"
        assert value.peers_ids is None

    def test_peers_ids(self) -> None:
        """Test ConversionFieldValue with peers_ids."""
        value = ConversionFieldValue(peers_ids=["id1", "id2"])
        assert value.attribute_value is None
        assert value.peer_id is None
        assert value.peers_ids == ["id1", "id2"]

    def test_no_fields_set_fails(self) -> None:
        """Test that ConversionFieldValue without any fields fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ConversionFieldValue()
        assert "Exactly one of `attribute_value`, `peer_id`, or `peers_ids` must be set" in str(exc_info.value)

    def test_multiple_fields_set_fails(self) -> None:
        """Test that ConversionFieldValue with multiple fields fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ConversionFieldValue(attribute_value="test", peer_id="id")
        assert "Exactly one of `attribute_value`, `peer_id`, or `peers_ids` must be set" in str(exc_info.value)


class TestConversionFieldInput:
    def test_source_field(self) -> None:
        """Test ConversionFieldInput with source_field."""
        field_input = ConversionFieldInput(source_field="name")
        assert field_input.source_field == "name"
        assert field_input.data is None
        assert field_input.use_default_value is False

    def test_data_with_attribute_value(self) -> None:
        """Test ConversionFieldInput with data containing an attribute value."""
        field_value = ConversionFieldValue(attribute_value="test_value")
        field_input = ConversionFieldInput(data=field_value)
        assert field_input.source_field is None
        assert field_input.data == field_value
        assert field_input.use_default_value is False

    def test_data_with_null_attribute_value(self) -> None:
        """Test ConversionFieldInput with data containing null attribute value.

        This is the full chain from the issue - when UI sends:
        {"city": {"data": {"attribute_value": null}}}
        """
        field_value = ConversionFieldValue(attribute_value=None)
        field_input = ConversionFieldInput(data=field_value)
        assert field_input.source_field is None
        assert field_input.data is not None
        assert field_input.data.attribute_value is None
        assert field_input.use_default_value is False

    def test_use_default_value(self) -> None:
        """Test ConversionFieldInput with use_default_value."""
        field_input = ConversionFieldInput(use_default_value=True)
        assert field_input.source_field is None
        assert field_input.data is None
        assert field_input.use_default_value is True

    def test_no_fields_set_fails(self) -> None:
        """Test that ConversionFieldInput without any fields fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ConversionFieldInput()
        assert "Exactly one of `source_field`, `data` or `use_default_value` must be set" in str(exc_info.value)

    def test_multiple_fields_set_fails(self) -> None:
        """Test that ConversionFieldInput with multiple fields fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ConversionFieldInput(source_field="name", use_default_value=True)
        assert "Exactly one of `source_field`, `data` or `use_default_value` must be set" in str(exc_info.value)
