"""CSV formatter for InfrahubNode query results."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from .base import extract_node_data, extract_node_detail, non_empty_columns

if TYPE_CHECKING:
    from ...node import InfrahubNode
    from ...schema import MainSchemaTypesAPI


class CsvFormatter:
    """Formats InfrahubNode data as CSV strings.

    Uses stdlib csv module for proper escaping and quoting of values.
    """

    @staticmethod
    def _safe_cell(value: str) -> str:
        """Prefix cell values that start with formula-triggering characters.

        Prevents CSV formula injection by prepending a single quote to
        values starting with ``=``, ``+``, ``-``, or ``@``.
        """
        if value and value[0] in {"=", "+", "-", "@"}:
            return f"'{value}"
        return value

    def format_list(
        self,
        nodes: list[InfrahubNode],
        schema: MainSchemaTypesAPI,
        show_all_columns: bool = False,
    ) -> str:
        """Format a list of nodes as CSV with a header row.

        Columns correspond to schema attribute and relationship names.
        Each node produces one data row.

        Args:
            nodes: List of InfrahubNode objects to format.
            schema: Schema definition for the node kind.
            show_all_columns: When True, include columns where every value is empty.

        Returns:
            CSV string with header and data rows.

        """
        all_columns = schema.attribute_names + schema.relationship_names
        rows = [extract_node_data(node, schema) for node in nodes]
        columns = all_columns if not rows or show_all_columns else non_empty_columns(rows, all_columns)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)

        for row_data in rows:
            writer.writerow([self._safe_cell(str(row_data.get(col, ""))) for col in columns])

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
        writer.writerow(["id", self._safe_cell(str(detail.get("id", "")))])
        writer.writerow(["display_label", self._safe_cell(str(detail.get("display_label", "")))])
        writer.writerow(["kind", self._safe_cell(str(detail.get("kind", "")))])

        # Attribute rows
        for attr_name in schema.attribute_names:
            attr_detail = detail.get(attr_name, {})
            value = attr_detail.get("value", "") if isinstance(attr_detail, dict) else attr_detail
            writer.writerow([attr_name, self._safe_cell(str(value))])

        # Relationship rows
        for rel_name in schema.relationship_names:
            rel_detail = detail.get(rel_name, {})
            if not isinstance(rel_detail, dict):
                writer.writerow([rel_name, self._safe_cell(str(rel_detail))])
                continue

            if rel_detail.get("cardinality") == "one":
                writer.writerow([rel_name, self._safe_cell(str(rel_detail.get("display_label", "")))])
            else:
                peers = rel_detail.get("peers", [])
                labels = [p.get("display_label", "") for p in peers]
                writer.writerow([rel_name, self._safe_cell(", ".join(labels))])

        return output.getvalue()
