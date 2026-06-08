"""Unit tests for infrahub_sdk.ctl.formatters.table (TableFormatter)."""

from __future__ import annotations

from unittest.mock import MagicMock

from infrahub_sdk.ctl.formatters.table import TableFormatter


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


class TestTableFormatterFormatList:
    """Tests for TableFormatter.format_list."""

    def test_format_list_returns_string(self) -> None:
        """Test that format_list returns a string."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = TableFormatter()

        result = formatter.format_list([node], schema)

        assert isinstance(result, str)

    def test_format_list_contains_attribute_column_header(self) -> None:
        """Test that format_list output includes attribute names as column headers."""
        schema = _make_mock_schema(["name", "status"], [])
        node = _make_mock_node({"name": "router1", "status": "active"}, {})
        formatter = TableFormatter()

        result = formatter.format_list([node], schema)

        assert "name" in result
        assert "status" in result

    def test_format_list_contains_relationship_column_header(self) -> None:
        """Test that format_list output includes relationship names as column headers."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = TableFormatter()

        result = formatter.format_list([node], schema)

        assert "site" in result

    def test_format_list_contains_attribute_value(self) -> None:
        """Test that format_list output includes node attribute values."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = TableFormatter()

        result = formatter.format_list([node], schema)

        assert "router1" in result

    def test_format_list_contains_relationship_value(self) -> None:
        """Test that format_list output includes relationship display labels."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = TableFormatter()

        result = formatter.format_list([node], schema)

        assert "DC1" in result

    def test_format_list_multiple_nodes(self) -> None:
        """Test that format_list renders all nodes."""
        schema = _make_mock_schema(["name"], [])
        node1 = _make_mock_node({"name": "router1"}, {}, node_id="id-1")
        node2 = _make_mock_node({"name": "router2"}, {}, node_id="id-2")
        formatter = TableFormatter()

        result = formatter.format_list([node1, node2], schema)

        assert "router1" in result
        assert "router2" in result


class TestTableFormatterFormatDetail:
    """Tests for TableFormatter.format_detail."""

    def test_format_detail_returns_string(self) -> None:
        """Test that format_detail returns a string."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = TableFormatter()

        result = formatter.format_detail(node, schema)

        assert isinstance(result, str)

    def test_format_detail_contains_field_column_header(self) -> None:
        """Test that format_detail output includes the Field column header."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = TableFormatter()

        result = formatter.format_detail(node, schema)

        assert "Field" in result

    def test_format_detail_contains_value_column_header(self) -> None:
        """Test that format_detail output includes the Value column header."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = TableFormatter()

        result = formatter.format_detail(node, schema)

        assert "Value" in result

    def test_format_detail_contains_id_field(self) -> None:
        """Test that format_detail output includes the id metadata field."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {}, node_id="abc-123")
        formatter = TableFormatter()

        result = formatter.format_detail(node, schema)

        assert "id" in result
        assert "abc-123" in result

    def test_format_detail_contains_display_label_field(self) -> None:
        """Test that format_detail output includes the display_label metadata field."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {}, display_label="Router One")
        formatter = TableFormatter()

        result = formatter.format_detail(node, schema)

        assert "display_label" in result
        assert "Router One" in result

    def test_format_detail_contains_attribute_name_and_value(self) -> None:
        """Test that format_detail includes attribute field names and values."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = TableFormatter()

        result = formatter.format_detail(node, schema)

        assert "name" in result
        assert "router1" in result

    def test_format_detail_contains_relationship_name_and_value(self) -> None:
        """Test that format_detail includes relationship field names and display labels."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = TableFormatter()

        result = formatter.format_detail(node, schema)

        assert "site" in result
        assert "DC1" in result
