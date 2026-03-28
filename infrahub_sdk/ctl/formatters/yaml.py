"""YAML formatter for InfrahubNode query results in Infrahub object format."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

from .base import extract_node_detail

if TYPE_CHECKING:
    from ...node import InfrahubNode
    from ...schema import MainSchemaTypesAPI

_INFRAHUB_API_VERSION = "infrahub.app/v1"
_INFRAHUB_KIND = "Object"


class YamlFormatter:
    """Formats InfrahubNode data as YAML in the Infrahub object spec format.

    Output follows the standard Infrahub file structure::

        ---
        apiVersion: infrahub.app/v1
        kind: Object
        spec:
          kind: <schema kind>
          data:
            - field1: value1
              field2: value2
    """

    def format_list(
        self,
        nodes: list[InfrahubNode],
        schema: MainSchemaTypesAPI,
        show_all_columns: bool = False,  # noqa: ARG002
    ) -> str:
        """Format a list of nodes as an Infrahub YAML object document.

        Each node becomes an entry in the spec.data array with its
        attribute and relationship values.

        Args:
            nodes: List of InfrahubNode objects to format.
            schema: Schema definition for the node kind.
            show_all_columns: Accepted for interface compatibility; not used for YAML.

        Returns:
            YAML string in Infrahub object format.
        """
        data_items = [self._node_to_data_entry(node, schema) for node in nodes]
        return self._build_document(schema.kind, data_items)

    def format_detail(self, node: InfrahubNode, schema: MainSchemaTypesAPI) -> str:
        """Format a single node as an Infrahub YAML object document.

        The spec.data array contains a single entry for the node.

        Args:
            node: The InfrahubNode to format.
            schema: Schema definition for the node kind.

        Returns:
            YAML string in Infrahub object format.
        """
        data_entry = self._node_to_data_entry(node, schema)
        return self._build_document(schema.kind, [data_entry])

    def _node_to_data_entry(
        self,
        node: InfrahubNode,
        schema: MainSchemaTypesAPI,
    ) -> dict[str, Any]:
        """Convert a single node into a data entry dict for YAML output.

        Args:
            node: The InfrahubNode to convert.
            schema: Schema definition for the node kind.

        Returns:
            Dict suitable for inclusion in the spec.data array.
        """
        detail = extract_node_detail(node, schema)
        entry: dict[str, Any] = {}

        # Attributes: extract plain values
        for attr_name in schema.attribute_names:
            attr_detail = detail.get(attr_name, {})
            if isinstance(attr_detail, dict):
                entry[attr_name] = attr_detail.get("value", "")
            else:
                entry[attr_name] = attr_detail

        # Relationships: format depends on cardinality
        for rel_name in schema.relationship_names:
            rel_detail = detail.get(rel_name, {})
            if not isinstance(rel_detail, dict):
                entry[rel_name] = rel_detail
                continue

            if rel_detail.get("cardinality") == "one":
                entry[rel_name] = rel_detail.get("display_label", "")
            else:
                peers = rel_detail.get("peers", [])
                if peers:
                    entry[rel_name] = {"data": [p.get("display_label", "") for p in peers]}
                else:
                    entry[rel_name] = {"data": []}

        return entry

    @staticmethod
    def _build_document(kind: str, data: list[dict[str, Any]]) -> str:
        """Build the full Infrahub YAML document structure.

        Args:
            kind: The schema kind string (e.g. "InfraDevice").
            data: List of data entry dicts for the spec.data array.

        Returns:
            Complete YAML document string with leading '---' separator.
        """
        document = {
            "apiVersion": _INFRAHUB_API_VERSION,
            "kind": _INFRAHUB_KIND,
            "spec": {
                "kind": kind,
                "data": data,
            },
        }
        return "---\n" + yaml.dump(
            document,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
