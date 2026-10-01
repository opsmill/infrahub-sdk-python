from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .constants import InfrahubClientMode
from .exceptions import GraphQLError, NodeNotFoundError, TrackingGroupCleanupError
from .utils import dict_hash

if TYPE_CHECKING:
    from .client import InfrahubClient, InfrahubClientSync
    from .node import InfrahubNode, InfrahubNodeSync, RelatedNodeBase
    from .schema import MainSchemaTypesAPI

ALREADY_DELETED_ERROR = "Unable to find the node"


@dataclass
class ReapResult:
    """How far a reap of the unused members got.

    Attributes:
        refused: The id of each member the server refused to delete, mapped to its reason.
        unattempted: The ids the reap never got to, because something unrelated to any
            member stopped it.
        error: The failure that stopped the reap, if one did.

    """

    refused: dict[str, str] = field(default_factory=dict)
    unattempted: list[str] = field(default_factory=list)
    error: Exception | None = None

    @property
    def retained_member_ids(self) -> list[str]:
        """The members that must stay in the group so a later run retries them."""
        return list(self.refused) + self.unattempted


class InfrahubGroupContextBase:
    """Base class for InfrahubGroupContext and InfrahubGroupContextSync."""

    def __init__(self) -> None:
        self.related_node_ids: list[str] = []
        self.related_group_ids: list[str] = []
        self.unused_member_ids: list[str] | None = None
        self.previous_members: Sequence[RelatedNodeBase] | None = None
        self.previous_children: list[RelatedNodeBase] | None = None
        self.identifier: str | None = None
        self.params: dict[str, str] = {}
        self.delete_unused_nodes: bool = False
        self.group_type: str = "CoreStandardGroup"
        self.group_params: dict[str, Any] = {}
        self.branch: str | None = None

    def set_properties(
        self,
        identifier: str,
        params: dict[str, str] | None = None,
        delete_unused_nodes: bool = False,
        group_type: str | None = None,
        group_params: dict[str, Any] | None = None,
        branch: str | None = None,
    ) -> None:
        """Setter method to set the values of identifier and params.

        Args:
            identifier: The new value for the identifier.
            params: A dictionary with new values for the params.

        """
        self.identifier = identifier
        self.params = params or {}
        self.delete_unused_nodes = delete_unused_nodes
        self.group_type = group_type or self.group_type
        self.group_params = group_params or {}
        self.branch = branch

    def _get_members(self) -> list[str]:
        """The ids of everything this run tracked."""
        return self.related_group_ids + self.related_node_ids

    def _set_unused_member_ids(self, previous_member_ids: list[str], members: list[str]) -> None:
        self.unused_member_ids = list(set(previous_member_ids) - set(members))

    def _reap_candidates(self) -> list[tuple[str, str]]:
        """The (kind, id) of every previous member this run no longer uses."""
        if not self.previous_members or not self.unused_member_ids:
            return []

        unused_member_ids = set(self.unused_member_ids)
        candidates: list[tuple[str, str]] = []
        for member in self.previous_members:
            if member.id is None or member.typename is None or member.id not in unused_member_ids:
                continue
            candidates.append((member.typename, member.id))

        return candidates

    @staticmethod
    def _error_messages(exc: GraphQLError) -> list[str]:
        """The server-side message of each error, without the query that triggered them."""
        return [
            str(error.get("message", error)) if isinstance(error, dict) else str(error) for error in exc.errors or []
        ]

    @classmethod
    def _is_already_deleted(cls, exc: GraphQLError) -> bool:
        """Whether the server reported nothing but missing nodes.

        A member removed by the cascade delete of another member is not a failure, but a
        response that also carries a genuine refusal must not be tolerated.
        """
        messages = cls._error_messages(exc)
        return bool(messages) and all(ALREADY_DELETED_ERROR in message for message in messages)

    @classmethod
    def _failure_reason(cls, exc: Exception) -> str:
        if isinstance(exc, GraphQLError) and (messages := cls._error_messages(exc)):
            return "; ".join(messages)
        return str(exc)

    def _get_params_as_str(self) -> str:
        """Convert the params in dict format, into a string."""
        params_as_str: list[str] = []
        for key, value in self.params.items():
            params_as_str.append(f"{key}: {value!s}")
        return ", ".join(params_as_str)

    def _generate_group_name(self, suffix: str | None = None) -> str:
        group_name = self.identifier or "sdk"

        if suffix:
            group_name += f"-{suffix}"

        if self.params:
            group_name += f"-{dict_hash(self.params)}"

        return group_name

    def _generate_group_description(self, schema: MainSchemaTypesAPI) -> str:
        """Generate the description of the group from the params.

        The result is truncated so it is not longer than the maximum length of the description field.
        """
        if not self.params:
            return ""

        description_str = self._get_params_as_str()
        description = schema.get_attribute(name="description")
        if description and description.max_length and len(description_str) > description.max_length:
            length = description.max_length - 5
            return description_str[:length] + "..."

        return description_str


