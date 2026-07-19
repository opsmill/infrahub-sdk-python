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
  (and cosmetic blank lines) change. :func:`format_schema_text` re-parses its
  own output and raises if the reloaded data differs from the input.

Comments other than the ``# yaml-language-server`` header are not preserved,
because the SDK serialises with PyYAML. The header is re-added canonically and
:func:`count_droppable_comments` lets callers warn about the rest.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

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


def reorder_mapping(data: dict[str, Any], leading: list[str], trailing: list[str]) -> dict[str, Any]:
    """Rebuild ``data`` with keys in canonical order.

    Keys in ``leading`` come first (in that order), keys in ``trailing`` come
    last (in that order), and any remaining keys keep their original relative
    order in between. Missing keys are skipped; nothing is dropped.

    Args:
        data: The mapping to reorder.
        leading: Keys to place first, in order.
        trailing: Keys to force to the end, in order.

    Returns:
        A new dict with the same items in canonical order.
    """
    result: dict[str, Any] = {key: data[key] for key in leading if key in data}
    known = set(leading) | set(trailing)
    result.update({key: value for key, value in data.items() if key not in known})
    result.update({key: data[key] for key in trailing if key in data})
    return result


def _format_choices(choices: Any) -> Any:
    if not isinstance(choices, list):
        return choices
    return [reorder_mapping(choice, CHOICE_ORDER, []) if isinstance(choice, dict) else choice for choice in choices]


def _format_attribute(attribute: dict[str, Any]) -> dict[str, Any]:
    ordered = reorder_mapping(attribute, ATTRIBUTE_ORDER, ATTRIBUTE_LAST)
    if "choices" in ordered:
        ordered["choices"] = _format_choices(ordered["choices"])
    return ordered


def _format_items(items: Any, formatter: Any) -> Any:
    if not isinstance(items, list):
        return items
    return [formatter(item) if isinstance(item, dict) else item for item in items]


def _format_entity(entity: dict[str, Any], leading: list[str], trailing: list[str]) -> dict[str, Any]:
    """Reorder an entity's own keys, then reorder the keys of its attributes and relationships."""
    ordered = reorder_mapping(entity, leading, trailing)
    if "attributes" in ordered:
        ordered["attributes"] = _format_items(ordered["attributes"], _format_attribute)
    if "relationships" in ordered:
        ordered["relationships"] = _format_items(
            ordered["relationships"],
            lambda rel: reorder_mapping(rel, RELATIONSHIP_ORDER, RELATIONSHIP_LAST),
        )
    return ordered


def _is_restricted(entity: dict[str, Any]) -> bool:
    return entity.get("namespace") in RESTRICTED_NAMESPACES


def format_document(content: dict[str, Any]) -> dict[str, Any]:
    """Return a new schema document with all keys in canonical order.

    Nodes and generics in a restricted namespace are left untouched. Extension
    entries are always formatted, since the extension block itself is authored
    by the user regardless of which node it extends.

    Args:
        content: The parsed schema document (as loaded from YAML).

    Returns:
        A new document dict; the input is not mutated.
    """
    result = reorder_mapping(content, FILE_ORDER, [])

    for section in ("generics", "nodes"):
        entities = result.get(section)
        if not isinstance(entities, list):
            continue
        result[section] = [
            entity
            if not isinstance(entity, dict) or _is_restricted(entity)
            else _format_entity(entity, NODE_ORDER, NODE_LAST)
            for entity in entities
        ]

    extensions = result.get("extensions")
    if isinstance(extensions, dict) and isinstance(extensions.get("nodes"), list):
        extensions["nodes"] = [
            _format_entity(entity, EXTENSION_NODE_ORDER, EXTENSION_NODE_LAST) if isinstance(entity, dict) else entity
            for entity in extensions["nodes"]
        ]

    return result


class _SchemaDumper(yaml.SafeDumper):
    """SafeDumper that indents block sequences to match the schema-library style."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:  # noqa: ARG002
        # Force indentless=False so that `- item` entries are indented under
        # their parent key (`attributes:\n  - name: ...`) instead of PyYAML's
        # default flush-left layout.
        return super().increase_indent(flow, indentless=False)


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    # Multiline strings (e.g. Jinja2 templates) are emitted as literal blocks
    # so they round-trip cleanly and stay readable.
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_SchemaDumper.add_representer(str, _str_representer)

# Top-level list items (nodes / generics) are indented by exactly two spaces by
# `_SchemaDumper`; deeper `- ` items (attributes, choices) are indented further.
_TOP_LEVEL_ITEM = re.compile(r"^  - ")
_TOP_LEVEL_SECTION = re.compile(r"^(generics|nodes|extensions):")


def _insert_blank_lines(text: str) -> str:
    """Add blank lines between top-level sections and node/generic entries.

    No blank lines are inserted between attribute/relationship items (they are
    always packed), matching the dominant schema-library convention.
    """
    lines = text.split("\n")
    output: list[str] = []
    for line in lines:
        needs_blank = bool(_TOP_LEVEL_SECTION.match(line) or _TOP_LEVEL_ITEM.match(line))
        if needs_blank and output and output[-1].strip() and not output[-1].endswith(":"):
            output.append("")
        output.append(line)
    return "\n".join(output)


def dump_schema(content: dict[str, Any]) -> str:
    """Serialise a schema document to canonical YAML text (without the header)."""
    body = yaml.dump(
        content,
        Dumper=_SchemaDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=4096,
    )
    return _insert_blank_lines(body)


def format_schema_text(content: dict[str, Any]) -> str:
    """Format a parsed schema document into final YAML text, header included.

    Args:
        content: The parsed schema document.

    Returns:
        The formatted YAML text, ready to write to disk.

    Raises:
        FormatError: If the formatted output does not reload to the same data,
            i.e. formatting would change the file's meaning.
    """
    formatted = format_document(content)
    text = SCHEMA_HEADER + dump_schema(formatted)

    reloaded = yaml.safe_load(text)
    if reloaded != content:
        raise FormatError("Formatting would change the schema content; aborting to avoid data loss.")

    return text


def is_schema_document(content: Any) -> bool:
    """Return True if ``content`` looks like an Infrahub schema file."""
    return (
        isinstance(content, dict)
        and "version" in content
        and any(key in content for key in ("nodes", "generics", "extensions"))
    )


def count_droppable_comments(raw_text: str) -> int:
    """Count comment lines that formatting will not preserve.

    The canonical ``# yaml-language-server`` header is excluded, since it is
    re-added by the formatter.

    Args:
        raw_text: The original file contents.

    Returns:
        The number of comment lines that would be lost.
    """
    count = 0
    for line in raw_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") and "yaml-language-server:" not in stripped:
            count += 1
    return count
