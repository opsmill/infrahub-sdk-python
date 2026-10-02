"""Unit tests for infrahub_sdk.ctl.formatters.json (JsonFormatter)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

from infrahub_sdk.ctl.formatters.json import JsonFormatter
from tests.unit.sdk.test_node_field_access import LOCATION_ID, PRIMARY_TAG_ID, no_field_warning

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from infrahub_sdk.node import InfrahubNode
    from infrahub_sdk.schema import NodeSchemaAPI


def _make_mock_schema(
    attr_names: list[str],
    rel_names: list[str],
    kind: str = "TestKind",
) -> MagicMock:
    """Build a minimal schema mock with the given attribute and relationship names.

    Args:
        attr_names: List of attribute names.
        rel_names: List of relationship names.
        kind: Schema kind string.

    Returns:
        MagicMock configured to behave like a MainSchemaTypesAPI object.

    """
    schema = MagicMock()
    schema.kind = kind
    schema.attribute_names = attr_names
    schema.relationship_names = rel_names
    for _name in rel_names:
        rel = MagicMock()
        rel.cardinality = "one"
        schema.get_relationship.return_value = rel
    return schema


def _make_mock_node(
    attr_values: dict[str, object],
    rel_values: dict[str, str],
    node_id: str = "test-id",
    display_label: str = "Test",
) -> MagicMock:
    """Build a minimal node mock with the given attribute and relationship values.

    Args:
        attr_values: Mapping of attribute name to value.
        rel_values: Mapping of relationship name to display_label string.
        node_id: The node ID.
        display_label: The display label for the node.

    Returns:
        MagicMock configured to behave like an InfrahubNode object.

    """
    node = MagicMock()
    node.id = node_id
    node.display_label = display_label
    for attr_name, value in attr_values.items():
        attr = MagicMock()
        attr.value = value
        setattr(node, attr_name, attr)
    for rel_name, label in rel_values.items():
        rel = MagicMock()
        rel.display_label = label
        rel.id = f"{rel_name}-id"
        setattr(node, rel_name, rel)
    return node


class TestJsonFormatterFormatList:
    """Tests for JsonFormatter.format_list."""

    def test_format_list_returns_valid_json(self) -> None:
        """Test that format_list output is valid JSON."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = JsonFormatter()

        result = formatter.format_list([node], schema)

        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_format_list_contains_attribute_value(self) -> None:
        """Test that format_list includes the node attribute value."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = JsonFormatter()

        result = formatter.format_list([node], schema)

        parsed = json.loads(result)
        assert parsed[0]["name"] == "router1"

    def test_format_list_multiple_nodes(self) -> None:
        """Test that format_list produces one array entry per node."""
        schema = _make_mock_schema(["name"], [])
        nodes = [
            _make_mock_node({"name": "router1"}, {}, node_id="id-1"),
            _make_mock_node({"name": "router2"}, {}, node_id="id-2"),
        ]
        formatter = JsonFormatter()

        result = formatter.format_list(cast("list[InfrahubNode]", nodes), schema)

        parsed = json.loads(result)
        assert len(parsed) == 2

    def test_format_list_empty_list_returns_json_array(self) -> None:
        """Test that format_list with an empty node list returns a JSON empty array."""
        schema = _make_mock_schema(["name"], [])
        formatter = JsonFormatter()

        result = formatter.format_list([], schema)

        assert result.strip() == "[]"

    def test_format_list_includes_relationship_value(self) -> None:
        """Test that format_list includes relationship display labels."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = JsonFormatter()

        result = formatter.format_list([node], schema)

        parsed = json.loads(result)
        assert parsed[0]["site"] == "DC1"


class TestJsonFormatterFormatDetail:
    """Tests for JsonFormatter.format_detail."""

    def test_format_detail_returns_valid_json(self) -> None:
        """Test that format_detail output is valid JSON."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = JsonFormatter()

        result = formatter.format_detail(node, schema)

        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_format_detail_contains_id(self) -> None:
        """Test that format_detail includes the node id field."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {}, node_id="abc-123")
        formatter = JsonFormatter()

        result = formatter.format_detail(node, schema)

        parsed = json.loads(result)
        assert parsed["id"] == "abc-123"

    def test_format_detail_contains_display_label(self) -> None:
        """Test that format_detail includes the display_label metadata field."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {}, display_label="Router One")
        formatter = JsonFormatter()

        result = formatter.format_detail(node, schema)

        parsed = json.loads(result)
        assert parsed["display_label"] == "Router One"

    def test_format_detail_contains_kind(self) -> None:
        """Test that format_detail includes the kind metadata field from schema."""
        schema = _make_mock_schema(["name"], [], kind="InfraDevice")
        node = _make_mock_node({"name": "router1"}, {})
        formatter = JsonFormatter()

        result = formatter.format_detail(node, schema)

        parsed = json.loads(result)
        assert parsed["kind"] == "InfraDevice"

    def test_format_detail_contains_attribute_value(self) -> None:
        """Test that format_detail includes attribute values nested under their name."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = JsonFormatter()

        result = formatter.format_detail(node, schema)

        parsed = json.loads(result)
        assert parsed["name"]["value"] == "router1"

    def test_format_detail_contains_relationship(self) -> None:
        """Test that format_detail includes relationship data."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = JsonFormatter()

        result = formatter.format_detail(node, schema)

        parsed = json.loads(result)
        assert "site" in parsed
        assert parsed["site"]["display_label"] == "DC1"


class TestJsonFormatterUnknownFields:
    """Fields the SDK never fetched are left out of the JSON output, without being read."""

    def test_format_list_omits_unknown_fields(
        self, fetched_location: Callable[[Collection[str]], InfrahubNode], location_schema: NodeSchemaAPI
    ) -> None:
        node = fetched_location({"description", "tags"})

        with no_field_warning():
            result = JsonFormatter().format_list([node], location_schema)

        assert json.loads(result) == [{"name": "DFW", "type": "SITE", "primary_tag": "red", "member_of_groups": ""}]

    def test_format_list_omits_unknown_cardinality_one_relationship(
        self, fetched_location: Callable[[Collection[str]], InfrahubNode], location_schema: NodeSchemaAPI
    ) -> None:
        node = fetched_location({"primary_tag"})

        with no_field_warning():
            result = JsonFormatter().format_list([node], location_schema)

        assert json.loads(result) == [
            {
                "name": "DFW",
                "description": "Dallas data center",
                "type": "SITE",
                "tags": "blue",
                "member_of_groups": "",
            }
        ]

    def test_format_detail_omits_unknown_fields(
        self, fetched_location: Callable[[Collection[str]], InfrahubNode], location_schema: NodeSchemaAPI
    ) -> None:
        node = fetched_location({"description", "tags"})

        with no_field_warning():
            result = JsonFormatter().format_detail(node, location_schema)

        assert json.loads(result) == {
            "id": LOCATION_ID,
            "display_label": "dfw1",
            "kind": "BuiltinLocation",
            "name": {"value": "DFW"},
            "type": {"value": "SITE"},
            "primary_tag": {"display_label": "red", "id": PRIMARY_TAG_ID, "cardinality": "one"},
            "member_of_groups": {"peers": [], "cardinality": "many"},
        }

    def test_format_detail_omits_unknown_cardinality_one_relationship(
        self, fetched_location: Callable[[Collection[str]], InfrahubNode], location_schema: NodeSchemaAPI
    ) -> None:
        node = fetched_location({"primary_tag"})

        with no_field_warning():
            result = JsonFormatter().format_detail(node, location_schema)

        assert "primary_tag" not in json.loads(result)