class InfrahubGroupContext(InfrahubGroupContextBase):
    """Represents a Infrahub GroupContext in an asynchronous context."""

    def __init__(self, client: InfrahubClient) -> None:
        super().__init__()
        self.client = client

    async def get_group(self, store_peers: bool = False) -> InfrahubNode | None:
        group_name = self._generate_group_name()
        try:
            group = await self.client.get(
                kind=self.group_type, name__value=group_name, include=["members"], branch=self.branch
            )
        except NodeNotFoundError:
            return None

        if not store_peers:
            return group

        self.previous_members = group._get_relationship_many(name="members").peers
        return group

    async def delete_unused(self) -> ReapResult:
        """Delete the members that this run no longer uses.

        A refusal by the server is a fact about the member, so it is recorded against it
        and the remaining candidates are still attempted. Any other failure is not a fact
        about the member being deleted, so it stops the reap and is returned as itself
        rather than blamed on every member in turn.

        Nothing is raised here: the caller has to record this run's membership before
        reporting the failure, or the nodes it created are left in no group at all.

        Returns:
            How far the reap got, and what must stay in the group.

        """
        result = ReapResult()
        candidates = self._reap_candidates()

        for position, (kind, member_id) in enumerate(candidates):
            try:
                await self.client.delete(kind=kind, id=member_id, branch=self.branch)
            except GraphQLError as exc:
                if self._is_already_deleted(exc):
                    continue
                result.refused[member_id] = self._failure_reason(exc)
            except Exception as exc:
                result.error = exc
                result.unattempted = [candidate_id for _, candidate_id in candidates[position:]]
                break

        return result

    async def add_related_nodes(self, ids: list[str], update_group_context: bool | None = None) -> None:
        """Add related Nodes IDs to the context.

        Args:
            ids (list[str]): List of node IDs to be added.
            update_group_context (Optional[bool], optional): Flag to control whether to update the group context.

        """
        if update_group_context is not False and (
            self.client.mode == InfrahubClientMode.TRACKING or self.client.update_group_context or update_group_context
        ):
            self.related_node_ids.extend(ids)

    async def add_related_groups(self, ids: list[str], update_group_context: bool | None = None) -> None:
        """Add related Groups IDs to the context.

        Args:
            ids (list[str]): List of group IDs to be added.
            update_group_context (Optional[bool], optional): Flag to control whether to update the group context.

        """
        if update_group_context is not False and (
            self.client.mode == InfrahubClientMode.TRACKING or self.client.update_group_context or update_group_context
        ):
            self.related_group_ids.extend(ids)

    async def update_group(self) -> None:
        """Create or update (using upsert) a CoreStandardGroup to store all the Nodes and Groups used during an execution.

        Raises:
            TrackingGroupCleanupError: When the server refused to delete one or more unused members.
            Exception: Whatever stopped the reap, when it was stopped by something other than a refusal.

        """
        members = self._get_members()

        existing_group = None
        if self.delete_unused_nodes:
            existing_group = await self.get_group(store_peers=True)

        previous_member_ids: list[str] = []
        if existing_group:
            previous_member_ids = existing_group._get_relationship_many(name="members").peer_ids
            self._set_unused_member_ids(previous_member_ids=previous_member_ids, members=members)

        reap = await self.delete_unused()

        # A run that tracked nothing and has no members left to reconcile must neither
        # create an empty group nor re-save one that is already empty.
        if not members and not previous_member_ids:
            return

        group_name = self._generate_group_name()
        schema = await self.client.schema.get(kind=self.group_type)
        description = self._generate_group_description(schema=schema)

        # The group is written before any failure is reported: whatever went wrong, the
        # nodes this run created are only reachable later once they are recorded here.
        group = await self.client.create(
            kind=self.group_type,
            name=group_name,
            description=description,
            members=members + reap.retained_member_ids,
            branch=self.branch,
            **self.group_params,
        )
        await group.save(allow_upsert=True, update_group_context=False)

        if reap.error:
            raise reap.error
        if reap.refused:
            raise TrackingGroupCleanupError(failures=reap.refused)
        # TODO : create anoter "read" group. Could be based of the store items
        # Need to filters the store items inherited from CoreGroup to add them as children
        # Need to validate that it's UUIDas "key" if we want to implement other methods to store item


