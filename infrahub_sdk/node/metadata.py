from __future__ import annotations

from .property import NodeProperty


class NodeMetadata:
    """Represents metadata about a node (created_at, created_by, updated_at, updated_by)."""

    def __init__(self, data: dict | None = None) -> None:
        """
        Args:
            data: Data containing the metadata fields from the GraphQL response.
        """
        self.created_at: str | None = None
        self.created_by: NodeProperty | None = None
        self.updated_at: str | None = None
        self.updated_by: NodeProperty | None = None

        if data:
            self.created_at = data.get("created_at")
            self.updated_at = data.get("updated_at")
            if data.get("created_by"):
                self.created_by = NodeProperty(data["created_by"])
            if data.get("updated_by"):
                self.updated_by = NodeProperty(data["updated_by"])

    def __repr__(self) -> str:
        return (
            f"NodeMetadata(created_at={self.created_at!r}, created_by={self.created_by!r}, "
            f"updated_at={self.updated_at!r}, updated_by={self.updated_by!r})"
        )

    @classmethod
    def _generate_query_data(cls) -> dict:
        """Generate the query structure for node_metadata fields."""
        return {
            "created_at": None,
            "created_by": {"id": None, "__typename": None, "display_label": None},
            "updated_at": None,
            "updated_by": {"id": None, "__typename": None, "display_label": None},
        }


class RelationshipMetadata:
    """Represents metadata about a relationship edge (updated_at, updated_by)."""

    def __init__(self, data: dict | None = None) -> None:
        """
        Args:
            data: Data containing the metadata fields from the GraphQL response.
        """
        self.updated_at: str | None = None
        self.updated_by: NodeProperty | None = None

        if data:
            self.updated_at = data.get("updated_at")
            if data.get("updated_by"):
                self.updated_by = NodeProperty(data["updated_by"])

    def __repr__(self) -> str:
        return f"RelationshipMetadata(updated_at={self.updated_at!r}, updated_by={self.updated_by!r})"

    @classmethod
    def _generate_query_data(cls) -> dict:
        """Generate the query structure for relationship_metadata fields."""
        return {
            "updated_at": None,
            "updated_by": {"id": None, "__typename": None, "display_label": None},
        }
