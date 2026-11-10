from __future__ import annotations

import inspect
import threading
import warnings
from typing import TYPE_CHECKING, Literal, overload

from infrahub_sdk.protocols_base import CoreNodeBase

from .exceptions import NodeInvalidError, NodeNotFoundError
from .node.parsers import parse_human_friendly_id

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .client import SchemaType, SchemaTypeSync
    from .node import InfrahubNode, InfrahubNodeSync
    from .protocols_base import CoreNode, CoreNodeSync


def get_schema_name(schema: type[SchemaType | SchemaTypeSync] | str | None = None) -> str | None:
    if isinstance(schema, str):
        return schema

    if schema is None:
        return None

    if issubclass(schema, CoreNodeBase):
        if inspect.iscoroutinefunction(schema.save):
            return schema.__name__
        if schema.__name__[-4:] == "Sync":
            return schema.__name__[:-4]
        return schema.__name__

    return None


class NodeStoreBranch:
    def __init__(self, name: str) -> None:
        self.branch_name = name

        self._objs: dict[str, InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync] = {}
        self._hfids: dict[str, dict[tuple, str]] = {}
        self._keys: dict[str, str] = {}
        self._uuids: dict[str, str] = {}
        # Entries written per internal id: a node's HFID can change after it is indexed, so it cannot be recomputed.
        self._keys_by_internal_id: dict[str, set[str]] = {}
        self._hfids_by_internal_id: dict[str, set[tuple[str, tuple]]] = {}
        # The sync batch saves nodes from several threads. Re-entrant because computing an HFID can read this store.
        self._lock = threading.RLock()

    def count(self) -> int:
        return len(self._objs)

    def set(self, node: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync, key: str | None = None) -> None:
        with self._lock:
            existing_internal_id = self._uuids.get(node.id) if node.id else None
            existing = self._objs.get(existing_internal_id) if existing_internal_id else None
            previous_keys: list[str] = []
            previous_hfids: list[tuple[str, tuple]] = []
            if existing is not None and existing is not node:
                kept = self._resolve_existing(existing=existing, new=node)
                if kept is not existing:
                    previous_keys, previous_hfids = self._unindex(existing._internal_id)
                node = kept

            self._index(node=node, key=key, previous_keys=previous_keys, previous_hfids=previous_hfids)

    def _resolve_existing(
        self,
        existing: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync,  # noqa: ARG002
        new: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync,
    ) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync:
        """Return the node to keep when the store already holds another object with the same id.

        The newest copy replaces the previous one, so fields that only the previous copy holds are lost.
        This is to be reworked to merge ``new`` into ``existing`` and keep ``existing``, so that a later
        query returning fewer fields does not drop attributes or relationships fetched earlier.
        """
        return new

    def _index(
        self,
        node: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync,
        key: str | None = None,
        previous_keys: Iterable[str] = (),
        previous_hfids: Iterable[tuple[str, tuple]] = (),
    ) -> None:
        internal_id = node._internal_id
        self._objs[internal_id] = node

        keys = [*previous_keys, key] if key else previous_keys
        for node_key in keys:
            self._keys[node_key] = internal_id
            self._keys_by_internal_id.setdefault(internal_id, set()).add(node_key)

        if node.id:
            self._uuids[node.id] = internal_id

        if hfid := node.get_human_friendly_id():
            hfid_entries: Iterable[tuple[str, tuple]] = [(kind, tuple(hfid)) for kind in node.get_all_kinds()]
        else:
            # A copy without a HFID, e.g. from a query with `only`, stays reachable by the previous HFID.
            hfid_entries = previous_hfids
        for kind, hfid_key in hfid_entries:
            self._hfids.setdefault(kind, {})[hfid_key] = internal_id
            self._hfids_by_internal_id.setdefault(internal_id, set()).add((kind, hfid_key))

    def _unindex(self, internal_id: str) -> tuple[list[str], list[tuple[str, tuple]]]:
        """Remove a node and the index entries that point to it, and return the keys and HFIDs that pointed to it."""
        node = self._objs.pop(internal_id, None)
        keys = [key for key in self._keys_by_internal_id.pop(internal_id, ()) if self._keys.get(key) == internal_id]
        hfids = [
            (kind, hfid)
            for kind, hfid in self._hfids_by_internal_id.pop(internal_id, ())
            if self._hfids.get(kind, {}).get(hfid) == internal_id
        ]

        if node is not None and node.id and self._uuids.get(node.id) == internal_id:
            del self._uuids[node.id]
        for key in keys:
            del self._keys[key]
        for kind, hfid in hfids:
            del self._hfids[kind][hfid]
        return keys, hfids

    def get(
        self,
        key: str | list[str],
        kind: type[SchemaType | SchemaTypeSync] | str | None = None,
        raise_when_missing: bool = True,
    ) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync | None:
        with self._lock:
            return self._get(key=key, kind=kind, raise_when_missing=raise_when_missing)

    def _get(
        self,
        key: str | list[str],
        kind: type[SchemaType | SchemaTypeSync] | str | None = None,
        raise_when_missing: bool = True,
    ) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync | None:
        found_invalid = False

        kind_name = get_schema_name(schema=kind)

        if isinstance(key, list):
            try:
                return self._get_by_hfid(key, kind=kind_name)
            except NodeNotFoundError:
                pass

        elif isinstance(key, str):
            try:
                return self._get_by_internal_id(key, kind=kind_name)
            except NodeInvalidError:
                found_invalid = True
            except NodeNotFoundError:
                pass

            try:
                return self._get_by_id(key, kind=kind_name)
            except NodeInvalidError:
                found_invalid = True
            except NodeNotFoundError:
                pass

            try:
                return self._get_by_key(key, kind=kind_name)
            except NodeInvalidError:
                found_invalid = True
            except NodeNotFoundError:
                pass

            try:
                return self._get_by_hfid(key, kind=kind_name)
            except NodeNotFoundError:
                pass

        if not raise_when_missing:
            return None

        if kind and found_invalid:
            raise NodeInvalidError(
                identifier={"key": [key] if isinstance(key, str) else key},
                message=f"Found a node of a different kind instead of {kind} for key {key!r} in the store ({self.branch_name})",
            )

        raise NodeNotFoundError(
            identifier={"key": [key] if isinstance(key, str) else key},
            message=f"Unable to find the node {key!r} in the store ({self.branch_name})",
        )

    def _get_by_internal_id(
        self, internal_id: str, kind: str | None = None
    ) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync:
        if internal_id not in self._objs:
            raise NodeNotFoundError(
                identifier={"internal_id": [internal_id]},
                message=f"Unable to find the node {internal_id!r} in the store ({self.branch_name})",
            )

        node = self._objs[internal_id]
        if kind and kind not in node.get_all_kinds():
            raise NodeInvalidError(
                node_type=kind,
                identifier={"internal_id": [internal_id]},
                message=f"Found a node of kind {node.get_kind()} instead of {kind} for internal_id {internal_id!r} in the store ({self.branch_name})",
            )

        return node

    def _get_by_key(
        self, key: str, kind: str | None = None
    ) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync:
        if key not in self._keys:
            raise NodeNotFoundError(
                identifier={"key": [key]},
                message=f"Unable to find the node {key!r} in the store ({self.branch_name})",
            )

        node = self._get_by_internal_id(self._keys[key])

        if kind and node.get_kind() != kind:
            raise NodeInvalidError(
                node_type=kind,
                identifier={"key": [key]},
                message=f"Found a node of kind {node.get_kind()} instead of {kind} for key {key!r} in the store ({self.branch_name})",
            )

        return node

    def _get_by_id(self, id: str, kind: str | None = None) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync:
        if id not in self._uuids:
            raise NodeNotFoundError(
                identifier={"id": [id]},
                message=f"Unable to find the node {id!r} in the store ({self.branch_name})",
            )

        node = self._get_by_internal_id(self._uuids[id])
        if kind and kind not in node.get_all_kinds():
            raise NodeInvalidError(
                node_type=kind,
                identifier={"id": [id]},
                message=f"Found a node of kind {node.get_kind()} instead of {kind} for id {id!r} in the store ({self.branch_name})",
            )

        return node

    def _get_by_hfid(
        self, hfid: str | list[str], kind: str | None = None
    ) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync:
        if not kind or (kind and isinstance(hfid, str) and hfid.startswith(kind)):
            node_kind, node_hfid = parse_human_friendly_id(hfid)
        else:
            node_kind = kind
            node_hfid = [hfid] if isinstance(hfid, str) else hfid

        exception_to_raise_if_not_found = NodeNotFoundError(
            node_type=node_kind,
            identifier={"hfid": node_hfid},
            message=f"Unable to find the node {hfid!r} in the store ({self.branch_name})",
        )

        if node_kind not in self._hfids:
            raise exception_to_raise_if_not_found

        if tuple(node_hfid) not in self._hfids[node_kind]:
            raise exception_to_raise_if_not_found

        node = self._objs.get(self._hfids[node_kind][tuple(node_hfid)])
        if node is None:
            raise exception_to_raise_if_not_found
        return node


