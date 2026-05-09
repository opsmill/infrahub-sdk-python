"""Unit tests for infrahub_sdk.ctl.formatters.csv (CsvFormatter)."""

from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock

from infrahub_sdk.ctl.formatters.csv import CsvFormatter


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


def _parse_csv(text: str) -> list[dict[str, str]]:
    """Parse a CSV string into a list of row dicts.

    Args:
        text: CSV-formatted string.

    Returns:
        List of dicts keyed by header row values.

    """
    return list(csv.DictReader(io.StringIO(text)))


class TestCsvFormatterFormatList:
    """Tests for CsvFormatter.format_list."""

    def test_format_list_returns_string(self) -> None:
        """Test that format_list returns a string."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = CsvFormatter()

        result = formatter.format_list([node], schema)

        assert isinstance(result, str)

    def test_format_list_has_header_row_with_attribute_name(self) -> None:
        """Test that the first row contains attribute column headers."""
        schema = _make_mock_schema(["name", "status"], [])
        node = _make_mock_node({"name": "router1", "status": "active"}, {})
        formatter = CsvFormatter()

        result = formatter.format_list([node], schema)

        rows = _parse_csv(result)
        assert "name" in rows[0]
        assert "status" in rows[0]

    def test_format_list_has_header_row_with_relationship_name(self) -> None:
        """Test that the first row contains relationship column headers."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = CsvFormatter()

        result = formatter.format_list([node], schema)

        rows = _parse_csv(result)
        assert "site" in rows[0]

    def test_format_list_data_row_contains_attribute_value(self) -> None:
        """Test that data rows contain the node attribute value."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = CsvFormatter()

        result = formatter.format_list([node], schema)

        rows = _parse_csv(result)
        assert rows[0]["name"] == "router1"

    def test_format_list_data_row_contains_relationship_value(self) -> None:
        """Test that data rows contain the relationship display label."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = CsvFormatter()

        result = formatter.format_list([node], schema)

        rows = _parse_csv(result)
        assert rows[0]["site"] == "DC1"

    def test_format_list_one_data_row_per_node(self) -> None:
        """Test that format_list produces one data row per node."""
        schema = _make_mock_schema(["name"], [])
        node1 = _make_mock_node({"name": "router1"}, {}, node_id="id-1")
        node2 = _make_mock_node({"name": "router2"}, {}, node_id="id-2")
        formatter = CsvFormatter()

        result = formatter.format_list([node1, node2], schema)

        rows = _parse_csv(result)
        assert len(rows) == 2

    def test_format_list_empty_nodes_returns_header_only(self) -> None:
        """Test that format_list with no nodes returns only the header row."""
        schema = _make_mock_schema(["name"], [])
        formatter = CsvFormatter()

        result = formatter.format_list([], schema)

        rows = _parse_csv(result)
        assert rows == []
        # With no data rows, all column headers are still shown
        assert "name" in result


class TestCsvFormatterFormatDetail:
    """Tests for CsvFormatter.format_detail."""

    def test_format_detail_returns_string(self) -> None:
        """Test that format_detail returns a string."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = CsvFormatter()

        result = formatter.format_detail(node, schema)

        assert isinstance(result, str)

    def test_format_detail_has_field_value_headers(self) -> None:
        """Test that format_detail output has field and value column headers."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = CsvFormatter()

        result = formatter.format_detail(node, schema)

        rows = _parse_csv(result)
        assert "field" in rows[0]
        assert "value" in rows[0]

    def test_format_detail_contains_id_row(self) -> None:
        """Test that format_detail includes a row for the node id."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {}, node_id="abc-123")
        formatter = CsvFormatter()

        result = formatter.format_detail(node, schema)

        rows = _parse_csv(result)
        id_row = next(r for r in rows if r["field"] == "id")
        assert id_row["value"] == "abc-123"

    def test_format_detail_contains_display_label_row(self) -> None:
        """Test that format_detail includes a row for display_label."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {}, display_label="Router One")
        formatter = CsvFormatter()

        result = formatter.format_detail(node, schema)

        rows = _parse_csv(result)
        label_row = next(r for r in rows if r["field"] == "display_label")
        assert label_row["value"] == "Router One"

    def test_format_detail_contains_kind_row(self) -> None:
        """Test that format_detail includes a row for the schema kind."""
        schema = _make_mock_schema(["name"], [], kind="InfraDevice")
        node = _make_mock_node({"name": "router1"}, {})
        formatter = CsvFormatter()

        result = formatter.format_detail(node, schema)

        rows = _parse_csv(result)
        kind_row = next(r for r in rows if r["field"] == "kind")
        assert kind_row["value"] == "InfraDevice"

    def test_format_detail_contains_attribute_row(self) -> None:
        """Test that format_detail includes a row for each attribute."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = CsvFormatter()

        result = formatter.format_detail(node, schema)

        rows = _parse_csv(result)
        name_row = next(r for r in rows if r["field"] == "name")
        assert name_row["value"] == "router1"

    def test_format_detail_contains_relationship_row(self) -> None:
        """Test that format_detail includes a row for each relationship."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = CsvFormatter()

        result = formatter.format_detail(node, schema)

        rows = _parse_csv(result)
        site_row = next(r for r in rows if r["field"] == "site")
        assert site_row["value"] == "DC1"
