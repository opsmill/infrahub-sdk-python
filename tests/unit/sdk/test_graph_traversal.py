from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.exceptions import Error, GraphQLError, NodeNotSavedError, VersionNotSupportedError
from infrahub_sdk.graph_traversal.models import PathNode, PathTraversalResult, ReachableNodesResult
from infrahub_sdk.graph_traversal.query import (
    build_path_traversal_input,
    build_reachable_nodes_input,
    is_unknown_field_error,
)
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.protocols_base import CoreNode

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI

    from .conftest import BothClients

PATH_TRAVERSAL_URL = "http://mock/graphql/main"

PATH_RESULT = {
    "paths": [
        {
            "depth": 2,
            "hops": [
                {
                    "node": {
                        "id": "n1",
                        "kind": "InterfacePhysical",
                        "label": "Physical Interface",
                        "display_label": "ha1-a",
                        "hfid": ["dev", "ha1-a"],
                    },
                    "relationship": None,
                },
                {
                    "node": {
                        "id": "n2",
                        "kind": "DcimCable",
                        "label": "Cable",
                        "display_label": "Cable-1",
                        "hfid": [],
                    },
                    "relationship": {
                        "from_rel": "connector",
                        "from_label": "Connector",
                        "to_rel": "connected_endpoints",
                        "to_label": "Connected Endpoints",
                        "kind": "Attribute",
                    },
                },
            ],
        }
    ],
    "source": {
        "id": "n1",
        "kind": "InterfacePhysical",
        "label": "Physical Interface",
        "display_label": "ha1-a",
        "hfid": [],
    },
    "destination": {"id": "n2", "kind": "DcimCable", "label": "Cable", "display_label": "Cable-1", "hfid": []},
    "count": 1,
    "excluded_kinds": ["IpamNamespace"],
}

REACHABLE_RESULT = {
    "source": {
        "id": "n1",
        "kind": "InterfacePhysical",
        "label": "Physical Interface",
        "display_label": "ha1-a",
        "hfid": [],
    },
    "dependencies": [
        {
            "node": {"id": "n2", "kind": "DcimCable", "label": "Cable", "display_label": "Cable-1", "hfid": []},
            "depth": 1,
            "path": {
                "depth": 1,
                "hops": [
                    {
                        "node": {
                            "id": "n2",
                            "kind": "DcimCable",
                            "label": "Cable",
                            "display_label": "Cable-1",
                            "hfid": [],
                        },
                        "relationship": None,
                    }
                ],
            },
        }
    ],
    "count": 1,
}


# --- input builders (pure logic) --------------------------------------------


def test_build_path_traversal_input_omits_unset() -> None:
    assert build_path_traversal_input("a", "b") == {"source_id": "a", "destination_id": "b"}


def test_build_path_traversal_input_includes_set_values() -> None:
    data = build_path_traversal_input("a", "b", max_depth=8, max_paths=5, kind_filter=["DcimCable"])
    assert data == {
        "source_id": "a",
        "destination_id": "b",
        "max_depth": 8,
        "max_paths": 5,
        "kind_filter": ["DcimCable"],
    }


def test_build_reachable_nodes_input() -> None:
    data = build_reachable_nodes_input("a", ["DcimCable"], max_results=10, shortest_paths_only=True)
    assert data == {
        "source_id": "a",
        "target_kinds": ["DcimCable"],
        "max_results": 10,
        "shortest_paths_only": True,
    }


# --- unknown-field detection (pure logic) -----------------------------------


def test_is_unknown_field_error_positive() -> None:
    errors = [{"message": "Cannot query field 'InfrahubPathTraversal' on type 'Query'."}]
    assert is_unknown_field_error(errors, "InfrahubPathTraversal") is True


def test_is_unknown_field_error_ignores_runtime_errors() -> None:
    errors = [{"message": "Source node not found: abc"}]
    assert is_unknown_field_error(errors, "InfrahubPathTraversal") is False


# --- model parsing (pure logic) ---------------------------------------------


def test_path_traversal_result_parsing() -> None:
    result = PathTraversalResult.model_validate(PATH_RESULT)
    assert result.count == 1
    assert result.excluded_kinds == ["IpamNamespace"]
    path = result.paths[0]
    assert path.depth == 2
    assert path.hops[0].relationship is None  # source-anchored first hop
    assert path.hops[1].relationship is not None
    assert path.hops[1].relationship.from_rel == "connector"
    assert result.source.hfid == []


def test_reachable_nodes_result_parsing() -> None:
    result = ReachableNodesResult.model_validate(REACHABLE_RESULT)
    assert result.count == 1
    assert result.dependencies[0].depth == 1
    assert result.dependencies[0].node.kind == "DcimCable"


def test_unbound_path_node_fetch_raises() -> None:
    node = PathNode.model_validate(PATH_RESULT["source"])
    with pytest.raises(Error, match="not bound to a client"):
        node.fetch()


