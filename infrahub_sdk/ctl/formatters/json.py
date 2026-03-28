"""JSON formatter for InfrahubNode query results."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .base import extract_node_data, extract_node_detail

if TYPE_CHECKING:
    from ...node import InfrahubNode
    from ...schema import MainSchemaTypesAPI


class JsonFormatter:
    """Formats InfrahubNode data as JSON strings.

    Uses stdlib json module with indentation for readable output.
    """

    def format_list(self, nodes: list[InfrahubNode], schema: MainSchemaTypesAPI) -> str:
        """Format a list of nodes as a JSON array.

        Each node is represented as a dict with attribute and
        relationship field names as keys.

        Args:
            nodes: List of InfrahubNode objects to format.
            schema: Schema definition for the node kind.

        Returns:
            JSON array string.
        """
        items = [extract_node_data(node, schema) for node in nodes]
        return json.dumps(items, indent=2, default=str)

    def format_detail(self, node: InfrahubNode, schema: MainSchemaTypesAPI) -> str:
        """Format a single node as a JSON object.

        Includes metadata (id, display_label, kind) along with
        all attributes and relationships.

        Args:
            node: The InfrahubNode to format.
            schema: Schema definition for the node kind.

        Returns:
            JSON object string.
        """
        detail = extract_node_detail(node, schema)
        return json.dumps(detail, indent=2, default=str)
