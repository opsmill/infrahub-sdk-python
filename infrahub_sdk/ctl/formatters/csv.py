"""CSV formatter for InfrahubNode query results."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from .base import extract_node_data, extract_node_detail

if TYPE_CHECKING:
    from ...node import InfrahubNode
    from ...schema import MainSchemaTypesAPI


class CsvFormatter:
    """Formats InfrahubNode data as CSV strings.

    Uses stdlib csv module for proper escaping and quoting of values.
    """

    def format_list(self, nodes: list[InfrahubNode], schema: MainSchemaTypesAPI) -> str:
        """Format a list of nodes as CSV with a header row.

        Columns correspond to schema attribute and relationship names.
        Each node produces one data row.

        Args:
            nodes: List of InfrahubNode objects to format.
            schema: Schema definition for the node kind.

        Returns:
            CSV string with header and data rows.
        """
        columns = schema.attribute_names + schema.relationship_names
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(columns)

        for node in nodes:
            row_data = extract_node_data(node, schema)
            writer.writerow([str(row_data.get(col, "")) for col in columns])

        return output.getvalue()

    def format_detail(self, node: InfrahubNode, schema: MainSchemaTypesAPI) -> str:
        """Format a single node as a two-column CSV (field, value).

        Includes metadata fields (id, display_label, kind) followed
        by all attributes and relationships.

        Args:
            node: The InfrahubNode to format.
            schema: Schema definition for the node kind.

        Returns:
            CSV string with field/value columns.
        """
        detail = extract_node_detail(node, schema)
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["field", "value"])

        # Metadata rows
        writer.writerow(["id", str(detail.get("id", ""))])
        writer.writerow(["display_label", str(detail.get("display_label", ""))])
        writer.writerow(["kind", str(detail.get("kind", ""))])

        # Attribute rows
        for attr_name in schema.attribute_names:
            attr_detail = detail.get(attr_name, {})
            value = attr_detail.get("value", "") if isinstance(attr_detail, dict) else attr_detail
            writer.writerow([attr_name, str(value)])

        # Relationship rows
        for rel_name in schema.relationship_names:
            rel_detail = detail.get(rel_name, {})
            if not isinstance(rel_detail, dict):
                writer.writerow([rel_name, str(rel_detail)])
                continue

            if rel_detail.get("cardinality") == "one":
                writer.writerow([rel_name, str(rel_detail.get("display_label", ""))])
            else:
                peers = rel_detail.get("peers", [])
                labels = [p.get("display_label", "") for p in peers]
                writer.writerow([rel_name, ", ".join(labels)])

        return output.getvalue()
