"""Pydantic models for the Infrahub graph-traversal queries (Infrahub 1.10+).

These mirror the server GraphQL types for ``InfrahubPathTraversal`` and
``InfrahubReachableNodes``. The server returns snake_case field names, so the
Python attributes map directly without aliasing. Models ignore unknown fields
so additive server changes do not break parsing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from ..exceptions import Error

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync


class GraphTraversalModel(BaseModel):
    """Base for all traversal models: tolerate unknown/extra server fields."""

    model_config = ConfigDict(extra="ignore")


# --- Shared building blocks -------------------------------------------------


class PathNode(GraphTraversalModel):
    """Identity of a node encountered during a traversal.

    This is a lightweight identity (no attributes or relationships). Use
    :meth:`fetch` to resolve it into the full SDK node when needed.
    """

    id: str
    kind: str
    label: str
    display_label: str
    hfid: list[str] = Field(default_factory=list)

    # Bound by the client after parsing so ``fetch()`` can resolve the full node.
    _client: InfrahubClient | InfrahubClientSync | None = PrivateAttr(default=None)
    _branch: str | None = PrivateAttr(default=None)

    def _bind(self, client: InfrahubClient | InfrahubClientSync, branch: str | None) -> None:
        self._client = client
        self._branch = branch

    def fetch(self, timeout: int | None = None) -> Any:
        """Resolve this node into the full SDK node.

        On an async client you await the return value (``await node.fetch()``); on a
        sync client it returns the node directly. The result is added to the client store,
        so fetching the same id again is served from the store.

        Raises:
            Error: If this node is not bound to a client (for example, constructed manually).

        """
        if self._client is None:
            raise Error("This PathNode is not bound to a client and cannot be fetched.")
        return self._client.get(kind=self.kind, id=self.id, populate_store=True, branch=self._branch, timeout=timeout)


class PathRelationship(GraphTraversalModel):
    """A relationship (edge) traversed between two nodes."""

    from_rel: str
    from_label: str
    to_rel: str
    to_label: str
    kind: str


class PathHop(GraphTraversalModel):
    """A single step in a path: the node visited and the relationship used to reach it.

    ``relationship`` is ``None`` for the source-anchored first hop.
    """

    node: PathNode
    relationship: PathRelationship | None = None


class Path(GraphTraversalModel):
    """One route between two nodes, as an ordered list of hops."""

    hops: list[PathHop] = Field(default_factory=list)
    depth: int

    def _bind(self, client: InfrahubClient | InfrahubClientSync, branch: str | None) -> None:
        for hop in self.hops:
            hop.node._bind(client, branch)


# --- InfrahubPathTraversal result -------------------------------------------


class PathTraversalResult(GraphTraversalModel):
    """Result of :meth:`InfrahubClient.traverse_paths`."""

    paths: list[Path] = Field(default_factory=list)
    source: PathNode
    destination: PathNode
    count: int
    excluded_kinds: list[str] = Field(default_factory=list)

    def _bind(self, client: InfrahubClient | InfrahubClientSync, branch: str | None) -> PathTraversalResult:
        self.source._bind(client, branch)
        self.destination._bind(client, branch)
        for path in self.paths:
            path._bind(client, branch)
        return self


# --- InfrahubReachableNodes result ------------------------------------------


class ReachableNode(GraphTraversalModel):
    """A node reachable from the source, with the path used to reach it."""

    node: PathNode
    depth: int
    path: Path


class ReachableNodesResult(GraphTraversalModel):
    """Result of :meth:`InfrahubClient.reachable_nodes`."""

    source: PathNode
    dependencies: list[ReachableNode] = Field(default_factory=list)
    count: int

    def _bind(self, client: InfrahubClient | InfrahubClientSync, branch: str | None) -> ReachableNodesResult:
        self.source._bind(client, branch)
        for dependency in self.dependencies:
            dependency.node._bind(client, branch)
            dependency.path._bind(client, branch)
        return self
