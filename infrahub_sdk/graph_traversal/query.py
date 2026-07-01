"""GraphQL query strings and variable builders for graph traversal (Infrahub 1.10+).

Both server queries accept a single complex input object passed as the GraphQL
variable ``$data``. The input field names are snake_case on the wire, matching
the SDK keyword arguments, so the variable dict is built directly with unset
optional fields omitted (the server applies its own defaults).
"""

from __future__ import annotations

from typing import Any

# Selection set shared by both queries.
_PATH_NODE_FIELDS = "id kind label display_label hfid"
_RELATIONSHIP_FIELDS = "from_rel from_label to_rel to_label kind"
_PATH_FIELDS = f"hops {{ node {{ {_PATH_NODE_FIELDS} }} relationship {{ {_RELATIONSHIP_FIELDS} }} }} depth"

PATH_TRAVERSAL_QUERY = f"""query InfrahubPathTraversal($data: PathTraversalInput!) {{
  InfrahubPathTraversal(data: $data) {{
    paths {{ {_PATH_FIELDS} }}
    source {{ {_PATH_NODE_FIELDS} }}
    destination {{ {_PATH_NODE_FIELDS} }}
    count
    excluded_kinds
    truncated_at_depth
  }}
}}"""

REACHABLE_NODES_QUERY = f"""query InfrahubReachableNodes($data: ReachableNodesInput!) {{
  InfrahubReachableNodes(data: $data) {{
    source {{ {_PATH_NODE_FIELDS} }}
    dependencies {{
      node {{ {_PATH_NODE_FIELDS} }}
      depth
      path {{ {_PATH_FIELDS} }}
    }}
    count
  }}
}}"""


def is_unknown_field_error(errors: list[dict[str, Any]], field_name: str) -> bool:
    """Return True if the GraphQL errors indicate ``field_name`` is an unknown query field.

    Used to detect a pre-1.10 server that lacks the traversal queries, so the SDK can
    raise a clear version error instead of surfacing an opaque validation failure. The
    server's own runtime errors (such as "Source node not found") do not match.
    """
    markers = ("cannot query field", "unknown field", "doesn't exist", "does not exist")
    for error in errors:
        message = str(error.get("message") or "").lower()
        if field_name.lower() in message and any(marker in message for marker in markers):
            return True
    return False


def build_path_traversal_input(
    source_id: str,
    destination_id: str,
    *,
    max_depth: int | None = None,
    max_paths: int | None = None,
    kind_filter: list[str] | None = None,
    relationship_filter: list[str] | None = None,
    excluded_namespaces: list[str] | None = None,
    excluded_kinds: list[str] | None = None,
    included_kinds: list[str] | None = None,
    shortest_paths_only: bool | None = None,
) -> dict[str, Any]:
    """Build the ``PathTraversalInput`` variable, omitting unset optional fields."""
    data: dict[str, Any] = {"source_id": source_id, "destination_id": destination_id}
    optional = {
        "max_depth": max_depth,
        "max_paths": max_paths,
        "kind_filter": kind_filter,
        "relationship_filter": relationship_filter,
        "excluded_namespaces": excluded_namespaces,
        "excluded_kinds": excluded_kinds,
        "included_kinds": included_kinds,
        "shortest_paths_only": shortest_paths_only,
    }
    data.update({key: value for key, value in optional.items() if value is not None})
    return data


def build_reachable_nodes_input(
    source_id: str,
    target_kinds: list[str],
    *,
    max_depth: int | None = None,
    max_results: int | None = None,
    max_paths: int | None = None,
    shortest_paths_only: bool | None = None,
) -> dict[str, Any]:
    """Build the ``ReachableNodesInput`` variable, omitting unset optional fields."""
    data: dict[str, Any] = {"source_id": source_id, "target_kinds": target_kinds}
    optional = {
        "max_depth": max_depth,
        "max_results": max_results,
        "max_paths": max_paths,
        "shortest_paths_only": shortest_paths_only,
    }
    data.update({key: value for key, value in optional.items() if value is not None})
    return data
