"""Opinionated formatter for Infrahub schema YAML files.

The formatter's single responsibility is the *ordering of keys* (lines) within
each node, generic, attribute, relationship and dropdown choice, so that
hand-authored schema files read consistently and produce small diffs.

Design constraints:

- Only the user's own ("core") nodes are formatted. Nodes and generics whose
  ``namespace`` is one of Infrahub's :data:`RESTRICTED_NAMESPACES` are left
  untouched, since those are Infrahub-mandatory and never hand-authored.
- List *items* are never reordered — attributes and relationships are grouped
  by domain logic by their authors and only loosely track ``order_weight``.
- The transformation is guaranteed to be semantics-preserving: only line order
  changes. :func:`format_schema_text` re-parses its own output and raises if
  the reloaded data differs from the input.

Formatting is done with ``ruamel.yaml`` in round-trip mode, so comments (the
``# yaml-language-server`` header, standalone notes, and inline comments),
quoting style, and flow-style sequences (e.g. ``[manufacturer, name__value]``)
are all preserved.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import yaml
from ruamel.yaml import YAML

# Mirrors ``infrahub.core.constants.RESTRICTED_NAMESPACES``. Kept as a local
# copy because the SDK does not depend on the Infrahub backend. This list is
# stable; if it drifts, a node in a newly restricted namespace would simply be
# formatted like a user node (a harmless outcome for a line-ordering tool).
RESTRICTED_NAMESPACES: list[str] = [
    "Account",
    "Branch",
    "Builtin",
    "Core",
    "Deprecated",
    "Diff",
    "Infrahub",
    "Internal",
    "Lineage",
    "Schema",
    "Profile",
    "Template",
]

SCHEMA_URL = "https://schema.infrahub.app/infrahub/schema/latest.json"
SCHEMA_HEADER = f"---\n# yaml-language-server: $schema={SCHEMA_URL}\n"

# Canonical key orders. Each pair is (leading keys, trailing keys); any key not
# listed is preserved in its original position between the two groups so the
# formatter never drops data.
FILE_ORDER = ["version", "generics", "nodes", "extensions"]

NODE_ORDER = [
    "name",
    "namespace",
    "description",
    "label",
    "icon",
    "documentation",
    "include_in_menu",
    "menu_placement",
    "inherit_from",
    "parent",
    "children",
    "hierarchical",
    "default_filter",
    "human_friendly_id",
    "order_by",
    "display_label",
    "display_labels",
    "uniqueness_constraints",
    "generate_profile",
    "generate_template",
    "used_by",
    "restricted_namespaces",
    "branch",
    "state",
]
NODE_LAST = ["attributes", "relationships"]

ATTRIBUTE_ORDER = [
    "name",
    "kind",
    "label",
    "unique",
    "read_only",
    "computed_attribute",
    "default_value",
    "enum",
    "choices",
    "regex",
    "min_length",
    "max_length",
    "parameters",
    "optional",
    "description",
    "allow_override",
    "branch",
    "deprecation",
    "state",
]
ATTRIBUTE_LAST = ["order_weight"]

RELATIONSHIP_ORDER = [
    "name",
    "peer",
    "label",
    "kind",
    "cardinality",
    "optional",
    "identifier",
    "direction",
    "on_delete",
    "hierarchical",
    "min_count",
    "max_count",
    "common_parent",
    "common_relatives",
    "read_only",
    "allow_override",
    "branch",
    "deprecation",
    "state",
    "description",
]
RELATIONSHIP_LAST = ["order_weight"]

CHOICE_ORDER = ["name", "label", "description", "color"]

EXTENSION_NODE_ORDER = ["kind", "inherit_from"]
EXTENSION_NODE_LAST = ["attributes", "relationships"]


class FormatError(Exception):
    """Raised when formatting would change the meaning of a schema file."""


def _build_yaml() -> YAML:
    """Return a round-trip YAML handler configured to match the schema-library style."""
    yaml_handler = YAML()
    yaml_handler.preserve_quotes = True
    # Schema files begin with a `---` document-start marker; keep it.
    yaml_handler.explicit_start = True
    # Match the schema-library layout: block sequences indented under their key
    # (`attributes:\n  - name: ...`).
    yaml_handler.indent(mapping=2, sequence=4, offset=2)
    # A very wide value keeps long scalars (descriptions, Jinja2 templates) on
    # their original line instead of being re-wrapped.
    yaml_handler.width = 4096
    return yaml_handler


def reorder_mapping(mapping: Any, leading: list[str], trailing: list[str]) -> None:
    """Reorder a mapping's keys in place into canonical order.

    Keys in ``leading`` come first (in that order), keys in ``trailing`` come
    last (in that order), and any remaining keys keep their original relative
    order in between. Reordering is done in place with ``move_to_end`` so the
    comments ruamel attaches to each key travel with it.

    Args:
        mapping: The (round-trip) mapping to reorder.
        leading: Keys to place first, in order.
        trailing: Keys to force to the end, in order.
    """
    # Round-trip maps (and OrderedDict) support move_to_end; anything else
    # (a scalar, a plain list) is left as-is.
    if not hasattr(mapping, "move_to_end"):
        return

    known = set(leading) | set(trailing)
    ordered_keys = [key for key in leading if key in mapping]
    ordered_keys += [key for key in mapping if key not in known]
    ordered_keys += [key for key in trailing if key in mapping]

    for key in ordered_keys:
        mapping.move_to_end(key)


def _format_attribute(attribute: Any) -> None:
    reorder_mapping(attribute, ATTRIBUTE_ORDER, ATTRIBUTE_LAST)
    choices = attribute.get("choices") if isinstance(attribute, dict) else None
    if isinstance(choices, list):
        for choice in choices:
            reorder_mapping(choice, CHOICE_ORDER, [])


def _format_entity(entity: Any, leading: list[str], trailing: list[str]) -> None:
    """Reorder an entity's own keys, then the keys of its attributes and relationships."""
    reorder_mapping(entity, leading, trailing)
    for attribute in entity.get("attributes") or []:
        _format_attribute(attribute)
    for relationship in entity.get("relationships") or []:
        reorder_mapping(relationship, RELATIONSHIP_ORDER, RELATIONSHIP_LAST)


