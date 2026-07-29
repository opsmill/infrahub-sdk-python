"""Unit tests for the pure schema-formatting logic in ``schema_format``."""

from __future__ import annotations

from collections import OrderedDict

import pytest
import yaml

from infrahub_sdk.ctl.schema_format import (
    FormatError,
    FormatOptions,
    format_schema_text,
    is_schema_document,
    reorder_mapping,
)

NODE_DOC = """\
---
# yaml-language-server: $schema=https://schema.infrahub.app/infrahub/schema/latest.json
version: "1.0"

nodes:
  - relationships:
      - peer: BuiltinTag
        name: tags
    attributes:
      - order_weight: 1500
        optional: true
        name: status
        kind: Dropdown
        choices:
          - color: "#fff"
            name: active
            label: Active
    namespace: Dcim
    name: Device
    label: Device
    description: A device.
"""


def _keys_of(text: str, path: list) -> list[str]:
    """Load formatted YAML and return the key order of the mapping at ``path``."""
    data = yaml.safe_load(text)
    for step in path:
        data = data[step]
    return list(data.keys())


def test_reorder_mapping_leading_trailing_and_unknown() -> None:
    data = OrderedDict([("order_weight", 1000), ("extra", "x"), ("kind", "Text"), ("name", "field")])
    reorder_mapping(data, leading=["name", "kind"], trailing=["order_weight"])

    # name/kind first, order_weight last, unknown key preserved in the middle.
    assert list(data.keys()) == ["name", "kind", "extra", "order_weight"]


def test_node_key_order_is_canonical() -> None:
    text = format_schema_text(NODE_DOC)

    # Top-level sections: version before nodes.
    assert _keys_of(text, [])[:2] == ["version", "nodes"]
    # name/namespace first; attributes then relationships always last.
    assert _keys_of(text, ["nodes", 0]) == [
        "name",
        "namespace",
        "description",
        "label",
        "attributes",
        "relationships",
    ]


def test_attribute_relationship_and_choice_inner_order() -> None:
    text = format_schema_text(NODE_DOC)

    attr_keys = _keys_of(text, ["nodes", 0, "attributes", 0])
    assert attr_keys == ["name", "kind", "choices", "optional", "order_weight"]
    assert attr_keys[-1] == "order_weight"

    assert _keys_of(text, ["nodes", 0, "attributes", 0, "choices", 0]) == ["name", "label", "color"]
    assert _keys_of(text, ["nodes", 0, "relationships", 0]) == ["name", "peer"]


def test_restricted_namespace_nodes_are_untouched() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - namespace: Core
    name: Something
    attributes:
      - order_weight: 1
        kind: Text
        name: x
  - namespace: Dcim
    name: Device
    attributes:
      - order_weight: 1
        kind: Text
        name: x
"""
    text = format_schema_text(doc)

    # Core node keeps its authored (scrambled) attribute key order.
    assert _keys_of(text, ["nodes", 0, "attributes", 0]) == ["order_weight", "kind", "name"]
    # Dcim (user) node is reordered.
    assert _keys_of(text, ["nodes", 1, "attributes", 0]) == ["name", "kind", "order_weight"]


def test_extensions_are_formatted() -> None:
    doc = """\
---
version: "1.0"
extensions:
  nodes:
    - relationships:
        - peer: LocationSite
          name: sites
      kind: OrganizationProvider
"""
    text = format_schema_text(doc)
    assert _keys_of(text, ["extensions", "nodes", 0]) == ["kind", "relationships"]
    assert _keys_of(text, ["extensions", "nodes", 0, "relationships", 0]) == ["name", "peer"]


def test_unknown_keys_are_preserved_not_dropped() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - name: Device
    namespace: Dcim
    some_future_key: value
"""
    text = format_schema_text(doc)
    assert _keys_of(text, ["nodes", 0]) == ["name", "namespace", "some_future_key"]
    assert yaml.safe_load(text)["nodes"][0]["some_future_key"] == "value"


