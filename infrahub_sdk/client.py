from __future__ import annotations

import asyncio
import copy
import logging
import time
from collections.abc import Coroutine, MutableMapping
from functools import wraps
from time import sleep
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    TypedDict,
    TypeVar,
    overload,
)
from urllib.parse import urlencode

import httpx
import ujson
from typing_extensions import Self

from .batch import InfrahubBatch, InfrahubBatchSync
from .branch import (
    BranchData,
    InfrahubBranchManager,
    InfrahubBranchManagerSync,
)
from .config import Config
from .constants import InfrahubClientMode
from .data import RepositoryBranchInfo, RepositoryData
from .diff import NodeDiff, diff_tree_node_to_node_diff, get_diff_summary_query
from .exceptions import (
    AuthenticationError,
    Error,
    GraphQLError,
    NodeNotFoundError,
    ServerNotReachableError,
    ServerNotResponsiveError,
    URLNotFoundError,
)
from .graphql import Mutation, Query
from .node import (
    InfrahubNode,
    InfrahubNodeSync,
)
from .object_store import ObjectStore, ObjectStoreSync
from .protocols_base import CoreNode, CoreNodeSync
from .queries import QUERY_USER, get_commit_update_mutation
from .query_groups import InfrahubGroupContext, InfrahubGroupContextSync
from .schema import InfrahubSchema, InfrahubSchemaSync, NodeSchemaAPI
from .store import NodeStore, NodeStoreSync
from .task.manager import InfrahubTaskManager, InfrahubTaskManagerSync
from .timestamp import Timestamp
from .types import AsyncRequester, HTTPMethod, Order, SyncRequester
from .utils import decode_json, get_user_permissions, is_valid_uuid

if TYPE_CHECKING:
    from types import TracebackType

    from .context import RequestContext


SchemaType = TypeVar("SchemaType", bound=CoreNode)
SchemaTypeSync = TypeVar("SchemaTypeSync", bound=CoreNodeSync)


class ProcessRelationsNode(TypedDict):
    nodes: list[InfrahubNode]
    related_nodes: list[InfrahubNode]


class ProcessRelationsNodeSync(TypedDict):
    """A dictionary type for results of processing nodes and their relationships (sync version)."""
    nodes: list[InfrahubNodeSync]
    related_nodes: list[InfrahubNodeSync]


def handle_relogin(func: Callable[..., Coroutine[Any, Any, httpx.Response]]):  # type: ignore[no-untyped-def]
    """
    Decorator for InfrahubClient methods to handle automatic re-login on expired signature errors.

    If a 401 error with "Expired Signature" message is received, it attempts to
    re-login using `client.login(refresh=True)` and then retries the original call.

    Args:
        func: The asynchronous client method to wrap.

    Returns:
        The wrapped function.
    """
    @wraps(func)
    async def wrapper(client: InfrahubClient, *args: Any, **kwargs: Any) -> httpx.Response:
        response = await func(client, *args, **kwargs)
        if response.status_code == 401:
            errors = response.json().get("errors", [])
            if "Expired Signature" in [error.get("message") for error in errors]:
                await client.login(refresh=True)
                return await func(client, *args, **kwargs)
        return response

    return wrapper


def handle_relogin_sync(func: Callable[..., httpx.Response]):  # type: ignore[no-untyped-def]
    """
    Decorator for InfrahubClientSync methods to handle automatic re-login on expired signature errors.

    If a 401 error with "Expired Signature" message is received, it attempts to
    re-login using `client.login(refresh=True)` and then retries the original call.

    Args:
        func: The synchronous client method to wrap.

    Returns:
        The wrapped function.
    """
    @wraps(func)
    def wrapper(client: InfrahubClientSync, *args: Any, **kwargs: Any) -> httpx.Response:
        response = func(client, *args, **kwargs)
        if response.status_code == 401:
            errors = response.json().get("errors", [])
            if "Expired Signature" in [error.get("message") for error in errors]:
                client.login(refresh=True)
                return func(client, *args, **kwargs)
        return response

    return wrapper


