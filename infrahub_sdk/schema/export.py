from __future__ import annotations

from typing import Any

from .main import GenericSchemaAPI, NodeSchemaAPI

# Namespaces reserved by the Infrahub server — mirrored from
# backend/infrahub/core/constants/__init__.py in the opsmill/infrahub repo.
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

_SCHEMA_EXPORT_EXCLUDE: set[str] = {"hash", "hierarchy", "used_by", "id", "state"}
# branch is inherited from the node and need not be repeated on each field
_FIELD_EXPORT_EXCLUDE: set[str] = {"inherited", "allow_override", "hierarchical", "id", "state", "branch"}

# Attribute field values that match schema loading defaults — omitted for cleaner output
_ATTR_EXPORT_DEFAULTS: dict[str, Any] = {
    "read_only": False,
    "optional": False,
}

# Relationship field values that match schema loading defaults — omitted for cleaner output
_REL_EXPORT_DEFAULTS: dict[str, Any] = {
    "direction": "bidirectional",
    "on_delete": "no-action",
    "cardinality": "many",
    "optional": True,
    "min_count": 0,
    "max_count": 0,
    "read_only": False,
}

# Relationship kinds that Infrahub generates automatically — never user-defined
_AUTO_GENERATED_REL_KINDS: frozenset[str] = frozenset({"Group", "Profile", "Hierarchy"})


def schema_to_export_dict(schema: NodeSchemaAPI | GenericSchemaAPI) -> dict[str, Any]:
    """Convert an API schema object to an export-ready dict (omits API-internal fields)."""
    data = schema.model_dump(exclude=_SCHEMA_EXPORT_EXCLUDE, exclude_none=True)

    # Pop attrs/rels so they can be re-inserted last for better readability
    data.pop("attributes", None)
    data.pop("relationships", None)

    # Generics with Hierarchy relationships were defined with `hierarchical: true`.
    # Restore that flag and drop the auto-generated rels so the schema round-trips cleanly.
    if isinstance(schema, GenericSchemaAPI) and any(
        rel.kind == "Hierarchy" for rel in schema.relationships if not rel.inherited
    ):
        data["hierarchical"] = True

    # Strip uniqueness_constraints that are auto-generated from `unique: true` attributes
    # (single-field entries of the form ["<attr>__value"]). User-defined multi-field
    # constraints are preserved.
    unique_attr_suffixes = {f"{attr.name}__value" for attr in schema.attributes if attr.unique}
    user_constraints = [
        c
        for c in (data.pop("uniqueness_constraints", None) or [])
        if not (len(c) == 1 and c[0] in unique_attr_suffixes)
    ]
    if user_constraints:
        data["uniqueness_constraints"] = user_constraints

    attributes = [
        {
            k: v
            for k, v in attr.model_dump(exclude=_FIELD_EXPORT_EXCLUDE, exclude_none=True).items()
            if k not in _ATTR_EXPORT_DEFAULTS or v != _ATTR_EXPORT_DEFAULTS[k]
        }
        for attr in schema.attributes
        if not attr.inherited
    ]
    if attributes:
        data["attributes"] = attributes

    relationships = [
        {
            k: v
            for k, v in rel.model_dump(exclude=_FIELD_EXPORT_EXCLUDE, exclude_none=True).items()
            if k not in _REL_EXPORT_DEFAULTS or v != _REL_EXPORT_DEFAULTS[k]
        }
        for rel in schema.relationships
        if not rel.inherited and rel.kind not in _AUTO_GENERATED_REL_KINDS
    ]
    if relationships:
        data["relationships"] = relationships

    return data
