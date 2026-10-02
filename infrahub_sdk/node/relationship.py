from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Generic, cast

from ..exceptions import (
    Error,
    UninitializedError,
)
from ..types import Order
from .constants import PROPERTIES_FLAG, PROPERTIES_OBJECT
from .metadata import NodeMetadata, RelationshipMetadata
from .related_node import PeerT, PeerTSync, RelatedNode, RelatedNodeSync
from .selection import check_selection_conflict, peer_kind_only, requests_identity_only

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync
    from ..schema import RelationshipSchemaAPI
    from .node import InfrahubNode, InfrahubNodeBase, InfrahubNodeSync


class RelationshipManagerBase(Generic[PeerT]):
    """Base class for :class:`RelationshipManager` and :class:`RelationshipManagerSync`.

    A ``RelationshipManagerBase`` exposes a cardinality-many relationship as a list of
    peers along with helpers to add, remove, or extend the set. Relationship managers are
    initialized lazily: until :meth:`fetch` (on the async/sync subclasses) is called, the
    members are not loaded and editing is not allowed. Reading the peers while ``is_loaded``
    is ``False`` warns with ``FieldNotLoadedWarning``.

    Attributes:
        name (str): The name of the relationship slot on the parent node.
        schema (RelationshipSchemaAPI): The schema describing the relationship.
        branch (str): The branch the relationship is bound to.
        peers (list[RelatedNode | RelatedNodeSync]): The current peer set.
        initialized (bool): ``True`` once the manager has been populated with data.

    """

    def __init__(self, name: str, branch: str, schema: RelationshipSchemaAPI) -> None:
        """Build the base relationship manager state.

        Args:
            name (str): The name of the relationship.
            branch (str): The branch where the relationship resides.
            schema (RelationshipSchemaAPI): The schema of the relationship.

        """
        self.initialized: bool = False
        self._has_update: bool = False
        self.name = name
        self.schema = schema
        self.branch = branch

        self._properties_flag = PROPERTIES_FLAG
        self._properties_object = PROPERTIES_OBJECT
        self._properties = self._properties_flag + self._properties_object

        self._peers: list[RelatedNode[PeerT] | RelatedNodeSync[PeerT]] = []

    @property
    def _owner(self) -> InfrahubNodeBase | None:
        return None

    @property
    def is_loaded(self) -> bool:
        """Return whether the SDK knows this relationship's peers. Reading this never warns.

        The peers are known once the manager is ``initialized``, or while the owning node has no ``id`` yet.

        Returns:
            bool: ``True`` when reading the peers returns what the SDK holds without a warning.

        """
        owner = self._owner
        return self.initialized or owner is None or not owner.id

    def _check_loaded(self) -> None:
        owner = self._owner
        if owner is not None and not self.is_loaded:
            owner._report_unloaded_read(self.name, hint_fetch=True)

    @property
    def peers(self) -> list[RelatedNode[PeerT] | RelatedNodeSync[PeerT]]:
        """Return the current peer set, as a list that can be modified in place.

        Returns:
            list[RelatedNode | RelatedNodeSync]: The peers, in insertion order.

        """
        self._check_loaded()
        return self._peers

    @peers.setter
    def peers(self, value: list[RelatedNode[PeerT] | RelatedNodeSync[PeerT]]) -> None:
        """Replace the current peer set."""
        self._peers = value

    @property
    def peer_ids(self) -> list[str]:
        """Return the IDs of all peers that have one.

        Returns:
            list[str]: The IDs of the peers, in insertion order.

        """
        self._check_loaded()
        return self._peer_ids()

    @property
    def peer_hfids(self) -> list[list[Any]]:
        """Return the HFIDs of all peers that have one.

        Returns:
            list[list[Any]]: The HFIDs of the peers as lists of components, in insertion order.

        """
        self._check_loaded()
        return self._peer_hfids()

    @property
    def peer_hfids_str(self) -> list[str]:
        """Return the HFIDs of all peers as separator-joined strings.

        Returns:
            list[str]: The HFIDs of the peers as ``Kind__part1__part2`` strings.

        """
        self._check_loaded()
        return [peer.hfid_str for peer in self._peers if peer.hfid_str]

    def _peer_ids(self) -> list[str]:
        return [peer.id for peer in self._peers if peer.id]

    def _peer_hfids(self) -> list[list[Any]]:
        return [peer.hfid for peer in self._peers if peer.hfid]

    @property
    def has_update(self) -> bool:
        """Return whether the peer set has been modified since initialization.

        Returns:
            bool: ``True`` after a successful :meth:`add`, :meth:`extend`, or :meth:`remove`.

        """
        return self._has_update

    @property
    def is_from_profile(self) -> bool:
        """Return whether this relationship was set from a profile.

        The relationship is considered profile-sourced only when every peer is itself
        sourced from a profile.

        Returns:
            bool: ``True`` when at least one peer exists and all peers are from a profile.

        """
        self._check_loaded()
        if not self._peers:
            return False
        all_profiles = [p.is_from_profile for p in self._peers]
        return bool(all_profiles) and all(all_profiles)

    def _generate_input_data(self, allocate_from_pool: bool = False) -> list[dict]:
        return [peer._generate_input_data(allocate_from_pool=allocate_from_pool) for peer in self._peers]

    def _generate_mutation_query(self) -> dict[str, Any]:
        # Does nothing for now
        return {}

    @classmethod
    def _generate_query_data(
        cls, peer_data: dict[str, Any] | None = None, property: bool = False, include_metadata: bool = False
    ) -> dict:
        """Generates the basic structure of a GraphQL query for relationships with multiple nodes.

        Args:
            peer_data (dict[str, Union[Any, Dict]], optional): Additional data to be included in the query for each node.
                This is used to add extra fields when prefetching related node data in many-to-many relationships.
            property (bool, optional): If True, includes property fields (is_protected, source, owner, etc.).
            include_metadata (bool, optional): If True, includes node_metadata and relationship_metadata fields.

        Returns:
            Dict: A dictionary representing the basic structure of a GraphQL query for multiple related nodes.
                It includes edges and node information (ID, display label, and typename), along with additional properties
                and any peer_data provided.

        """
        data: dict[str, Any] = {
            "edges": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
        }

        properties: dict[str, Any] = {}
        if property:
            for prop_name in PROPERTIES_FLAG:
                properties[prop_name] = None
            for prop_name in PROPERTIES_OBJECT:
                properties[prop_name] = {"id": None, "display_label": None, "__typename": None}
            data["edges"]["properties"] = properties

        if include_metadata:
            data["edges"]["node_metadata"] = NodeMetadata._generate_query_data()
            data["edges"]["relationship_metadata"] = RelationshipMetadata._generate_query_data()

        if peer_data:
            data["edges"]["node"].update(peer_data)

        return data


