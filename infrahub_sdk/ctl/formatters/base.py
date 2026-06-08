"""Base formatter protocol and shared helper functions for node data extraction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ...node import InfrahubNode
    from ...schema import MainSchemaTypesAPI


class BaseFormatter(Protocol):
    """Protocol defining the interface all formatters must implement.

    Formatters convert InfrahubNode objects into string representations
    for display in various output formats (table, JSON, CSV, YAML).
    """

    def format_list(
        self,
        nodes: list[InfrahubNode],
        schema: MainSchemaTypesAPI,
        show_all_columns: bool = False,
    ) -> str:
        """Format a list of nodes for display.

        Args:
            nodes: List of InfrahubNode objects to format.
            schema: Schema definition for the node kind.
            show_all_columns: When True, include columns where every value is empty.

        Returns:
            Formatted string representation of all nodes.

        """
        ...

    def format_detail(self, node: InfrahubNode, schema: MainSchemaTypesAPI) -> str:
        """Format a single node's detail view.

        Args:
            node: The InfrahubNode to format.
            schema: Schema definition for the node kind.

        Returns:
            Formatted string with full node details.

        """
        ...


def _extract_relationship_value(
    node: InfrahubNode,
    rel_name: str,
    cardinality: str,
) -> str:
    """Extract a display value from a relationship on a node.

    Args:
        node: The node containing the relationship.
        rel_name: Name of the relationship attribute.
        cardinality: Either "one" or "many".

    Returns:
        Display string for the relationship value.

    """
    rel = getattr(node, rel_name, None)
    if rel is None:
        return ""

    if cardinality == "one":
        return rel.display_label or rel.id or ""

    # cardinality == "many": RelationshipManager with .peers
    peers = getattr(rel, "peers", [])
    labels = [p.display_label or p.id or "" for p in peers]
    return ", ".join(labels)


def extract_node_data(
    node: InfrahubNode,
    schema: MainSchemaTypesAPI,
) -> dict[str, Any]:
    """Extract a flat dict of field names to display values from a node.

    Handles both attributes and relationships. Attribute values of None
    are converted to empty strings. Relationship values are rendered as
    display labels.

    Args:
        node: The InfrahubNode to extract data from.
        schema: Schema definition describing attributes and relationships.

    Returns:
        Dict mapping field names to their string display values.

    """
    data: dict[str, Any] = {}

    for attr_name in schema.attribute_names:
        attr = getattr(node, attr_name, None)
        value = attr.value if attr is not None else None
        data[attr_name] = value if value is not None else ""

    for rel_name in schema.relationship_names:
        rel_schema = schema.get_relationship(rel_name)
        data[rel_name] = _extract_relationship_value(node, rel_name, rel_schema.cardinality)

    return data


def non_empty_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    """Return only columns that have at least one non-empty value across all rows.

    Args:
        rows: List of row dicts (from extract_node_data).
        columns: All candidate column names.

    Returns:
        Filtered list of column names with data.

    """
    return [col for col in columns if any(str(row.get(col, "")).strip() for row in rows)]


def extract_node_detail(
    node: InfrahubNode,
    schema: MainSchemaTypesAPI,
) -> dict[str, Any]:
    """Extract a rich detail dict from a node including metadata.

    Similar to extract_node_data but includes the node ID, display label,
    and schema kind as additional metadata fields.

    Args:
        node: The InfrahubNode to extract data from.
        schema: Schema definition describing attributes and relationships.

    Returns:
        Dict with metadata fields (id, display_label, kind) followed
        by attribute and relationship values.

    """
    detail: dict[str, Any] = {
        "id": node.id or "",
        "display_label": node.display_label or "",
        "kind": schema.kind,
    }

    for attr_name in schema.attribute_names:
        attr = getattr(node, attr_name, None)
        if attr is not None:
            detail[attr_name] = {
                "value": attr.value if attr.value is not None else "",
            }
        else:
            detail[attr_name] = {"value": ""}

    for rel_name in schema.relationship_names:
        rel_schema = schema.get_relationship(rel_name)
        rel = getattr(node, rel_name, None)

        if rel_schema.cardinality == "one":
            if rel is not None:
                detail[rel_name] = {
                    "display_label": rel.display_label or "",
                    "id": rel.id or "",
                    "cardinality": "one",
                }
            else:
                detail[rel_name] = {
                    "display_label": "",
                    "id": "",
                    "cardinality": "one",
                }
        else:
            peers = getattr(rel, "peers", []) if rel is not None else []
            detail[rel_name] = {
                "peers": [
                    {
                        "display_label": p.display_label or "",
                        "id": p.id or "",
                    }
                    for p in peers
                ],
                "cardinality": "many",
            }

    return detail
