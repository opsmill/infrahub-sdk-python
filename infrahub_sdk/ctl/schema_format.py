"""Opinionated formatter for Infrahub schema YAML files.

The formatter's core responsibility is the *ordering of keys* (lines) within
each node, generic, attribute, relationship and dropdown choice, so that
hand-authored schema files read consistently and produce small diffs.

By default the transformation is purely cosmetic and semantics-preserving:
only line order changes, and :func:`format_schema_text` re-parses its own
output and raises if the reloaded data differs from the input.

Three opt-in transforms (see :class:`FormatOptions`) go further and *do* change
what is written — each is off by default and neutralised in the safety check so
only its intended effect is allowed:

- ``strip_defaults`` — drop keys whose value equals the schema default (context
  aware: ``optional: true`` is redundant on a relationship but meaningful on an
  attribute).
- ``sort_by_order_weight`` — sort attributes and relationships ascending by
  ``order_weight``; items without one keep their authored order and go last.
- ``backfill_order_weight`` — give attributes/relationships that lack an
  ``order_weight`` a single constant value.

Formatting is done with ``ruamel.yaml`` in round-trip mode, so comments (the
``# yaml-language-server`` header, standalone notes, and inline comments),
quoting style, and flow-style sequences (e.g. ``[manufacturer, name__value]``)
are preserved. Standalone comments sitting *between* attributes/relationships
may not follow their item when ``sort_by_order_weight`` reorders the list;
inline comments on a value always travel with it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from io import StringIO
from typing import Any

import yaml
from ruamel.yaml import YAML, YAMLError

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

# order_weight has no numeric default in the schema (the UI falls back to
# declaration order), so backfill writes this constant.
DEFAULT_BACKFILL_ORDER_WEIGHT = 1000

# Matches a real yaml-language-server directive: a comment line whose first
# non-whitespace content is ``# yaml-language-server:``. Deliberately does not
# match the substring appearing in a scalar value or an unrelated comment.
_LANGUAGE_SERVER_HEADER_RE = re.compile(r"^[ \t]*#[ \t]*yaml-language-server[ \t]*:", re.MULTILINE)

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

# Strippable defaults, grounded in the published JSON schema's ``default``
# values. Consequential or internal fields (``branch``, ``state``,
# ``inherited``, ``display``) are intentionally excluded: stripping an explicit
# value there would couple the schema to whatever the default happens to be at
# load time.
ENTITY_DEFAULTS: dict[str, Any] = {
    "generate_profile": True,
    "generate_template": False,
    "hierarchical": False,
}
ATTRIBUTE_DEFAULTS: dict[str, Any] = {
    "read_only": False,
    "unique": False,
    "optional": False,
    "allow_override": "any",
}
RELATIONSHIP_DEFAULTS: dict[str, Any] = {
    "kind": "Generic",
    "cardinality": "many",
    "optional": True,
    "direction": "bidirectional",
    "read_only": False,
    "allow_override": "any",
    "min_count": 0,
    "max_count": 0,
}


@dataclass(frozen=True)
class FormatOptions:
    """Opt-in transforms that change file content beyond key ordering."""

    strip_defaults: bool = False
    sort_by_order_weight: bool = False
    backfill_order_weight: bool = False


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


def _strip_default_keys(mapping: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Remove keys whose value equals the schema default."""
    for key, default in defaults.items():
        if key in mapping and mapping[key] == default:
            del mapping[key]


def _order_weight_sort_key(item: Any) -> float:
    weight = item.get("order_weight") if isinstance(item, dict) else None
    # Missing/non-numeric weights sort last; a stable sort keeps their order.
    return weight if isinstance(weight, int) and not isinstance(weight, bool) else float("inf")


def _format_item(item: Any, defaults: dict[str, Any], leading: list[str], options: FormatOptions) -> None:
    if not isinstance(item, dict):
        return
    if options.backfill_order_weight and "order_weight" not in item:
        item["order_weight"] = DEFAULT_BACKFILL_ORDER_WEIGHT
    if options.strip_defaults:
        _strip_default_keys(item, defaults)
    reorder_mapping(item, leading, ["order_weight"])
    if defaults is ATTRIBUTE_DEFAULTS:
        choices = item.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                reorder_mapping(choice, CHOICE_ORDER, [])


def _format_item_list(items: Any, defaults: dict[str, Any], leading: list[str], options: FormatOptions) -> None:
    if not isinstance(items, list):
        return
    for item in items:
        _format_item(item, defaults, leading, options)
    if options.sort_by_order_weight:
        items.sort(key=_order_weight_sort_key)


def _format_entity(entity: Any, leading: list[str], trailing: list[str], options: FormatOptions) -> None:
    """Reorder an entity's own keys, then transform its attributes and relationships."""
    if options.strip_defaults:
        _strip_default_keys(entity, ENTITY_DEFAULTS)
    reorder_mapping(entity, leading, trailing)
    _format_item_list(entity.get("attributes"), ATTRIBUTE_DEFAULTS, ATTRIBUTE_ORDER, options)
    _format_item_list(entity.get("relationships"), RELATIONSHIP_DEFAULTS, RELATIONSHIP_ORDER, options)


