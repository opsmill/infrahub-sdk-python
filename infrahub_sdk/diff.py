from __future__ import annotations

from typing import (
    Any,
)

from typing_extensions import NotRequired, TypedDict


class NodeDiff(TypedDict):
    branch: str
    kind: str
    id: str
    action: str
    display_label: str
    elements: list[NodeDiffElement]


class NodeDiffElement(TypedDict):
    name: str
    element_type: str
    action: str
    summary: NodeDiffSummary
    peers: NotRequired[list[NodeDiffPeer]]


class NodeDiffSummary(TypedDict):
    added: int
    updated: int
    removed: int


class NodeDiffPeer(TypedDict):
    action: str
    summary: NodeDiffSummary


def get_diff_summary_query() -> str:
    return """
        query GetDiffTree($branch_name: String!) {
            DiffTree(branch: $branch_name) {
                nodes {
                    uuid
                    kind
                    status
                    label
                    num_added
                    num_updated
                    num_removed
                    attributes {
                        name
                        status
                        num_added
                        num_updated
                        num_removed
                    }
                    relationships {
                        name
                        status
                        cardinality
                        num_added
                        num_updated
                        num_removed
                        elements {
                            status
                            num_added
                            num_updated
                            num_removed
                        }
                    }
                }
            }
        }
    """


def diff_tree_node_to_node_diff(node_dict: dict[str, Any], branch_name: str) -> NodeDiff:
    element_diffs: list[NodeDiffElement] = []
    if "attributes" in node_dict:
        for attr_dict in node_dict["attributes"]:
            attr_diff = NodeDiffElement(
                action=str(attr_dict.get("status")),
                element_type="ATTRIBUTE",
                name=str(attr_dict.get("name")),
                summary={
                    "added": int(attr_dict.get("num_added") or 0),
                    "removed": int(attr_dict.get("num_removed") or 0),
                    "updated": int(attr_dict.get("num_updated") or 0),
                },
            )
            element_diffs.append(attr_diff)
    if "relationships" in node_dict:
        for relationship_dict in node_dict["relationships"]:
            is_cardinality_one = str(relationship_dict.get("cardinality")).upper() == "ONE"
            relationship_diff = NodeDiffElement(
                action=str(relationship_dict.get("status")),
                element_type="RELATIONSHIP_ONE" if is_cardinality_one else "RELATIONSHIP_MANY",
                name=str(relationship_dict.get("name")),
                summary={
                    "added": int(relationship_dict.get("num_added") or 0),
                    "removed": int(relationship_dict.get("num_removed") or 0),
                    "updated": int(relationship_dict.get("num_updated") or 0),
                },
            )
            if not is_cardinality_one and "elements" in relationship_dict:
                peer_diffs = []
                for element_dict in relationship_dict["elements"]:
                    peer_diffs.append(
                        NodeDiffPeer(
                            action=str(element_dict.get("status")),
                            summary={
                                "added": int(element_dict.get("num_added") or 0),
                                "removed": int(element_dict.get("num_removed") or 0),
                                "updated": int(element_dict.get("num_updated") or 0),
                            },
                        )
                    )
                relationship_diff["peers"] = peer_diffs
            element_diffs.append(relationship_diff)
    node_diff = NodeDiff(
        branch=branch_name,
        kind=str(node_dict.get("kind")),
        id=str(node_dict.get("uuid")),
        action=str(node_dict.get("action")),
        display_label=str(node_dict.get("label")),
        elements=element_diffs,
    )
    return node_diff
