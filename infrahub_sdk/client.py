from __future__ import annotations

import asyncio
import copy
import logging
import time
import warnings
from collections.abc import Coroutine, Mapping, MutableMapping
from datetime import datetime
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
    MUTATION_QUERY_TASK,
    BranchData,
    InfrahubBranchManager,
    InfrahubBranchManagerSync,
)
from .config import Config
from .constants import InfrahubClientMode
from .convert_object_type import CONVERT_OBJECT_MUTATION, ConversionFieldInput
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

    from httpx._transports.base import AsyncBaseTransport, BaseTransport
    from httpx._types import ProxyTypes

    from .context import RequestContext


SchemaType = TypeVar("SchemaType", bound=CoreNode)
SchemaTypeSync = TypeVar("SchemaTypeSync", bound=CoreNodeSync)


class ProcessRelationsNode(TypedDict):
    nodes: list[InfrahubNode]
    related_nodes: list[InfrahubNode]


class ProxyConfig(TypedDict):
    proxy: ProxyTypes | None
    mounts: Mapping[str, AsyncBaseTransport | None] | None


class ProxyConfigSync(TypedDict):
    proxy: ProxyTypes | None
    mounts: Mapping[str, BaseTransport | None] | None


class ProcessRelationsNodeSync(TypedDict):
    nodes: list[InfrahubNodeSync]
    related_nodes: list[InfrahubNodeSync]


def handle_relogin(
    func: Callable[..., Coroutine[Any, Any, httpx.Response]],
) -> Callable[..., Coroutine[Any, Any, httpx.Response]]:
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


def handle_relogin_sync(func: Callable[..., httpx.Response]) -> Callable[..., httpx.Response]:
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


def raise_for_error_deprecation_warning(value: bool | None) -> None:
    if value is not None:
        warnings.warn(
            "Using `raise_for_error` is deprecated, use `try/except` to handle errors.",
            DeprecationWarning,
            stacklevel=1,
        )


class BaseClient:
    """Base class for InfrahubClient and InfrahubClientSync"""

    def __init__(
        self,
        address: str = "",
        config: Config | dict[str, Any] | None = None,
    ) -> None:
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
        _ = self.config.tls_context  # Early load of the TLS context to catch errors

    def _initialize(self) -> None:
        """Sets the properties for each version of the client"""

    def _record(self, response: httpx.Response) -> None:
        self.config.custom_recorder.record(response)

    def _echo(self, url: str, query: str, variables: dict | None = None) -> None:
        if self.config.echo_graphql_queries:
            print(f"URL: {url}")
            print(f"QUERY:\n{query}")
            if variables:
                print(f"VARIABLES:\n{ujson.dumps(variables, indent=4)}\n")

    @property
    def request_context(self) -> RequestContext | None:
        return self._request_context

    @request_context.setter
    def request_context(self, request_context: RequestContext) -> None:
        self._request_context = request_context

    def start_tracking(
        self,
        identifier: str | None = None,
        params: dict[str, Any] | None = None,
        delete_unused_nodes: bool = False,
        group_type: str | None = None,
        group_params: dict[str, Any] | None = None,
        branch: str | None = None,
    ) -> Self:
        self.mode = InfrahubClientMode.TRACKING
        identifier = identifier or self.identifier or "python-sdk"
        self.set_context_properties(
            identifier=identifier,
            params=params,
            delete_unused_nodes=delete_unused_nodes,
            group_type=group_type,
            group_params=group_params,
            branch=branch,
        )
        return self

    def set_context_properties(
        self,
        identifier: str,
        params: dict[str, str] | None = None,
        delete_unused_nodes: bool = True,
        reset: bool = True,
        group_type: str | None = None,
        group_params: dict[str, Any] | None = None,
        branch: str | None = None,
    ) -> None:
        if reset:
            if isinstance(self, InfrahubClient):
                self.group_context = InfrahubGroupContext(self)
            elif isinstance(self, InfrahubClientSync):
                self.group_context = InfrahubGroupContextSync(self)

        self.group_context.set_properties(
            identifier=identifier,
            params=params,
            delete_unused_nodes=delete_unused_nodes,
            group_type=group_type,
            group_params=group_params,
            branch=branch or self.default_branch,
        )

    def _graphql_url(
        self,
        branch_name: str | None = None,
        at: str | Timestamp | None = None,
    ) -> str:
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
            mutation="InfrahubIPAddressPoolGetResource",
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
            mutation="InfrahubIPPrefixPoolGetResource",
            query={"ok": None, "node": {"id": None, "kind": None, "identifier": None, "display_label": None}},
            input_data={"data": input_data},
        )


