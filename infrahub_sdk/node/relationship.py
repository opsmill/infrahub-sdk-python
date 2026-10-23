from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Generic, cast

from ..exceptions import (
    Error,
    UninitializedError,
)
from ..schema import GenericSchemaAPI
from ..types import Order
from ._only import check_only_names, check_only_names_on_every_kind
from .constants import PROPERTIES_FLAG, PROPERTIES_OBJECT
from .metadata import NodeMetadata, RelationshipMetadata
from .related_node import PeerT, PeerTSync, RelatedNode, RelatedNodeSync

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync
<<<<<<< HEAD
    from ..schema import MainSchemaTypesAPI, RelationshipSchemaAPI
=======
    from ..schema import RelationshipSchemaAPI
>>>>>>> origin/develop
    from .node import InfrahubNode, InfrahubNodeBase, InfrahubNodeSync


class RelationshipManagerBase(Generic[PeerT]):
    """Base class for :class:`RelationshipManager` and :class:`RelationshipManagerSync`.

    A ``RelationshipManagerBase`` exposes a cardinality-many relationship as a list of
    peers along with helpers to add, remove, or extend the set. Relationship managers are
    initialized lazily: until :meth:`fetch` (on the async/sync subclasses) is called, the
    members are not loaded and editing is not allowed.

    Attributes:
        name (str): The name of the relationship slot on the parent node.
        schema (RelationshipSchemaAPI): The schema describing the relationship.
        branch (str): The branch the relationship is bound to.
        peers (list[RelatedNode | RelatedNodeSync]): The current peer set. Assigning a list marks the
            relationship as loaded.
        initialized (bool): ``True`` once the manager has been populated with data.
        is_loaded (bool): ``True`` once the manager has been populated with data or its peers were
            assigned, when it does not belong to a node, or when the node has no ``id`` yet.

    """

    # The node the relationship belongs to; the subclasses set it.
    node: InfrahubNodeBase | None = None

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
        self._peers_assigned = False

    @property
    def peers(self) -> list[RelatedNode[PeerT] | RelatedNodeSync[PeerT]]:
        """Return the peer set.

        The list returned is the one the relationship holds, so changing it in place changes the
        relationship.

        Returns:
            list[RelatedNode | RelatedNodeSync]: The peers, in insertion order.

        Raises:
            FieldNotLoadedError: The node was queried with ``only`` and the relationship was not fetched.

        """
        self._raise_if_not_loaded()
        return self._peers

    @peers.setter
    def peers(self, value: list[RelatedNode[PeerT] | RelatedNodeSync[PeerT]]) -> None:
        self._peers = value
        self._peers_assigned = True

    @property
    def is_loaded(self) -> bool:
        """Return whether this relationship holds the peers from its node's data or from an assignment.

        Never raises and sends no request.

        Returns:
            bool: ``True`` when the relationship is initialized (the data the node was built from
            contained it, or :meth:`fetch` ran), when a list was assigned to ``peers``, when the
            relationship does not belong to a node, or when its node has no ``id`` yet. ``False``
            otherwise.

        """
        return self.initialized or self._peers_assigned or self.node is None or not self.node.id

    def _raise_if_not_loaded(self) -> None:
        if not self.is_loaded and self.node is not None and self.node._only_marker is not None:
            raise self.node._only_marker.not_loaded_error(kind=self.node.get_kind(), field=self.name)

    @property
    def peer_ids(self) -> list[str]:
        """Return the IDs of all peers that have one.

        Returns:
            list[str]: The IDs of the peers, in insertion order.

        Raises:
            FieldNotLoadedError: The node was queried with ``only`` and the relationship was not fetched.

        """
        return [peer.id for peer in self.peers if peer.id]

    @property
    def peer_hfids(self) -> list[list[Any]]:
        """Return the HFIDs of all peers that have one.

        Returns:
            list[list[Any]]: The HFIDs of the peers as lists of components, in insertion order.

        Raises:
            FieldNotLoadedError: The node was queried with ``only`` and the relationship was not fetched.

        """
        return [peer.hfid for peer in self.peers if peer.hfid]

    @property
    def peer_hfids_str(self) -> list[str]:
        """Return the HFIDs of all peers as separator-joined strings.

        Returns:
            list[str]: The HFIDs of the peers as ``Kind__part1__part2`` strings.

        Raises:
            FieldNotLoadedError: The node was queried with ``only`` and the relationship was not fetched.

        """
        return [peer.hfid_str for peer in self.peers if peer.hfid_str]

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

        Raises:
            FieldNotLoadedError: The node was queried with ``only`` and the relationship was not fetched.

        """
        self._raise_if_not_loaded()
        if not self._peers:
            return False
        all_profiles = [p.is_from_profile for p in self._peers]
        return bool(all_profiles) and all(all_profiles)

    def _generate_input_data(self, allocate_from_pool: bool = False) -> list[dict]:
        return [peer._generate_input_data(allocate_from_pool=allocate_from_pool) for peer in self._peers]

    def _peer_ids_per_kind(self) -> dict[str, list[str]]:
        ids_per_kind_map: dict[str, list[str]] = defaultdict(list)
        for peer in self._peers:
            if not peer.id or not peer.typename:
                raise Error("Unable to fetch the peer, id and/or typename are not defined")
            ids_per_kind_map[peer.typename].append(peer.id)
        return ids_per_kind_map

    def _reload_kwargs(self, node: InfrahubNodeBase) -> dict[str, Any]:
        """The arguments of the `get` that reloads `node` with this relationship only."""
        if node._only_marker is not None:
            # Keep the node from `only` in the store instead of replacing it with this narrower copy.
            return {"only": [self.schema.name], "populate_store": False}
        # `ancestors` and `descendants` are not schema relationships, so they may be missing from these names.
        exclude = [
            name for name in node._schema.relationship_names + node._schema.attribute_names if name != self.schema.name
        ]
        return {"include": [self.schema.name], "exclude": exclude}

    def _reload_kwargs(self) -> dict[str, Any]:
        """The arguments of the `get` that reloads `self.node` with this relationship only.

        Raises:
            UninitializedError: If the manager has no node or the node has no ``id``.

        """
        if self.node is None or not self.node.id:
            raise UninitializedError(f"Unable to fetch '{self.schema.name}' on a node that has not been saved")
        schema = self.node._schema
        # `ancestors` and `descendants` are not schema relationships, so they may be missing from these names.
        exclude = [name for name in schema.relationship_names + schema.attribute_names if name != self.schema.name]
        # Keep `self.node` in the store instead of replacing it with this copy that has no attribute values.
        return {"include": [self.schema.name], "exclude": exclude, "populate_store": False}

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

    node: InfrahubNode

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

    def __getitem__(self, item: int) -> RelatedNode[PeerT]:
        self._raise_if_not_loaded()
        return cast("RelatedNode[PeerT]", self._peers[item])

    async def fetch(self, only: list[str] | None = None) -> None:
        """Populate the peer set and fetch every peer with its default fields, or only the fields named in ``only``.

        When the manager is not yet initialized, the parent node is re-queried with this
        relationship included so the peer list can be populated. When the parent node was
        queried with ``only``, the re-query requests this relationship alone and does not
        replace the parent node in the client store. The peers are then fetched in a
        parallel batch grouped by kind and stored in the client store.

        Args:
            only (list[str], optional): The only attributes and relationships to fetch on each peer, which also
                gets its ``id``, ``display_label`` and ``__typename``. Every name must be a field of every peer's
                kind. Reading a field of a peer that was not fetched raises FieldNotLoadedError.

        Raises:
