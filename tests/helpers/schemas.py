from __future__ import annotations

from typing import Any

from infrahub_sdk.schema import NodeSchemaAPI


def node_schema(
    name: str, relationships: list[dict[str, Any]] | None = None, inherit_from: list[str] | None = None
) -> dict[str, Any]:
    """A node schema in the Repro namespace, as the schema API returns it."""
    return {
        "name": name,
        "namespace": "Repro",
        "inherit_from": inherit_from or [],
        "attributes": [{"name": "name", "kind": "Text"}],
        "relationships": relationships or [],
    }


def mandatory(name: str, peer: str, cardinality: str = "one") -> dict[str, Any]:
    """A mandatory relationship to `peer`."""
    return {"name": name, "peer": peer, "optional": False, "cardinality": cardinality}


def node_schemas(*nodes: dict[str, Any]) -> dict[str, NodeSchemaAPI]:
    """The given node schemas, by kind."""
    schemas = [NodeSchemaAPI(**node) for node in nodes]
    return {schema.kind: schema for schema in schemas}
