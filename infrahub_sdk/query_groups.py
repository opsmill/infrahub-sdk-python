from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .constants import InfrahubClientMode
from .exceptions import GraphQLError, NodeNotFoundError, TrackingGroupCleanupError
from .utils import dict_hash

if TYPE_CHECKING:
    from .client import InfrahubClient, InfrahubClientSync
    from .node import InfrahubNode, InfrahubNodeSync, RelatedNodeBase
    from .schema import MainSchemaTypesAPI


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

    async def delete_unused(self) -> dict[str, str]:
        """Delete the members that this run no longer uses.

        Every candidate is attempted even when the server refuses some of them, so one
        refusal cannot leave the rest of the unused members behind. Only refusals are
        collected; any other failure propagates for the caller to handle.

        Returns:
            The id of each member the server refused to delete, mapped to the reason.

        """
        failures: dict[str, str] = {}
        if not self.previous_members or not self.unused_member_ids:
            return failures

        for member in self.previous_members:
            if member.id not in self.unused_member_ids or not member.typename:
                continue
            try:
                await self.client.delete(kind=member.typename, id=member.id, branch=self.branch)
            except GraphQLError as exc:
                if exc.message and "Unable to find the node" in exc.message:
                    # The node was already removed by the cascade delete of another node
                    continue
                failures[member.id] = exc.message or str(exc)

        return failures

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
            TrackingGroupCleanupError: When one or more unused members could not be deleted.

        """
        members: list[str] = self.related_group_ids + self.related_node_ids

        existing_group = None
        if self.delete_unused_nodes:
            existing_group = await self.get_group(store_peers=True)

        # A run that tracked nothing and has no group to reconcile must not create an empty one.
        if not members and existing_group is None:
            return

        failures: dict[str, str] = {}
        if existing_group:
            previous_member_ids: list[str] = existing_group._get_relationship_many(name="members").peer_ids
            self.unused_member_ids = list(set(previous_member_ids) - set(members))
            failures = await self.delete_unused()

            # An already-empty group that stays empty needs no upsert.
            if not members and not previous_member_ids:
                return

        group_name = self._generate_group_name()
        schema = await self.client.schema.get(kind=self.group_type)
        description = self._generate_group_description(schema=schema)

        # Members that could not be deleted stay in the group so a later run retries them.
        group = await self.client.create(
            kind=self.group_type,
            name=group_name,
            description=description,
            members=members + list(failures),
            branch=self.branch,
            **self.group_params,
        )
        await group.save(allow_upsert=True, update_group_context=False)

        if failures:
            raise TrackingGroupCleanupError(failures=failures)
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

    def delete_unused(self) -> dict[str, str]:
        """Delete the members that this run no longer uses.

        Every candidate is attempted even when the server refuses some of them, so one
        refusal cannot leave the rest of the unused members behind. Only refusals are
        collected; any other failure propagates for the caller to handle.

        Returns:
            The id of each member the server refused to delete, mapped to the reason.

        """
        failures: dict[str, str] = {}
        if not self.previous_members or not self.unused_member_ids:
            return failures

        for member in self.previous_members:
            if member.id not in self.unused_member_ids or not member.typename:
                continue
            try:
                self.client.delete(kind=member.typename, id=member.id, branch=self.branch)
            except GraphQLError as exc:
                if exc.message and "Unable to find the node" in exc.message:
                    # The node was already removed by the cascade delete of another node
                    continue
                failures[member.id] = exc.message or str(exc)

        return failures

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
            TrackingGroupCleanupError: When one or more unused members could not be deleted.

        """
        members: list[str] = self.related_node_ids + self.related_group_ids

        existing_group = None
        if self.delete_unused_nodes:
            existing_group = self.get_group(store_peers=True)

        # A run that tracked nothing and has no group to reconcile must not create an empty one.
        if not members and existing_group is None:
            return

        failures: dict[str, str] = {}
        if existing_group:
            previous_member_ids: list[str] = existing_group._get_relationship_many(name="members").peer_ids
            self.unused_member_ids = list(set(previous_member_ids) - set(members))
            failures = self.delete_unused()

            # An already-empty group that stays empty needs no upsert.
            if not members and not previous_member_ids:
                return

        group_name = self._generate_group_name()
        schema = self.client.schema.get(kind=self.group_type)
        description = self._generate_group_description(schema=schema)

        # Members that could not be deleted stay in the group so a later run retries them.
        group = self.client.create(
            kind=self.group_type,
            name=group_name,
            description=description,
            members=members + list(failures),
            branch=self.branch,
            **self.group_params,
        )
        group.save(allow_upsert=True, update_group_context=False)

        if failures:
            raise TrackingGroupCleanupError(failures=failures)

        # TODO : create anoter "read" group. Could be based of the store items
        # Need to filters the store items inherited from CoreGroup to add them as children
        # Need to validate that it's UUIDas "key" if we want to implement other methods to store item