<<<<<<< HEAD
            FieldNotFoundError: A name in ``only`` is not a field of the relationship's peer kind, raised before
                any request, or is missing on the kind of one of the peers, raised before any peer is queried.
            TypeError: ``only`` is a string instead of a list of field names; raised before any request.
=======
            UninitializedError: If the manager is not initialized and the parent node has no ``id``.
>>>>>>> origin/develop
            Error: If any peer is missing an ``id`` or ``typename`` and cannot be resolved.

        """
        if only is not None:
            peer_schema = await self.client.schema.get(kind=self.schema.peer, branch=self.branch)
            check_only_names(
                only=only, schema=peer_schema, implementing_schemas=await self._implementing_schemas(peer_schema)
            )

        if not self.initialized:
<<<<<<< HEAD
=======
            reload_kwargs = self._reload_kwargs()
>>>>>>> origin/develop
            node = await self.client.get(
                kind=self.node._schema.kind,
                id=self.node.id,
                branch=self.branch,
<<<<<<< HEAD
                **self._reload_kwargs(node=self.node),
=======
                **reload_kwargs,
>>>>>>> origin/develop
            )
            rm = getattr(node, self.schema.name)
            self._peers = rm._peers
            self.initialized = True

        ids_per_kind_map = self._peer_ids_per_kind()
        if only is not None:
            check_only_names_on_every_kind(
                only=only,
                schemas=[await self.client.schema.get(kind=kind, branch=self.branch) for kind in ids_per_kind_map],
            )

        # Pass `only` only when set, so client overrides written before it keep working.
        only_kwargs: dict[str, Any] = {} if only is None else {"only": only}
        batch = await self.client.create_batch()
        for kind, ids in ids_per_kind_map.items():
            batch.add(
                task=self.client.filters,
                kind=kind,
                ids=ids,
                populate_store=True,
                branch=self.branch,
                parallel=True,
                order=Order(disable=True),
                **only_kwargs,
            )

        async for _ in batch.execute():
            pass

    async def _implementing_schemas(self, schema: MainSchemaTypesAPI) -> list[MainSchemaTypesAPI]:
        if not isinstance(schema, GenericSchemaAPI):
            return []
        return [await self.client.schema.get(kind=kind, branch=self.branch) for kind in schema.used_by]

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

        if (new_node.id and new_node.id not in self.peer_ids) or (
            new_node.hfid and new_node.hfid not in self.peer_hfids
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

        if node_to_remove.id and node_to_remove.id in self.peer_ids:
            idx = self.peer_ids.index(node_to_remove.id)
            if self._peers[idx].id != node_to_remove.id:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.id}")

            self._peers.pop(idx)
            self._has_update = True

        elif node_to_remove.hfid and node_to_remove.hfid in self.peer_hfids:
            idx = self.peer_hfids.index(node_to_remove.hfid)
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

    node: InfrahubNodeSync

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

    def __getitem__(self, item: int) -> RelatedNodeSync[PeerTSync]:
        self._raise_if_not_loaded()
        return cast("RelatedNodeSync[PeerTSync]", self._peers[item])

    def fetch(self, only: list[str] | None = None) -> None:
        """Populate the peer set and fetch every peer with its default fields, or only the fields named in ``only``.

        When the manager is not yet initialized, the parent node is re-queried with this
        relationship included so the peer list can be populated. When the parent node was
        queried with ``only``, the re-query requests this relationship alone and does not
        replace the parent node in the client store. The peers are then fetched in a
        parallel batch grouped by kind and stored in the client store.

        Args:
            only (list[str], optional): The only attributes and relationships to fetch on each peer, which also
                gets its ``id``, ``display_label`` and ``__typename``. Every name must be a field of every peer's
                kind. Reading a field of a peer that was not fetched raises FieldNotLoadedError.

        Raises:
