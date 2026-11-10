from __future__ import annotations

import inspect
import warnings
from typing import TYPE_CHECKING, Literal, overload

from infrahub_sdk.protocols_base import CoreNodeBase

from .exceptions import NodeInvalidError, NodeNotFoundError
from .node.parsers import parse_human_friendly_id

if TYPE_CHECKING:
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

    def count(self) -> int:
        return len(self._objs)

    def set(self, node: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync, key: str | None = None) -> None:
        existing_internal_id = self._uuids.get(node.id) if node.id else None
        if existing_internal_id and existing_internal_id != node._internal_id:
            existing = self._objs[existing_internal_id]
            kept = self._resolve_existing(existing=existing, new=node)
            if kept is not existing:
                for previous_key in self._unindex(existing_internal_id):
                    self._keys[previous_key] = kept._internal_id
            node = kept

        self._index(node=node, key=key)

    def _resolve_existing(
        self,
        existing: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync,
        new: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync,
    ) -> InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync:
        """Return the node to keep when the store already holds another object with the same id."""
        return new

    def _index(self, node: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync, key: str | None = None) -> None:
        self._objs[node._internal_id] = node

        if key:
            self._keys[key] = node._internal_id

        if node.id:
            self._uuids[node.id] = node._internal_id

        if hfid := node.get_human_friendly_id():
            for kind in node.get_all_kinds():
                if kind not in self._hfids:
                    self._hfids[kind] = {}
                self._hfids[kind][tuple(hfid)] = node._internal_id

    def _unindex(self, internal_id: str) -> list[str]:
        """Remove a node and the index entries that point to it, and return the keys that pointed to it."""
        node = self._objs.pop(internal_id, None)
        if node is None:
            return []

        if node.id and self._uuids.get(node.id) == internal_id:
            del self._uuids[node.id]

        if hfid := node.get_human_friendly_id():
            for kind in node.get_all_kinds():
                if self._hfids.get(kind, {}).get(tuple(hfid)) == internal_id:
                    del self._hfids[kind][tuple(hfid)]

        keys = [key for key, value in self._keys.items() if value == internal_id]
        for key in keys:
            del self._keys[key]
        return keys

    def _remove(self, node: InfrahubNode | InfrahubNodeSync | CoreNode | CoreNodeSync) -> None:
        """Remove the node, and any other object stored for the same id."""
        self._unindex(node._internal_id)
        if node.id and (internal_id := self._uuids.get(node.id)):
            self._unindex(internal_id)

    def get(
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

        internal_id = self._hfids[node_kind][tuple(node_hfid)]
        return self._objs[internal_id]


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

        if branch not in self._branches:
            self._branches[branch] = NodeStoreBranch(name=branch)

        self._branches[branch].set(node=node, key=key)

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

    def _remove(
        self, node: InfrahubNode | InfrahubNodeSync | SchemaType | SchemaTypeSync, branch: str | None = None
    ) -> None:
        branch = self._get_branch(branch or node.get_branch())
        if branch in self._branches:
            self._branches[branch]._remove(node=node)

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