class BaseClient:
    """Base class for InfrahubClient and InfrahubClientSync"""

    def __init__(
        self,
        address: str = "",
        config: Config | dict[str, Any] | None = None,
    ):
        """
        Initializes the BaseClient.

        Args:
            address: The Infrahub server address. Overrides address in config if provided.
            config: A Config object or a dictionary to initialize the client's configuration.
                    If None, a default Config object will be created.
        """
        self.client = None
        self.headers = {"content-type": "application/json"}
        self.access_token: str = ""
        self.refresh_token: str = ""
        if isinstance(config, Config):
            self.config = config
        else:
            config = config or {}
            self.config = Config(**config)

        self.default_branch = self.config.default_infrahub_branch
        self.default_timeout = self.config.timeout
        self.config.address = address or self.config.address
        self.insert_tracker = self.config.insert_tracker
        self.log = self.config.logger or logging.getLogger("infrahub_sdk")
        self.address = self.config.address
        self.mode = self.config.mode
        self.pagination_size = self.config.pagination_size
        self.retry_delay = self.config.retry_delay
        self.retry_on_failure = self.config.retry_on_failure

        if self.config.api_token:
            self.headers["X-INFRAHUB-KEY"] = self.config.api_token

        self.max_concurrent_execution = self.config.max_concurrent_execution

        self.update_group_context = self.config.update_group_context
        self.identifier = self.config.identifier
        self.group_context: InfrahubGroupContext | InfrahubGroupContextSync
        self._initialize()
        self._request_context: RequestContext | None = None

    def _initialize(self) -> None:
        """
        Sets the version-specific properties for the client (async or sync).
        To be implemented by subclasses.
        """

    def _record(self, response: httpx.Response) -> None:
        """
        Records the HTTP response using the custom recorder if configured.

        Args:
            response: The httpx.Response object to record.
        """
        self.config.custom_recorder.record(response)

    def _echo(self, url: str, query: str, variables: dict | None = None) -> None:
        """
        Prints the GraphQL query details to stdout if echo_graphql_queries is enabled in config.

        Args:
            url: The GraphQL endpoint URL.
            query: The GraphQL query string.
            variables: Optional dictionary of variables for the query.
        """
        if self.config.echo_graphql_queries:
            print(f"URL: {url}")
            print(f"QUERY:\n{query}")
            if variables:
                print(f"VARIABLES:\n{ujson.dumps(variables, indent=4)}\n")

    @property
    def request_context(self) -> RequestContext | None:
        """The current request context, if any."""
        return self._request_context

    @request_context.setter
    def request_context(self, request_context: RequestContext) -> None:
        """
        Sets the request context for the client.

        Args:
            request_context: The RequestContext object.
        """
        self._request_context = request_context

    def start_tracking(
        self,
        identifier: str | None = None,
        params: dict[str, Any] | None = None,
        delete_unused_nodes: bool = False,
        group_type: str | None = None,
    ) -> Self:
        """
        Switches the client to TRACKING mode and configures the group context.

        In TRACKING mode, changes made via the client can be associated with a group,
        allowing for features like automatic cleanup of unused nodes.

        Args:
            identifier: A unique identifier for the tracking group. Defaults to `self.identifier` or "python-sdk".
            params: Optional parameters to associate with the tracking group.
            delete_unused_nodes: If True, nodes associated with this group that are no longer
                                 referenced might be deleted when the context ends.
            group_type: An optional type for the group.

        Returns:
            The client instance (self).
        """
        self.mode = InfrahubClientMode.TRACKING
        identifier = identifier or self.identifier or "python-sdk"
        self.set_context_properties(
            identifier=identifier, params=params, delete_unused_nodes=delete_unused_nodes, group_type=group_type
        )
        return self

    def set_context_properties(
        self,
        identifier: str,
        params: dict[str, str] | None = None,
        delete_unused_nodes: bool = True,
        reset: bool = True,
        group_type: str | None = None,
    ) -> None:
        """
        Sets the properties for the group context used in TRACKING mode.

        Args:
            identifier: A unique identifier for the tracking group.
            params: Optional parameters to associate with the tracking group.
            delete_unused_nodes: If True, nodes associated with this group that are no longer
                                 referenced might be deleted when the context ends.
            reset: If True (default), initializes a new group context.
            group_type: An optional type for the group.
        """
        if reset:
            if isinstance(self, InfrahubClient):
                self.group_context = InfrahubGroupContext(self)
            elif isinstance(self, InfrahubClientSync):
                self.group_context = InfrahubGroupContextSync(self)
        self.group_context.set_properties(
            identifier=identifier, params=params, delete_unused_nodes=delete_unused_nodes, group_type=group_type
        )

    def _graphql_url(
        self,
        branch_name: str | None = None,
        at: str | Timestamp | None = None,
    ) -> str:
        """
        Constructs the GraphQL API URL for a given branch and optional timestamp.

        Args:
            branch_name: The name of the branch. If None, the base GraphQL URL is returned.
            at: An optional timestamp or ISO 8601 string to query at a specific point in time.

        Returns:
            The constructed GraphQL URL.
        """
        url = f"{self.config.address}/graphql"
        if branch_name:
            url += f"/{branch_name}"

        url_params = {}
        if at:
            at = Timestamp(at)
            url_params["at"] = at.to_string()
            url += "?" + urlencode(url_params)

        return url

    def _build_ip_address_allocation_query(
        self,
        resource_pool_id: str,
        identifier: str | None = None,
        prefix_length: int | None = None,
        address_type: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Mutation:
        """
        Builds a GraphQL mutation for allocating an IP address from a resource pool.

        Args:
            resource_pool_id: The ID of the CoreIPAddressPool.
            identifier: Optional identifier for idempotent allocation.
            prefix_length: Optional prefix length for the allocated address.
            address_type: Optional type/kind of the IP address to allocate.
            data: Optional dictionary of additional data to set on the allocated IP address.

        Returns:
            A Mutation object for the IP address allocation.
        """
        input_data: dict[str, Any] = {"id": resource_pool_id}

        if identifier:
            input_data["identifier"] = identifier
        if prefix_length:
            input_data["prefix_length"] = prefix_length
        if address_type:
            input_data["prefix_type"] = address_type
        if data:
            input_data["data"] = data

        return Mutation(
            name="AllocateIPAddress",
            mutation="IPAddressPoolGetResource",
            query={"ok": None, "node": {"id": None, "kind": None, "identifier": None, "display_label": None}},
            input_data={"data": input_data},
        )

    def _build_ip_prefix_allocation_query(
        self,
        resource_pool_id: str,
        identifier: str | None = None,
        prefix_length: int | None = None,
        member_type: str | None = None,
        prefix_type: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Mutation:
        """
        Builds a GraphQL mutation for allocating an IP prefix from a resource pool.

        Args:
            resource_pool_id: The ID of the CoreIPPrefixPool.
            identifier: Optional identifier for idempotent allocation.
            prefix_length: Optional length of the prefix to allocate.
            member_type: Optional member type for the prefix ("prefix" or "address").
            prefix_type: Optional type/kind of the IP prefix to allocate.
            data: Optional dictionary of additional data to set on the allocated IP prefix.

        Returns:
            A Mutation object for the IP prefix allocation.

        Raises:
            ValueError: If `member_type` is provided and is not "prefix" or "address".
        """
        input_data: dict[str, Any] = {"id": resource_pool_id}

        if identifier:
            input_data["identifier"] = identifier
        if prefix_length:
            input_data["prefix_length"] = prefix_length
        if member_type:
            if member_type not in ("prefix", "address"):
                raise ValueError("member_type possible values are 'prefix' or 'address'")
            input_data["member_type"] = member_type
        if prefix_type:
            input_data["prefix_type"] = prefix_type
        if data:
            input_data["data"] = data

        return Mutation(
            name="AllocateIPPrefix",
            mutation="IPPrefixPoolGetResource",
            query={"ok": None, "node": {"id": None, "kind": None, "identifier": None, "display_label": None}},
            input_data={"data": input_data},
        )


class InfrahubClient(BaseClient):
    """
    Asynchronous GraphQL Client to interact with an Infrahub instance.

    This client provides methods for CRUD operations on Infrahub nodes,
    branch management, schema introspection, and other Infrahub-specific functionalities.
    It uses `httpx` for asynchronous HTTP requests.
    """

    group_context: InfrahubGroupContext

    def _initialize(self) -> None:
        """Initializes asynchronous client-specific components."""
        self.schema = InfrahubSchema(self)
        self.branch = InfrahubBranchManager(self)
        self.object_store = ObjectStore(self)
        self.store = NodeStore(default_branch=self.default_branch)
        self.task = InfrahubTaskManager(self)
        self.concurrent_execution_limit = asyncio.Semaphore(self.max_concurrent_execution)
        self._request_method: AsyncRequester = self.config.requester or self._default_request_method
        self.group_context = InfrahubGroupContext(self)

    async def get_version(self) -> str:
        """
        Retrieves the version of the connected Infrahub instance.

        Returns:
            A string representing the Infrahub server version.
        """
        response = await self.execute_graphql(query="query { InfrahubInfo { version }}")
        version = response.get("InfrahubInfo", {}).get("version", "")
        return version

    async def get_user(self) -> dict:
        """
        Retrieves information about the currently authenticated user.

        Returns:
            A dictionary containing user profile information.
        """
        user_info = await self.execute_graphql(query=QUERY_USER)
        return user_info

    async def get_user_permissions(self) -> dict:
        """
        Retrieves the permissions of the currently authenticated user.

        Returns:
            A dictionary representing the user's permissions.
        """
        user_info = await self.get_user()
        return get_user_permissions(user_info["AccountProfile"]["member_of_groups"]["edges"])

    @overload
    async def create(
        self,
        kind: str,
        data: dict | None = ...,
        branch: str | None = ...,
        **kwargs: Any,
    ) -> InfrahubNode: ...

    @overload
    async def create(
        self,
        kind: type[SchemaType],
        data: dict | None = ...,
        branch: str | None = ...,
        **kwargs: Any,
    ) -> SchemaType: ...

    async def create(
        self,
        kind: str | type[SchemaType],
        data: dict | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> InfrahubNode | SchemaType:
        """
        Creates a new Infrahub node.

        Args:
            kind: The kind of the node to create (e.g., "CoreSite") or its type (e.g., CoreSite).
            data: A dictionary of data to initialize the node with.
                  Can be used instead of or in addition to kwargs.
            branch: The branch on which to create the node. Defaults to the client's default branch.
            timeout: Optional timeout in seconds for the schema retrieval.
            **kwargs: Attributes and their values to set on the new node.

        Returns:
            An `InfrahubNode` instance (or a typed subclass if `kind` was a type)
            representing the newly created node. It is not yet saved to Infrahub.
            Call `.save()` on the returned node to persist it.

        Raises:
            ValueError: If neither `data` nor `kwargs` are provided.
        """
        branch = branch or self.default_branch

        schema = await self.schema.get(kind=kind, branch=branch, timeout=timeout)

        if not data and not kwargs:
            raise ValueError("Either data or a list of keywords but be provided")

        return InfrahubNode(client=self, schema=schema, branch=branch, data=data or kwargs)

    async def delete(self, kind: str | type[SchemaType], id: str, branch: str | None = None) -> None:
        """
        Deletes an Infrahub node by its ID.

        Note: This performs an immediate deletion request to the server.

        Args:
            kind: The kind of the node to delete or its type.
            id: The ID of the node to delete.
            branch: The branch from which to delete the node. Defaults to the client's default branch.
        """
        branch = branch or self.default_branch
        schema = await self.schema.get(kind=kind, branch=branch)

        node = InfrahubNode(client=self, schema=schema, branch=branch, data={"id": id})
        await node.delete()

    @overload
    async def get(
        self,
        kind: type[SchemaType],
        raise_when_missing: Literal[False],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> SchemaType | None: ...

    @overload
    async def get(
        self,
        kind: type[SchemaType],
        raise_when_missing: Literal[True],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> SchemaType: ...

    @overload
    async def get(
        self,
        kind: type[SchemaType],
        raise_when_missing: bool = ...,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> SchemaType: ...

    @overload
    async def get(
        self,
        kind: str,
        raise_when_missing: Literal[False],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> InfrahubNode | None: ...

    @overload
    async def get(
        self,
        kind: str,
        raise_when_missing: Literal[True],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> InfrahubNode: ...

    @overload
    async def get(
        self,
        kind: str,
        raise_when_missing: bool = ...,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> InfrahubNode: ...

    async def get(
        self,
        kind: str | type[SchemaType],
        raise_when_missing: bool = True,
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        id: str | None = None,
        hfid: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        populate_store: bool = True,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        property: bool = False,
        **kwargs: Any,
    ) -> InfrahubNode | SchemaType | None:
        """
        Retrieves a single Infrahub node by its ID, HFID, or other unique attributes.

        Args:
            kind: The kind of the node to retrieve (e.g., "CoreSite") or its type (e.g., CoreSite).
            raise_when_missing: If True (default), raises `NodeNotFoundError` if the node isn't found.
                                If False, returns None when not found.
            at: Optional timestamp to retrieve the node state at a specific time.
            branch: The branch to retrieve the node from. Defaults to the client's default branch.
            timeout: Optional timeout in seconds for the GraphQL request.
            id: The UUID of the node.
            hfid: A list of Human-Friendly IDs to search for.
            include: List of specific attributes or relationships to include in the response.
            exclude: List of attributes or relationships to exclude from the response.
            populate_store: If True (default), the retrieved node is added/updated in the client's NodeStore.
            fragment: If True, uses GraphQL fragments (useful for generic schema types).
            prefetch_relationships: If True, attempts to prefetch data for related nodes.
            property: If True, indicates that a property field is being queried directly.
            **kwargs: Additional filter criteria (attribute=value pairs) to find the node.

        Returns:
            An `InfrahubNode` (or its typed subclass) if found, or None if `raise_when_missing` is False.

        Raises:
            NodeNotFoundError: If `raise_when_missing` is True and no node matches the criteria.
            IndexError: If more than one node matches the criteria.
            ValueError: If no filter criteria (id, hfid, or kwargs) are provided, or if filtering
                        by HFID is attempted on a node kind that doesn't support it.
        """
        branch = branch or self.default_branch
        schema = await self.schema.get(kind=kind, branch=branch)

        filters: MutableMapping[str, Any] = {}

        if id:
            if not is_valid_uuid(id) and isinstance(schema, NodeSchemaAPI) and schema.default_filter:
                filters[schema.default_filter] = id
            else:
                filters["ids"] = [id]
        if hfid:
            if isinstance(schema, NodeSchemaAPI) and schema.human_friendly_id:
                filters["hfid"] = hfid
            else:
                raise ValueError("Cannot filter by HFID if the node doesn't have an HFID defined")
        if kwargs:
            filters.update(kwargs)
        if len(filters) == 0:
            raise ValueError("At least one filter must be provided to get()")

        results = await self.filters(
            kind=kind,
            at=at,
            branch=branch,
            timeout=timeout,
            populate_store=populate_store,
            include=include,
            exclude=exclude,
            fragment=fragment,
            prefetch_relationships=prefetch_relationships,
            property=property,
            **filters,
        )

        if len(results) == 0 and raise_when_missing:
            raise NodeNotFoundError(branch_name=branch, node_type=schema.kind, identifier=filters)
        if len(results) == 0 and not raise_when_missing:
            return None
        if len(results) > 1:
            raise IndexError("More than 1 node returned")

        return results[0]

    async def _process_nodes_and_relationships(
        self,
        response: dict[str, Any],
        schema_kind: str,
        branch: str,
        prefetch_relationships: bool,
        timeout: int | None = None,
    ) -> ProcessRelationsNode:
        """
        Processes InfrahubNode objects and their relationships from a GraphQL query response.

        This is an internal helper method.

        Args:
            response: The raw dictionary response from a GraphQL query.
            schema_kind: The `kind` of the primary nodes being processed from the response.
            branch: The branch name these nodes belong to.
            prefetch_relationships: If True, additionally processes and fetches related nodes.
            timeout: Optional timeout for fetching related node schemas.

        Returns:
            A ProcessRelationsNode TypedDict containing:
                - 'nodes': A list of processed `InfrahubNode` objects.
                - 'related_nodes': A list of `InfrahubNode` objects that are related to the primary nodes
                                 (populated if `prefetch_relationships` is True).
        """

        nodes: list[InfrahubNode] = []
        related_nodes: list[InfrahubNode] = []

        for item in response.get(schema_kind, {}).get("edges", []):
            node = await InfrahubNode.from_graphql(client=self, branch=branch, data=item, timeout=timeout)
            nodes.append(node)

            if prefetch_relationships:
                await node._process_relationships(
                    node_data=item, branch=branch, related_nodes=related_nodes, timeout=timeout
                )

        return ProcessRelationsNode(nodes=nodes, related_nodes=related_nodes)

    async def count(
        self,
        kind: str | type[SchemaType],
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        partial_match: bool = False,
        **kwargs: Any,
    ) -> int:
        """
        Counts the number of nodes of a given kind that match the specified filters.

        Args:
            kind: The kind of the node (e.g., "CoreSite") or its type (e.g., CoreSite).
            at: Optional timestamp to count nodes at a specific time.
            branch: The branch to count nodes in. Defaults to the client's default branch.
            timeout: Optional timeout in seconds for the GraphQL request.
            partial_match: If True, allows partial matching for string filters.
            **kwargs: Filter criteria (attribute=value pairs) for counting nodes.

        Returns:
            The number of matching nodes.
        """
        filters: dict[str, Any] = dict(kwargs)

        if partial_match:
            filters["partial_match"] = True

        schema = await self.schema.get(kind=kind, branch=branch)
        branch = branch or self.default_branch
        if at:
            at = Timestamp(at)

        data: dict[str, Any] = {
            "count": None,
            "@filters": filters,
        }

        response = await self.execute_graphql(
            query=Query(query={schema.kind: data}).render(),
            branch_name=branch,
            at=at,
            timeout=timeout,
        )
        return int(response.get(schema.kind, {}).get("count", 0))

    @overload
    async def all(
        self,
        kind: type[SchemaType],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
    ) -> list[SchemaType]: ...

    @overload
    async def all(
        self,
        kind: str,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
    ) -> list[InfrahubNode]: ...

    async def all(
        self,
        kind: str | type[SchemaType],
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        populate_store: bool = True,
        offset: int | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        property: bool = False,
        parallel: bool = False,
        order: Order | None = None,
    ) -> list[InfrahubNode] | list[SchemaType]:
        """
        Retrieves all nodes of a given kind.

        This is a convenience method that calls `filters()` without any specific filter arguments.

        Args:
            kind: The kind of the nodes to query (e.g., "CoreSite") or its type (e.g., CoreSite).
            at: Optional timestamp to query nodes at a specific time.
            branch: The branch to query from. Defaults to the client's default branch.
            timeout: Optional timeout in seconds for GraphQL requests.
            populate_store: If True (default), retrieved nodes are added/updated in the client's NodeStore.
            offset: Optional offset for pagination.
            limit: Optional limit for pagination.
            include: List of specific attributes or relationships to include in the response.
            exclude: List of attributes or relationships to exclude from the response.
            fragment: If True, uses GraphQL fragments (useful for generic schema types).
            prefetch_relationships: If True, attempts to prefetch data for related nodes.
            property: If True, indicates that property fields are being queried directly.
            parallel: If True, fetches pages in parallel (can be faster but consumes more resources).
            order: Optional `Order` object to specify sorting. Disabling order enhances performance.

        Returns:
            A list of `InfrahubNode` objects (or their typed subclasses).
        """
        return await self.filters(
            kind=kind,
            at=at,
            branch=branch,
            timeout=timeout,
            populate_store=populate_store,
            offset=offset,
            limit=limit,
            include=include,
            exclude=exclude,
            fragment=fragment,
            prefetch_relationships=prefetch_relationships,
            property=property,
            parallel=parallel,
            order=order,
        )

    @overload
    async def filters(
        self,
        kind: type[SchemaType],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        partial_match: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
        **kwargs: Any,
    ) -> list[SchemaType]: ...

    @overload
    async def filters(
        self,
        kind: str,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        partial_match: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
        **kwargs: Any,
    ) -> list[InfrahubNode]: ...

    async def filters(
        self,
        kind: str | type[SchemaType],
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        populate_store: bool = True,
        offset: int | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        partial_match: bool = False,
        property: bool = False,
        parallel: bool = False,
        order: Order | None = None,
        **kwargs: Any,
    ) -> list[InfrahubNode] | list[SchemaType]:
        """
        Retrieves nodes of a given kind based on provided filters and pagination options.

        Args:
            kind: The kind of the nodes to query (e.g., "CoreSite") or its type (e.g., CoreSite).
            at: Optional timestamp to query nodes at a specific time.
            branch: The branch to query from. Defaults to the client's default branch.
            timeout: Optional timeout in seconds for GraphQL requests.
            populate_store: If True (default), retrieved nodes are added/updated in the client's NodeStore.
            offset: Optional offset for pagination.
            limit: Optional limit for pagination. If set, `parallel` processing might be less effective
                   if limit is smaller than pagination_size.
            include: List of specific attributes or relationships to include in the response.
            exclude: List of attributes or relationships to exclude from the response.
            fragment: If True, uses GraphQL fragments (useful for generic schema types).
            prefetch_relationships: If True, attempts to prefetch data for related nodes.
            partial_match: If True, allows partial matching for string filters.
            property: If True, indicates that property fields are being queried directly.
            parallel: If True, fetches pages in parallel (can be faster but consumes more resources).
                      Not recommended if `limit` is set to a small value.
            order: Optional `Order` object to specify sorting. Disabling order enhances performance.
            **kwargs: Additional filter criteria (attribute=value pairs) for the query.

        Returns:
            A list of `InfrahubNode` objects (or their typed subclasses) that match the filters.
        """
        branch = branch or self.default_branch
        schema = await self.schema.get(kind=kind, branch=branch)
        if at:
            at = Timestamp(at)

        node = InfrahubNode(client=self, schema=schema, branch=branch)
        filters = kwargs
        pagination_size = self.pagination_size

        async def process_page(page_offset: int, page_number: int) -> tuple[dict, ProcessRelationsNode]:
            """Process a single page of results."""
            query_data = await InfrahubNode(client=self, schema=schema, branch=branch).generate_query_data(
                offset=offset or page_offset,
                limit=limit or pagination_size,
                filters=filters,
                include=include,
                exclude=exclude,
                fragment=fragment,
                prefetch_relationships=prefetch_relationships,
                partial_match=partial_match,
                property=property,
                order=order,
            )
            query = Query(query=query_data)
            response = await self.execute_graphql(
                query=query.render(),
                branch_name=branch,
                at=at,
                tracker=f"query-{str(schema.kind).lower()}-page{page_number}",
                timeout=timeout,
            )

            process_result: ProcessRelationsNode = await self._process_nodes_and_relationships(
                response=response,
                schema_kind=schema.kind,
                branch=branch,
                prefetch_relationships=prefetch_relationships,
                timeout=timeout,
            )
            return response, process_result

        async def process_batch() -> tuple[list[InfrahubNode], list[InfrahubNode]]:
            """Process queries in parallel mode."""
            nodes = []
            related_nodes = []
            batch_process = await self.create_batch()
            count = await self.count(kind=schema.kind, partial_match=partial_match, **filters)
            total_pages = (count + pagination_size - 1) // pagination_size

            for page_number in range(1, total_pages + 1):
                page_offset = (page_number - 1) * pagination_size
                batch_process.add(task=process_page, node=node, page_offset=page_offset, page_number=page_number)

            async for _, response in batch_process.execute():
                nodes.extend(response[1]["nodes"])
                related_nodes.extend(response[1]["related_nodes"])

            return nodes, related_nodes

        async def process_non_batch() -> tuple[list[InfrahubNode], list[InfrahubNode]]:
            """Process queries without parallel mode."""
            nodes = []
            related_nodes = []
            has_remaining_items = True
            page_number = 1

            while has_remaining_items:
                page_offset = (page_number - 1) * pagination_size
                response, process_result = await process_page(page_offset, page_number)

                nodes.extend(process_result["nodes"])
                related_nodes.extend(process_result["related_nodes"])
                remaining_items = response[schema.kind].get("count", 0) - (page_offset + pagination_size)
                if remaining_items < 0 or offset is not None or limit is not None:
                    has_remaining_items = False
                page_number += 1

            return nodes, related_nodes

        # Select parallel or non-parallel processing
        nodes, related_nodes = await (process_batch() if parallel else process_non_batch())

        if populate_store:
            for node in nodes:
                if node.id:
                    self.store.set(node=node)
            related_nodes = list(set(related_nodes))
            for node in related_nodes:
                if node.id:
                    self.store.set(node=node)
        return nodes

    def clone(self, branch: str | None = None) -> InfrahubClient:
        """
        Creates a new `InfrahubClient` instance with a cloned configuration.

        This is useful for creating a client for a different branch while retaining
        the original client's settings (address, credentials, etc.).

        Args:
            branch: Optional new default branch name for the cloned client.
                    If None, the current client's default branch is used.

        Returns:
            A new `InfrahubClient` instance.
        """
        return InfrahubClient(config=self.config.clone(branch=branch))

    async def execute_graphql(
        self,
        query: str,
        variables: dict | None = None,
        branch_name: str | None = None,
        at: str | Timestamp | None = None,
        timeout: int | None = None,
        raise_for_error: bool = True,
        tracker: str | None = None,
    ) -> dict:
        """
        Executes a raw GraphQL query or mutation.

        If `retry_on_failure` is True in the client config, the query will be retried
        if the server is unreachable.

        Args:
            query: The GraphQL query or mutation string.
            variables: Optional dictionary of variables for the query.
            branch_name: The branch to execute against. Defaults to the client's default branch.
            at: Optional timestamp to execute the query at a specific time.
            timeout: Optional timeout in seconds for this specific request.
            raise_for_error: If True (default), raises `GraphQLError` if the response contains errors.
            tracker: Optional tracker string to include in request headers for debugging/logging.

        Returns:
            A dictionary containing the "data" part of the GraphQL response.

        Raises:
            ServerNotReachableError: If the server cannot be reached after retries (if enabled).
            httpx.HTTPStatusError: For HTTP errors (e.g., 401, 403, 404) if not handled otherwise.
            AuthenticationError: For 401/403 errors specifically.
            URLNotFoundError: For 404 errors.
            GraphQLError: If `raise_for_error` is True and the GraphQL response contains errors.
            Error: If an unexpected situation occurs where the response object isn't initialized.
        """

        branch_name = branch_name or self.default_branch
        url = self._graphql_url(branch_name=branch_name, at=at)

        payload: dict[str, str | dict] = {"query": query}
        if variables:
            payload["variables"] = variables

        headers = copy.copy(self.headers or {})
        if self.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        self._echo(url=url, query=query, variables=variables)

        retry = True
        resp = None
        start_time = time.time()
        while retry and time.time() - start_time < self.config.max_retry_duration:
            retry = self.retry_on_failure
            try:
                resp = await self._post(url=url, payload=payload, headers=headers, timeout=timeout)

                if raise_for_error:
                    resp.raise_for_status()

                retry = False
            except ServerNotReachableError:
                if retry:
                    self.log.warning(
                        f"Unable to connect to {self.address}, will retry in {self.retry_delay} seconds .."
                    )
                    await asyncio.sleep(delay=self.retry_delay)
                else:
                    self.log.error(f"Unable to connect to {self.address} .. ")
                    raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in [401, 403]:
                    response = decode_json(response=exc.response)
                    errors = response.get("errors", [])
                    messages = [error.get("message") for error in errors]
                    raise AuthenticationError(" | ".join(messages)) from exc
                if exc.response.status_code == 404:
                    raise URLNotFoundError(url=url)

        if not resp:
            raise Error("Unexpected situation, resp hasn't been initialized.")

        response = decode_json(response=resp)

        if "errors" in response:
            raise GraphQLError(errors=response["errors"], query=query, variables=variables)

        return response["data"]

        # TODO add a special method to execute mutation that will check if the method returned OK

    @handle_relogin
    async def _post(
        self, url: str, payload: dict, headers: dict | None = None, timeout: int | None = None
    ) -> httpx.Response:
        """Execute a HTTP POST with HTTPX.

        Raises:
            ServerNotReachableError if we are not able to connect to the server
            ServerNotResponsiveError if the server didn't respond before the timeout expired
        """
        await self.login()

        headers = headers or {}
        base_headers = copy.copy(self.headers or {})
        headers.update(base_headers)

        return await self._request(
            url=url, method=HTTPMethod.POST, headers=headers, timeout=timeout or self.default_timeout, payload=payload
        )

    @handle_relogin
    async def _get(self, url: str, headers: dict | None = None, timeout: int | None = None) -> httpx.Response:
        """Execute a HTTP GET with HTTPX.

        Raises:
            ServerNotReachableError if we are not able to connect to the server
            ServerNotResponsiveError if the server didnd't respond before the timeout expired
        """
        await self.login()

        headers = headers or {}
        base_headers = copy.copy(self.headers or {})
        headers.update(base_headers)

        return await self._request(
            url=url, method=HTTPMethod.GET, headers=headers, timeout=timeout or self.default_timeout
        )

    async def _request(
        self, url: str, method: HTTPMethod, headers: dict[str, Any], timeout: int, payload: dict | None = None
    ) -> httpx.Response:
        """
        Internal method to make an HTTP request using the configured requester.

        Also handles recording the response.

        Args:
            url: The URL for the request.
            method: The HTTP method (GET, POST, etc.).
            headers: Dictionary of request headers.
            timeout: Request timeout in seconds.
            payload: Optional request payload (typically for POST/PUT).

        Returns:
            An `httpx.Response` object.
        """
        response = await self._request_method(url=url, method=method, headers=headers, timeout=timeout, payload=payload)
        self._record(response)
        return response

    async def _default_request_method(
        self, url: str, method: HTTPMethod, headers: dict[str, Any], timeout: int, payload: dict | None = None
    ) -> httpx.Response:
        """
        The default asynchronous HTTP request method using httpx.AsyncClient.

        Handles proxy configuration and TLS verification settings.

        Args:
            url: The URL for the request.
            method: The HTTP method.
            headers: Request headers.
            timeout: Request timeout in seconds.
            payload: Optional request payload.

        Returns:
            An `httpx.Response` object.

        Raises:
            ServerNotReachableError: If a network error occurs.
            ServerNotResponsiveError: If a read timeout occurs.
        """
        params: dict[str, Any] = {}
        if payload:
            params["json"] = payload

        proxy_config: dict[str, str | dict[str, httpx.HTTPTransport]] = {}
        if self.config.proxy:
            proxy_config["proxy"] = self.config.proxy
        elif self.config.proxy_mounts.is_set:
            proxy_config["mounts"] = {
                key: httpx.HTTPTransport(proxy=value)
                for key, value in self.config.proxy_mounts.model_dump(by_alias=True).items()
            }

        async with httpx.AsyncClient(
            **proxy_config,  # type: ignore[arg-type]
            verify=self.config.tls_ca_file if self.config.tls_ca_file else not self.config.tls_insecure,
        ) as client:
            try:
                response = await client.request(
                    method=method.value,
                    url=url,
                    headers=headers,
                    timeout=timeout,
                    **params,
                )
            except httpx.NetworkError as exc:
                raise ServerNotReachableError(address=self.address) from exc
            except httpx.ReadTimeout as exc:
                raise ServerNotResponsiveError(url=url, timeout=timeout) from exc

        return response

    async def refresh_login(self) -> None:
        """
        Refreshes the authentication access token using the stored refresh token.

        Updates `self.access_token` and the "Authorization" header.
        This method is called automatically by decorated request methods if a token expires.

        Raises:
            httpx.HTTPStatusError: If the refresh request itself fails (e.g., invalid refresh token).
        """
        if not self.refresh_token:
            return

        url = f"{self.address}/api/auth/refresh"
        response = await self._request(
            url=url,
            method=HTTPMethod.POST,
            headers={"content-type": "application/json", "Authorization": f"Bearer {self.refresh_token}"},
            timeout=self.default_timeout,
        )

        response.raise_for_status()
        data = decode_json(response=response)
        self.access_token = data["access_token"]
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    async def login(self, refresh: bool = False) -> None:
        """
        Logs into Infrahub using username/password or refreshes an existing session.

        If password authentication is not configured, this method does nothing.
        If an access token already exists and `refresh` is False, it does nothing.
        If `refresh` is True and a refresh token exists, it attempts `refresh_login()`.
        Otherwise, it performs a full login with username and password.

        Updates `self.access_token`, `self.refresh_token`, and the "Authorization" header.

        Args:
            refresh: If True, forces an attempt to refresh the token if one exists.

        Raises:
            AuthenticationError: If login fails due to authentication issues (e.g., bad credentials
                                 during initial login, or non-401 error during refresh).
            httpx.HTTPStatusError: For other HTTP errors during the login process.
        """
        if not self.config.password_authentication:
            return

        if self.access_token and not refresh:
            return

        if self.refresh_token and refresh:
            try:
                await self.refresh_login()
                return
            except httpx.HTTPStatusError as exc:
                # If we got a 401 while trying to refresh a token we must restart the authentication process
                # Other status codes indicate other errors
                if exc.response.status_code != 401:
                    response = exc.response.json()
                    errors = response.get("errors", [])
                    messages = [error.get("message") for error in errors]
                    raise AuthenticationError(" | ".join(messages)) from exc

        url = f"{self.address}/api/auth/login"
        response = await self._request(
            url=url,
            method=HTTPMethod.POST,
            payload={"username": self.config.username, "password": self.config.password},
            headers={"content-type": "application/json"},
            timeout=self.default_timeout,
        )

        response.raise_for_status()
        data = decode_json(response=response)
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    async def query_gql_query(
        self,
        name: str,
        variables: dict | None = None,
        update_group: bool = False,
        subscribers: list[str] | None = None,
        params: dict | None = None,
        branch_name: str | None = None,
        at: str | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> dict:
        """
        Executes a pre-defined GraphQL query stored on the Infrahub server by its name.

        Args:
            name: The name of the stored GraphQL query.
            variables: Optional dictionary of variables for the query.
            update_group: If True, associates this query with the current tracking group (if active).
            subscribers: Optional list of subscriber identifiers.
            params: Optional dictionary of additional URL parameters.
            branch_name: The branch to execute against. Defaults to client's default.
            at: Optional timestamp to execute at a specific time.
            timeout: Optional timeout for this request.
            tracker: Optional tracker string for request headers.
            raise_for_error: If True (default), raises an exception on HTTP or GraphQL errors.

        Returns:
            A dictionary containing the query's response data.

        Raises:
            httpx.HTTPStatusError: For HTTP errors if `raise_for_error` is True.
        """
        url = f"{self.address}/api/query/{name}"
        url_params = copy.deepcopy(params or {})
        headers = copy.copy(self.headers or {})

        if self.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        if branch_name:
            url_params["branch"] = branch_name
        if at:
            url_params["at"] = at

        if subscribers:
            url_params["subscribers"] = subscribers

        url_params["update_group"] = str(update_group).lower()

        if url_params:
            url_params_str = []
            url_params_dict = {}
            for key, value in url_params.items():
                if isinstance(value, (list)):
                    for item in value:
                        url_params_str.append((key, item))
                else:
                    url_params_dict[key] = value

            url += "?"
            if url_params_dict:
                url += urlencode(url_params_dict) + "&"
            if url_params_str:
                url += urlencode(url_params_str)

        payload = {}
        if variables:
            payload["variables"] = variables

        resp = await self._post(
            url=url,
            headers=headers,
            payload=payload,
            timeout=timeout or self.default_timeout,
        )

        if raise_for_error:
            resp.raise_for_status()

        return decode_json(response=resp)

    async def get_diff_summary(
        self,
        branch: str,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> list[NodeDiff]:
        """
        Retrieves a summary of differences (diffs) for a given branch.

        Args:
            branch: The name of the branch to get the diff summary for.
            timeout: Optional timeout for the GraphQL request.
            tracker: Optional tracker string for request headers.
            raise_for_error: If True (default), raises an exception on HTTP or GraphQL errors.

        Returns:
            A list of `NodeDiff` objects representing the changes on the branch.
        """
        query = get_diff_summary_query()
        response = await self.execute_graphql(
            query=query,
            branch_name=branch,
            timeout=timeout,
            tracker=tracker,
            raise_for_error=raise_for_error,
            variables={"branch_name": branch},
        )

        node_diffs: list[NodeDiff] = []
        diff_tree = response["DiffTree"]

        if diff_tree is None or "nodes" not in diff_tree:
            return []
        for node_dict in diff_tree["nodes"]:
            node_diff = diff_tree_node_to_node_diff(node_dict=node_dict, branch_name=branch)
            node_diffs.append(node_diff)

        return node_diffs

    @overload
    async def allocate_next_ip_address(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> SchemaType: ...

    @overload
    async def allocate_next_ip_address(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> SchemaType | None: ...

    @overload
    async def allocate_next_ip_address(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> SchemaType: ...

    @overload
    async def allocate_next_ip_address(
        self,
        resource_pool: CoreNode,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> CoreNode: ...

    @overload
    async def allocate_next_ip_address(
        self,
        resource_pool: CoreNode,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> CoreNode | None: ...

    @overload
    async def allocate_next_ip_address(
        self,
        resource_pool: CoreNode,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> CoreNode | None: ...

    async def allocate_next_ip_address(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType] | None = None,  # noqa: ARG002
        identifier: str | None = None,
        prefix_length: int | None = None,
        address_type: str | None = None,
        data: dict[str, Any] | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> CoreNode | SchemaType | None:
        """
        Allocates the next available IP address from a specified CoreIPAddressPool.

        Args:
            resource_pool: The `CoreIPAddressPool` node from which to allocate.
            kind: Optional specific type of `CoreIPAddress` to expect (e.g., a custom subclass).
            identifier: Optional identifier for idempotent allocation. If provided, subsequent calls
                        with the same identifier will return the same allocated address.
            prefix_length: Optional desired prefix length for the allocated IP address.
            address_type: Optional specific kind of IP address to allocate if the pool supports multiple.
            data: Optional dictionary of attributes to set on the newly allocated IP address node.
            branch: The branch on which to perform the allocation. Defaults to the client's default branch.
            timeout: Optional timeout for the GraphQL request.
            tracker: Optional tracker string for request headers.
            raise_for_error: If True (default), raises an exception on HTTP or GraphQL errors.
                             If False and allocation fails, returns None.

        Returns:
            The allocated `CoreIPAddress` node (or its typed subclass if `kind` was specified),
            or None if allocation failed and `raise_for_error` is False.

        Raises:
            ValueError: If `resource_pool` is not a "CoreIPAddressPool".
            GraphQLError: If allocation fails and `raise_for_error` is True.
        """
        if resource_pool.get_kind() != "CoreIPAddressPool":
            raise ValueError("resource_pool is not an IP address pool")

        branch = branch or self.default_branch
        mutation_name = "IPAddressPoolGetResource"

        query = self._build_ip_address_allocation_query(
            resource_pool_id=resource_pool.id,
            identifier=identifier,
            prefix_length=prefix_length,
            address_type=address_type,
            data=data,
        )
        response = await self.execute_graphql(
            query=query.render(),
            branch_name=branch,
            timeout=timeout,
            tracker=tracker,
            raise_for_error=raise_for_error,
        )

        if response[mutation_name]["ok"]:
            resource_details = response[mutation_name]["node"]
            return await self.get(kind=resource_details["kind"], id=resource_details["id"], branch=branch)
        return None

    @overload
    async def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> SchemaType: ...

    @overload
    async def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> SchemaType | None: ...

    @overload
    async def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> SchemaType: ...

    @overload
    async def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNode,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> CoreNode: ...

    @overload
    async def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNode,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> CoreNode | None: ...

    @overload
    async def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNode,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> CoreNode | None: ...

    async def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNode,
        kind: type[SchemaType] | None = None,  # noqa: ARG002
        identifier: str | None = None,
        prefix_length: int | None = None,
        member_type: str | None = None,
        prefix_type: str | None = None,
        data: dict[str, Any] | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> CoreNode | SchemaType | None:
        """
        Allocates the next available IP prefix from a specified CoreIPPrefixPool.

        Args:
            resource_pool: The `CoreIPPrefixPool` node from which to allocate.
            kind: Optional specific type of `CoreIPPrefix` to expect (e.g., a custom subclass).
            identifier: Optional identifier for idempotent allocation.
            prefix_length: Optional desired length of the prefix to allocate.
            member_type: Optional member type for the prefix (e.g., "prefix", "address").
            prefix_type: Optional specific kind of IP prefix to allocate if the pool supports multiple.
            data: Optional dictionary of attributes to set on the newly allocated IP prefix node.
            branch: The branch on which to perform the allocation. Defaults to the client's default branch.
            timeout: Optional timeout for the GraphQL request.
            tracker: Optional tracker string for request headers.
            raise_for_error: If True (default), raises an exception on HTTP or GraphQL errors.
                             If False and allocation fails, returns None.

        Returns:
            The allocated `CoreIPPrefix` node (or its typed subclass if `kind` was specified),
            or None if allocation failed and `raise_for_error` is False.

        Raises:
            ValueError: If `resource_pool` is not a "CoreIPPrefixPool".
            GraphQLError: If allocation fails and `raise_for_error` is True.
        """
        if resource_pool.get_kind() != "CoreIPPrefixPool":
            raise ValueError("resource_pool is not an IP prefix pool")

        branch = branch or self.default_branch
        mutation_name = "IPPrefixPoolGetResource"

        query = self._build_ip_prefix_allocation_query(
            resource_pool_id=resource_pool.id,
            identifier=identifier,
            prefix_length=prefix_length,
            member_type=member_type,
            prefix_type=prefix_type,
            data=data,
        )
        response = await self.execute_graphql(
            query=query.render(), branch_name=branch, timeout=timeout, tracker=tracker, raise_for_error=raise_for_error
        )

        if response[mutation_name]["ok"]:
            resource_details = response[mutation_name]["node"]
            return await self.get(kind=resource_details["kind"], id=resource_details["id"], branch=branch)
        return None

    async def create_batch(self, return_exceptions: bool = False) -> InfrahubBatch:
        """
        Creates an `InfrahubBatch` instance for managing concurrent asynchronous tasks.

        Args:
            return_exceptions: If True, exceptions from tasks in the batch will be returned
                               as results instead of being raised.

        Returns:
            An `InfrahubBatch` instance.
        """
        return InfrahubBatch(semaphore=self.concurrent_execution_limit, return_exceptions=return_exceptions)

    async def get_list_repositories(
        self, branches: dict[str, BranchData] | None = None, kind:str = "CoreGenericRepository"
    ) -> dict[str, RepositoryData]:
        """
        Retrieves a list of repositories and their branch information.

        Args:
            branches: Optional dictionary of branch data. If None, all branches are fetched.
            kind: The kind of repository node to list (defaults to "CoreGenericRepository").

        Returns:
            A dictionary where keys are repository names and values are `RepositoryData` objects.
        """
        branches = branches or await self.branch.all()

        batch = await self.create_batch()
        for branch_name, branch in branches.items():
            batch.add(
                task=self.all,
                node=branch,  # type: ignore[arg-type]
                kind=kind,
                branch=branch_name,
                fragment=True,
                include=["id", "name", "location", "commit", "ref", "internal_status"],
            )

        responses: dict[str, Any] = {}
        async for branch, response in batch.execute():
            responses[branch.name] = response

        repositories: dict[str, RepositoryData] = {}

        for branch_name, response in responses.items():
            for repository in response:
                repo_name = repository.name.value
                if repo_name not in repositories:
                    repositories[repo_name] = RepositoryData(
                        repository=repository,
                        branches={},
                    )

                repositories[repo_name].branches[branch_name] = repository.commit.value
                repositories[repo_name].branch_info[branch_name] = RepositoryBranchInfo(
                    internal_status=repository.internal_status.value
                )

        return repositories

    async def repository_update_commit(
        self, branch_name: str, repository_id: str, commit: str, is_read_only: bool = False
    ) -> bool:
        """
        Updates the commit SHA for a specific repository on a given branch.

        Args:
            branch_name: The name of the branch where the repository's commit will be updated.
            repository_id: The ID of the repository node to update.
            commit: The new commit SHA.
            is_read_only: If True, uses a read-only mutation (e.g., for dry runs or checks).

        Returns:
            True if the operation was successful (the GraphQL mutation returned ok).
        """
        variables = {"repository_id": str(repository_id), "commit": str(commit)}
        await self.execute_graphql(
            query=get_commit_update_mutation(is_read_only=is_read_only),
            variables=variables,
            branch_name=branch_name,
            tracker="mutation-repository-update-commit",
        )

        return True

    async def __aenter__(self) -> Self:
        """Enters an asynchronous context, returning the client instance."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """
        Exits an asynchronous context.

        If the client was in TRACKING mode and no exception occurred,
        it finalizes the group context (e.g., by calling `update_group()`).
        Resets client mode to DEFAULT.
        """
        if exc_type is None and self.mode == InfrahubClientMode.TRACKING:
            await self.group_context.update_group()

        self.mode = InfrahubClientMode.DEFAULT


class InfrahubClientSync(BaseClient):
    """
    Synchronous GraphQL Client to interact with an Infrahub instance.

    This client provides methods for CRUD operations on Infrahub nodes,
    branch management, schema introspection, and other Infrahub-specific functionalities.
    It uses `httpx` for synchronous HTTP requests.
    """
    schema: InfrahubSchemaSync
    branch: InfrahubBranchManagerSync
    object_store: ObjectStoreSync
    store: NodeStoreSync
    task: InfrahubTaskManagerSync
    group_context: InfrahubGroupContextSync

    def _initialize(self) -> None:
        """Initializes synchronous client-specific components."""
        self.schema = InfrahubSchemaSync(self)
        self.branch = InfrahubBranchManagerSync(self)
        self.object_store = ObjectStoreSync(self)
        self.store = NodeStoreSync(default_branch=self.default_branch)
        self.task = InfrahubTaskManagerSync(self)
        self._request_method: SyncRequester = self.config.sync_requester or self._default_request_method
        self.group_context = InfrahubGroupContextSync(self)

    def get_version(self) -> str:
        """
        Retrieves the version of the connected Infrahub instance.

        Returns:
            A string representing the Infrahub server version.
        """
        response = self.execute_graphql(query="query { InfrahubInfo { version }}")
        version = response.get("InfrahubInfo", {}).get("version", "")
        return version

    def get_user(self) -> dict:
        """
        Retrieves information about the currently authenticated user.

        Returns:
            A dictionary containing user profile information.
        """
        user_info = self.execute_graphql(query=QUERY_USER)
        return user_info

    def get_user_permissions(self) -> dict:
        """
        Retrieves the permissions of the currently authenticated user.

        Returns:
            A dictionary representing the user's permissions.
        """
        user_info = self.get_user()
        return get_user_permissions(user_info["AccountProfile"]["member_of_groups"]["edges"])

    @overload
    def create(
        self,
        kind: str,
        data: dict | None = ...,
        branch: str | None = ...,
        **kwargs: Any,
    ) -> InfrahubNodeSync: ...

    @overload
    def create(
        self,
        kind: type[SchemaTypeSync],
        data: dict | None = ...,
        branch: str | None = ...,
        **kwargs: Any,
    ) -> SchemaTypeSync: ...

    def create(
        self,
        kind: str | type[SchemaTypeSync],
        data: dict | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> InfrahubNodeSync | SchemaTypeSync:
        """
        Creates a new Infrahub node (synchronous version).

        Args:
            kind: The kind of the node to create (e.g., "CoreSite") or its type (e.g., CoreSite).
            data: A dictionary of data to initialize the node with.
            branch: The branch on which to create the node. Defaults to the client's default branch.
            timeout: Optional timeout for schema retrieval.
            **kwargs: Attributes and their values to set on the new node.

        Returns:
            An `InfrahubNodeSync` instance (or a typed subclass) representing the new node.
            It is not yet saved. Call `.save()` on the returned node to persist it.

        Raises:
            ValueError: If neither `data` nor `kwargs` are provided.
        """
        branch = branch or self.default_branch
        schema = self.schema.get(kind=kind, branch=branch, timeout=timeout)

        if not data and not kwargs:
            raise ValueError("Either data or a list of keywords but be provided")

        return InfrahubNodeSync(client=self, schema=schema, branch=branch, data=data or kwargs)

    def delete(self, kind: str | type[SchemaTypeSync], id: str, branch: str | None = None) -> None:
        """
        Deletes an Infrahub node by its ID (synchronous version).

        Note: This performs an immediate deletion request to the server.

        Args:
            kind: The kind of the node to delete or its type.
            id: The ID of the node to delete.
            branch: The branch from which to delete the node. Defaults to the client's default branch.
        """
        branch = branch or self.default_branch
        schema = self.schema.get(kind=kind, branch=branch)

        node = InfrahubNodeSync(client=self, schema=schema, branch=branch, data={"id": id})
        node.delete()

    def clone(self, branch: str | None = None) -> InfrahubClientSync:
        """
        Creates a new `InfrahubClientSync` instance with a cloned configuration.

        Args:
            branch: Optional new default branch name for the cloned client.

        Returns:
            A new `InfrahubClientSync` instance.
        """
        return InfrahubClientSync(config=self.config.clone(branch=branch))

    def execute_graphql(
        self,
        query: str,
        variables: dict | None = None,
        branch_name: str | None = None,
        at: str | Timestamp | None = None,
        timeout: int | None = None,
        raise_for_error: bool = True,
        tracker: str | None = None,
    ) -> dict:
        """
        Executes a raw GraphQL query or mutation (synchronous version).

        If `retry_on_failure` is True in config, retries if the server is unreachable.

        Args:
            query: The GraphQL query or mutation string.
            variables: Optional dictionary of variables.
            branch_name: Branch to execute against. Defaults to client's default.
            at: Optional timestamp for point-in-time query.
            timeout: Optional request timeout in seconds.
            raise_for_error: If True (default), raises `GraphQLError` on response errors.
            tracker: Optional tracker string for request headers.

        Returns:
            A dictionary containing the "data" part of the GraphQL response.

        Raises:
            ServerNotReachableError: If server unreachable after retries.
            httpx.HTTPStatusError: For HTTP errors if not handled otherwise.
            AuthenticationError: For 401/403 errors.
            URLNotFoundError: For 404 errors.
            GraphQLError: If `raise_for_error` is True and response has errors.
            Error: If response object isn't initialized unexpectedly.
        """

        branch_name = branch_name or self.default_branch
        url = self._graphql_url(branch_name=branch_name, at=at)

        payload: dict[str, str | dict] = {"query": query}
        if variables:
            payload["variables"] = variables

        headers = copy.copy(self.headers or {})
        if self.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        self._echo(url=url, query=query, variables=variables)

        retry = True
        resp = None
        start_time = time.time()
        while retry and time.time() - start_time < self.config.max_retry_duration:
            retry = self.retry_on_failure
            try:
                resp = self._post(url=url, payload=payload, headers=headers, timeout=timeout)

                if raise_for_error:
                    resp.raise_for_status()

                retry = False
            except ServerNotReachableError:
                if retry:
                    self.log.warning(
                        f"Unable to connect to {self.address}, will retry in {self.retry_delay} seconds .."
                    )
                    sleep(self.retry_delay)
                else:
                    self.log.error(f"Unable to connect to {self.address} .. ")
                    raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in [401, 403]:
                    response = decode_json(response=exc.response)
                    errors = response.get("errors", [])
                    messages = [error.get("message") for error in errors]
                    raise AuthenticationError(" | ".join(messages)) from exc
                if exc.response.status_code == 404:
                    raise URLNotFoundError(url=url)

        if not resp:
            raise Error("Unexpected situation, resp hasn't been initialized.")

        response = decode_json(response=resp)

        if "errors" in response:
            raise GraphQLError(errors=response["errors"], query=query, variables=variables)

        return response["data"]

        # TODO add a special method to execute mutation that will check if the method returned OK

    def count(
        self,
        kind: str | type[SchemaTypeSync], # Corrected type hint
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        partial_match: bool = False,
        **kwargs: Any,
    ) -> int:
        """
        Counts nodes of a given kind matching filters (synchronous version).

        Args:
            kind: The kind of the node or its type (e.g., CoreSiteSync).
            at: Optional timestamp for point-in-time count.
            branch: Branch to count in. Defaults to client's default.
            timeout: Optional request timeout.
            partial_match: If True, allows partial string matching.
            **kwargs: Filter criteria (attribute=value).

        Returns:
            The number of matching nodes.
        """
        filters: dict[str, Any] = dict(kwargs)

        if partial_match:
            filters["partial_match"] = True

        schema = self.schema.get(kind=kind, branch=branch)
        branch = branch or self.default_branch
        if at:
            at = Timestamp(at)

        data: dict[str, Any] = {
            "count": None,
            "@filters": filters,
        }

        response = self.execute_graphql(
            query=Query(query={schema.kind: data}).render(),
            branch_name=branch,
            at=at,
            timeout=timeout,
        )
        return int(response.get(schema.kind, {}).get("count", 0))

    @overload
    def all(
        self,
        kind: type[SchemaTypeSync],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
    ) -> list[SchemaTypeSync]: ...

    @overload
    def all(
        self,
        kind: str,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
    ) -> list[InfrahubNodeSync]: ...

    def all(
        self,
        kind: str | type[SchemaTypeSync],
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        populate_store: bool = True,
        offset: int | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        property: bool = False,
        parallel: bool = False,
        order: Order | None = None,
    ) -> list[InfrahubNodeSync] | list[SchemaTypeSync]:
        """
        Retrieves all nodes of a given kind (synchronous version).

        Calls `filters()` without specific filter arguments.

        Args:
            kind: Node kind (e.g., "CoreSite") or type (e.g., CoreSiteSync).
            at: Optional timestamp for point-in-time query.
            branch: Branch to query. Defaults to client's default.
            timeout: Optional request timeout.
            populate_store: If True (default), updates client's NodeStore.
            offset: Optional pagination offset.
            limit: Optional pagination limit.
            include: Specific attributes/relationships to include.
            exclude: Attributes/relationships to exclude.
            fragment: If True, uses GraphQL fragments.
            prefetch_relationships: If True, prefetches related node data.
            property: If True, indicates direct property field query.
            parallel: If True, fetches pages in parallel (thread pool).
            order: Optional `Order` object for sorting.

        Returns:
            A list of `InfrahubNodeSync` objects (or typed subclasses).
        """
        return self.filters(
            kind=kind,
            at=at,
            branch=branch,
            timeout=timeout,
            populate_store=populate_store,
            offset=offset,
            limit=limit,
            include=include,
            exclude=exclude,
            fragment=fragment,
            prefetch_relationships=prefetch_relationships,
            property=property,
            parallel=parallel,
            order=order,
        )

    def _process_nodes_and_relationships(
        self,
        response: dict[str, Any],
        schema_kind: str,
        branch: str,
        prefetch_relationships: bool,
        timeout: int | None = None,
    ) -> ProcessRelationsNodeSync:
        """
        Processes InfrahubNodeSync objects and relationships from a GraphQL response (synchronous version).

        Internal helper method.

        Args:
            response: Raw dictionary response from GraphQL.
            schema_kind: `kind` of primary nodes being processed.
            branch: Branch name for these nodes.
            prefetch_relationships: If True, processes and fetches related nodes.
            timeout: Optional timeout for fetching related node schemas.

        Returns:
            ProcessRelationsNodeSync TypedDict with 'nodes' and 'related_nodes' lists.
        """

        nodes: list[InfrahubNodeSync] = []
        related_nodes: list[InfrahubNodeSync] = []

        for item in response.get(schema_kind, {}).get("edges", []):
            node = InfrahubNodeSync.from_graphql(client=self, branch=branch, data=item, timeout=timeout)
            nodes.append(node)

            if prefetch_relationships:
                node._process_relationships(node_data=item, branch=branch, related_nodes=related_nodes, timeout=timeout)

        return ProcessRelationsNodeSync(nodes=nodes, related_nodes=related_nodes)

    @overload
    def filters(
        self,
        kind: type[SchemaTypeSync],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        partial_match: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
        **kwargs: Any,
    ) -> list[SchemaTypeSync]: ...

    @overload
    def filters(
        self,
        kind: str,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        populate_store: bool = ...,
        offset: int | None = ...,
        limit: int | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        partial_match: bool = ...,
        property: bool = ...,
        parallel: bool = ...,
        order: Order | None = ...,
        **kwargs: Any,
    ) -> list[InfrahubNodeSync]: ...

    def filters(
        self,
        kind: str | type[SchemaTypeSync],
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        populate_store: bool = True,
        offset: int | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        partial_match: bool = False,
        property: bool = False,
        parallel: bool = False,
        order: Order | None = None,
        **kwargs: Any,
    ) -> list[InfrahubNodeSync] | list[SchemaTypeSync]:
        """
        Retrieves nodes based on filters and pagination (synchronous version).

        Args:
            kind: Node kind (e.g., "CoreSite") or type (e.g., CoreSiteSync).
            at: Optional timestamp for point-in-time query.
            branch: Branch to query. Defaults to client's default.
            timeout: Optional request timeout.
            populate_store: If True (default), updates client's NodeStore.
            offset: Optional pagination offset.
            limit: Optional pagination limit.
            include: Specific attributes/relationships to include.
            exclude: Attributes/relationships to exclude.
            fragment: If True, uses GraphQL fragments.
            prefetch_relationships: If True, prefetches related node data.
            partial_match: If True, allows partial string matching.
            property: If True, indicates direct property field query.
            parallel: If True, fetches pages in parallel (thread pool).
            order: Optional `Order` object for sorting.
            **kwargs: Filter criteria (attribute=value).

        Returns:
            List of `InfrahubNodeSync` objects (or typed subclasses) matching filters.
        """
        branch = branch or self.default_branch
        schema = self.schema.get(kind=kind, branch=branch)
        node = InfrahubNodeSync(client=self, schema=schema, branch=branch)
        if at:
            at = Timestamp(at)
        filters = kwargs
        pagination_size = self.pagination_size

        def process_page(page_offset: int, page_number: int) -> tuple[dict, ProcessRelationsNodeSync]:
            """Process a single page of results."""
            query_data = InfrahubNodeSync(client=self, schema=schema, branch=branch).generate_query_data(
                offset=offset or page_offset,
                limit=limit or pagination_size,
                filters=filters,
                include=include,
                exclude=exclude,
                fragment=fragment,
                prefetch_relationships=prefetch_relationships,
                partial_match=partial_match,
                property=property,
                order=order,
            )
            query = Query(query=query_data)
            response = self.execute_graphql(
                query=query.render(),
                branch_name=branch,
                at=at,
                timeout=timeout,
                tracker=f"query-{str(schema.kind).lower()}-page{page_number}",
            )

            process_result: ProcessRelationsNodeSync = self._process_nodes_and_relationships(
                response=response,
                schema_kind=schema.kind,
                branch=branch,
                prefetch_relationships=prefetch_relationships,
                timeout=timeout,
            )
            return response, process_result

        def process_batch() -> tuple[list[InfrahubNodeSync], list[InfrahubNodeSync]]:
            """Process queries in parallel mode."""
            nodes = []
            related_nodes = []
            batch_process = self.create_batch()

            count = self.count(kind=schema.kind, partial_match=partial_match, **filters)
            total_pages = (count + pagination_size - 1) // pagination_size

            for page_number in range(1, total_pages + 1):
                page_offset = (page_number - 1) * pagination_size
                batch_process.add(task=process_page, node=node, page_offset=page_offset, page_number=page_number)

            for _, response in batch_process.execute():
                nodes.extend(response[1]["nodes"])
                related_nodes.extend(response[1]["related_nodes"])

            return nodes, related_nodes

        def process_non_batch() -> tuple[list[InfrahubNodeSync], list[InfrahubNodeSync]]:
            """Process queries without parallel mode."""
            nodes = []
            related_nodes = []
            has_remaining_items = True
            page_number = 1

            while has_remaining_items:
                page_offset = (page_number - 1) * pagination_size
                response, process_result = process_page(page_offset, page_number)

                nodes.extend(process_result["nodes"])
                related_nodes.extend(process_result["related_nodes"])

                remaining_items = response[schema.kind].get("count", 0) - (page_offset + pagination_size)
                if remaining_items < 0 or offset is not None or limit is not None:
                    has_remaining_items = False
                page_number += 1

            return nodes, related_nodes

        # Select parallel or non-parallel processing
        nodes, related_nodes = process_batch() if parallel else process_non_batch()

        if populate_store:
            for node in nodes:
                if node.id:
                    self.store.set(node=node)
            related_nodes = list(set(related_nodes))
            for node in related_nodes:
                if node.id:
                    self.store.set(node=node)
        return nodes

    @overload
    def get(
        self,
        kind: type[SchemaTypeSync],
        raise_when_missing: Literal[False],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> SchemaTypeSync | None: ...

    @overload
    def get(
        self,
        kind: type[SchemaTypeSync],
        raise_when_missing: Literal[True],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> SchemaTypeSync: ...

    @overload
    def get(
        self,
        kind: type[SchemaTypeSync],
        raise_when_missing: bool = ...,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> SchemaTypeSync: ...

    @overload
    def get(
        self,
        kind: str,
        raise_when_missing: Literal[False],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> InfrahubNodeSync | None: ...

    @overload
    def get(
        self,
        kind: str,
        raise_when_missing: Literal[True],
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> InfrahubNodeSync: ...

    @overload
    def get(
        self,
        kind: str,
        raise_when_missing: bool = ...,
        at: Timestamp | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        id: str | None = ...,
        hfid: list[str] | None = ...,
        include: list[str] | None = ...,
        exclude: list[str] | None = ...,
        populate_store: bool = ...,
        fragment: bool = ...,
        prefetch_relationships: bool = ...,
        property: bool = ...,
        **kwargs: Any,
    ) -> InfrahubNodeSync: ...

    def get(
        self,
        kind: str | type[SchemaTypeSync],
        raise_when_missing: bool = True,
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        id: str | None = None,
        hfid: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        populate_store: bool = True,
        fragment: bool = False,
        prefetch_relationships: bool = False,
        property: bool = False,
        **kwargs: Any,
    ) -> InfrahubNodeSync | SchemaTypeSync | None:
        """
        Retrieves a single node by ID, HFID, or attributes (synchronous version).

        Args:
            kind: Node kind (e.g., "CoreSite") or type (e.g., CoreSiteSync).
            raise_when_missing: If True (default), raises `NodeNotFoundError`.
                                If False, returns None if not found.
            at: Optional timestamp for point-in-time query.
            branch: Branch to query. Defaults to client's default.
            timeout: Optional request timeout.
            id: UUID of the node.
            hfid: List of Human-Friendly IDs.
            include: Specific attributes/relationships to include.
            exclude: Attributes/relationships to exclude.
            populate_store: If True (default), updates client's NodeStore.
            fragment: If True, uses GraphQL fragments.
            prefetch_relationships: If True, prefetches related node data.
            property: If True, indicates direct property field query.
            **kwargs: Additional filter criteria (attribute=value).

        Returns:
            `InfrahubNodeSync` (or typed subclass) if found, or None.

        Raises:
            NodeNotFoundError: If `raise_when_missing` and node not found.
            IndexError: If multiple nodes match.
            ValueError: If no filters provided or HFID used incorrectly.
        """
        branch = branch or self.default_branch
        schema = self.schema.get(kind=kind, branch=branch)

        filters: MutableMapping[str, Any] = {}

        if id:
            if not is_valid_uuid(id) and isinstance(schema, NodeSchemaAPI) and schema.default_filter:
                filters[schema.default_filter] = id
            else:
                filters["ids"] = [id]
        if hfid:
            if isinstance(schema, NodeSchemaAPI) and schema.human_friendly_id:
                filters["hfid"] = hfid
            else:
                raise ValueError("Cannot filter by HFID if the node doesn't have an HFID defined")
        if kwargs:
            filters.update(kwargs)
        if len(filters) == 0:
            raise ValueError("At least one filter must be provided to get()")

        results = self.filters(
            kind=kind,
            at=at,
            branch=branch,
            timeout=timeout,
            populate_store=populate_store,
            include=include,
            exclude=exclude,
            fragment=fragment,
            prefetch_relationships=prefetch_relationships,
            property=property,
            **filters,
        )

        if len(results) == 0 and raise_when_missing:
            raise NodeNotFoundError(branch_name=branch, node_type=schema.kind, identifier=filters)
        if len(results) == 0 and not raise_when_missing:
            return None
        if len(results) > 1:
            raise IndexError("More than 1 node returned")

        return results[0]

    def create_batch(self, return_exceptions: bool = False) -> InfrahubBatchSync:
        """
        Creates an `InfrahubBatchSync` for managing concurrent synchronous tasks using a thread pool.

        Note: Due to the nature of thread pools, execution order of tasks within the batch
        is not guaranteed. Avoid using for operations with strong interdependencies.

        Args:
            return_exceptions: If True, exceptions from tasks are returned as results
                               instead of being raised.

        Returns:
            An `InfrahubBatchSync` instance.
        """
        return InfrahubBatchSync(
            max_concurrent_execution=self.max_concurrent_execution, return_exceptions=return_exceptions
        )

    def get_list_repositories(
        self, branches: dict[str, BranchData] | None = None, kind: str = "CoreGenericRepository"
    ) -> dict[str, RepositoryData]:
        """
        Retrieves a list of repositories and their branch information.

        Note: This method is deprecated in the async client and not implemented
              in the sync client.

        Raises:
            NotImplementedError
        """
        raise NotImplementedError(
            "This method is deprecated in the async client and won't be implemented in the sync client."
        )

    def query_gql_query(
        self,
        name: str,
        variables: dict | None = None,
        update_group: bool = False,
        subscribers: list[str] | None = None,
        params: dict | None = None,
        branch_name: str | None = None,
        at: str | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> dict:
        """
        Executes a pre-defined GraphQL query stored on Infrahub by name (synchronous version).

        Args:
            name: Name of the stored GraphQL query.
            variables: Optional dictionary of variables.
            update_group: If True, associates query with current tracking group.
            subscribers: Optional list of subscriber identifiers.
            params: Optional dictionary of additional URL parameters.
            branch_name: Branch to execute against. Defaults to client's default.
            at: Optional timestamp for point-in-time query.
            timeout: Optional request timeout.
            tracker: Optional tracker string for request headers.
            raise_for_error: If True (default), raises on HTTP/GraphQL errors.

        Returns:
            Dictionary containing query response data.

        Raises:
            httpx.HTTPStatusError: For HTTP errors if `raise_for_error` is True.
        """
        url = f"{self.address}/api/query/{name}"
        url_params = copy.deepcopy(params or {})
        headers = copy.copy(self.headers or {})

        if self.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        if branch_name:
            url_params["branch"] = branch_name
        if at:
            url_params["at"] = at
        if subscribers:
            url_params["subscribers"] = subscribers

        url_params["update_group"] = str(update_group).lower()

        if url_params:
            url_params_str = []
            url_params_dict = {}
            for key, value in url_params.items():
                if isinstance(value, (list)):
                    for item in value:
                        url_params_str.append((key, item))
                else:
                    url_params_dict[key] = value

            url += "?"
            if url_params_dict:
                url += urlencode(url_params_dict) + "&"
            if url_params_str:
                url += urlencode(url_params_str)

        payload = {}
        if variables:
            payload["variables"] = variables

        resp = self._post(
            url=url,
            headers=headers,
            payload=payload,
            timeout=timeout or self.default_timeout,
        )

        if raise_for_error:
            resp.raise_for_status()

        return decode_json(response=resp)

    def get_diff_summary(
        self,
        branch: str,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> list[NodeDiff]:
        """
        Retrieves a diff summary for a branch (synchronous version).

        Args:
            branch: Name of the branch.
            timeout: Optional request timeout.
            tracker: Optional tracker string for request headers.
            raise_for_error: If True (default), raises on HTTP/GraphQL errors.

        Returns:
            List of `NodeDiff` objects representing changes.
        """
        query = get_diff_summary_query()
        response = self.execute_graphql(
            query=query,
            branch_name=branch,
            timeout=timeout,
            tracker=tracker,
            raise_for_error=raise_for_error,
            variables={"branch_name": branch},
        )

        node_diffs: list[NodeDiff] = []
        diff_tree = response["DiffTree"]

        if diff_tree is None or "nodes" not in diff_tree:
            return []
        for node_dict in diff_tree["nodes"]:
            node_diff = diff_tree_node_to_node_diff(node_dict=node_dict, branch_name=branch)
            node_diffs.append(node_diff)

        return node_diffs

    @overload
    def allocate_next_ip_address(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> SchemaTypeSync: ...

    @overload
    def allocate_next_ip_address(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> SchemaTypeSync | None: ...

    @overload
    def allocate_next_ip_address(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> SchemaTypeSync: ...

    @overload
    def allocate_next_ip_address(
        self,
        resource_pool: CoreNodeSync,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> CoreNodeSync: ...

    @overload
    def allocate_next_ip_address(
        self,
        resource_pool: CoreNodeSync,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> CoreNodeSync | None: ...

    @overload
    def allocate_next_ip_address(
        self,
        resource_pool: CoreNodeSync,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        address_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> CoreNodeSync | None: ...

    def allocate_next_ip_address(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync] | None = None,  # noqa: ARG002
        identifier: str | None = None,
        prefix_length: int | None = None,
        address_type: str | None = None,
        data: dict[str, Any] | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> CoreNodeSync | SchemaTypeSync | None:
        """
        Allocates next IP address from a pool (synchronous version).

        Args:
            resource_pool: `CoreIPAddressPool` node.
            kind: Optional specific type of `CoreIPAddress` to expect.
            identifier: Optional identifier for idempotent allocation.
            prefix_length: Optional desired prefix length.
            address_type: Optional specific kind of IP address if pool supports multiple.
            data: Optional attributes for the new IP address node.
            branch: Branch for allocation. Defaults to client's default.
            timeout: Optional request timeout.
            tracker: Optional tracker string.
            raise_for_error: If True (default), raises on errors.
                             If False, returns None on allocation failure.

        Returns:
            Allocated `CoreIPAddress` node (or typed subclass), or None.

        Raises:
            ValueError: If `resource_pool` is not "CoreIPAddressPool".
            GraphQLError: If allocation fails and `raise_for_error` is True.
        """
        if resource_pool.get_kind() != "CoreIPAddressPool":
            raise ValueError("resource_pool is not an IP address pool")

        branch = branch or self.default_branch
        mutation_name = "IPAddressPoolGetResource"

        query = self._build_ip_address_allocation_query(
            resource_pool_id=resource_pool.id,
            identifier=identifier,
            prefix_length=prefix_length,
            address_type=address_type,
            data=data,
        )
        response = self.execute_graphql(
            query=query.render(), branch_name=branch, timeout=timeout, tracker=tracker, raise_for_error=raise_for_error
        )

        if response[mutation_name]["ok"]:
            resource_details = response[mutation_name]["node"]
            return self.get(kind=resource_details["kind"], id=resource_details["id"], branch=branch)
        return None

    @overload
    def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> SchemaTypeSync: ...

    @overload
    def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> SchemaTypeSync | None: ...

    @overload
    def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync],
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> SchemaTypeSync: ...

    @overload
    def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNodeSync,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[True] = True,
    ) -> CoreNodeSync: ...

    @overload
    def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNodeSync,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: Literal[False] = False,
    ) -> CoreNodeSync | None: ...

    @overload
    def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNodeSync,
        kind: None = ...,
        identifier: str | None = ...,
        prefix_length: int | None = ...,
        member_type: str | None = ...,
        prefix_type: str | None = ...,
        data: dict[str, Any] | None = ...,
        branch: str | None = ...,
        timeout: int | None = ...,
        tracker: str | None = ...,
        raise_for_error: bool = ...,
    ) -> CoreNodeSync | None: ...

    def allocate_next_ip_prefix(
        self,
        resource_pool: CoreNodeSync,
        kind: type[SchemaTypeSync] | None = None,  # noqa: ARG002
        identifier: str | None = None,
        prefix_length: int | None = None,
        member_type: str | None = None,
        prefix_type: str | None = None,
        data: dict[str, Any] | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool = True,
    ) -> CoreNodeSync | SchemaTypeSync | None:
        """
        Allocates next IP prefix from a pool (synchronous version).

        Args:
            resource_pool: `CoreIPPrefixPool` node.
            kind: Optional specific type of `CoreIPPrefix` to expect.
            identifier: Optional identifier for idempotent allocation.
            prefix_length: Optional desired prefix length.
            member_type: Optional member type (e.g., "prefix", "address").
            prefix_type: Optional specific kind of IP prefix if pool supports multiple.
            data: Optional attributes for the new IP prefix node.
            branch: Branch for allocation. Defaults to client's default.
            timeout: Optional request timeout.
            tracker: Optional tracker string.
            raise_for_error: If True (default), raises on errors.
                             If False, returns None on allocation failure.

        Returns:
            Allocated `CoreIPPrefix` node (or typed subclass), or None.

        Raises:
            ValueError: If `resource_pool` is not "CoreIPPrefixPool".
            GraphQLError: If allocation fails and `raise_for_error` is True.
        """
        if resource_pool.get_kind() != "CoreIPPrefixPool":
            raise ValueError("resource_pool is not an IP prefix pool")

        branch = branch or self.default_branch
        mutation_name = "IPPrefixPoolGetResource"

        query = self._build_ip_prefix_allocation_query(
            resource_pool_id=resource_pool.id,
            identifier=identifier,
            prefix_length=prefix_length,
            member_type=member_type,
            prefix_type=prefix_type,
            data=data,
        )
        response = self.execute_graphql(
            query=query.render(), branch_name=branch, timeout=timeout, tracker=tracker, raise_for_error=raise_for_error
        )

        if response[mutation_name]["ok"]:
            resource_details = response[mutation_name]["node"]
            return self.get(kind=resource_details["kind"], id=resource_details["id"], branch=branch)
        return None

    def repository_update_commit(
        self, branch_name: str, repository_id: str, commit: str, is_read_only: bool = False
    ) -> bool:
        """
        Updates the commit SHA for a repository on a branch.

        Note: This method is deprecated in the async client and not implemented
              in the sync client.

        Raises:
            NotImplementedError
        """
        raise NotImplementedError(
            "This method is deprecated in the async client and won't be implemented in the sync client."
        )

    @handle_relogin_sync
    def _get(self, url: str, headers: dict | None = None, timeout: int | None = None) -> httpx.Response:
        """
        Executes an HTTP GET request with login handling (synchronous version).

        Args:
            url: The URL for the GET request.
            headers: Optional request headers.
            timeout: Optional request timeout.

        Returns:
            An `httpx.Response` object.

        Raises:
            ServerNotReachableError: If the server is not reachable.
            ServerNotResponsiveError: If the server times out.
        """
        self.login()

        headers = headers or {}
        base_headers = copy.copy(self.headers or {})
        headers.update(base_headers)

        return self._request(url=url, method=HTTPMethod.GET, headers=headers, timeout=timeout or self.default_timeout)

    @handle_relogin_sync
    def _post(self, url: str, payload: dict, headers: dict | None = None, timeout: int | None = None) -> httpx.Response:
        """
        Executes an HTTP POST request with login handling (synchronous version).

        Args:
            url: The URL for the POST request.
            payload: The request payload.
            headers: Optional request headers.
            timeout: Optional request timeout.

        Returns:
            An `httpx.Response` object.

        Raises:
            ServerNotReachableError: If the server is not reachable.
            ServerNotResponsiveError: If the server times out.
        """
        self.login()

        headers = headers or {}
        base_headers = copy.copy(self.headers or {})
        headers.update(base_headers)

        return self._request(
            url=url, method=HTTPMethod.POST, payload=payload, headers=headers, timeout=timeout or self.default_timeout
        )

    def _request(
        self, url: str, method: HTTPMethod, headers: dict[str, Any], timeout: int, payload: dict | None = None
    ) -> httpx.Response:
        """
        Internal method for making HTTP requests (synchronous version).

        Uses the configured synchronous requester and records the response.

        Args:
            url: Request URL.
            method: HTTP method.
            headers: Request headers.
            timeout: Request timeout.
            payload: Optional request payload.

        Returns:
            An `httpx.Response` object.
        """
        response = self._request_method(url=url, method=method, headers=headers, timeout=timeout, payload=payload)
        self._record(response)
        return response

    def _default_request_method(
        self, url: str, method: HTTPMethod, headers: dict[str, Any], timeout: int, payload: dict | None = None
    ) -> httpx.Response:
        """
        Default synchronous HTTP request method using `httpx.Client`.

        Handles proxy and TLS settings.

        Args:
            url: Request URL.
            method: HTTP method.
            headers: Request headers.
            timeout: Request timeout.
            payload: Optional request payload.

        Returns:
            An `httpx.Response` object.

        Raises:
            ServerNotReachableError: If a network error occurs.
            ServerNotResponsiveError: If a read timeout occurs.
        """
        params: dict[str, Any] = {}
        if payload:
            params["json"] = payload

        proxy_config: dict[str, str | dict[str, httpx.HTTPTransport]] = {}
        if self.config.proxy:
            proxy_config["proxy"] = self.config.proxy
        elif self.config.proxy_mounts.is_set:
            proxy_config["mounts"] = {
                key: httpx.HTTPTransport(proxy=value)
                for key, value in self.config.proxy_mounts.model_dump(by_alias=True).items()
            }

        with httpx.Client(
            **proxy_config,  # type: ignore[arg-type]
            verify=self.config.tls_ca_file if self.config.tls_ca_file else not self.config.tls_insecure,
        ) as client:
            try:
                response = client.request(
                    method=method.value,
                    url=url,
                    headers=headers,
                    timeout=timeout,
                    **params,
                )
            except httpx.NetworkError as exc:
                raise ServerNotReachableError(address=self.address) from exc
            except httpx.ReadTimeout as exc:
                raise ServerNotResponsiveError(url=url, timeout=timeout) from exc

        return response

    def refresh_login(self) -> None:
        """
        Refreshes authentication token (synchronous version).

        Updates `self.access_token` and "Authorization" header.
        Called automatically by decorated request methods on token expiry.

        Raises:
            httpx.HTTPStatusError: If refresh request fails.
        """
        if not self.refresh_token:
            return

        url = f"{self.address}/api/auth/refresh"
        response = self._request(
            url=url,
            method=HTTPMethod.POST,
            headers={"content-type": "application/json", "Authorization": f"Bearer {self.refresh_token}"},
            timeout=self.default_timeout,
        )

        response.raise_for_status()
        data = decode_json(response=response)
        self.access_token = data["access_token"]
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    def login(self, refresh: bool = False) -> None:
        """
        Logs into Infrahub or refreshes session (synchronous version).

        Performs full login if no token or `refresh` is False.
        Attempts token refresh if `refresh` is True and refresh token exists.
        Updates `self.access_token`, `self.refresh_token`, and "Authorization" header.

        Args:
            refresh: If True, attempts to refresh token if available.

        Raises:
            AuthenticationError: On authentication failure.
            httpx.HTTPStatusError: For other HTTP errors.
        """
        if not self.config.password_authentication:
            return

        if self.access_token and not refresh:
            return

        if self.refresh_token and refresh:
            try:
                self.refresh_login()
                return
            except httpx.HTTPStatusError as exc:
                # If we got a 401 while trying to refresh a token we must restart the authentication process
                # Other status codes indicate other errors
                if exc.response.status_code != 401:
                    response = exc.response.json()
                    errors = response.get("errors", [])
                    messages = [error.get("message") for error in errors]
                    raise AuthenticationError(" | ".join(messages)) from exc

        url = f"{self.address}/api/auth/login"
        response = self._request(
            url=url,
            method=HTTPMethod.POST,
            payload={"username": self.config.username, "password": self.config.password},
            headers={"content-type": "application/json"},
            timeout=self.default_timeout,
        )

        response.raise_for_status()
        data = decode_json(response=response)
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    def __enter__(self) -> Self:
        """Enters a synchronous context, returning the client instance."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """
        Exits a synchronous context.

        If client was in TRACKING mode and no exception occurred,
        finalizes group context (e.g., calls `update_group()`).
        Resets client mode to DEFAULT.
        """
        if exc_type is None and self.mode == InfrahubClientMode.TRACKING:
            self.group_context.update_group()

        self.mode = InfrahubClientMode.DEFAULT
