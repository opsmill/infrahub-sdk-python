from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ..exceptions import (
    UninitializedError,
)
from .constants import PROPERTIES_FLAG, PROPERTIES_OBJECT
from .related_node import RelatedNode, RelatedNodeSync

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync
    from ..schema import RelationshipSchemaAPI
    from .node import InfrahubNode, InfrahubNodeSync


class RelationshipManagerBase:
    """Base class for RelationshipManager and RelationshipManagerSync"""

    def __init__(self, name: str, branch: str, schema: RelationshipSchemaAPI):
        """
        Args:
            name (str): The name of the relationship.
            branch (str): The branch where the relationship resides.
            schema (RelationshipSchema): The schema of the relationship.
        """
        self.initialized: bool = False
        self._has_update: bool = False
        self.name = name
        self.schema = schema
        self.branch = branch

        self._properties_flag = PROPERTIES_FLAG
        self._properties_object = PROPERTIES_OBJECT
        self._properties = self._properties_flag + self._properties_object

        self.peers: list[RelatedNode | RelatedNodeSync] = []

    @property
    def peer_ids(self) -> list[str]:
        return [peer.id for peer in self.peers if peer.id]

    @property
    def peer_hfids(self) -> list[list[Any]]:
        return [peer.hfid for peer in self.peers if peer.hfid]

    @property
    def peer_hfids_str(self) -> list[str]:
        return [peer.hfid_str for peer in self.peers if peer.hfid_str]

    @property
    def has_update(self) -> bool:
        return self._has_update

    def _generate_input_data(self, allocate_from_pool: bool = False) -> list[dict]:
        return [peer._generate_input_data(allocate_from_pool=allocate_from_pool) for peer in self.peers]

    def _generate_mutation_query(self) -> dict[str, Any]:
        # Does nothing for now
        return {}

    @classmethod
    def _generate_query_data(cls, peer_data: dict[str, Any] | None = None, property: bool = False) -> dict:
        """Generates the basic structure of a GraphQL query for relationships with multiple nodes.

        Args:
            peer_data (dict[str, Union[Any, Dict]], optional): Additional data to be included in the query for each node.
                This is used to add extra fields when prefetching related node data in many-to-many relationships.

        Returns:
            Dict: A dictionary representing the basic structure of a GraphQL query for multiple related nodes.
                It includes count, edges, and node information (ID, display label, and typename), along with additional properties
                and any peer_data provided.
        """
        data: dict[str, Any] = {
            "count": None,
            "edges": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
        }

        properties: dict[str, Any] = {}
        if property:
            for prop_name in PROPERTIES_FLAG:
                properties[prop_name] = None
            for prop_name in PROPERTIES_OBJECT:
                properties[prop_name] = {"id": None, "display_label": None, "__typename": None}

        if properties:
            data["edges"]["properties"] = properties
        if peer_data:
            data["edges"]["node"].update(peer_data)

        return data


class RelationshipManager(RelationshipManagerBase):
    """Manages relationships of a node in an asynchronous context."""

    def __init__(
        self,
        name: str,
        client: InfrahubClient,
        node: InfrahubNode,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
    ):
        """
        Args:
            name (str): The name of the relationship.
            client (InfrahubClient): The client used to interact with the backend.
            node (InfrahubNode): The node to which the relationship belongs.
            branch (str): The branch where the relationship resides.
            schema (RelationshipSchema): The schema of the relationship.
            data (Union[Any, dict]): Initial data for the relationships.
        """
        self.client = client
        self.node = node

        super().__init__(name=name, schema=schema, branch=branch)

        self.initialized = data is not None
        self._has_update = False

        if data is None:
            return

        if isinstance(data, list):
            for item in data:
                self.peers.append(
                    RelatedNode(name=name, client=self.client, branch=self.branch, schema=schema, data=item)
                )
        elif isinstance(data, dict) and "edges" in data:
            for item in data["edges"]:
                self.peers.append(
                    RelatedNode(name=name, client=self.client, branch=self.branch, schema=schema, data=item)
                )
        else:
            raise ValueError(f"Unexpected format for {name} found a {type(data)}, {data}")

    def __getitem__(self, item: int) -> RelatedNode:
        return self.peers[item]  # type: ignore[return-value]

    async def fetch(self) -> None:
        if not self.initialized:
            exclude = self.node._schema.relationship_names + self.node._schema.attribute_names
            exclude.remove(self.schema.name)
            node = await self.client.get(
                kind=self.node._schema.kind,
                id=self.node.id,
                branch=self.branch,
                include=[self.schema.name],
                exclude=exclude,
            )
            rm = getattr(node, self.schema.name)
            self.peers = rm.peers
            self.initialized = True

        for peer in self.peers:
            await peer.fetch()  # type: ignore[misc]

    def add(self, data: str | RelatedNode | dict) -> None:
        """Add a new peer to this relationship."""
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        new_node = RelatedNode(schema=self.schema, client=self.client, branch=self.branch, data=data)

        if (new_node.id and new_node.id not in self.peer_ids) or (
            new_node.hfid and new_node.hfid not in self.peer_hfids
        ):
            self.peers.append(new_node)
            self._has_update = True

    def extend(self, data: Iterable[str | RelatedNode | dict]) -> None:
        """Add new peers to this relationship."""
        for d in data:
            self.add(d)

    def remove(self, data: str | RelatedNode | dict) -> None:
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        node_to_remove = RelatedNode(schema=self.schema, client=self.client, branch=self.branch, data=data)

        if node_to_remove.id and node_to_remove.id in self.peer_ids:
            idx = self.peer_ids.index(node_to_remove.id)
            if self.peers[idx].id != node_to_remove.id:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.id}")

            self.peers.pop(idx)
            self._has_update = True

        elif node_to_remove.hfid and node_to_remove.hfid in self.peer_hfids:
            idx = self.peer_hfids.index(node_to_remove.hfid)
            if self.peers[idx].hfid != node_to_remove.hfid:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.hfid}")

            self.peers.pop(idx)
            self._has_update = True


