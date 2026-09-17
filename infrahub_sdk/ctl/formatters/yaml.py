"""YAML formatter for InfrahubNode query results in Infrahub object format.

Produces YAML that is round-trippable with ``infrahubctl object load``.
Empty/null attribute values and unset relationships are omitted so the
output can be loaded back without validation errors.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Any

import yaml

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
        """Format a list of nodes as an Infrahub YAML object document."""
        data_items = [self._node_to_data_entry(node, schema) for node in nodes]
        return self._build_document(schema.kind, data_items)

    def format_detail(self, node: InfrahubNode, schema: MainSchemaTypesAPI) -> str:
        """Format a single node as an Infrahub YAML object document."""
        data_entry = self._node_to_data_entry(node, schema)
        return self._build_document(schema.kind, [data_entry])

    def _node_to_data_entry(
        self,
        node: InfrahubNode,
        schema: MainSchemaTypesAPI,
    ) -> dict[str, Any]:
        """Convert a node into a dict compatible with ObjectFile spec format.

        Omits empty/null attribute values and unset relationships so the
        output can be loaded back via ``infrahubctl object load`` without
        validation errors.
        """
        entry: dict[str, Any] = {}

        # Attributes: only include non-empty values
        for attr_name in schema.attribute_names:
            attr = getattr(node, attr_name, None)
            if attr is None:
                continue
            value = attr.value
            if not value and value != 0 and value is not False:
                continue
            if isinstance(
                value,
                (
                    ipaddress.IPv4Interface,
                    ipaddress.IPv6Interface,
                    ipaddress.IPv4Network,
                    ipaddress.IPv6Network,
                    ipaddress.IPv4Address,
                    ipaddress.IPv6Address,
                ),
            ):
                value = str(value)
            entry[attr_name] = value

        # Relationships: skip unset, use HFID when available
        for rel_name in schema.relationship_names:
            rel_schema = schema.get_relationship(rel_name)
            rel = getattr(node, rel_name, None)
            if rel is None:
                continue

            if rel_schema.cardinality == "one":
                ref = _related_node_ref(rel)
                if ref is not None:
                    entry[rel_name] = ref
            else:
                peers = getattr(rel, "peers", None) or []
                refs = [r for p in peers if (r := _related_node_ref(p)) is not None]
                if refs:
                    entry[rel_name] = refs

        return entry

    @staticmethod
    def _build_document(kind: str, data: list[dict[str, Any]]) -> str:
        """Build the full Infrahub YAML document structure."""
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


def _related_node_ref(rel: Any) -> str | list[str] | None:
    """Build a reference value for a related node suitable for ObjectFile.

    Uses the HFID if available. For single-component HFIDs, returns a
    plain string. For multi-component HFIDs, returns a list. Falls back
    to display_label.

    Args:
        rel: A RelatedNode object.

    Returns:
        A string, list of strings, or None if the relationship is unset.

    """
    hfid = getattr(rel, "hfid", None)
    if hfid:
        return hfid[0] if len(hfid) == 1 else list(hfid)
    label = getattr(rel, "display_label", None)
    return label or None
