"""Unit tests for infrahub_sdk.ctl.parsers."""

from __future__ import annotations

import pytest
import typer

from infrahub_sdk.ctl.parsers import parse_filter_args, parse_set_args, validate_set_fields


class TestParseSetArgs:
    """Tests for parse_set_args."""

    def test_single_key_value_pair(self) -> None:
        """Test parse_set_args with a single valid key=value argument."""
        result = parse_set_args(["name=router1"])
        assert result == {"name": "router1"}

    def test_multiple_key_value_pairs(self) -> None:
        """Test parse_set_args with multiple valid key=value arguments."""
        result = parse_set_args(["name=router1", "status=active"])
        assert result == {"name": "router1", "status": "active"}

    def test_value_containing_equals_sign(self) -> None:
        """Test that only the first = is used as the split point."""
        result = parse_set_args(["description=a=b=c"])
        assert result == {"description": "a=b=c"}

    def test_empty_list(self) -> None:
        """Test parse_set_args with an empty list returns an empty dict."""
        result = parse_set_args([])
        assert result == {}

    def test_missing_equals_raises_bad_parameter(self) -> None:
        """Test parse_set_args raises BadParameter when = is absent."""
        with pytest.raises(typer.BadParameter, match="Invalid format"):
            parse_set_args(["nameonly"])

    def test_empty_key_raises_bad_parameter(self) -> None:
        """Test parse_set_args raises BadParameter when key is empty."""
        with pytest.raises(typer.BadParameter, match="Key must not be empty"):
            parse_set_args(["=value"])

    def test_whitespace_only_key_raises_bad_parameter(self) -> None:
        """Test parse_set_args raises BadParameter when key is only whitespace."""
        with pytest.raises(typer.BadParameter, match="Key must not be empty"):
            parse_set_args(["   =value"])

    def test_value_can_be_empty_string(self) -> None:
        """Test parse_set_args accepts an empty string value."""
        result = parse_set_args(["name="])
        assert result == {"name": ""}


class TestParseFilterArgs:
    """Tests for parse_filter_args."""

    def test_single_filter_argument(self) -> None:
        """Test parse_filter_args with a single valid filter argument."""
        result = parse_filter_args(["name__value=router1"])
        assert result == {"name__value": "router1"}

    def test_multiple_filter_arguments(self) -> None:
        """Test parse_filter_args with multiple valid filter arguments."""
        result = parse_filter_args(["name__value=router1", "status__value=active"])
        assert result == {"name__value": "router1", "status__value": "active"}

    def test_empty_list(self) -> None:
        """Test parse_filter_args with an empty list returns an empty dict."""
        result = parse_filter_args([])
        assert result == {}

    def test_missing_equals_raises_bad_parameter(self) -> None:
        """Test parse_filter_args raises BadParameter when = is absent."""
        with pytest.raises(typer.BadParameter, match="Invalid format"):
            parse_filter_args(["name__value"])

    def test_value_containing_equals_sign(self) -> None:
        """Test that only the first = splits the filter argument."""
        result = parse_filter_args(["description__value=x=y"])
        assert result == {"description__value": "x=y"}


class TestValidateSetFields:
    """Tests for validate_set_fields."""

    def test_all_attribute_fields_valid(self) -> None:
        """Test validate_set_fields passes when all keys are valid attribute names."""
        data = {"name": "router1", "status": "active"}
        validate_set_fields(data, attribute_names=["name", "status"], relationship_names=[])

    def test_all_relationship_fields_valid(self) -> None:
        """Test validate_set_fields passes when all keys are valid relationship names."""
        data = {"site": "dc1"}
        validate_set_fields(data, attribute_names=[], relationship_names=["site"])

    def test_mixed_attribute_and_relationship_fields_valid(self) -> None:
        """Test validate_set_fields passes with a mix of attribute and relationship keys."""
        data = {"name": "router1", "site": "dc1"}
        validate_set_fields(data, attribute_names=["name"], relationship_names=["site"])

    def test_empty_data_passes(self) -> None:
        """Test validate_set_fields passes when data is empty."""
        validate_set_fields({}, attribute_names=["name"], relationship_names=["site"])

    def test_unknown_field_raises_bad_parameter(self) -> None:
        """Test validate_set_fields raises BadParameter for an unknown field."""
        data = {"unknown_field": "value"}
        with pytest.raises(typer.BadParameter, match="Unknown field"):
            validate_set_fields(data, attribute_names=["name"], relationship_names=["site"])

    def test_error_message_lists_invalid_field(self) -> None:
        """Test that the error message includes the invalid field name."""
        data = {"bogus": "value"}
        with pytest.raises(typer.BadParameter, match="bogus"):
            validate_set_fields(data, attribute_names=["name"], relationship_names=[])

    def test_error_message_lists_valid_fields(self) -> None:
        """Test that the error message includes the list of valid fields."""
        data = {"bogus": "value"}
        with pytest.raises(typer.BadParameter, match="name"):
            validate_set_fields(data, attribute_names=["name"], relationship_names=["site"])

    def test_multiple_unknown_fields_raises_bad_parameter(self) -> None:
        """Test validate_set_fields raises BadParameter listing multiple unknown fields."""
        data = {"bad1": "x", "bad2": "y"}
        with pytest.raises(typer.BadParameter, match="bad1"):
            validate_set_fields(data, attribute_names=["name"], relationship_names=[])
