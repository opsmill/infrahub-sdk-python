"""Unit tests for infrahub_sdk.ctl.formatters.yaml (YamlFormatter)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import yaml  # pyright: ignore[reportMissingModuleSource]

from infrahub_sdk.ctl.formatters.yaml import YamlFormatter


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


class TestYamlFormatterFormatList:
    """Tests for YamlFormatter.format_list."""

    def test_format_list_produces_valid_yaml(self) -> None:
        """Test that format_list output can be parsed as valid YAML."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_list([node], schema)

        parsed = yaml.safe_load(result)
        assert isinstance(parsed, dict)

    def test_format_list_contains_api_version(self) -> None:
        """Test that format_list output contains the infrahub apiVersion field."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_list([node], schema)

        parsed = yaml.safe_load(result)
        assert parsed["apiVersion"] == "infrahub.app/v1"

    def test_format_list_contains_kind_object(self) -> None:
        """Test that format_list output has kind set to Object."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_list([node], schema)

        parsed = yaml.safe_load(result)
        assert parsed["kind"] == "Object"

    def test_format_list_spec_kind_matches_schema(self) -> None:
        """Test that spec.kind matches the schema kind."""
        schema = _make_mock_schema(["name"], [], kind="InfraDevice")
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_list([node], schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["kind"] == "InfraDevice"

    def test_format_list_spec_data_is_list(self) -> None:
        """Test that spec.data is a list."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_list([node], schema)

        parsed = yaml.safe_load(result)
        assert isinstance(parsed["spec"]["data"], list)

    def test_format_list_data_contains_attribute_value(self) -> None:
        """Test that spec.data entries contain the attribute value."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_list([node], schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["data"][0]["name"] == "router1"

    def test_format_list_data_one_entry_per_node(self) -> None:
        """Test that spec.data contains one entry per node."""
        schema = _make_mock_schema(["name"], [])
        node1 = _make_mock_node({"name": "router1"}, {}, node_id="id-1")
        node2 = _make_mock_node({"name": "router2"}, {}, node_id="id-2")
        formatter = YamlFormatter()

        result = formatter.format_list([node1, node2], schema)

        parsed = yaml.safe_load(result)
        assert len(parsed["spec"]["data"]) == 2

    def test_format_list_starts_with_document_separator(self) -> None:
        """Test that the YAML output starts with the --- document separator."""
        schema = _make_mock_schema(["name"], [])
        formatter = YamlFormatter()

        result = formatter.format_list([], schema)

        assert result.startswith("---")


class TestYamlFormatterFormatDetail:
    """Tests for YamlFormatter.format_detail."""

    def test_format_detail_produces_valid_yaml(self) -> None:
        """Test that format_detail output can be parsed as valid YAML."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert isinstance(parsed, dict)

    def test_format_detail_spec_data_has_single_entry(self) -> None:
        """Test that format_detail produces exactly one entry in spec.data."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert len(parsed["spec"]["data"]) == 1

    def test_format_detail_data_entry_contains_attribute(self) -> None:
        """Test that the single spec.data entry contains the attribute value."""
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["data"][0]["name"] == "router1"

    def test_format_detail_relationship_uses_display_label(self) -> None:
        """Test that relationship values are stored as display_label strings."""
        schema = _make_mock_schema(["name"], ["site"])
        node = _make_mock_node({"name": "router1"}, {"site": "DC1"})
        formatter = YamlFormatter()

        result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["data"][0]["site"] == "DC1"


class TestYamlFormatterEdgeCases:
    """Edge case tests targeting uncovered branches in YamlFormatter._node_to_data_entry."""

    def test_attr_detail_not_dict_uses_raw_value(self) -> None:
        """Test that a non-dict attr_detail is used as the raw entry value.

        Covers the ``else`` branch in _node_to_data_entry for attributes when
        detail.get(attr_name) returns something that is not a dict.
        """
        schema = _make_mock_schema(["name"], [])
        node = _make_mock_node({"name": "router1"}, {})
        formatter = YamlFormatter()

        fake_detail = {
            "id": "test-id",
            "display_label": "Test",
            "kind": "TestKind",
            "name": "raw-string-value",  # not a dict
        }
        with patch(
            "infrahub_sdk.ctl.formatters.yaml.extract_node_detail",
            return_value=fake_detail,
        ):
            result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["data"][0]["name"] == "raw-string-value"

    def test_rel_detail_not_dict_uses_raw_value(self) -> None:
        """Test that a non-dict rel_detail is used as the raw entry value.

        Covers the ``not isinstance(rel_detail, dict)`` branch for relationships.
        """
        schema = _make_mock_schema([], ["site"])
        node = _make_mock_node({}, {"site": "DC1"})
        formatter = YamlFormatter()

        fake_detail = {
            "id": "test-id",
            "display_label": "Test",
            "kind": "TestKind",
            "site": "non-dict-rel-value",  # not a dict
        }
        with patch(
            "infrahub_sdk.ctl.formatters.yaml.extract_node_detail",
            return_value=fake_detail,
        ):
            result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["data"][0]["site"] == "non-dict-rel-value"

    def test_rel_cardinality_one_with_empty_display_label(self) -> None:
        """Test cardinality-one relationship with an empty display_label.

        Covers the ``cardinality == "one"`` branch where display_label is "".
        """
        schema = _make_mock_schema([], ["site"])
        node = _make_mock_node({}, {})
        # Attach a relationship with empty display_label using configure_mock
        # to avoid setattr with a constant string literal.
        rel = MagicMock()
        rel.display_label = ""
        rel.id = "site-id"
        node.configure_mock(site=rel)
        formatter = YamlFormatter()

        result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert not parsed["spec"]["data"][0]["site"]

    def test_rel_cardinality_many_with_empty_peers(self) -> None:
        """Test cardinality-many relationship with an empty peers list.

        Covers the ``peers`` empty branch producing ``{"data": []}``.
        """
        schema = MagicMock()
        schema.kind = "TestKind"
        schema.attribute_names = []
        schema.relationship_names = ["tags"]

        def get_rel_side_effect(name: str) -> MagicMock:
            rel = MagicMock()
            rel.cardinality = "many"
            return rel

        schema.get_relationship = MagicMock(side_effect=get_rel_side_effect)

        node = MagicMock()
        node.id = "test-id"
        node.display_label = "Test"
        rel_manager = MagicMock()
        rel_manager.peers = []
        node.configure_mock(tags=rel_manager)

        formatter = YamlFormatter()
        result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["data"][0]["tags"] == {"data": []}

    def test_rel_cardinality_many_with_peers(self) -> None:
        """Test cardinality-many relationship with populated peers.

        Covers the ``peers`` non-empty branch producing ``{"data": [...]}``.
        """
        schema = MagicMock()
        schema.kind = "TestKind"
        schema.attribute_names = []
        schema.relationship_names = ["tags"]

        def get_rel_side_effect(name: str) -> MagicMock:
            rel = MagicMock()
            rel.cardinality = "many"
            return rel

        schema.get_relationship = MagicMock(side_effect=get_rel_side_effect)

        node = MagicMock()
        node.id = "test-id"
        node.display_label = "Test"
        rel_manager = MagicMock()
        rel_manager.peers = [
            MagicMock(display_label="peer1", id="id1"),
            MagicMock(display_label="peer2", id="id2"),
        ]
        node.configure_mock(tags=rel_manager)

        formatter = YamlFormatter()
        result = formatter.format_detail(node, schema)

        parsed = yaml.safe_load(result)
        assert parsed["spec"]["data"][0]["tags"] == {"data": ["peer1", "peer2"]}
