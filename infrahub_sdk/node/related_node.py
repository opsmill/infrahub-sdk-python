from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..exceptions import (
    Error,
)
from ..protocols_base import CoreNodeBase
from .constants import PROPERTIES_FLAG, PROPERTIES_OBJECT

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync
    from ..schema import RelationshipSchemaAPI
    from .node import InfrahubNode, InfrahubNodeSync


class RelatedNodeBase:
    """Base class for representing a related node in a relationship."""

    def __init__(self, branch: str, schema: RelationshipSchemaAPI, data: Any | dict, name: str | None = None):
        """
        Args:
            branch (str): The branch where the related node resides.
            schema (RelationshipSchema): The schema of the relationship.
            data (Union[Any, dict]): Data representing the related node.
            name (Optional[str]): The name of the related node.
        """
        self.schema = schema
        self.name = name

        self._branch = branch

        self._properties_flag = PROPERTIES_FLAG
        self._properties_object = PROPERTIES_OBJECT
        self._properties = self._properties_flag + self._properties_object

        self._peer = None
        self._id: str | None = None
        self._hfid: list[str] | None = None
        self._display_label: str | None = None
        self._typename: str | None = None

        if isinstance(data, (CoreNodeBase)):
            self._peer = data
            for prop in self._properties:
                setattr(self, prop, None)

        elif isinstance(data, list):
            data = {"hfid": data}
        elif not isinstance(data, dict):
            data = {"id": data}

        if isinstance(data, dict):
            # To support both with and without pagination, we split data into node_data and properties_data
            # We should probably clean that once we'll remove the code without pagination.
            node_data = data.get("node", data)
            properties_data = data.get("properties", data)

            if node_data:
                self._id = node_data.get("id", None)
                self._hfid = node_data.get("hfid", None)
                self._kind = node_data.get("kind", None)
                self._display_label = node_data.get("display_label", None)
                self._typename = node_data.get("__typename", None)

            self.updated_at: str | None = data.get("updated_at", data.get("_relation__updated_at", None))

            # FIXME, we won't need that once we are only supporting paginated results
            if self._typename and self._typename.startswith("Related"):
                self._typename = self._typename[7:]

            for prop in self._properties:
                prop_data = properties_data.get(prop, properties_data.get(f"_relation__{prop}", None))
                if prop_data and isinstance(prop_data, dict) and "id" in prop_data:
                    setattr(self, prop, prop_data["id"])
                elif prop_data and isinstance(prop_data, (str, bool)):
                    setattr(self, prop, prop_data)
                else:
                    setattr(self, prop, None)

    @property
    def id(self) -> str | None:
        if self._peer:
            return self._peer.id
        return self._id

    @property
    def hfid(self) -> list[Any] | None:
        if self._peer:
            return self._peer.hfid
        return self._hfid

    @property
    def hfid_str(self) -> str | None:
        if self._peer and self.hfid:
            return self._peer.get_human_friendly_id_as_string(include_kind=True)
        return None

    @property
    def is_resource_pool(self) -> bool:
        if self._peer:
            return self._peer.is_resource_pool()
        return False

    @property
    def initialized(self) -> bool:
        return bool(self.id) or bool(self.hfid)

    @property
    def display_label(self) -> str | None:
        if self._peer:
            return self._peer.display_label
        return self._display_label

    @property
    def typename(self) -> str | None:
        if self._peer:
            return self._peer.typename
        return self._typename

    def _generate_input_data(self, allocate_from_pool: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {}

        if self.is_resource_pool and allocate_from_pool:
            return {"from_pool": {"id": self.id}}

        if self.id is not None:
            data["id"] = self.id
        elif self.hfid is not None:
            data["hfid"] = self.hfid
            if self._kind is not None:
                data["kind"] = self._kind

        for prop_name in self._properties:
            if getattr(self, prop_name) is not None:
                data[f"_relation__{prop_name}"] = getattr(self, prop_name)

        return data

    def _generate_mutation_query(self) -> dict[str, Any]:
        if self.name and self.is_resource_pool:
            # If a related node points to a pool, ask for the ID of the pool allocated resource
            return {self.name: {"node": {"id": None, "display_label": None, "__typename": None}}}
        return {}

    @classmethod
    def _generate_query_data(cls, peer_data: dict[str, Any] | None = None, property: bool = False) -> dict:
        """Generates the basic structure of a GraphQL query for a single relationship.

        Args:
            peer_data (dict[str, Union[Any, Dict]], optional): Additional data to be included in the query for the node.
                This is used to add extra fields when prefetching related node data.

        Returns:
            Dict: A dictionary representing the basic structure of a GraphQL query, including the node's ID, display label,
                and typename. The method also includes additional properties and any peer_data provided.
        """
        data: dict[str, Any] = {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}}
        properties: dict[str, Any] = {}

        if property:
            for prop_name in PROPERTIES_FLAG:
                properties[prop_name] = None
            for prop_name in PROPERTIES_OBJECT:
                properties[prop_name] = {"id": None, "display_label": None, "__typename": None}

        if properties:
            data["properties"] = properties
        if peer_data:
            data["node"].update(peer_data)

        return data