class RelationshipManager(RelationshipManagerBase[PeerT]):
    """Asynchronous manager for a cardinality-many relationship.

    Extends :class:`RelationshipManagerBase` with the ability to populate and edit the
    peer set against an :class:`InfrahubClient`: :meth:`fetch` resolves every peer in a
    parallel batch and :meth:`add`, :meth:`extend`, and :meth:`remove` mutate the peer
    list in memory. Peers are exposed as :class:`RelatedNode` instances and can be
    accessed by index via ``manager[i]``.
    """

    def __init__(
        self,
        name: str,
        client: InfrahubClient,
        node: InfrahubNode,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
    ) -> None:
        """Initialize the async relationship manager.

        Args:
            name (str): The name of the relationship.
            client (InfrahubClient): The client used to interact with the backend.
            node (InfrahubNode): The node to which the relationship belongs.
            branch (str): The branch where the relationship resides.
            schema (RelationshipSchema): The schema of the relationship.
            data (Union[Any, dict]): Initial data for the relationships.

        Raises:
            ValueError: If ``data`` is in an unexpected format.

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
                self._peers.append(
                    cast(
                        "RelatedNode[PeerT]",
                        RelatedNode(name=name, client=self.client, branch=self.branch, schema=schema, data=item),
                    )
                )
        elif isinstance(data, dict) and "edges" in data:
            for item in data["edges"]:
                self._peers.append(
                    cast(
                        "RelatedNode[PeerT]",
                        RelatedNode(name=name, client=self.client, branch=self.branch, schema=schema, data=item),
                    )
                )
        else:
            raise ValueError(
                f"Relationship '{name}' expects a list of nodes (cardinality many), "
                f"but received a single {type(data).__name__}. "
                f"Wrap the value in a list, e.g. {name}=[value]."
            )

    @property
    def _owner(self) -> InfrahubNode:
        return self.node

    def __getitem__(self, item: int) -> RelatedNode[PeerT]:
        self._check_loaded()
        return cast("RelatedNode[PeerT]", self._peers[item])

    async def fetch(self, only: list[str] | None = None, exclude: list[str] | None = None) -> None:
        """Populate the peer set and resolve every peer to a full node.

        When the manager is not yet initialized, the parent node is re-queried for this
        relationship alone so the peer list can be populated. The peers are then fetched in
        a parallel batch, one query per peer kind, and stored in the client store.

        Args:
            only (list[str], optional): Exactly the peer attributes and relationships to query,
                plus ``id``, ``display_label`` and ``__typename``. Each name must be a field of
                the relationship's peer kind or of a kind implementing it, and each peer kind is
                asked for the names it defines. A peer kind left with identity fields only, which
                its references already hold, is not queried, and its peers stay references. Reading
                any other field of a fetched peer raises ``FieldNotLoadedError``. Cannot be combined
                with ``exclude``.
            exclude (list[str], optional): Peer attributes or relationships to leave out of the query.

        Raises:
            SelectionConflictError: If ``only`` is combined with ``exclude``.
            SelectionFieldNotFoundError: If a name in ``only`` is neither a field of the peer kind
                nor of any kind implementing it.
            Error: If any peer is missing an ``id`` or ``typename`` and cannot be resolved.

        """
        check_selection_conflict(None, exclude, only)
        if only is not None:
            await self.client._get_schema_for_selection(
                kind=self.schema.peer, branch=self.branch, include=None, exclude=None, only=only, fragment=True
            )

        if not self.initialized:
            # The narrow parent is not stored, so it never replaces a fuller copy of the node in the store.
            node = await self.client.get(
                kind=self.node._schema.kind,
                id=self.node.id,
                branch=self.branch,
                populate_store=False,
                only=[self.schema.name],
            )
            rm = getattr(node, self.schema.name)
            self._peers = rm.peers
            self.initialized = True

        ids_per_kind_map = defaultdict(list)
        for peer in self._peers:
            if not peer.id or not peer.typename:
                raise Error("Unable to fetch the peer, id and/or typename are not defined")
            ids_per_kind_map[peer.typename].append(peer.id)

        batch = await self.client.create_batch()
        for kind, ids in ids_per_kind_map.items():
            kind_only = (
                None
                if only is None
                else peer_kind_only(only, await self.client.schema.get(kind=kind, branch=self.branch))
            )
            if kind_only is not None and requests_identity_only(kind_only):
                continue
            batch.add(
                task=self.client.filters,
                kind=kind,
                ids=ids,
                populate_store=True,
                branch=self.branch,
                parallel=True,
                order=Order(disable=True),
                exclude=exclude,
                only=kind_only,
            )

        async for _ in batch.execute():
            pass

    def add(self, data: str | RelatedNode | dict) -> None:
        """Add a new peer to this relationship.

        The new peer is only added when its ID or HFID is not already present; duplicate
        adds are silently ignored.

        Args:
            data (str | RelatedNode | dict): The peer to add. Accepts an ID string, an
                existing :class:`RelatedNode`, or a dict describing the peer (with ``id``
                or ``hfid`` keys, plus optional relationship properties).

        Raises:
            UninitializedError: If :meth:`fetch` has not been called on this manager yet.

        """
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        new_node = cast(
            "RelatedNode[PeerT]", RelatedNode(schema=self.schema, client=self.client, branch=self.branch, data=data)
        )

        if (new_node.id and new_node.id not in self._peer_ids()) or (
            new_node.hfid and new_node.hfid not in self._peer_hfids()
        ):
            self._peers.append(new_node)
            self._has_update = True

    def extend(self, data: Iterable[str | RelatedNode | dict]) -> None:
        """Add new peers to this relationship.

        This is a convenience wrapper that calls :meth:`add` for every item in ``data``.
        Items already present (by ID or HFID) are silently ignored.

        Args:
            data (Iterable[str | RelatedNode | dict]): The peers to add, in any of the
                formats accepted by :meth:`add`.

        Raises:
            UninitializedError: If :meth:`fetch` has not been called on this manager yet.

        """
        for d in data:
            self.add(d)

    def remove(self, data: str | RelatedNode | dict) -> None:
        """Remove a peer from this relationship.

        The peer to remove is matched first by ID, then by HFID. When no match is found,
        the call is a no-op.

        Args:
            data (str | RelatedNode | dict): The peer to remove. Accepts an ID string, an
                existing :class:`RelatedNode`, or a dict describing the peer.

        Raises:
            UninitializedError: If :meth:`fetch` has not been called on this manager yet.
            IndexError: If the internal peer index is inconsistent with the lookup result.

        """
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        node_to_remove = RelatedNode(schema=self.schema, client=self.client, branch=self.branch, data=data)

        if node_to_remove.id and node_to_remove.id in (peer_ids := self._peer_ids()):
            idx = peer_ids.index(node_to_remove.id)
            if self._peers[idx].id != node_to_remove.id:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.id}")

            self._peers.pop(idx)
            self._has_update = True

        elif node_to_remove.hfid and node_to_remove.hfid in (peer_hfids := self._peer_hfids()):
            idx = peer_hfids.index(node_to_remove.hfid)
            if self._peers[idx].hfid != node_to_remove.hfid:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.hfid}")

            self._peers.pop(idx)
            self._has_update = True


class RelationshipManagerSync(RelationshipManagerBase[PeerTSync]):
    """Synchronous manager for a cardinality-many relationship.

    Synchronous counterpart of :class:`RelationshipManager`. Extends
    :class:`RelationshipManagerBase` with the ability to populate and edit the peer set
    against an :class:`InfrahubClientSync`: :meth:`fetch` resolves every peer in a
    parallel batch and :meth:`add`, :meth:`extend`, and :meth:`remove` mutate the peer
    list in memory. Peers are exposed as :class:`RelatedNodeSync` instances and can be
    accessed by index via ``manager[i]``.
    """

    def __init__(
        self,
        name: str,
        client: InfrahubClientSync,
        node: InfrahubNodeSync,
        branch: str,
        schema: RelationshipSchemaAPI,
        data: Any | dict,
    ) -> None:
        """Initialize the sync relationship manager.

        Args:
            name (str): The name of the relationship.
            client (InfrahubClientSync): The client used to interact with the backend synchronously.
            node (InfrahubNodeSync): The node to which the relationship belongs.
            branch (str): The branch where the relationship resides.
            schema (RelationshipSchema): The schema of the relationship.
            data (Union[Any, dict]): Initial data for the relationships.

        Raises:
            ValueError: If ``data`` is in an unexpected format.

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
                self._peers.append(
                    cast(
                        "RelatedNodeSync[PeerTSync]",
                        RelatedNodeSync(name=name, client=self.client, branch=self.branch, schema=schema, data=item),
                    )
                )
        elif isinstance(data, dict) and "edges" in data:
            for item in data["edges"]:
                self._peers.append(
                    cast(
                        "RelatedNodeSync[PeerTSync]",
                        RelatedNodeSync(name=name, client=self.client, branch=self.branch, schema=schema, data=item),
                    )
                )
        else:
            raise ValueError(
                f"Relationship '{name}' expects a list of nodes (cardinality many), "
                f"but received a single {type(data).__name__}. "
                f"Wrap the value in a list, e.g. {name}=[value]."
            )

    @property
    def _owner(self) -> InfrahubNodeSync:
        return self.node

    def __getitem__(self, item: int) -> RelatedNodeSync[PeerTSync]:
        self._check_loaded()
        return cast("RelatedNodeSync[PeerTSync]", self._peers[item])

    def fetch(self, only: list[str] | None = None, exclude: list[str] | None = None) -> None:
        """Populate the peer set and resolve every peer to a full node.

        When the manager is not yet initialized, the parent node is re-queried for this
        relationship alone so the peer list can be populated. The peers are then fetched in
        a parallel batch, one query per peer kind, and stored in the client store.

        Args:
            only (list[str], optional): Exactly the peer attributes and relationships to query,
                plus ``id``, ``display_label`` and ``__typename``. Each name must be a field of
                the relationship's peer kind or of a kind implementing it, and each peer kind is
                asked for the names it defines. A peer kind left with identity fields only, which
                its references already hold, is not queried, and its peers stay references. Reading
                any other field of a fetched peer raises ``FieldNotLoadedError``. Cannot be combined
                with ``exclude``.
            exclude (list[str], optional): Peer attributes or relationships to leave out of the query.

        Raises:
            SelectionConflictError: If ``only`` is combined with ``exclude``.
            SelectionFieldNotFoundError: If a name in ``only`` is neither a field of the peer kind
                nor of any kind implementing it.
            Error: If any peer is missing an ``id`` or ``typename`` and cannot be resolved.

        """
        check_selection_conflict(None, exclude, only)
        if only is not None:
            self.client._get_schema_for_selection(
                kind=self.schema.peer, branch=self.branch, include=None, exclude=None, only=only, fragment=True
            )

        if not self.initialized:
            # The narrow parent is not stored, so it never replaces a fuller copy of the node in the store.
            node = self.client.get(
                kind=self.node._schema.kind,
                id=self.node.id,
                branch=self.branch,
                populate_store=False,
                only=[self.schema.name],
            )
            rm = getattr(node, self.schema.name)
            self._peers = rm.peers
            self.initialized = True

        ids_per_kind_map = defaultdict(list)
        for peer in self._peers:
            if not peer.id or not peer.typename:
                raise Error("Unable to fetch the peer, id and/or typename are not defined")
            ids_per_kind_map[peer.typename].append(peer.id)

        batch = self.client.create_batch()
        for kind, ids in ids_per_kind_map.items():
            kind_only = (
                None if only is None else peer_kind_only(only, self.client.schema.get(kind=kind, branch=self.branch))
            )
            if kind_only is not None and requests_identity_only(kind_only):
                continue
            batch.add(
                task=self.client.filters,
                kind=kind,
                ids=ids,
                populate_store=True,
                branch=self.branch,
                parallel=True,
                order=Order(disable=True),
                exclude=exclude,
                only=kind_only,
            )

        for _ in batch.execute():
            pass

    def add(self, data: str | RelatedNodeSync | dict) -> None:
        """Add a new peer to this relationship.

        The new peer is only added when its ID or HFID is not already present; duplicate
        adds are silently ignored.

        Args:
            data (str | RelatedNodeSync | dict): The peer to add. Accepts an ID string,
                an existing :class:`RelatedNodeSync`, or a dict describing the peer (with
                ``id`` or ``hfid`` keys, plus optional relationship properties).

        Raises:
            UninitializedError: If :meth:`fetch` has not been called on this manager yet.

        """
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        new_node = cast(
            "RelatedNodeSync[PeerTSync]",
            RelatedNodeSync(schema=self.schema, client=self.client, branch=self.branch, data=data),
        )

        if (new_node.id and new_node.id not in self._peer_ids()) or (
            new_node.hfid and new_node.hfid not in self._peer_hfids()
        ):
            self._peers.append(new_node)
            self._has_update = True

    def extend(self, data: Iterable[str | RelatedNodeSync | dict]) -> None:
        """Add new peers to this relationship.

        This is a convenience wrapper that calls :meth:`add` for every item in ``data``.
        Items already present (by ID or HFID) are silently ignored.

        Args:
            data (Iterable[str | RelatedNodeSync | dict]): The peers to add, in any of the
                formats accepted by :meth:`add`.

        Raises:
            UninitializedError: If :meth:`fetch` has not been called on this manager yet.

        """
        for d in data:
            self.add(d)

    def remove(self, data: str | RelatedNodeSync | dict) -> None:
        """Remove a peer from this relationship.

        The peer to remove is matched first by ID, then by HFID. When no match is found,
        the call is a no-op.

        Args:
            data (str | RelatedNodeSync | dict): The peer to remove. Accepts an ID string,
                an existing :class:`RelatedNodeSync`, or a dict describing the peer.

        Raises:
            UninitializedError: If :meth:`fetch` has not been called on this manager yet.
            IndexError: If the internal peer index is inconsistent with the lookup result.

        """
        if not self.initialized:
            raise UninitializedError("Must call fetch() on RelationshipManager before editing members")
        node_to_remove = RelatedNodeSync(schema=self.schema, client=self.client, branch=self.branch, data=data)

        if node_to_remove.id and node_to_remove.id in (peer_ids := self._peer_ids()):
            idx = peer_ids.index(node_to_remove.id)
            if self._peers[idx].id != node_to_remove.id:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.id}")
            self._peers.pop(idx)
            self._has_update = True

        elif node_to_remove.hfid and node_to_remove.hfid in (peer_hfids := self._peer_hfids()):
            idx = peer_hfids.index(node_to_remove.hfid)
            if self._peers[idx].hfid != node_to_remove.hfid:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.hfid}")

            self._peers.pop(idx)
            self._has_update = True