<<<<<<< HEAD
            FieldNotFoundError: A name in ``only`` is not a field of the relationship's peer kind, raised before
                any request, or is missing on the kind of one of the peers, raised before any peer is queried.
            TypeError: ``only`` is a string instead of a list of field names; raised before any request.
=======
            UninitializedError: If the manager is not initialized and the parent node has no ``id``.
>>>>>>> origin/develop
            Error: If any peer is missing an ``id`` or ``typename`` and cannot be resolved.

        """
        if only is not None:
            peer_schema = self.client.schema.get(kind=self.schema.peer, branch=self.branch)
            check_only_names(
                only=only, schema=peer_schema, implementing_schemas=self._implementing_schemas(peer_schema)
            )

        if not self.initialized:
<<<<<<< HEAD
=======
            reload_kwargs = self._reload_kwargs()
>>>>>>> origin/develop
            node = self.client.get(
                kind=self.node._schema.kind,
                id=self.node.id,
                branch=self.branch,
<<<<<<< HEAD
                **self._reload_kwargs(node=self.node),
=======
                **reload_kwargs,
>>>>>>> origin/develop
            )
            rm = getattr(node, self.schema.name)
            self._peers = rm._peers
            self.initialized = True

        ids_per_kind_map = self._peer_ids_per_kind()
        if only is not None:
            check_only_names_on_every_kind(
                only=only,
                schemas=[self.client.schema.get(kind=kind, branch=self.branch) for kind in ids_per_kind_map],
            )

        # Pass `only` only when set, so client overrides written before it keep working.
        only_kwargs: dict[str, Any] = {} if only is None else {"only": only}
        batch = self.client.create_batch()
        for kind, ids in ids_per_kind_map.items():
            batch.add(
                task=self.client.filters,
                kind=kind,
                ids=ids,
                populate_store=True,
                branch=self.branch,
                parallel=True,
                order=Order(disable=True),
                **only_kwargs,
            )

        for _ in batch.execute():
            pass

    def _implementing_schemas(self, schema: MainSchemaTypesAPI) -> list[MainSchemaTypesAPI]:
        if not isinstance(schema, GenericSchemaAPI):
            return []
        return [self.client.schema.get(kind=kind, branch=self.branch) for kind in schema.used_by]

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

        if (new_node.id and new_node.id not in self.peer_ids) or (
            new_node.hfid and new_node.hfid not in self.peer_hfids
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

        if node_to_remove.id and node_to_remove.id in self.peer_ids:
            idx = self.peer_ids.index(node_to_remove.id)
            if self._peers[idx].id != node_to_remove.id:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.id}")
            self._peers.pop(idx)
            self._has_update = True

        elif node_to_remove.hfid and node_to_remove.hfid in self.peer_hfids:
            idx = self.peer_hfids.index(node_to_remove.hfid)
            if self._peers[idx].hfid != node_to_remove.hfid:
                raise IndexError(f"Unexpected situation, the node with the index {idx} should be {node_to_remove.hfid}")

            self._peers.pop(idx)
            self._has_update = True