class RelatedNode(RelatedNodeBase):
    """Represents a RelatedNodeBase in an asynchronous context."""

    def __init__(
        self,
        client: InfrahubClient,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
        name: str | None = None,
    ):
        """
        Args:
            client (InfrahubClient): The client used to interact with the backend asynchronously.
            branch (str): The branch where the related node resides.
            schema (RelationshipSchema): The schema of the relationship.
            data (Union[Any, dict]): Data representing the related node.
            name (Optional[str]): The name of the related node.
        """
        self._client = client
        super().__init__(branch=branch, schema=schema, data=data, name=name)

    async def fetch(self, timeout: int | None = None) -> None:
        if not self.id or not self.typename:
            raise Error("Unable to fetch the peer, id and/or typename are not defined")

        self._peer = await self._client.get(
            kind=self.typename, id=self.id, populate_store=True, branch=self._branch, timeout=timeout
        )

    @property
    def peer(self) -> InfrahubNode:
        return self.get()

    def get(self) -> InfrahubNode:
        if self._peer:
            return self._peer  # type: ignore[return-value]

        if self.id and self.typename:
            return self._client.store.get(key=self.id, kind=self.typename, branch=self._branch)  # type: ignore[return-value]

        if self.hfid_str:
            return self._client.store.get(key=self.hfid_str, branch=self._branch)  # type: ignore[return-value]

        raise ValueError("Node must have at least one identifier (ID or HFID) to query it.")


class RelatedNodeSync(RelatedNodeBase):
    """Represents a related node in a synchronous context."""

    def __init__(
        self,
        client: InfrahubClientSync,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
        name: str | None = None,
    ):
        """
        Args:
            client (InfrahubClientSync): The client used to interact with the backend synchronously.
            branch (str): The branch where the related node resides.
            schema (RelationshipSchema): The schema of the relationship.
            data (Union[Any, dict]): Data representing the related node.
            name (Optional[str]): The name of the related node.
        """
        self._client = client
        super().__init__(branch=branch, schema=schema, data=data, name=name)

    def fetch(self, timeout: int | None = None) -> None:
        if not self.id or not self.typename:
            raise Error("Unable to fetch the peer, id and/or typename are not defined")

        self._peer = self._client.get(
            kind=self.typename, id=self.id, populate_store=True, branch=self._branch, timeout=timeout
        )

    @property
    def peer(self) -> InfrahubNodeSync:
        return self.get()

    def get(self) -> InfrahubNodeSync:
        if self._peer:
            return self._peer  # type: ignore[return-value]

        if self.id and self.typename:
            return self._client.store.get(key=self.id, kind=self.typename, branch=self._branch)  # type: ignore[return-value]

        if self.hfid_str:
            return self._client.store.get(key=self.hfid_str, branch=self._branch)  # type: ignore[return-value]

        raise ValueError("Node must have at least one identifier (ID or HFID) to query it.")