class RelationshipManagerSync(RelationshipManagerBase):
    """Manages relationships of a node in a synchronous context."""

    def __init__(
        self,
        name: str,
        client: InfrahubClientSync,
        node: InfrahubNodeSync,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
    ):
        """
        Args:
            name (str): The name of the relationship.
            client (InfrahubClientSync): The client used to interact with the backend synchronously.
            node (InfrahubNodeSync): The node to which the relationship belongs.
            branch (str): The branch where the relationship resides.
            schema (RelationshipSchema): The schema of the relationship.
            data (Union[Any, dict]): Initial data for the relationships.
        """
        self.client = client
        self.node = node

        super().__init__(name=name, schema=schema, branch=branch)

        self.initialized = data is not None
        self._has_update = False

        if data is None:
            return

        if isinstance(data, list):
            for item in data:
                self.peers.append(
                    RelatedNodeSync(name=name, client=self.client, branch=self.branch, schema=schema, data=item)
                )
        elif isinstance(data, dict) and "edges" in data:
            for item in data["edges"]:
                self.peers.append(
                    RelatedNodeSync(name=name, client=self.client, branch=self.branch, schema=schema, data=item)
                )
        else:
            raise ValueError(f"Unexpected format for {name} found a {type(data)}, {data}")

    def __getitem__(self, item: int) -> RelatedNodeSync:
        return self.peers[item]  # type: ignore[return-value]

    def fetch(self) -> None:
        if not self.initialized:
            exclude = self.node._schema.relationship_names + self.node._schema.attribute_names
            exclude.remove(self.schema.name)
            node = self.client.get(
                kind=self.node._schema.kind,
                id=self.node.id,
                branch=self.branch,
                include=[self.schema.name],
                exclude=exclude,
            )
            rm = getattr(node, self.schema.name)
            self.peers = rm.peers
            self.initialized = True

        for peer in self.peers:
            peer.fetch()

    def add(self, data: str | RelatedNodeSync | dict) -> None:
        """Add a new peer to this relationship."""
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        new_node = RelatedNodeSync(schema=self.schema, client=self.client, branch=self.branch, data=data)

        if (new_node.id and new_node.id not in self.peer_ids) or (
            new_node.hfid and new_node.hfid not in self.peer_hfids
        ):
            self.peers.append(new_node)
            self._has_update = True

    def extend(self, data: Iterable[str | RelatedNodeSync | dict]) -> None:
        """Add new peers to this relationship."""
        for d in data:
            self.add(d)

    def remove(self, data: str | RelatedNodeSync | dict) -> None:
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        node_to_remove = RelatedNodeSync(schema=self.schema, client=self.client, branch=self.branch, data=data)

        if node_to_remove.id and node_to_remove.id in self.peer_ids:
            idx = self.peer_ids.index(node_to_remove.id)
            if self.peers[idx].id != node_to_remove.id:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.id}")
            self.peers.pop(idx)
            self._has_update = True

        elif node_to_remove.hfid and node_to_remove.hfid in self.peer_hfids:
            idx = self.peer_hfids.index(node_to_remove.hfid)
            if self.peers[idx].hfid != node_to_remove.hfid:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.hfid}")

            self.peers.pop(idx)
            self._has_update = True