class InfrahubClient(BaseClient):
    """GraphQL Client to interact with Infrahub."""

    group_context: InfrahubGroupContext

    def _initialize(self) -> None:
        self.schema = InfrahubSchema(self)
        self.branch = InfrahubBranchManager(self)
        self.object_store = ObjectStore(self)
        self.store = NodeStore(default_branch=self.default_branch)
        self.task = InfrahubTaskManager(self)
        self._request_method: AsyncRequester = self.config.requester or self._default_request_method
        self.group_context = InfrahubGroupContext(self)

    async def get_version(self) -> str:
        """Return the Infrahub version."""
        response = await self.execute_graphql(query="query { InfrahubInfo { version }}")
        return response.get("InfrahubInfo", {}).get("version", "")

    async def get_user(self) -> dict:
        """Return user information"""
        return await self.execute_graphql(query=QUERY_USER)

    async def get_user_permissions(self) -> dict:
        """Return user permissions"""
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
        branch = branch or self.default_branch

        schema = await self.schema.get(kind=kind, branch=branch, timeout=timeout)

        if not data and not kwargs:
            raise ValueError("Either data or a list of keywords but be provided")

        return InfrahubNode(client=self, schema=schema, branch=branch, data=data or kwargs)

    async def delete(self, kind: str | type[SchemaType], id: str, branch: str | None = None) -> None:
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
        include: list[str] | None,
        timeout: int | None = None,
    ) -> ProcessRelationsNode:
        """Processes InfrahubNode and their Relationships from the GraphQL query response.

        Args:
            response (dict[str, Any]): The response from the GraphQL query.
            schema_kind (str): The kind of schema being queried.
            branch (str): The branch name.
            prefetch_relationships (bool): Flag to indicate whether to prefetch relationship data.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.

        Returns:
            ProcessRelationsNodeSync: A TypedDict containing two lists:
                - 'nodes': A list of InfrahubNode objects representing the nodes processed.
                - 'related_nodes': A list of InfrahubNode objects representing the related nodes
        """

        nodes: list[InfrahubNode] = []
        related_nodes: list[InfrahubNode] = []

        for item in response.get(schema_kind, {}).get("edges", []):
            node = await InfrahubNode.from_graphql(client=self, branch=branch, data=item, timeout=timeout)
            nodes.append(node)

            if prefetch_relationships or (include and any(rel in include for rel in node._relationships)):
                await node._process_relationships(
                    node_data=item,
                    branch=branch,
                    related_nodes=related_nodes,
                    timeout=timeout,
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
        """Return the number of nodes of a given kind."""
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
        """Retrieve all nodes of a given kind

        Args:
            kind (str): kind of the nodes to query
            at (Timestamp, optional): Time of the query. Defaults to Now.
            branch (str, optional): Name of the branch to query from. Defaults to default_branch.
            populate_store (bool, optional): Flag to indicate whether to populate the store with the retrieved nodes.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.
            offset (int, optional): The offset for pagination.
            limit (int, optional): The limit for pagination.
            include (list[str], optional): List of attributes or relationships to include in the query.
            exclude (list[str], optional): List of attributes or relationships to exclude from the query.
            fragment (bool, optional): Flag to use GraphQL fragments for generic schemas.
            prefetch_relationships (bool, optional): Flag to indicate whether to prefetch related node data.
            parallel (bool, optional): Whether to use parallel processing for the query.
            order (Order, optional): Ordering related options. Setting `disable=True` enhances performances.

        Returns:
            list[InfrahubNode]: List of Nodes
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
        """Retrieve nodes of a given kind based on provided filters.

        Args:
            kind (str): kind of the nodes to query
            at (Timestamp, optional): Time of the query. Defaults to Now.
            branch (str, optional): Name of the branch to query from. Defaults to default_branch.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.
            populate_store (bool, optional): Flag to indicate whether to populate the store with the retrieved nodes.
            offset (int, optional): The offset for pagination.
            limit (int, optional): The limit for pagination.
            include (list[str], optional): List of attributes or relationships to include in the query.
            exclude (list[str], optional): List of attributes or relationships to exclude from the query.
            fragment (bool, optional): Flag to use GraphQL fragments for generic schemas.
            prefetch_relationships (bool, optional): Flag to indicate whether to prefetch related node data.
            partial_match (bool, optional): Allow partial match of filter criteria for the query.
            parallel (bool, optional): Whether to use parallel processing for the query.
            order (Order, optional): Ordering related options. Setting `disable=True` enhances performances.
            **kwargs (Any): Additional filter criteria for the query.

        Returns:
            list[InfrahubNodeSync]: List of Nodes that match the given filters.
        """
        branch = branch or self.default_branch
        schema = await self.schema.get(kind=kind, branch=branch)
        if at:
            at = Timestamp(at)

        filters = kwargs
        pagination_size = self.pagination_size

        async def process_page(page_offset: int, page_number: int) -> tuple[dict, ProcessRelationsNode]:
            """Process a single page of results."""
            query_data = await InfrahubNode(client=self, schema=schema, branch=branch).generate_query_data(
                offset=page_offset if offset is None else offset,
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
                include=include,
            )
            return response, process_result

        async def process_batch() -> tuple[list[InfrahubNode], list[InfrahubNode]]:
            """Process queries in parallel mode."""
            nodes = []
            related_nodes = []
            batch_process = await self.create_batch()
            count = await self.count(kind=schema.kind, branch=branch, partial_match=partial_match, **filters)
            total_pages = (count + pagination_size - 1) // pagination_size

            for page_number in range(1, total_pages + 1):
                page_offset = (page_number - 1) * pagination_size
                batch_process.add(task=process_page, page_offset=page_offset, page_number=page_number)

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
                response, process_result = await process_page(page_offset=page_offset, page_number=page_number)

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
        """Return a cloned version of the client using the same configuration"""
        return InfrahubClient(config=self.config.clone(branch=branch))

    async def execute_graphql(
        self,
        query: str,
        variables: dict | None = None,
        branch_name: str | None = None,
        at: str | Timestamp | None = None,
        timeout: int | None = None,
        raise_for_error: bool | None = None,
        tracker: str | None = None,
    ) -> dict:
        """Execute a GraphQL query (or mutation).
        If retry_on_failure is True, the query will retry until the server becomes reacheable.

        Args:
            query (_type_): GraphQL Query to execute, can be a query or a mutation
            variables (dict, optional): Variables to pass along with the GraphQL query. Defaults to None.
            branch_name (str, optional): Name of the branch on which the query will be executed. Defaults to None.
            at (str, optional): Time when the query should be executed. Defaults to None.
            timeout (int, optional): Timeout in second for the query. Defaults to None.
            raise_for_error (bool | None, optional): Deprecated. Controls only HTTP status handling.
                - None (default) or True: HTTP errors raise via resp.raise_for_status().
                - False: HTTP errors are not automatically raised. Defaults to None.

        Raises:
            GraphQLError: When the GraphQL response contains errors.

        Returns:
            dict: The GraphQL data payload (response["data"]).
        """
        raise_for_error_deprecation_warning(value=raise_for_error)

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

                if raise_for_error in (None, True):
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
        self,
        url: str,
        payload: dict,
        headers: dict | None = None,
        timeout: int | None = None,
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
            url=url,
            method=HTTPMethod.POST,
            headers=headers,
            timeout=timeout or self.default_timeout,
            payload=payload,
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
            url=url,
            method=HTTPMethod.GET,
            headers=headers,
            timeout=timeout or self.default_timeout,
        )

    async def _request(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        response = await self._request_method(url=url, method=method, headers=headers, timeout=timeout, payload=payload)
        self._record(response)
        return response

    async def _default_request_method(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        params: dict[str, Any] = {}
        if payload:
            params["json"] = payload

        proxy_config: ProxyConfig = {"proxy": None, "mounts": None}
        if self.config.proxy:
            proxy_config["proxy"] = self.config.proxy
        elif self.config.proxy_mounts.is_set:
            proxy_config["mounts"] = {
                key: httpx.AsyncHTTPTransport(proxy=value)
                for key, value in self.config.proxy_mounts.model_dump(by_alias=True).items()
            }

        async with httpx.AsyncClient(
            **proxy_config,
            verify=self.config.tls_context,
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
        if not self.refresh_token:
            return

        url = f"{self.address}/api/auth/refresh"
        response = await self._request(
            url=url,
            method=HTTPMethod.POST,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {self.refresh_token}",
            },
            timeout=self.default_timeout,
        )

        response.raise_for_status()
        data = decode_json(response=response)
        self.access_token = data["access_token"]
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    async def login(self, refresh: bool = False) -> None:
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
                    errors = response.get("errors")
                    messages = [error.get("message") for error in errors]
                    raise AuthenticationError(" | ".join(messages)) from exc

        url = f"{self.address}/api/auth/login"
        response = await self._request(
            url=url,
            method=HTTPMethod.POST,
            payload={
                "username": self.config.username,
                "password": self.config.password,
            },
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
        raise_for_error: bool | None = None,
    ) -> dict:
        raise_for_error_deprecation_warning(value=raise_for_error)

        url = f"{self.address}/api/query/{name}"
        url_params = copy.deepcopy(params or {})
        url_params["branch"] = branch_name or self.default_branch

        headers = copy.copy(self.headers or {})

        if self.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

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

        if raise_for_error in (None, True):
            resp.raise_for_status()

        return decode_json(response=resp)

    async def create_diff(
        self,
        branch: str,
        name: str,
        from_time: datetime,
        to_time: datetime,
        wait_until_completion: bool = True,
    ) -> bool | str:
        if from_time > to_time:
            raise ValueError("from_time must be <= to_time")
        input_data = {
            "wait_until_completion": wait_until_completion,
            "data": {
                "name": name,
                "branch": branch,
                "from_time": from_time.isoformat(),
                "to_time": to_time.isoformat(),
            },
        }

        mutation_query = MUTATION_QUERY_TASK if not wait_until_completion else {"ok": None}
        query = Mutation(mutation="DiffUpdate", input_data=input_data, query=mutation_query)
        response = await self.execute_graphql(query=query.render(), tracker="mutation-diff-update")

        if not wait_until_completion and "task" in response["DiffUpdate"]:
            return response["DiffUpdate"]["task"]["id"]

        return response["DiffUpdate"]["ok"]

    async def get_diff_summary(
        self,
        branch: str,
        name: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool | None = None,
    ) -> list[NodeDiff]:
        query = get_diff_summary_query()
        input_data = {"branch_name": branch}
        if name:
            input_data["name"] = name
        if from_time and to_time and from_time > to_time:
            raise ValueError("from_time must be <= to_time")
        if from_time:
            input_data["from_time"] = from_time.isoformat()
        if to_time:
            input_data["to_time"] = to_time.isoformat()
        response = await self.execute_graphql(
            query=query,
            branch_name=branch,
            timeout=timeout,
            tracker=tracker,
            raise_for_error=raise_for_error,
            variables=input_data,
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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = None,
    ) -> CoreNode | SchemaType | None:
        """Allocate a new IP address by using the provided resource pool.

        Args:
            resource_pool (InfrahubNode): Node corresponding to the pool to allocate resources from.
            identifier (str, optional): Value to perform idempotent allocation, the same resource will be returned for a given identifier.
            prefix_length (int, optional): Length of the prefix to set on the address to allocate.
            address_type (str, optional): Kind of the address to allocate.
            data (dict, optional): A key/value map to use to set attributes values on the allocated address.
            branch (str, optional): Name of the branch to allocate from. Defaults to default_branch.
            timeout (int, optional): Flag to indicate whether to populate the store with the retrieved nodes.
            tracker (str, optional): The offset for pagination.
            raise_for_error (bool, optional): Deprecated, raise an error if the HTTP status is not 2XX.
        Returns:
            InfrahubNode: Node corresponding to the allocated resource.
        """
        if resource_pool.get_kind() != "CoreIPAddressPool":
            raise ValueError("resource_pool is not an IP address pool")

        branch = branch or self.default_branch
        mutation_name = "InfrahubIPAddressPoolGetResource"

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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = None,
    ) -> CoreNode | SchemaType | None:
        """Allocate a new IP prefix by using the provided resource pool.

        Args:
            resource_pool: Node corresponding to the pool to allocate resources from.
            identifier: Value to perform idempotent allocation, the same resource will be returned for a given identifier.
            prefix_length: Length of the prefix to allocate.
            member_type: Member type of the prefix to allocate.
            prefix_type: Kind of the prefix to allocate.
            data: A key/value map to use to set attributes values on the allocated prefix.
            branch: Name of the branch to allocate from. Defaults to default_branch.
            timeout: Flag to indicate whether to populate the store with the retrieved nodes.
            tracker: The offset for pagination.
            raise_for_error (bool, optional): Deprecated, raise an error if the HTTP status is not 2XX.
        Returns:
            InfrahubNode: Node corresponding to the allocated resource.
        """
        if resource_pool.get_kind() != "CoreIPPrefixPool":
            raise ValueError("resource_pool is not an IP prefix pool")

        branch = branch or self.default_branch
        mutation_name = "InfrahubIPPrefixPoolGetResource"

        query = self._build_ip_prefix_allocation_query(
            resource_pool_id=resource_pool.id,
            identifier=identifier,
            prefix_length=prefix_length,
            member_type=member_type,
            prefix_type=prefix_type,
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

    async def create_batch(self, return_exceptions: bool = False) -> InfrahubBatch:
        return InfrahubBatch(
            max_concurrent_execution=self.max_concurrent_execution, return_exceptions=return_exceptions
        )

    async def get_list_repositories(
        self,
        branches: dict[str, BranchData] | None = None,
        kind: str = "CoreGenericRepository",
    ) -> dict[str, RepositoryData]:
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
        self,
        branch_name: str,
        repository_id: str,
        commit: str,
        is_read_only: bool = False,
    ) -> bool:
        variables = {"repository_id": str(repository_id), "commit": str(commit)}
        await self.execute_graphql(
            query=get_commit_update_mutation(is_read_only=is_read_only),
            variables=variables,
            branch_name=branch_name,
            tracker="mutation-repository-update-commit",
        )

        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None and self.mode == InfrahubClientMode.TRACKING:
            await self.group_context.update_group()

        self.mode = InfrahubClientMode.DEFAULT

    async def convert_object_type(
        self,
        node_id: str,
        target_kind: str,
        branch: str | None = None,
        fields_mapping: dict[str, ConversionFieldInput] | None = None,
    ) -> InfrahubNode:
        """
        Convert a given node to another kind on a given branch. `fields_mapping` keys are target fields names
        and its values indicate how to fill in these fields. Any mandatory field not having an equivalent field
        in the source kind should be specified in this mapping. See https://docs.infrahub.app/guides/object-convert-type
        for more information.
        """

        if fields_mapping is None:
            mapping_dict = {}
        else:
            mapping_dict = {field_name: model.model_dump(mode="json") for field_name, model in fields_mapping.items()}

        branch_name = branch or self.default_branch
        response = await self.execute_graphql(
            query=CONVERT_OBJECT_MUTATION,
            variables={
                "node_id": node_id,
                "fields_mapping": mapping_dict,
                "target_kind": target_kind,
            },
            branch_name=branch_name,
            raise_for_error=True,
        )
        return await InfrahubNode.from_graphql(client=self, branch=branch_name, data=response["ConvertObjectType"])


class InfrahubClientSync(BaseClient):
    schema: InfrahubSchemaSync
    branch: InfrahubBranchManagerSync
    object_store: ObjectStoreSync
    store: NodeStoreSync
    task: InfrahubTaskManagerSync
    group_context: InfrahubGroupContextSync

    def _initialize(self) -> None:
        self.schema = InfrahubSchemaSync(self)
        self.branch = InfrahubBranchManagerSync(self)
        self.object_store = ObjectStoreSync(self)
        self.store = NodeStoreSync(default_branch=self.default_branch)
        self.task = InfrahubTaskManagerSync(self)
        self._request_method: SyncRequester = self.config.sync_requester or self._default_request_method
        self.group_context = InfrahubGroupContextSync(self)

    def get_version(self) -> str:
        """Return the Infrahub version."""
        response = self.execute_graphql(query="query { InfrahubInfo { version }}")
        return response.get("InfrahubInfo", {}).get("version", "")

    def get_user(self) -> dict:
        """Return user information"""
        return self.execute_graphql(query=QUERY_USER)

    def get_user_permissions(self) -> dict:
        """Return user permissions"""
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
        branch = branch or self.default_branch
        schema = self.schema.get(kind=kind, branch=branch, timeout=timeout)

        if not data and not kwargs:
            raise ValueError("Either data or a list of keywords but be provided")

        return InfrahubNodeSync(client=self, schema=schema, branch=branch, data=data or kwargs)

    def delete(self, kind: str | type[SchemaTypeSync], id: str, branch: str | None = None) -> None:
        branch = branch or self.default_branch
        schema = self.schema.get(kind=kind, branch=branch)

        node = InfrahubNodeSync(client=self, schema=schema, branch=branch, data={"id": id})
        node.delete()

    def clone(self, branch: str | None = None) -> InfrahubClientSync:
        """Return a cloned version of the client using the same configuration"""
        return InfrahubClientSync(config=self.config.clone(branch=branch))

    def execute_graphql(
        self,
        query: str,
        variables: dict | None = None,
        branch_name: str | None = None,
        at: str | Timestamp | None = None,
        timeout: int | None = None,
        raise_for_error: bool | None = None,
        tracker: str | None = None,
    ) -> dict:
        """Execute a GraphQL query (or mutation).
        If retry_on_failure is True, the query will retry until the server becomes reacheable.

        Args:
            query (str): GraphQL Query to execute, can be a query or a mutation
            variables (dict, optional): Variables to pass along with the GraphQL query. Defaults to None.
            branch_name (str, optional): Name of the branch on which the query will be executed. Defaults to None.
            at (str, optional): Time when the query should be executed. Defaults to None.
            timeout (int, optional): Timeout in second for the query. Defaults to None.
            raise_for_error (bool | None, optional): Deprecated. Controls only HTTP status handling.
                - None (default) or True: HTTP errors raise via `resp.raise_for_status()`.
                - False: HTTP errors are not automatically raised.
              GraphQL errors always raise `GraphQLError`. Defaults to None.

        Raises:
            GraphQLError: When the GraphQL response contains errors.

        Returns:
            dict: The GraphQL data payload (`response["data"]`).
        """
        raise_for_error_deprecation_warning(value=raise_for_error)

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

                if raise_for_error in (None, True):
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
        kind: str | type[SchemaType],
        at: Timestamp | None = None,
        branch: str | None = None,
        timeout: int | None = None,
        partial_match: bool = False,
        **kwargs: Any,
    ) -> int:
        """Return the number of nodes of a given kind."""
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
        """Retrieve all nodes of a given kind

        Args:
            kind (str): kind of the nodes to query
            at (Timestamp, optional): Time of the query. Defaults to Now.
            branch (str, optional): Name of the branch to query from. Defaults to default_branch.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.
            populate_store (bool, optional): Flag to indicate whether to populate the store with the retrieved nodes.
            offset (int, optional): The offset for pagination.
            limit (int, optional): The limit for pagination.
            include (list[str], optional): List of attributes or relationships to include in the query.
            exclude (list[str], optional): List of attributes or relationships to exclude from the query.
            fragment (bool, optional): Flag to use GraphQL fragments for generic schemas.
            prefetch_relationships (bool, optional): Flag to indicate whether to prefetch related node data.
            parallel (bool, optional): Whether to use parallel processing for the query.
            order (Order, optional): Ordering related options. Setting `disable=True` enhances performances.

        Returns:
            list[InfrahubNodeSync]: List of Nodes
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
        include: list[str] | None,
        timeout: int | None = None,
    ) -> ProcessRelationsNodeSync:
        """Processes InfrahubNodeSync and their Relationships from the GraphQL query response.

        Args:
            response (dict[str, Any]): The response from the GraphQL query.
            schema_kind (str): The kind of schema being queried.
            branch (str): The branch name.
            prefetch_relationships (bool): Flag to indicate whether to prefetch relationship data.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.

        Returns:
            ProcessRelationsNodeSync: A TypedDict containing two lists:
                - 'nodes': A list of InfrahubNodeSync objects representing the nodes processed.
                - 'related_nodes': A list of InfrahubNodeSync objects representing the related nodes
        """

        nodes: list[InfrahubNodeSync] = []
        related_nodes: list[InfrahubNodeSync] = []

        for item in response.get(schema_kind, {}).get("edges", []):
            node = InfrahubNodeSync.from_graphql(client=self, branch=branch, data=item, timeout=timeout)
            nodes.append(node)

            if prefetch_relationships or (include and any(rel in include for rel in node._relationships)):
                node._process_relationships(
                    node_data=item,
                    branch=branch,
                    related_nodes=related_nodes,
                    timeout=timeout,
                )

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
        """Retrieve nodes of a given kind based on provided filters.

        Args:
            kind (str): kind of the nodes to query
            at (Timestamp, optional): Time of the query. Defaults to Now.
            branch (str, optional): Name of the branch to query from. Defaults to default_branch.
            timeout (int, optional): Overrides default timeout used when querying the GraphQL API. Specified in seconds.
            populate_store (bool, optional): Flag to indicate whether to populate the store with the retrieved nodes.
            offset (int, optional): The offset for pagination.
            limit (int, optional): The limit for pagination.
            include (list[str], optional): List of attributes or relationships to include in the query.
            exclude (list[str], optional): List of attributes or relationships to exclude from the query.
            fragment (bool, optional): Flag to use GraphQL fragments for generic schemas.
            prefetch_relationships (bool, optional): Flag to indicate whether to prefetch related node data.
            partial_match (bool, optional): Allow partial match of filter criteria for the query.
            parallel (bool, optional): Whether to use parallel processing for the query.
            order (Order, optional): Ordering related options. Setting `disable=True` enhances performances.
            **kwargs (Any): Additional filter criteria for the query.

        Returns:
            list[InfrahubNodeSync]: List of Nodes that match the given filters.
        """
        branch = branch or self.default_branch
        schema = self.schema.get(kind=kind, branch=branch)
        if at:
            at = Timestamp(at)

        filters = kwargs
        pagination_size = self.pagination_size

        def process_page(page_offset: int, page_number: int) -> tuple[dict, ProcessRelationsNodeSync]:
            """Process a single page of results."""
            query_data = InfrahubNodeSync(client=self, schema=schema, branch=branch).generate_query_data(
                offset=page_offset if offset is None else offset,
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
                include=include,
            )
            return response, process_result

        def process_batch() -> tuple[list[InfrahubNodeSync], list[InfrahubNodeSync]]:
            """Process queries in parallel mode."""
            nodes = []
            related_nodes = []
            batch_process = self.create_batch()

            count = self.count(kind=schema.kind, branch=branch, partial_match=partial_match, **filters)
            total_pages = (count + pagination_size - 1) // pagination_size

            for page_number in range(1, total_pages + 1):
                page_offset = (page_number - 1) * pagination_size
                batch_process.add(task=process_page, page_offset=page_offset, page_number=page_number)

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
                response, process_result = process_page(page_offset=page_offset, page_number=page_number)

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
        """Create a batch to execute multiple queries concurrently.

        Executing the batch will be performed using a thread pool, meaning it cannot guarantee the execution order. It is not recommended to use such
        batch to manipulate objects that depend on each others.
        """
        return InfrahubBatchSync(
            max_concurrent_execution=self.max_concurrent_execution,
            return_exceptions=return_exceptions,
        )

    def get_list_repositories(
        self,
        branches: dict[str, BranchData] | None = None,
        kind: str = "CoreGenericRepository",
    ) -> dict[str, RepositoryData]:
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
        raise_for_error: bool | None = None,
    ) -> dict:
        raise_for_error_deprecation_warning(value=raise_for_error)

        url = f"{self.address}/api/query/{name}"
        url_params = copy.deepcopy(params or {})
        url_params["branch"] = branch_name or self.default_branch

        headers = copy.copy(self.headers or {})

        if self.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

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

        if raise_for_error in (None, True):
            resp.raise_for_status()

        return decode_json(response=resp)

    def create_diff(
        self,
        branch: str,
        name: str,
        from_time: datetime,
        to_time: datetime,
        wait_until_completion: bool = True,
    ) -> bool | str:
        if from_time > to_time:
            raise ValueError("from_time must be <= to_time")
        input_data = {
            "wait_until_completion": wait_until_completion,
            "data": {
                "name": name,
                "branch": branch,
                "from_time": from_time.isoformat(),
                "to_time": to_time.isoformat(),
            },
        }

        mutation_query = MUTATION_QUERY_TASK if not wait_until_completion else {"ok": None}
        query = Mutation(mutation="DiffUpdate", input_data=input_data, query=mutation_query)
        response = self.execute_graphql(query=query.render(), tracker="mutation-diff-update")

        if not wait_until_completion and "task" in response["DiffUpdate"]:
            return response["DiffUpdate"]["task"]["id"]

        return response["DiffUpdate"]["ok"]

    def get_diff_summary(
        self,
        branch: str,
        name: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        timeout: int | None = None,
        tracker: str | None = None,
        raise_for_error: bool | None = None,
    ) -> list[NodeDiff]:
        query = get_diff_summary_query()
        input_data = {"branch_name": branch}
        if name:
            input_data["name"] = name
        if from_time and to_time and from_time > to_time:
            raise ValueError("from_time must be <= to_time")
        if from_time:
            input_data["from_time"] = from_time.isoformat()
        if to_time:
            input_data["to_time"] = to_time.isoformat()
        response = self.execute_graphql(
            query=query,
            branch_name=branch,
            timeout=timeout,
            tracker=tracker,
            raise_for_error=raise_for_error,
            variables=input_data,
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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = None,
    ) -> CoreNodeSync | SchemaTypeSync | None:
        """Allocate a new IP address by using the provided resource pool.

        Args:
            resource_pool (InfrahubNodeSync): Node corresponding to the pool to allocate resources from.
            identifier (str, optional): Value to perform idempotent allocation, the same resource will be returned for a given identifier.
            prefix_length (int, optional): Length of the prefix to set on the address to allocate.
            address_type (str, optional): Kind of the address to allocate.
            data (dict, optional): A key/value map to use to set attributes values on the allocated address.
            branch (str, optional): Name of the branch to allocate from. Defaults to default_branch.
            timeout (int, optional): Flag to indicate whether to populate the store with the retrieved nodes.
            tracker (str, optional): The offset for pagination.
            raise_for_error (bool, optional): The limit for pagination.
        Returns:
            InfrahubNodeSync: Node corresponding to the allocated resource.
        """
        if resource_pool.get_kind() != "CoreIPAddressPool":
            raise ValueError("resource_pool is not an IP address pool")

        branch = branch or self.default_branch
        mutation_name = "InfrahubIPAddressPoolGetResource"

        query = self._build_ip_address_allocation_query(
            resource_pool_id=resource_pool.id,
            identifier=identifier,
            prefix_length=prefix_length,
            address_type=address_type,
            data=data,
        )
        response = self.execute_graphql(
            query=query.render(),
            branch_name=branch,
            timeout=timeout,
            tracker=tracker,
            raise_for_error=raise_for_error,
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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = ...,
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
        raise_for_error: bool | None = None,
    ) -> CoreNodeSync | SchemaTypeSync | None:
        """Allocate a new IP prefix by using the provided resource pool.

        Args:
            resource_pool (InfrahubNodeSync): Node corresponding to the pool to allocate resources from.
            identifier (str, optional): Value to perform idempotent allocation, the same resource will be returned for a given identifier.
            size (int, optional): Length of the prefix to allocate.
            member_type (str, optional): Member type of the prefix to allocate.
            prefix_type (str, optional): Kind of the prefix to allocate.
            data (dict, optional): A key/value map to use to set attributes values on the allocated prefix.
            branch (str, optional): Name of the branch to allocate from. Defaults to default_branch.
            timeout (int, optional): Flag to indicate whether to populate the store with the retrieved nodes.
            tracker (str, optional): The offset for pagination.
            raise_for_error (bool, optional): The limit for pagination.
        Returns:
            InfrahubNodeSync: Node corresponding to the allocated resource.
        """
        if resource_pool.get_kind() != "CoreIPPrefixPool":
            raise ValueError("resource_pool is not an IP prefix pool")

        branch = branch or self.default_branch
        mutation_name = "InfrahubIPPrefixPoolGetResource"

        query = self._build_ip_prefix_allocation_query(
            resource_pool_id=resource_pool.id,
            identifier=identifier,
            prefix_length=prefix_length,
            member_type=member_type,
            prefix_type=prefix_type,
            data=data,
        )
        response = self.execute_graphql(
            query=query.render(),
            branch_name=branch,
            timeout=timeout,
            tracker=tracker,
            raise_for_error=raise_for_error,
        )

        if response[mutation_name]["ok"]:
            resource_details = response[mutation_name]["node"]
            return self.get(kind=resource_details["kind"], id=resource_details["id"], branch=branch)
        return None

    def repository_update_commit(
        self,
        branch_name: str,
        repository_id: str,
        commit: str,
        is_read_only: bool = False,
    ) -> bool:
        raise NotImplementedError(
            "This method is deprecated in the async client and won't be implemented in the sync client."
        )

    @handle_relogin_sync
    def _get(self, url: str, headers: dict | None = None, timeout: int | None = None) -> httpx.Response:
        """Execute a HTTP GET with HTTPX.

        Raises:
            ServerNotReachableError if we are not able to connect to the server
            ServerNotResponsiveError if the server didnd't respond before the timeout expired
        """
        self.login()

        headers = headers or {}
        base_headers = copy.copy(self.headers or {})
        headers.update(base_headers)

        return self._request(
            url=url,
            method=HTTPMethod.GET,
            headers=headers,
            timeout=timeout or self.default_timeout,
        )

    @handle_relogin_sync
    def _post(
        self,
        url: str,
        payload: dict,
        headers: dict | None = None,
        timeout: int | None = None,
    ) -> httpx.Response:
        """Execute a HTTP POST with HTTPX.

        Raises:
            ServerNotReachableError if we are not able to connect to the server
            ServerNotResponsiveError if the server didnd't respond before the timeout expired
        """
        self.login()

        headers = headers or {}
        base_headers = copy.copy(self.headers or {})
        headers.update(base_headers)

        return self._request(
            url=url,
            method=HTTPMethod.POST,
            payload=payload,
            headers=headers,
            timeout=timeout or self.default_timeout,
        )

    def _request(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        response = self._request_method(url=url, method=method, headers=headers, timeout=timeout, payload=payload)
        self._record(response)
        return response

    def _default_request_method(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        params: dict[str, Any] = {}
        if payload:
            params["json"] = payload

        proxy_config: ProxyConfigSync = {"proxy": None, "mounts": None}

        if self.config.proxy:
            proxy_config["proxy"] = self.config.proxy
        elif self.config.proxy_mounts.is_set:
            proxy_config["mounts"] = {
                key: httpx.HTTPTransport(proxy=value)
                for key, value in self.config.proxy_mounts.model_dump(by_alias=True).items()
            }

        with httpx.Client(
            **proxy_config,
            verify=self.config.tls_context,
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
        if not self.refresh_token:
            return

        url = f"{self.address}/api/auth/refresh"
        response = self._request(
            url=url,
            method=HTTPMethod.POST,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {self.refresh_token}",
            },
            timeout=self.default_timeout,
        )

        response.raise_for_status()
        data = decode_json(response=response)
        self.access_token = data["access_token"]
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    def login(self, refresh: bool = False) -> None:
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
                    errors = response.get("errors")
                    messages = [error.get("message") for error in errors]
                    raise AuthenticationError(" | ".join(messages)) from exc

        url = f"{self.address}/api/auth/login"
        response = self._request(
            url=url,
            method=HTTPMethod.POST,
            payload={
                "username": self.config.username,
                "password": self.config.password,
            },
            headers={"content-type": "application/json"},
            timeout=self.default_timeout,
        )

        response.raise_for_status()
        data = decode_json(response=response)
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None and self.mode == InfrahubClientMode.TRACKING:
            self.group_context.update_group()

        self.mode = InfrahubClientMode.DEFAULT

    def convert_object_type(
        self,
        node_id: str,
        target_kind: str,
        branch: str | None = None,
        fields_mapping: dict[str, ConversionFieldInput] | None = None,
    ) -> InfrahubNodeSync:
        """
        Convert a given node to another kind on a given branch. `fields_mapping` keys are target fields names
        and its values indicate how to fill in these fields. Any mandatory field not having an equivalent field
        in the source kind should be specified in this mapping. See https://docs.infrahub.app/guides/object-convert-type
        for more information.
        """

        if fields_mapping is None:
            mapping_dict = {}
        else:
            mapping_dict = {field_name: model.model_dump(mode="json") for field_name, model in fields_mapping.items()}

        branch_name = branch or self.default_branch
        response = self.execute_graphql(
            query=CONVERT_OBJECT_MUTATION,
            variables={
                "node_id": node_id,
                "fields_mapping": mapping_dict,
                "target_kind": target_kind,
            },
            branch_name=branch_name,
            raise_for_error=True,
        )
        return InfrahubNodeSync.from_graphql(client=self, branch=branch_name, data=response["ConvertObjectType"])