class NodeStoreBase:
    """Internal Store for InfrahubNode objects.

    Often while creating a lot of new objects,
    we need to save them in order to reuse them later to associate them with another node for example.
    """

    def __init__(self, default_branch: str | None = None) -> None:
        self._branches: dict[str, NodeStoreBranch] = {}

        if default_branch is None:
            default_branch = "main"
            warnings.warn(
                "Using a store without specifying a default branch is deprecated and will be removed in a future version. "
                "Please explicitly specify a branch name.",
                DeprecationWarning,
                stacklevel=2,
            )

        self._default_branch = default_branch

    def _get_branch(self, branch: str | None = None) -> str:
        return branch or self._default_branch

    def _set(
        self,
        node: InfrahubNode | InfrahubNodeSync | SchemaType | SchemaTypeSync,
        key: str | None = None,
        branch: str | None = None,
    ) -> None:
        branch = self._get_branch(branch or node.get_branch())
        store_branch = self._branches.get(branch) or self._branches.setdefault(branch, NodeStoreBranch(name=branch))
        store_branch.set(node=node, key=key)

    def _get(  # type: ignore[no-untyped-def]
        self,
        key: str | list[str],
        kind: type[SchemaType | SchemaTypeSync] | str | None = None,
        raise_when_missing: bool = True,
        branch: str | None = None,
    ):
        branch = self._get_branch(branch)
        store_branch = self._branches.get(branch) or NodeStoreBranch(name=branch)

        return store_branch.get(key=key, kind=kind, raise_when_missing=raise_when_missing)

    def count(self, branch: str | None = None) -> int:
        branch = self._get_branch(branch)

        if branch not in self._branches:
            return 0

        return self._branches[branch].count()