def _is_restricted(entity: Any) -> bool:
    return isinstance(entity, dict) and entity.get("namespace") in RESTRICTED_NAMESPACES


def format_document(data: Any) -> None:
    """Reorder every key in a parsed schema document in place, into canonical order.

    Nodes and generics in a restricted namespace are left untouched. Extension
    entries are always formatted, since the extension block itself is authored
    by the user regardless of which node it extends.

    Args:
        data: The parsed (round-trip) schema document.
    """
    reorder_mapping(data, FILE_ORDER, [])

    for section in ("generics", "nodes"):
        entities = data.get(section)
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if isinstance(entity, dict) and not _is_restricted(entity):
                _format_entity(entity, NODE_ORDER, NODE_LAST)

    extensions = data.get("extensions")
    if isinstance(extensions, dict) and isinstance(extensions.get("nodes"), list):
        for entity in extensions["nodes"]:
            if isinstance(entity, dict):
                _format_entity(entity, EXTENSION_NODE_ORDER, EXTENSION_NODE_LAST)


def _ensure_schema_header(text: str) -> str:
    """Add the canonical ``# yaml-language-server`` header if the file lacks one."""
    if "yaml-language-server" in text:
        return text
    if text.startswith("---\n"):
        return SCHEMA_HEADER + text[len("---\n") :]
    return SCHEMA_HEADER + text


def is_schema_document(content: Any) -> bool:
    """Return True if ``content`` looks like an Infrahub schema file."""
    return (
        isinstance(content, dict)
        and "version" in content
        and any(key in content for key in ("nodes", "generics", "extensions"))
    )


def format_schema_text(raw_text: str) -> str:
    """Format the text of a schema file into canonical YAML text.

    Args:
        raw_text: The original file contents.

    Returns:
        The formatted YAML text, with comments and quoting preserved.

    Raises:
        FormatError: If the formatted output does not reload to the same data,
            i.e. formatting would change the file's meaning.
    """
    yaml_handler = _build_yaml()
    data = yaml_handler.load(raw_text)

    if not is_schema_document(data):
        return raw_text

    format_document(data)

    buffer = StringIO()
    yaml_handler.dump(data, buffer)
    text = _ensure_schema_header(buffer.getvalue())

    if yaml.safe_load(text) != yaml.safe_load(raw_text):
        raise FormatError("Formatting would change the schema content; aborting to avoid data loss.")

    return text
