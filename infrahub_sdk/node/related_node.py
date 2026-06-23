from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Generic, cast, overload

from typing_extensions import TypeVar

from ..exceptions import Error
from ..protocols_base import CoreNodeBase
from .constants import PROFILE_KIND_PREFIX, PROPERTIES_FLAG, PROPERTIES_OBJECT
from .metadata import NodeMetadata, RelationshipMetadata

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync
    from ..schema import RelationshipSchemaAPI
    from .node import InfrahubNode, InfrahubNodeBase, InfrahubNodeSync

# Type of the related peer node. Defaults to ``InfrahubNode``/``InfrahubNodeSync`` so that
# existing un-parameterised ``RelatedNode`` / ``RelatedNodeSync`` usage keeps returning the
# dynamic node, while generated protocols can parameterise it (e.g. ``RelatedNode[CoreDevice]``)
# to preserve the peer type through ``.peer`` / ``.get()``.
PeerT = TypeVar("PeerT", default="InfrahubNode")
PeerTSync = TypeVar("PeerTSync", default="InfrahubNodeSync")


class RelatedNodeBase:
    """Base class for representing a related node in a relationship.

    A ``RelatedNodeBase`` is the peer end of a cardinality-one relationship. It carries
    the lightweight identification of the peer (``id``, ``hfid``, ``typename``, ...) along
    with the relationship-edge properties (``source``, ``owner``, ``is_protected``, ...).
    The full peer node is fetched lazily through :meth:`RelatedNode.fetch` /
    :meth:`RelatedNodeSync.fetch`.

    Attributes:
        schema (RelationshipSchemaAPI): The schema describing the relationship.
        name (str | None): The name of the relationship slot on the parent node.
        updated_at (str | None): ISO-8601 timestamp of the most recent edge update.

    """

    def __init__(self, branch: str, schema: RelationshipSchemaAPI, data: Any | dict, name: str | None = None) -> None:
        """Build a ``RelatedNodeBase`` from raw data.

        Args:
            branch (str): The branch where the related node resides.
            schema (RelationshipSchemaAPI): The schema of the relationship.
            data (Any | dict): Data representing the related node. Accepts a peer
                :class:`CoreNodeBase` instance, a list (treated as an HFID), a string
                (treated as an ID), or a dict in either paginated or flat GraphQL format.
            name (str, optional): The name of the relationship slot on the parent node.

        """
        self.schema = schema
        self.name = name

        self._branch = branch

        self._properties_flag = PROPERTIES_FLAG
        self._properties_object = PROPERTIES_OBJECT
        self._properties = self._properties_flag + self._properties_object

        self._peer: InfrahubNodeBase | CoreNodeBase | None = None
        self._id: str | None = None
        self._hfid: list[str] | None = None
        self._display_label: str | None = None
        self._typename: str | None = None
        self._kind: str | None = None
        self._source_typename: str | None = None
        self._relationship_metadata: RelationshipMetadata | None = None
        # True once the user has assigned to this relationship via Node.__setattr__.
        # Distinguishes "never loaded" (partial GraphQL payload) from "explicitly cleared"
        # so we don't silently null-clear unfetched relationships on save.
        self._peer_has_been_mutated: bool = False

        # Detect node instances. InfrahubNodeBase is imported lazily here to avoid a
        # circular import (node.py imports this module at load time).
        from .node import InfrahubNodeBase as _InfrahubNodeBase  # noqa: PLC0415

        if isinstance(data, (CoreNodeBase, _InfrahubNodeBase)):
            self._peer = cast("InfrahubNodeBase | CoreNodeBase", data)
            for prop in self._properties:
                setattr(self, prop, None)
            self._relationship_metadata = None

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

            self.updated_at: str | None = data.get("updated_at", properties_data.get("updated_at", None))

            # FIXME, we won't need that once we are only supporting paginated results
            if self._typename and self._typename.startswith("Related"):
                self._typename = self._typename[7:]

            for prop in self._properties:
                prop_data = properties_data.get(prop, properties_data.get(f"_relation__{prop}", None))
                if prop_data and isinstance(prop_data, dict) and "id" in prop_data:
                    setattr(self, prop, prop_data["id"])
                    if prop == "source" and "__typename" in prop_data:
                        self._source_typename = prop_data["__typename"]
                elif prop_data and isinstance(prop_data, (str, bool)):
                    setattr(self, prop, prop_data)
                else:
                    setattr(self, prop, None)

            # Parse relationship metadata (at edge level)
            if data.get("relationship_metadata"):
                self._relationship_metadata = RelationshipMetadata(data["relationship_metadata"])

    @property
    def id(self) -> str | None:
        """Return the parsed peer id without triggering a store lookup.

        Returns None when the response carried only hfid_str (no id, no peer)
        — in that case .peer.id would resolve through the store and yield a
        non-None id, so .id and .peer.id are NOT interchangeable.

        Returns:
            str | None: The peer node ID, or ``None`` when neither the peer nor an ID is set.

        """
        if self._peer:
            return self._peer.id
        return self._id

    @property
    def hfid(self) -> list[Any] | None:
        """Return the human-friendly ID of the related node.

        Returns:
            list[Any] | None: The peer HFID as a list of components, or ``None`` when not set.

        """
        if self._peer:
            return self._peer.hfid
        return self._hfid

    @property
    def hfid_str(self) -> str | None:
        """Return the human-friendly ID of the related node as a separator-joined string.

        The returned string includes the kind prefix and is therefore suitable as a key
        for the client store.

        Returns:
            str | None: The peer HFID joined with the HFID separator, or ``None`` when
            unavailable (no resolved peer or missing HFID).

        """
        if self._peer and self.hfid:
            return self._peer.get_human_friendly_id_as_string(include_kind=True)
        return None

    @property
    def is_resource_pool(self) -> bool:
        """Return whether the related node is a resource pool.

        Returns:
            bool: ``True`` when the resolved peer inherits from ``CoreResourcePool``.

        """
        if self._peer:
            return self._peer.is_resource_pool()
        return False

    @property
    def initialized(self) -> bool:
        """Return whether this related node has an identifier.

        Returns:
            bool: ``True`` when an ID or HFID is known and the relationship can be referenced.

        """
        return bool(self.id) or bool(self.hfid)

    @property
    def display_label(self) -> str | None:
        """Return the human-readable label of the related node.

        Returns:
            str | None: The peer display label, or ``None`` when not provided.

        """
        if self._peer:
            return self._peer.display_label
        return self._display_label

    @property
    def typename(self) -> str | None:
        """Return the GraphQL ``__typename`` of the related node.

        Returns:
            str | None: The peer typename, or ``None`` when not provided.

        """
        if self._peer:
            return self._peer.typename
        return self._typename

    @property
    def kind(self) -> str | None:
        """Return the schema kind of the related node.

        Returns:
            str | None: The peer schema kind, or ``None`` when not provided.

        """
        if self._peer:
            return self._peer.get_kind()
        return self._kind

    @property
    def is_from_profile(self) -> bool:
        """Return whether this relationship was set from a profile.

        A relationship is considered profile-sourced when the typename of its ``source``
        property starts with the profile kind prefix.

        Returns:
            bool: ``True`` when the relationship's source is a profile node.

        """
        if not self._source_typename:
            return False
        return bool(re.match(rf"^{PROFILE_KIND_PREFIX}[A-Z]", self._source_typename))

    def get_relationship_metadata(self) -> RelationshipMetadata | None:
        """Return the relationship-edge metadata (``updated_at``, ``updated_by``).

        The metadata is populated only when the parent query was executed with
        ``include_metadata=True``.

        Returns:
            RelationshipMetadata | None: The edge metadata if fetched, otherwise ``None``.

        """
        return self._relationship_metadata

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
    def _generate_query_data(
        cls, peer_data: dict[str, Any] | None = None, property: bool = False, include_metadata: bool = False
    ) -> dict:
        """Generates the basic structure of a GraphQL query for a single relationship.

        Args:
            peer_data (dict[str, Union[Any, Dict]], optional): Additional data to be included in the query for the node.
                This is used to add extra fields when prefetching related node data.
            property (bool, optional): If True, includes property fields (is_protected, source, owner, etc.).
            include_metadata (bool, optional): If True, includes node_metadata (for the peer node) and
                relationship_metadata (for the relationship edge) fields.

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

            data["properties"] = properties

        if include_metadata:
            # node_metadata is for the peer InfrahubNode (populated via from_graphql)
            data["node_metadata"] = NodeMetadata._generate_query_data()
            # relationship_metadata is for the relationship edge itself
            data["relationship_metadata"] = RelationshipMetadata._generate_query_data()

        if peer_data:
            data["node"].update(peer_data)

        return data


class RelatedNode(RelatedNodeBase, Generic[PeerT]):
    """Asynchronous related node bound to an :class:`InfrahubClient`.

    Extends :class:`RelatedNodeBase` with the ability to lazily resolve the peer node:
    :meth:`fetch` retrieves the full peer from the backend, :meth:`get` returns it from
    the local cache or the client store, and :attr:`peer` is a convenience accessor
    around :meth:`get`.
    """

    def __init__(
        self,
        client: InfrahubClient,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
        name: str | None = None,
    ) -> None:
        """Initialize the async related node.

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
        """Fetch the full peer node from the backend and cache it on this object.

        After ``fetch()`` completes, attribute and relationship access on the peer is
        available via :attr:`peer` or :meth:`get`.

        Args:
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.

        Raises:
            Error: If neither ``id`` nor ``typename`` is set on this related node.

        """
        if not self.id or not self.typename:
            raise Error("Unable to fetch the peer, id and/or typename are not defined")

        self._peer = await self._client.get(
            kind=self.typename, id=self.id, populate_store=True, branch=self._branch, timeout=timeout
        )

    @property
    def peer(self) -> PeerT:
        """Return the resolved peer node.

        This is a convenience accessor for :meth:`get`; the peer must already have been
        fetched or stored in the client store.

        Returns:
            PeerT: The resolved peer node.

        """
        return self.get()

    def get(self) -> PeerT:
        """Return the resolved peer node from cache or the client store.

        Lookup order:

        1. The peer cached locally after a successful :meth:`fetch`.
        2. The client store keyed by ``id`` and ``typename``.
        3. The client store keyed by ``hfid_str``.

        When resolving via ``hfid_str`` the returned node has a non-None id even when
        this ``RelatedNode``'s ``.id`` is None — that is the case in which ``.peer.id``
        and ``.id`` diverge.

        Returns:
            PeerT: The resolved peer node.

        Raises:
            ValueError: If neither an ID nor an HFID is available to look up the peer.

        """
        if self._peer:
            return cast("PeerT", self._peer)

        if self.id and self.typename:
            return cast("PeerT", self._client.store.get(key=self.id, kind=self.typename, branch=self._branch))

        if self.hfid_str:
            return cast("PeerT", self._client.store.get(key=self.hfid_str, branch=self._branch))

        raise ValueError("Node must have at least one identifier (ID or HFID) to query it.")