class NodeStore(NodeStoreBase):
    @overload
    def get(
        self,
        key: str | list[str],
        kind: type[SchemaType],
        raise_when_missing: Literal[True] = True,
        branch: str | None = ...,
    ) -> SchemaType: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: type[SchemaType],
        raise_when_missing: Literal[False] = False,
        branch: str | None = ...,
    ) -> SchemaType | None: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: type[SchemaType],
        raise_when_missing: bool = ...,
        branch: str | None = ...,
    ) -> SchemaType: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: str | None = ...,
        raise_when_missing: Literal[True] = True,
        branch: str | None = ...,
    ) -> InfrahubNode: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: str | None = ...,
        raise_when_missing: Literal[False] = False,
        branch: str | None = ...,
    ) -> InfrahubNode | None: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: str | None = ...,
        raise_when_missing: bool = ...,
        branch: str | None = ...,
    ) -> InfrahubNode: ...

    def get(
        self,
        key: str | list[str],
        kind: str | type[SchemaType] | None = None,
        raise_when_missing: bool = True,
        branch: str | None = None,
    ) -> InfrahubNode | SchemaType | None:
        return self._get(key=key, kind=kind, raise_when_missing=raise_when_missing, branch=branch)

    @overload
    def get_by_hfid(
        self, key: str | list[str], raise_when_missing: Literal[True] = True, branch: str | None = ...
    ) -> InfrahubNode: ...

    @overload
    def get_by_hfid(
        self, key: str | list[str], raise_when_missing: Literal[False] = False, branch: str | None = ...
    ) -> InfrahubNode | None: ...

    def get_by_hfid(
        self, key: str | list[str], raise_when_missing: bool = True, branch: str | None = None
    ) -> InfrahubNode | None:
        warnings.warn(
            "get_by_hfid() is deprecated and will be removed in a future version. Use get() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get(key=key, raise_when_missing=raise_when_missing, branch=branch)

    def set(self, node: InfrahubNode | SchemaType, key: str | None = None, branch: str | None = None) -> None:
        return self._set(node=node, key=key, branch=branch)


class NodeStoreSync(NodeStoreBase):
    @overload
    def get(
        self,
        key: str | list[str],
        kind: type[SchemaTypeSync],
        raise_when_missing: Literal[True] = True,
        branch: str | None = ...,
    ) -> SchemaTypeSync: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: type[SchemaTypeSync],
        raise_when_missing: Literal[False] = False,
        branch: str | None = ...,
    ) -> SchemaTypeSync | None: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: type[SchemaTypeSync],
        raise_when_missing: bool = ...,
        branch: str | None = ...,
    ) -> SchemaTypeSync: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: str | None = ...,
        raise_when_missing: Literal[True] = True,
        branch: str | None = ...,
    ) -> InfrahubNodeSync: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: str | None = ...,
        raise_when_missing: Literal[False] = False,
        branch: str | None = ...,
    ) -> InfrahubNodeSync | None: ...

    @overload
    def get(
        self,
        key: str | list[str],
        kind: str | None = ...,
        raise_when_missing: bool = ...,
        branch: str | None = ...,
    ) -> InfrahubNodeSync: ...

    def get(
        self,
        key: str | list[str],
        kind: str | type[SchemaTypeSync] | None = None,
        raise_when_missing: bool = True,
        branch: str | None = None,
    ) -> InfrahubNodeSync | SchemaTypeSync | None:
        return self._get(key=key, kind=kind, raise_when_missing=raise_when_missing, branch=branch)

    @overload
    def get_by_hfid(
        self, key: str | list[str], raise_when_missing: Literal[True] = True, branch: str | None = ...
    ) -> InfrahubNodeSync: ...

    @overload
    def get_by_hfid(
        self, key: str | list[str], raise_when_missing: Literal[False] = False, branch: str | None = ...
    ) -> InfrahubNodeSync | None: ...

    def get_by_hfid(
        self, key: str | list[str], raise_when_missing: bool = True, branch: str | None = None
    ) -> InfrahubNodeSync | None:
        warnings.warn(
            "get_by_hfid() is deprecated and will be removed in a future version. Use get() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get(key=key, raise_when_missing=raise_when_missing, branch=branch)

    def set(self, node: InfrahubNodeSync | SchemaTypeSync, key: str | None = None, branch: str | None = None) -> None:
        return self._set(node=node, key=key, branch=branch)