def _is_restricted(entity: Any) -> bool:
    return isinstance(entity, dict) and entity.get("namespace") in RESTRICTED_NAMESPACES


def format_document(data: Any, options: FormatOptions | None = None) -> None:
    """Reorder (and optionally transform) a parsed schema document in place.

    Nodes and generics in a restricted namespace are left untouched. Extension
    entries are always formatted, since the extension block itself is authored
    by the user regardless of which node it extends.

    Args:
        data: The parsed (round-trip) schema document.
        options: Opt-in transforms; defaults to key-ordering only.

    """
    options = options or FormatOptions()
    reorder_mapping(data, FILE_ORDER, [])

    for section in ("generics", "nodes"):
        entities = data.get(section)
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if isinstance(entity, dict) and not _is_restricted(entity):
                _format_entity(entity, NODE_ORDER, NODE_LAST, options)

    extensions = data.get("extensions")
    if isinstance(extensions, dict) and isinstance(extensions.get("nodes"), list):
        for entity in extensions["nodes"]:
            if isinstance(entity, dict):
                _format_entity(entity, EXTENSION_NODE_ORDER, EXTENSION_NODE_LAST, options)


def _ensure_schema_header(text: str) -> str:
    """Add the canonical ``# yaml-language-server`` header if the file lacks one.

    Only an actual header *directive line* counts as present — a bare
    ``yaml-language-server`` substring elsewhere (in a scalar value or an
    unrelated comment) must not suppress the header.
    """
    if _LANGUAGE_SERVER_HEADER_RE.search(text):
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


def _normalize_item(item: Any, defaults: dict[str, Any], options: FormatOptions) -> Any:
    if not isinstance(item, dict):
        return item
    normalized = dict(item)
    if options.strip_defaults:
        for key, default in defaults.items():
            normalized.setdefault(key, default)
    if options.backfill_order_weight:
        normalized.setdefault("order_weight", DEFAULT_BACKFILL_ORDER_WEIGHT)
    return normalized


def _normalize_entity(entity: Any, options: FormatOptions) -> Any:
    if not isinstance(entity, dict):
        return entity
    normalized = dict(entity)
    if options.strip_defaults:
        for key, default in ENTITY_DEFAULTS.items():
            normalized.setdefault(key, default)
    for key, defaults in (("attributes", ATTRIBUTE_DEFAULTS), ("relationships", RELATIONSHIP_DEFAULTS)):
        items = normalized.get(key)
        if isinstance(items, list):
            items = [_normalize_item(item, defaults, options) for item in items]
            if options.sort_by_order_weight:
                # Sort by full item content, not by name or weight (both of
                # which can repeat): a total, content-based order lets the guard
                # permit any reorder while still catching a dropped or corrupted
                # item.
                items = sorted(items, key=lambda it: json.dumps(it, sort_keys=True, default=str))
            normalized[key] = items
    return normalized


def _normalize_for_guard(data: Any, options: FormatOptions) -> Any:
    """Collapse exactly the intended transforms so the guard permits them.

    The same normalisation is applied to the input and the formatted output, so
    an intended change (a stripped default, a reordered list, a backfilled
    weight) is neutralised on both sides while any *unintended* corruption still
    causes inequality. With no options set this is effectively an identity.
    """
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    for section in ("generics", "nodes"):
        entities = normalized.get(section)
        if isinstance(entities, list):
            normalized[section] = [_normalize_entity(entity, options) for entity in entities]
    extensions = normalized.get("extensions")
    if isinstance(extensions, dict) and isinstance(extensions.get("nodes"), list):
        extensions = dict(extensions)
        extensions["nodes"] = [_normalize_entity(entity, options) for entity in extensions["nodes"]]
        normalized["extensions"] = extensions
    return normalized


def format_schema_text(raw_text: str, options: FormatOptions | None = None) -> str:
    """Format the text of a schema file into canonical YAML text.

    Args:
        raw_text: The original file contents.
        options: Opt-in transforms; defaults to key-ordering only.

    Returns:
        The formatted YAML text, with comments and quoting preserved.

    Raises:
        FormatError: If the file cannot be parsed as round-trip YAML (e.g. a
            duplicate key), or if formatting would change the file's meaning
            beyond the transforms requested via ``options``.

    """
    options = options or FormatOptions()
    yaml_handler = _build_yaml()
    try:
        # Round-trip loading is stricter than the PyYAML safe_load used to
        # discover schema files (e.g. it rejects duplicate keys). Convert that
        # into a per-file FormatError so one bad file does not abort the run.
        data = yaml_handler.load(raw_text)
    except YAMLError as exc:
        raise FormatError(f"could not parse as YAML: {exc}") from exc

    if not is_schema_document(data):
        return raw_text

    format_document(data, options)

    buffer = StringIO()
    yaml_handler.dump(data, buffer)
    text = _ensure_schema_header(buffer.getvalue())

    original = _normalize_for_guard(yaml.safe_load(raw_text), options)
    formatted = _normalize_for_guard(yaml.safe_load(text), options)
    if original != formatted:
        raise FormatError("Formatting would change the schema content; aborting to avoid data loss.")

    return text
