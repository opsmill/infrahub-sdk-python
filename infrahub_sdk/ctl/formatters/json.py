"""JSON formatter for InfrahubNode query results."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson

from .base import extract_node_data, extract_node_detail

if TYPE_CHECKING:
    from ...node import InfrahubNode
    from ...schema import MainSchemaTypesAPI


class JsonFormatter:
    """Formats InfrahubNode data as JSON strings.

    Uses orjson with indentation for readable output.
    """

    def format_list(
        self,
        nodes: list[InfrahubNode],
        schema: MainSchemaTypesAPI,
        show_all_columns: bool = False,  # noqa: ARG002
    ) -> str:
        """Format a list of nodes as a JSON array.

        Each node is represented as a dict with attribute and
        relationship field names as keys.

        Args:
            nodes: List of InfrahubNode objects to format.
            schema: Schema definition for the node kind.
            show_all_columns: Accepted for interface compatibility; not used for JSON.

        Returns:
            JSON array string.

        """
        items = [extract_node_data(node, schema) for node in nodes]
        return orjson.dumps(
            items, option=orjson.OPT_INDENT_2 | orjson.OPT_PASSTHROUGH_DATETIME | orjson.OPT_NON_STR_KEYS, default=str
        ).decode()

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
        return orjson.dumps(
            detail, option=orjson.OPT_INDENT_2 | orjson.OPT_PASSTHROUGH_DATETIME | orjson.OPT_NON_STR_KEYS, default=str
        ).decode()