def test_comments_are_preserved() -> None:
    doc = """\
---
# yaml-language-server: $schema=https://schema.infrahub.app/infrahub/schema/latest.json
version: "1.0"

nodes:
  # a banner comment before the node
  - namespace: Dcim
    name: Device
    attributes:
      - name: status
        kind: Dropdown
        choices:
          - name: active
            color: "#7fbf7f" # a trailing inline comment
"""
    text = format_schema_text(doc)
    assert "# a banner comment before the node" in text
    assert "# a trailing inline comment" in text
    assert "yaml-language-server" in text


def test_flow_style_sequences_are_preserved() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - name: Device
    namespace: Dcim
    uniqueness_constraints:
      - [manufacturer, name__value]
"""
    text = format_schema_text(doc)
    # The inline (flow) sequence is not expanded to block style.
    assert "[manufacturer, name__value]" in text


def test_quotes_are_preserved() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - name: Device
    namespace: Dcim
    description: "A quoted description"
"""
    text = format_schema_text(doc)
    assert 'description: "A quoted description"' in text
    assert 'version: "1.0"' in text


def test_multiline_string_round_trips() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - name: Device
    namespace: Dcim
    attributes:
      - name: computed
        kind: Text
        read_only: true
        computed_attribute:
          kind: Jinja2
          jinja2_template: >-
            {{ a__value }}-{{ b__value }}
"""
    text = format_schema_text(doc)
    assert yaml.safe_load(text) == yaml.safe_load(doc)


def test_header_is_added_when_missing() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - name: Device
    namespace: Dcim
"""
    text = format_schema_text(doc)
    assert text.startswith("---\n# yaml-language-server:")


def test_format_is_idempotent_and_semantics_preserved() -> None:
    once = format_schema_text(NODE_DOC)
    assert format_schema_text(once) == once
    assert yaml.safe_load(once) == yaml.safe_load(NODE_DOC)


def test_non_schema_document_is_returned_unchanged() -> None:
    doc = "apiVersion: infrahub.app/v1\nkind: Menu\nspec:\n  data: []\n"
    assert format_schema_text(doc) == doc


def test_format_error_raised_on_semantic_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate a formatting step that silently drops data; the guard must catch it.
    def _wipe(data: dict, options: object = None) -> None:
        data.clear()

    monkeypatch.setattr("infrahub_sdk.ctl.schema_format.format_document", _wipe)

    with pytest.raises(FormatError):
        format_schema_text(NODE_DOC)


def test_malformed_non_list_attributes_is_left_untouched() -> None:
    # A parseable schema whose `attributes` is not a list must not crash the
    # formatter; that section is simply left as-is.
    doc = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    attributes: 5
    relationships: not-a-list
"""
    text = format_schema_text(doc)
    assert yaml.safe_load(text) == yaml.safe_load(doc)


def test_header_not_added_when_substring_appears_in_scalar() -> None:
    # `yaml-language-server` appearing in a value (not as a real header line)
    # must not suppress the header being added.
    doc = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    description: see the yaml-language-server extension docs
"""
    text = format_schema_text(doc)
    assert text.startswith("---\n# yaml-language-server: $schema=")
    # The real directive appears exactly once (added, not duplicated later).
    assert text.count("# yaml-language-server:") == 1


def test_existing_header_is_not_duplicated() -> None:
    doc = """\
---
# yaml-language-server: $schema=https://schema.infrahub.app/infrahub/schema/latest.json
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
"""
    text = format_schema_text(doc)
    assert text.count("# yaml-language-server:") == 1


STRIP_DOC = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    attributes:
      - name: a
        kind: Text
        optional: false
      - name: b
        kind: Text
        optional: true
    relationships:
      - name: r1
        peer: DcimX
        optional: true
        cardinality: many
        kind: Generic
      - name: r2
        peer: DcimY
        optional: false
        cardinality: one
        kind: Attribute