class RelatedNodeSync(RelatedNodeBase, Generic[PeerTSync]):
    """Synchronous related node bound to an :class:`InfrahubClientSync`.

    Synchronous counterpart of :class:`RelatedNode`. Extends :class:`RelatedNodeBase`
    with the ability to lazily resolve the peer node: :meth:`fetch` retrieves the full
    peer from the backend, :meth:`get` returns it from the local cache or the client
    store, and :attr:`peer` is a convenience accessor around :meth:`get`.
    """

    def __init__(
        self,
        client: InfrahubClientSync,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
        name: str | None = None,
    ) -> None:
        """Initialize the sync related node.

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
        """Fetch the full peer node from the backend and cache it on this object.

        After ``fetch()`` completes, attribute and relationship access on the peer is
        available via :attr:`peer` or :meth:`get`.

        Args:
            timeout (int, optional): Overrides the default timeout used when querying the
                GraphQL API. Specified in seconds.

        Raises:
            Error: If neither ``id`` nor ``typename`` is set on this related node.

        """
        if not self.id or not self.typename:
            raise Error("Unable to fetch the peer, id and/or typename are not defined")

        self._peer = self._client.get(
            kind=self.typename, id=self.id, populate_store=True, branch=self._branch, timeout=timeout
        )

    @property
    def peer(self) -> PeerTSync:
        """Return the resolved peer node.

        This is a convenience accessor for :meth:`get`; the peer must already have been
        fetched or stored in the client store.

        Returns:
            PeerTSync: The resolved peer node.

        """
        return self.get()

    def get(self) -> PeerTSync:
        """Return the resolved peer node from cache or the client store.

        Lookup order:

        1. The peer cached locally after a successful :meth:`fetch`.
        2. The client store keyed by ``id`` and ``typename``.
        3. The client store keyed by ``hfid_str``.

        When resolving via ``hfid_str`` the returned node has a non-None id even when
        this ``RelatedNode``'s ``.id`` is None — that is the case in which ``.peer.id``
        and ``.id`` diverge.

        Returns:
            PeerTSync: The resolved peer node.

        Raises:
            ValueError: If neither an ID nor an HFID is available to look up the peer.

        """
        if self._peer:
            return cast("PeerTSync", self._peer)

        if self.id and self.typename:
            return cast("PeerTSync", self._client.store.get(key=self.id, kind=self.typename, branch=self._branch))

        if self.hfid_str:
            return cast("PeerTSync", self._client.store.get(key=self.hfid_str, branch=self._branch))

        raise ValueError("Node must have at least one identifier (ID or HFID) to query it.")


class RelationshipAttribute(Generic[PeerT]):
    """Typing descriptor for a cardinality-one relationship on a generated protocol.

    It reads back as ``RelatedNode[PeerT]`` (so ``.peer`` keeps the peer type) but accepts
    assignment of an id string, an HFID, a peer node, or ``None`` — mirroring the runtime
    ``InfrahubNode.__setattr__`` behaviour, which wraps the assigned value in a ``RelatedNode``.

    This type only appears in generated protocols (it is never instantiated at runtime), so it
    exists purely to give ``node.rel`` separate read and assignment types under a type checker.
    """

    @overload
    def __get__(self, instance: None, owner: Any = None) -> RelationshipAttribute[PeerT]: ...

    @overload
    def __get__(self, instance: object, owner: Any = None) -> RelatedNode[PeerT]: ...

    def __get__(self, instance: object | None, owner: Any = None) -> RelationshipAttribute[PeerT] | RelatedNode[PeerT]:
        raise NotImplementedError  # typing-only descriptor; never invoked at runtime

    def __set__(self, instance: object, value: str | list[str] | PeerT | None) -> None:
        raise NotImplementedError  # typing-only descriptor; never invoked at runtime


class RelationshipAttributeSync(Generic[PeerTSync]):
    """Synchronous counterpart of :class:`RelationshipAttribute`."""

    @overload
    def __get__(self, instance: None, owner: Any = None) -> RelationshipAttributeSync[PeerTSync]: ...

    @overload
    def __get__(self, instance: object, owner: Any = None) -> RelatedNodeSync[PeerTSync]: ...

    def __get__(
        self, instance: object | None, owner: Any = None
    ) -> RelationshipAttributeSync[PeerTSync] | RelatedNodeSync[PeerTSync]:
        raise NotImplementedError  # typing-only descriptor; never invoked at runtime

    def __set__(self, instance: object, value: str | list[str] | PeerTSync | None) -> None:
        raise NotImplementedError  # typing-only descriptor; never invoked at runtime
