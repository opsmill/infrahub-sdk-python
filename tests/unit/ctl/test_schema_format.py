"""Unit tests for the pure schema-formatting logic in ``schema_format``."""

from __future__ import annotations

import pytest
import yaml

from infrahub_sdk.ctl.schema_format import (
    SCHEMA_HEADER,
    FormatError,
    count_droppable_comments,
    format_document,
    format_schema_text,
    is_schema_document,
    reorder_mapping,
)


def test_reorder_mapping_leading_trailing_and_unknown() -> None:
    data = {"order_weight": 1000, "extra": "x", "kind": "Text", "name": "field"}
    result = reorder_mapping(data, leading=["name", "kind"], trailing=["order_weight"])

    # name/kind first, order_weight last, unknown key preserved in the middle.
    assert list(result.keys()) == ["name", "kind", "extra", "order_weight"]
    # Values are untouched.
    assert result == data


def test_node_key_order_is_canonical() -> None:
    document = {
        "nodes": [
            {
                "relationships": [{"peer": "BuiltinTag", "name": "tags"}],
                "attributes": [{"order_weight": 1000, "kind": "Text", "name": "name"}],
                "namespace": "Dcim",
                "name": "Device",
                "label": "Device",
                "description": "A device.",
            }
        ],
        "version": "1.0",
    }

    result = format_document(document)

    # Top-level sections: version before nodes.
    assert list(result.keys()) == ["version", "nodes"]

    node = result["nodes"][0]
    # name/namespace first; attributes then relationships always last.
    assert list(node.keys()) == ["name", "namespace", "description", "label", "attributes", "relationships"]


def test_attribute_and_relationship_inner_order() -> None:
    document = {
        "version": "1.0",
        "nodes": [
            {
                "name": "Device",
                "namespace": "Dcim",
                "attributes": [
                    {
                        "order_weight": 1500,
                        "optional": True,
                        "name": "status",
                        "kind": "Dropdown",
                        "choices": [{"color": "#fff", "name": "active", "label": "Active"}],
                    }
                ],
                "relationships": [
                    {
                        "order_weight": 900,
                        "optional": False,
                        "cardinality": "one",
                        "kind": "Parent",
                        "peer": "DcimSite",
                        "name": "site",
                    }
                ],
            }
        ],
    }

    node = format_document(document)["nodes"][0]

    attr = node["attributes"][0]
    assert list(attr.keys()) == ["name", "kind", "choices", "optional", "order_weight"]
    # order_weight is always last for attributes.
    assert list(attr.keys())[-1] == "order_weight"
    # choice keys are canonically ordered.
    assert list(attr["choices"][0].keys()) == ["name", "label", "color"]

    rel = node["relationships"][0]
    assert list(rel.keys()) == ["name", "peer", "kind", "cardinality", "optional", "order_weight"]


def test_restricted_namespace_nodes_are_untouched() -> None:
    scrambled = {"order_weight": 1, "kind": "Text", "name": "x"}
    document = {
        "version": "1.0",
        "nodes": [
            {"namespace": "Core", "name": "Something", "attributes": [dict(scrambled)]},
            {"namespace": "Dcim", "name": "Device", "attributes": [dict(scrambled)]},
        ],
    }

    result = format_document(document)

    # Core node left exactly as authored (keys not reordered).
    core_attr = result["nodes"][0]["attributes"][0]
    assert list(core_attr.keys()) == ["order_weight", "kind", "name"]

    # Dcim (user) node is reordered.
    dcim_attr = result["nodes"][1]["attributes"][0]
    assert list(dcim_attr.keys()) == ["name", "kind", "order_weight"]


def test_extensions_are_formatted() -> None:
    document = {
        "version": "1.0",
        "extensions": {
            "nodes": [
                {
                    "relationships": [{"peer": "LocationSite", "name": "sites"}],
                    "kind": "OrganizationProvider",
                }
            ]
        },
    }

    ext_node = format_document(document)["extensions"]["nodes"][0]
    assert list(ext_node.keys()) == ["kind", "relationships"]
    assert list(ext_node["relationships"][0].keys()) == ["name", "peer"]


def test_unknown_keys_are_preserved_not_dropped() -> None:
    document = {
        "version": "1.0",
        "nodes": [{"name": "Device", "namespace": "Dcim", "some_future_key": "value"}],
    }
    node = format_document(document)["nodes"][0]
    assert node["some_future_key"] == "value"
    # Unknown key sits after the known leading keys.
    assert list(node.keys()) == ["name", "namespace", "some_future_key"]


def test_format_schema_text_adds_header_and_is_idempotent() -> None:
    document = {
        "version": "1.0",
        "nodes": [{"namespace": "Dcim", "name": "Device", "label": "Device"}],
    }

    text = format_schema_text(document)
    assert text.startswith(SCHEMA_HEADER)
    assert "yaml-language-server" in text

    # Running the formatter on its own output is a no-op.
    assert format_schema_text(yaml.safe_load(text)) == text


def test_format_schema_text_preserves_semantics() -> None:
    document = {
        "version": "1.0",
        "generics": [
            {
                "name": "GenericDevice",
                "namespace": "Dcim",
                "attributes": [{"name": "name", "kind": "Text", "unique": True, "order_weight": 1000}],
            }
        ],
    }
    text = format_schema_text(document)
    assert yaml.safe_load(text) == document


def test_multiline_string_uses_literal_block() -> None:
    document = {
        "version": "1.0",
        "nodes": [
            {
                "name": "Device",
                "namespace": "Dcim",
                "attributes": [
                    {
                        "name": "computed",
                        "kind": "Text",
                        "read_only": True,
                        "computed_attribute": {"kind": "Jinja2", "jinja2_template": "line1\nline2\n"},
                    }
                ],
            }
        ],
    }
    text = format_schema_text(document)
    assert "jinja2_template: |" in text
    # Round-trips to the same value.
    assert yaml.safe_load(text) == document


def test_blank_line_between_top_level_entries() -> None:
    document = {
        "version": "1.0",
        "nodes": [
            {"name": "A", "namespace": "Dcim"},
            {"name": "B", "namespace": "Dcim"},
        ],
    }
    text = format_schema_text(document)
    # There is a blank line separating the two node entries.
    assert "\n\n  - name: B" in text


def test_format_error_raised_on_semantic_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    document = {"version": "1.0", "nodes": [{"name": "A", "namespace": "Dcim"}]}

    # Simulate a serializer that silently drops data; the guard must catch it.
    monkeypatch.setattr("infrahub_sdk.ctl.schema_format.dump_schema", lambda _content: "version: '1.0'\n")

    with pytest.raises(FormatError):
        format_schema_text(document)


def test_is_schema_document() -> None:
    assert is_schema_document({"version": "1.0", "nodes": []})
    assert is_schema_document({"version": "1.0", "generics": []})
    assert is_schema_document({"version": "1.0", "extensions": {}})
    assert not is_schema_document({"version": "1.0"})
    assert not is_schema_document({"nodes": []})
    assert not is_schema_document({"apiVersion": "infrahub.app/v1", "kind": "Menu"})
    assert not is_schema_document("not a dict")


def test_count_droppable_comments_excludes_header() -> None:
    raw = (
        "---\n"
        "# yaml-language-server: $schema=https://schema.infrahub.app/infrahub/schema/latest.json\n"
        "version: '1.0'\n"
        "# a real comment\n"
        "nodes: []  # trailing comment on a line\n"
        "  # indented comment\n"
    )
    # Header excluded; the standalone and indented comments count. The trailing
    # inline comment on a data line is not a standalone comment line.
    assert count_droppable_comments(raw) == 2