"""


def test_strip_defaults_removes_only_default_values() -> None:
    node = yaml.safe_load(format_schema_text(STRIP_DOC, FormatOptions(strip_defaults=True)))["nodes"][0]
    attrs = {a["name"]: a for a in node["attributes"]}
    rels = {r["name"]: r for r in node["relationships"]}

    # Attribute default optional:false stripped; non-default optional:true kept.
    assert "optional" not in attrs["a"]
    assert attrs["b"]["optional"] is True

    # Relationship defaults (optional:true, cardinality:many, kind:Generic) stripped.
    assert set(rels["r1"].keys()) == {"name", "peer"}
    # Non-default relationship values are kept.
    assert rels["r2"]["optional"] is False
    assert rels["r2"]["cardinality"] == "one"
    assert rels["r2"]["kind"] == "Attribute"


SORT_DOC = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    attributes:
      - name: c
        kind: Text
        order_weight: 3000
      - name: a
        kind: Text
        order_weight: 1000
      - name: b
        kind: Text
      - name: d
        kind: Text
        order_weight: 2000
"""


def test_sort_by_order_weight_ascending_missing_last() -> None:
    node = yaml.safe_load(format_schema_text(SORT_DOC, FormatOptions(sort_by_order_weight=True)))["nodes"][0]
    names = [a["name"] for a in node["attributes"]]
    # Weighted ascending (a=1000, d=2000, c=3000), then the weightless one last.
    assert names == ["a", "d", "c", "b"]


def test_sort_permits_same_named_items_with_different_weights() -> None:
    # The guard must neutralise the reorder by full content, not by name — two
    # items sharing a name but differing in weight should sort, not abort.
    doc = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    attributes:
      - name: dup
        kind: Text
        order_weight: 2000
      - name: dup
        kind: Number
        order_weight: 1000
"""
    text = format_schema_text(doc, FormatOptions(sort_by_order_weight=True))
    attrs = yaml.safe_load(text)["nodes"][0]["attributes"]
    assert [a["order_weight"] for a in attrs] == [1000, 2000]


def test_backfill_order_weight_only_fills_missing() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    attributes:
      - name: a
        kind: Text
      - name: b
        kind: Text
        order_weight: 5
"""
    node = yaml.safe_load(format_schema_text(doc, FormatOptions(backfill_order_weight=True)))["nodes"][0]
    weights = {a["name"]: a["order_weight"] for a in node["attributes"]}
    assert weights == {"a": 1000, "b": 5}


def test_flags_are_idempotent_and_off_by_default() -> None:
    # Off by default: no content change beyond ordering (STRIP_DOC has a
    # strippable default that must survive when the flag is not set).
    default_out = yaml.safe_load(format_schema_text(STRIP_DOC))
    assert default_out["nodes"][0]["attributes"][0].get("optional") is False

    opts = FormatOptions(strip_defaults=True, sort_by_order_weight=True, backfill_order_weight=True)
    once = format_schema_text(STRIP_DOC, opts)
    assert format_schema_text(once, opts) == once


def test_reorder_mapping_ignores_non_mapping() -> None:
    # A scalar/None has no move_to_end; the call must be a harmless no-op.
    reorder_mapping("not a mapping", ["name"], [])
    reorder_mapping(None, ["name"], [])


def test_non_dict_list_items_and_nodes_are_left_untouched() -> None:
    doc = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    attributes:
      - just_a_string
  - a_scalar_node
"""
    opts = FormatOptions(strip_defaults=True, sort_by_order_weight=True, backfill_order_weight=True)
    text = format_schema_text(doc, opts)
    assert yaml.safe_load(text) == yaml.safe_load(doc)


def test_extensions_with_non_dict_node_left_untouched() -> None:
    doc = """\
---
version: "1.0"
extensions:
  nodes:
    - a_scalar_entry
"""
    assert yaml.safe_load(format_schema_text(doc)) == yaml.safe_load(doc)


def test_is_schema_document() -> None:
    assert is_schema_document({"version": "1.0", "nodes": []})
    assert is_schema_document({"version": "1.0", "generics": []})
    assert is_schema_document({"version": "1.0", "extensions": {}})
    assert not is_schema_document({"version": "1.0"})
    assert not is_schema_document({"nodes": []})
    assert not is_schema_document({"apiVersion": "infrahub.app/v1", "kind": "Menu"})
    assert not is_schema_document("not a dict")