async def test_kind_filter_accepts_protocol_classes(clients: BothClients, httpx_mock: HTTPXMock) -> None:
    class DcimCable(CoreNode): ...

    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        match_headers={"X-Infrahub-Tracker": "query-path-traversal"},
        json={"data": {"InfrahubPathTraversal": PATH_RESULT}},
    )
    await clients.standard.traverse_paths("a", "b", kind_filter=[DcimCable, "InterfacePhysical"])

    sent = json.loads(httpx_mock.get_requests()[0].content)
    assert sent["variables"]["data"]["kind_filter"] == ["DcimCable", "InterfacePhysical"]


async def test_traverse_paths_accepts_node_objects(
    clients: BothClients, location_schema: NodeSchemaAPI, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        match_headers={"X-Infrahub-Tracker": "query-path-traversal"},
        json={"data": {"InfrahubPathTraversal": PATH_RESULT}},
    )
    src = InfrahubNode(client=clients.standard, schema=location_schema, data={"id": "src-uuid"})
    dst = InfrahubNode(client=clients.standard, schema=location_schema, data={"id": "dst-uuid"})
    await clients.standard.traverse_paths(src, dst)

    sent = json.loads(httpx_mock.get_requests()[0].content)
    assert sent["variables"]["data"]["source_id"] == "src-uuid"
    assert sent["variables"]["data"]["destination_id"] == "dst-uuid"


async def test_traverse_paths_node_without_id_raises(clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    node = InfrahubNode(client=clients.standard, schema=location_schema, data={})
    with pytest.raises(Error, match="unsaved node as the graph traversal source") as exc_info:
        await clients.standard.traverse_paths(node, "dst-uuid")
    # The generic NodeNotSavedError is wrapped with traversal-specific context.
    assert isinstance(exc_info.value.__cause__, NodeNotSavedError)


# --- client methods (httpx_mock at the transport boundary) ------------------


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_traverse_paths_query_and_parse(clients: BothClients, client_type: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        match_headers={"X-Infrahub-Tracker": "query-path-traversal"},
        json={"data": {"InfrahubPathTraversal": PATH_RESULT}},
    )
    if client_type == "standard":
        result = await clients.standard.traverse_paths("a", "b", max_depth=8, kind_filter=["DcimCable"])
    else:
        result = clients.sync.traverse_paths("a", "b", max_depth=8, kind_filter=["DcimCable"])

    assert isinstance(result, PathTraversalResult)
    assert result.count == 1
    relationship = result.paths[0].hops[1].relationship
    assert relationship is not None
    assert relationship.to_rel == "connected_endpoints"
    assert result.excluded_kinds == ["IpamNamespace"]
    # nodes are bound to the originating client so .fetch() can resolve them
    expected_client = clients.standard if client_type == "standard" else clients.sync
    assert result.paths[0].hops[0].node._client is expected_client
    assert result.source._client is expected_client


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_path_exists_true(clients: BothClients, client_type: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        match_headers={"X-Infrahub-Tracker": "query-path-traversal"},
        json={"data": {"InfrahubPathTraversal": PATH_RESULT}},
    )
    if client_type == "standard":
        exists = await clients.standard.path_exists("a", "b")
    else:
        exists = clients.sync.path_exists("a", "b")

    assert exists is True
    # path_exists only needs a single path to answer the question
    sent = json.loads(httpx_mock.get_requests()[0].content)
    assert sent["variables"]["data"]["max_paths"] == 1


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_path_exists_false(clients: BothClients, client_type: str, httpx_mock: HTTPXMock) -> None:
    empty = {**PATH_RESULT, "paths": [], "count": 0}
    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        match_headers={"X-Infrahub-Tracker": "query-path-traversal"},
        json={"data": {"InfrahubPathTraversal": empty}},
    )
    if client_type == "standard":
        exists = await clients.standard.path_exists("a", "b")
    else:
        exists = clients.sync.path_exists("a", "b")

    assert exists is False


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_reachable_nodes_query_and_parse(clients: BothClients, client_type: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        match_headers={"X-Infrahub-Tracker": "query-reachable-nodes"},
        json={"data": {"InfrahubReachableNodes": REACHABLE_RESULT}},
    )
    if client_type == "standard":
        result = await clients.standard.reachable_nodes("a", ["DcimCable"], max_results=5)
    else:
        result = clients.sync.reachable_nodes("a", ["DcimCable"], max_results=5)

    assert isinstance(result, ReachableNodesResult)
    assert result.count == 1
    assert result.dependencies[0].node.kind == "DcimCable"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_traverse_paths_version_guard(clients: BothClients, client_type: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        json={"errors": [{"message": "Cannot query field 'InfrahubPathTraversal' on type 'Query'."}]},
    )
    with pytest.raises(VersionNotSupportedError, match=r"1\.10"):
        if client_type == "standard":
            await clients.standard.traverse_paths("a", "b")
        else:
            clients.sync.traverse_paths("a", "b")


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_traverse_paths_other_graphql_error_propagates(
    clients: BothClients, client_type: str, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=PATH_TRAVERSAL_URL,
        json={"errors": [{"message": "Source node not found: a"}]},
    )
    with pytest.raises(GraphQLError, match="Source node not found"):
        if client_type == "standard":
            await clients.standard.traverse_paths("a", "b")
        else:
            clients.sync.traverse_paths("a", "b")