class InfrahubGroupContextSync(InfrahubGroupContextBase):
    """Represents a Infrahub GroupContext in an synchronous context."""

    def __init__(self, client: InfrahubClientSync) -> None:
        super().__init__()
        self.client = client

    def get_group(self, store_peers: bool = False) -> InfrahubNodeSync | None:
        group_name = self._generate_group_name()
        try:
            group = self.client.get(
                kind=self.group_type, name__value=group_name, include=["members"], branch=self.branch
            )
        except NodeNotFoundError:
            return None

        if not store_peers:
            return group

        self.previous_members = group._get_relationship_many(name="members").peers
        return group

    def delete_unused(self) -> ReapResult:
        """Delete the members that this run no longer uses.

        A refusal by the server is a fact about the member, so it is recorded against it
        and the remaining candidates are still attempted. Any other failure is not a fact
        about the member being deleted, so it stops the reap and is returned as itself
        rather than blamed on every member in turn.

        Nothing is raised here: the caller has to record this run's membership before
        reporting the failure, or the nodes it created are left in no group at all.

        Returns:
            How far the reap got, and what must stay in the group.

        """
        result = ReapResult()
        candidates = self._reap_candidates()

        for position, (kind, member_id) in enumerate(candidates):
            try:
                self.client.delete(kind=kind, id=member_id, branch=self.branch)
            except GraphQLError as exc:
                if self._is_already_deleted(exc):
                    continue
                result.refused[member_id] = self._failure_reason(exc)
            except Exception as exc:
                result.error = exc
                result.unattempted = [candidate_id for _, candidate_id in candidates[position:]]
                break

        return result

    def add_related_nodes(self, ids: list[str], update_group_context: bool | None = None) -> None:
        """Add related Nodes IDs to the context.

        Args:
            ids (list[str]): List of node IDs to be added.
            update_group_context (Optional[bool], optional): Flag to control whether to update the group context.

        """
        if update_group_context is not False and (
            self.client.mode == InfrahubClientMode.TRACKING or self.client.update_group_context or update_group_context
        ):
            self.related_node_ids.extend(ids)

    def add_related_groups(self, ids: list[str], update_group_context: bool | None = None) -> None:
        """Add related Groups IDs to the context.

        Args:
            ids (list[str]): List of group IDs to be added.
            update_group_context (Optional[bool], optional): Flag to control whether to update the group context.

        """
        if update_group_context is not False and (
            self.client.mode == InfrahubClientMode.TRACKING or self.client.update_group_context or update_group_context
        ):
            self.related_group_ids.extend(ids)

    def update_group(self) -> None:
        """Create or update (using upsert) a CoreStandardGroup to store all the Nodes and Groups used during an execution.

        Raises:
            TrackingGroupCleanupError: When the server refused to delete one or more unused members.
            Exception: Whatever stopped the reap, when it was stopped by something other than a refusal.

        """
        members = self._get_members()

        existing_group = None
        if self.delete_unused_nodes:
            existing_group = self.get_group(store_peers=True)

        previous_member_ids: list[str] = []
        if existing_group:
            previous_member_ids = existing_group._get_relationship_many(name="members").peer_ids
            self._set_unused_member_ids(previous_member_ids=previous_member_ids, members=members)

        reap = self.delete_unused()

        # A run that tracked nothing and has no members left to reconcile must neither
        # create an empty group nor re-save one that is already empty.
        if not members and not previous_member_ids:
            return

        group_name = self._generate_group_name()
        schema = self.client.schema.get(kind=self.group_type)
        description = self._generate_group_description(schema=schema)

        # The group is written before any failure is reported: whatever went wrong, the
        # nodes this run created are only reachable later once they are recorded here.
        group = self.client.create(
            kind=self.group_type,
            name=group_name,
            description=description,
            members=members + reap.retained_member_ids,
            branch=self.branch,
            **self.group_params,
        )
        group.save(allow_upsert=True, update_group_context=False)

        if reap.error:
            raise reap.error
        if reap.refused:
            raise TrackingGroupCleanupError(failures=reap.refused)

        # TODO : create anoter "read" group. Could be based of the store items
        # Need to filters the store items inherited from CoreGroup to add them as children
        # Need to validate that it's UUIDas "key" if we want to implement other methods to store item
