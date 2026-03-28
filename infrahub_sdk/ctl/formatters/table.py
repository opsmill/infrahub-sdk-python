"""Rich table formatter for InfrahubNode query results."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from .base import extract_node_data, extract_node_detail

if TYPE_CHECKING:
    from ...node import InfrahubNode
    from ...schema import MainSchemaTypesAPI


class TableFormatter:
    """Formats InfrahubNode data as Rich tables.

    Uses Rich library to render attractive, aligned tables with
    column headers derived from the schema field names.
    """

    def format_list(self, nodes: list[InfrahubNode], schema: MainSchemaTypesAPI) -> str:
        """Format a list of nodes as a Rich table.

        Creates a table with one column per attribute and relationship,
        and one row per node.

        Args:
            nodes: List of InfrahubNode objects to format.
            schema: Schema definition for the node kind.

        Returns:
            Rendered table string.
        """
        columns = schema.attribute_names + schema.relationship_names
        table = Table(title=schema.kind, show_lines=False)

        for col in columns:
            table.add_column(col, overflow="fold")

        for node in nodes:
            row_data = extract_node_data(node, schema)
            table.add_row(*(str(row_data.get(col, "")) for col in columns))

        return self._render(table)

    def format_detail(self, node: InfrahubNode, schema: MainSchemaTypesAPI) -> str:
        """Format a single node as a key-value detail view.

        Renders a two-column table (Field / Value) with metadata,
        attributes, and relationships sections.

        Args:
            node: The InfrahubNode to format.
            schema: Schema definition for the node kind.

        Returns:
            Rendered detail string.
        """
        detail = extract_node_detail(node, schema)

        table = Table(
            title=f"{schema.kind} Detail",
            show_lines=True,
        )
        table.add_column("Field", style="bold")
        table.add_column("Value")

        # Metadata section
        table.add_row("id", str(detail.get("id", "")))
        table.add_row("display_label", str(detail.get("display_label", "")))
        table.add_row("kind", str(detail.get("kind", "")))

        # Attributes section
        for attr_name in schema.attribute_names:
            attr_detail = detail.get(attr_name, {})
            value = attr_detail.get("value", "") if isinstance(attr_detail, dict) else attr_detail
            table.add_row(attr_name, str(value))

        # Relationships section
        for rel_name in schema.relationship_names:
            rel_detail = detail.get(rel_name, {})
            if not isinstance(rel_detail, dict):
                table.add_row(rel_name, str(rel_detail))
                continue

            if rel_detail.get("cardinality") == "one":
                label = rel_detail.get("display_label", "")
                table.add_row(rel_name, str(label))
            else:
                peers = rel_detail.get("peers", [])
                labels = [p.get("display_label", "") for p in peers]
                table.add_row(rel_name, ", ".join(labels))

        return self._render(table)

    @staticmethod
    def _render(renderable: Table) -> str:
        """Capture Rich renderable output to a string.

        Args:
            renderable: A Rich Table or other renderable object.

        Returns:
            The rendered string output.
        """
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=False, width=120)
        console.print(renderable)
        return buffer.getvalue()
