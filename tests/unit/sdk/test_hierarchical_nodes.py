"""Tests for hierarchical nodes parent, children, ancestors and descendants functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient, InfrahubClientSync

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)


@pytest.fixture
async def hierarchical_schema() -> NodeSchemaAPI:
    """Schema for a hierarchical location node with hierarchy support."""
    data = {
        "name": "Location",
        "namespace": "Infra",
        "default_filter": "name__value",
        "attributes": [
            {"name": "name", "kind": "String", "unique": True},
            {"name": "description", "kind": "String", "optional": True},
        ],
        "relationships": [
            {
                "name": "parent",
                "peer": "InfraLocation",
                "optional": True,
                "cardinality": "one",
                "kind": "Hierarchy",
            },
            {
                "name": "children",
                "peer": "InfraLocation",
                "optional": True,
                "cardinality": "many",
                "kind": "Hierarchy",
            },
        ],
    }
    schema_api = NodeSchema(**data).convert_api()
    # Set hierarchy field manually since it's not part of NodeSchema but only NodeSchemaAPI
    # This field would normally be set by the backend
    schema_api.hierarchy = "InfraLocation"
    return schema_api


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_hierarchical_node_has_hierarchy_support(
    client: InfrahubClient, client_sync: InfrahubClientSync, hierarchical_schema, client_type
) -> None:
    """Test that hierarchical nodes are properly detected and support parent/children/ancestors/descendants."""
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=hierarchical_schema)
    else:
        node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema)

    # Check that hierarchy support is detected
    assert node._hierarchy_support is True
    assert hierarchical_schema.hierarchy == "InfraLocation"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_hierarchical_node_has_all_hierarchical_fields(
    client: InfrahubClient, client_sync: InfrahubClientSync, hierarchical_schema, client_type
) -> None:
    """Test that hierarchical nodes have parent, children, ancestors and descendants attributes."""
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=hierarchical_schema)
    else:
        node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema)

    # Check that all hierarchical fields are accessible
    assert hasattr(node, "parent")
    assert hasattr(node, "children")
    assert hasattr(node, "ancestors")
    assert hasattr(node, "descendants")

    # Check parent is initialized as RelatedNode
    parent = node.parent
    assert parent is not None
    assert parent.name == "parent"
    assert parent.schema.cardinality == "one"

    # Check children is initialized as RelationshipManager
    children = node.children
    assert children is not None
    assert children.name == "children"
    assert children.schema.cardinality == "many"

    # Check ancestors is initialized as RelationshipManager
    ancestors = node.ancestors
    assert ancestors is not None
    assert ancestors.name == "ancestors"
    assert ancestors.schema.read_only is True
    assert ancestors.schema.cardinality == "many"

    # Check descendants is initialized as RelationshipManager
    descendants = node.descendants
    assert descendants is not None
    assert descendants.name == "descendants"
    assert descendants.schema.read_only is True
    assert descendants.schema.cardinality == "many"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_hierarchical_node_with_parent_data(
    client: InfrahubClient, client_sync: InfrahubClientSync, hierarchical_schema, client_type
) -> None:
    """Test that hierarchical nodes can be initialized with parent data."""
    data = {
        "id": "location-1",
        "name": {"value": "California"},
        "description": {"value": "State in USA"},
        "parent": {"node": {"id": "parent-1", "__typename": "InfraLocation", "display_label": "USA"}},
    }

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=hierarchical_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema, data=data)

    # Check parent is properly initialized
    assert node.parent.initialized is True
    assert node.parent.id == "parent-1"
    assert node.parent.display_label == "USA"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_hierarchical_node_with_children_data(
    client: InfrahubClient, client_sync: InfrahubClientSync, hierarchical_schema, client_type
) -> None:
    """Test that hierarchical nodes can be initialized with children data."""
    data = {
        "id": "location-1",
        "name": {"value": "USA"},
        "description": {"value": "United States"},
        "children": {
            "edges": [
                {"node": {"id": "child-1", "__typename": "InfraLocation", "display_label": "California"}},
                {"node": {"id": "child-2", "__typename": "InfraLocation", "display_label": "New York"}},
            ]
        },
    }

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=hierarchical_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema, data=data)

    # Check children are properly initialized
    assert node.children.initialized is True
    assert len(node.children.peers) == 2
    assert node.children.peers[0].id == "child-1"
    assert node.children.peers[0].display_label == "California"
    assert node.children.peers[1].id == "child-2"
    assert node.children.peers[1].display_label == "New York"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_hierarchical_node_with_ancestors_data(
    client: InfrahubClient, client_sync: InfrahubClientSync, hierarchical_schema, client_type
) -> None:
    """Test that hierarchical nodes can be initialized with ancestors data."""
    data = {
        "id": "location-1",
        "name": {"value": "USA"},
        "description": {"value": "United States"},
        "ancestors": {
            "edges": [
                {"node": {"id": "ancestor-1", "__typename": "InfraLocation", "display_label": "Earth"}},
                {"node": {"id": "ancestor-2", "__typename": "InfraLocation", "display_label": "Americas"}},
            ]
        },
    }

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=hierarchical_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema, data=data)

    # Check ancestors are properly initialized
    assert node.ancestors.initialized is True
    assert len(node.ancestors.peers) == 2
    assert node.ancestors.peers[0].id == "ancestor-1"
    assert node.ancestors.peers[0].display_label == "Earth"
    assert node.ancestors.peers[1].id == "ancestor-2"
    assert node.ancestors.peers[1].display_label == "Americas"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_hierarchical_node_with_descendants_data(
    client: InfrahubClient, client_sync: InfrahubClientSync, hierarchical_schema, client_type
) -> None:
    """Test that hierarchical nodes can be initialized with descendants data."""
    data = {
        "id": "location-1",
        "name": {"value": "USA"},
        "description": {"value": "United States"},
        "descendants": {
            "edges": [
                {"node": {"id": "descendant-1", "__typename": "InfraLocation", "display_label": "California"}},
                {"node": {"id": "descendant-2", "__typename": "InfraLocation", "display_label": "New York"}},
                {"node": {"id": "descendant-3", "__typename": "InfraLocation", "display_label": "Texas"}},
            ]
        },
    }

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=hierarchical_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema, data=data)

    # Check descendants are properly initialized
    assert node.descendants.initialized is True
    assert len(node.descendants.peers) == 3
    assert node.descendants.peers[0].id == "descendant-1"
    assert node.descendants.peers[0].display_label == "California"
    assert node.descendants.peers[1].id == "descendant-2"
    assert node.descendants.peers[1].display_label == "New York"
    assert node.descendants.peers[2].id == "descendant-3"
    assert node.descendants.peers[2].display_label == "Texas"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_non_hierarchical_node_no_hierarchical_fields(
    client: InfrahubClient, client_sync: InfrahubClientSync, location_schema, client_type
) -> None:
    """Test that non-hierarchical nodes don't have parent/children/ancestors/descendants."""
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema)
    else:
        node = InfrahubNodeSync(client=client_sync, schema=location_schema)

    # Check that hierarchy support is not detected
    assert node._hierarchy_support is False

    # Check that accessing hierarchical fields raises AttributeError
    with pytest.raises(AttributeError, match="has no attribute 'parent'"):
        _ = node.parent

    with pytest.raises(AttributeError, match="has no attribute 'children'"):
        _ = node.children

    with pytest.raises(AttributeError, match="has no attribute 'ancestors'"):
        _ = node.ancestors

    with pytest.raises(AttributeError, match="has no attribute 'descendants'"):
        _ = node.descendants


async def test_hierarchical_node_query_generation_includes_parent(client: InfrahubClient, hierarchical_schema) -> None:
    """Test that query generation includes parent when requested."""
    # Pre-populate schema cache to avoid fetching from server
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client.schema.set_cache(cache_data)

    node = InfrahubNode(client=client, schema=hierarchical_schema)

    # Generate query with parent included
    query_data = await node.generate_query_data_node(include=["parent"])

    # Check that parent is in the query
    assert "parent" in query_data
    assert "node" in query_data["parent"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["parent"]["node"]


async def test_hierarchical_node_query_generation_includes_children(
    client: InfrahubClient, hierarchical_schema
) -> None:
    """Test that query generation includes children when requested."""
    # Pre-populate schema cache to avoid fetching from server
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client.schema.set_cache(cache_data)

    node = InfrahubNode(client=client, schema=hierarchical_schema)

    # Generate query with children included
    query_data = await node.generate_query_data_node(include=["children"])

    # Check that children is in the query
    assert "children" in query_data
    assert "edges" in query_data["children"]
    assert "node" in query_data["children"]["edges"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["children"]["edges"]["node"]


async def test_hierarchical_node_query_generation_includes_ancestors(
    client: InfrahubClient, hierarchical_schema
) -> None:
    """Test that query generation includes ancestors when requested."""
    # Pre-populate schema cache to avoid fetching from server
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client.schema.set_cache(cache_data)

    node = InfrahubNode(client=client, schema=hierarchical_schema)

    # Generate query with ancestors included
    query_data = await node.generate_query_data_node(include=["ancestors"])

    # Check that ancestors is in the query
    assert "ancestors" in query_data
    assert "edges" in query_data["ancestors"]
    assert "node" in query_data["ancestors"]["edges"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["ancestors"]["edges"]["node"]


async def test_hierarchical_node_query_generation_includes_descendants(
    client: InfrahubClient, hierarchical_schema
) -> None:
    """Test that query generation includes descendants when requested."""
    # Pre-populate schema cache to avoid fetching from server
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client.schema.set_cache(cache_data)

    node = InfrahubNode(client=client, schema=hierarchical_schema)

    # Generate query with descendants included
    query_data = await node.generate_query_data_node(include=["descendants"])

    # Check that descendants is in the query
    assert "descendants" in query_data
    assert "edges" in query_data["descendants"]
    assert "node" in query_data["descendants"]["edges"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["descendants"]["edges"]["node"]


async def test_hierarchical_node_query_generation_prefetch_relationships(
    client: InfrahubClient, hierarchical_schema
) -> None:
    """Test that query generation includes all hierarchical fields with prefetch_relationships=True."""
    # Pre-populate schema cache to avoid fetching from server
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client.schema.set_cache(cache_data)

    node = InfrahubNode(client=client, schema=hierarchical_schema)

    # Generate query with prefetch_relationships
    query_data = await node.generate_query_data_node(prefetch_relationships=True)

    # Check that all hierarchical fields are in the query
    assert "parent" in query_data
    assert "children" in query_data
    assert "ancestors" in query_data
    assert "descendants" in query_data


async def test_hierarchical_node_query_generation_exclude(client: InfrahubClient, hierarchical_schema) -> None:
    """Test that query generation respects exclude for hierarchical fields."""
    # Pre-populate schema cache to avoid fetching from server
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client.schema.set_cache(cache_data)

    node = InfrahubNode(client=client, schema=hierarchical_schema)

    # Generate query with parent and ancestors excluded but prefetch_relationships enabled
    query_data = await node.generate_query_data_node(prefetch_relationships=True, exclude=["parent", "ancestors"])

    # Check that parent and ancestors are excluded but children and descendants are present
    assert "parent" not in query_data
    assert "ancestors" not in query_data
    assert "children" in query_data
    assert "descendants" in query_data


def test_hierarchical_node_sync_query_generation_includes_parent(
    client_sync: InfrahubClientSync, hierarchical_schema
) -> None:
    """Test that sync query generation includes parent when requested."""
    # Set schema in cache to avoid HTTP request
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client_sync.schema.set_cache(cache_data)

    node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema)

    # Generate query with parent included
    query_data = node.generate_query_data_node(include=["parent"])

    # Check that parent is in the query
    assert "parent" in query_data
    assert "node" in query_data["parent"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["parent"]["node"]


def test_hierarchical_node_sync_query_generation_includes_children(
    client_sync: InfrahubClientSync, hierarchical_schema
) -> None:
    """Test that sync query generation includes children when requested."""
    # Set schema in cache to avoid HTTP request
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client_sync.schema.set_cache(cache_data)

    node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema)

    # Generate query with children included
    query_data = node.generate_query_data_node(include=["children"])

    # Check that children is in the query
    assert "children" in query_data
    assert "edges" in query_data["children"]
    assert "node" in query_data["children"]["edges"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["children"]["edges"]["node"]


def test_hierarchical_node_sync_query_generation_includes_ancestors(
    client_sync: InfrahubClientSync, hierarchical_schema
) -> None:
    """Test that sync query generation includes ancestors when requested."""
    # Set schema in cache to avoid HTTP request
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client_sync.schema.set_cache(cache_data)

    node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema)

    # Generate query with ancestors included
    query_data = node.generate_query_data_node(include=["ancestors"])

    # Check that ancestors is in the query
    assert "ancestors" in query_data
    assert "edges" in query_data["ancestors"]
    assert "node" in query_data["ancestors"]["edges"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["ancestors"]["edges"]["node"]


def test_hierarchical_node_sync_query_generation_includes_descendants(
    client_sync: InfrahubClientSync, hierarchical_schema
) -> None:
    """Test that sync query generation includes descendants when requested."""
    # Set schema in cache to avoid HTTP request
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client_sync.schema.set_cache(cache_data)

    node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema)

    # Generate query with descendants included
    query_data = node.generate_query_data_node(include=["descendants"])

    # Check that descendants is in the query
    assert "descendants" in query_data
    assert "edges" in query_data["descendants"]
    assert "node" in query_data["descendants"]["edges"]

    # Check that the fragment is used for hierarchical fields
    assert "...on InfraLocation" in query_data["descendants"]["edges"]["node"]


async def test_hierarchical_node_no_infinite_recursion_with_children(
    client: InfrahubClient, hierarchical_schema
) -> None:
    """Test that including children does not cause infinite recursion."""
    # Pre-populate schema cache to avoid fetching from server
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client.schema.set_cache(cache_data)

    node = InfrahubNode(client=client, schema=hierarchical_schema)

    # This should not cause infinite recursion
    query_data = await node.generate_query_data_node(include=["children"])

    # Check that children is in the query
    assert "children" in query_data
    # But hierarchical fields should not be nested in the peer data
    children_node_data = query_data["children"]["edges"]["node"]["...on InfraLocation"]
    assert "parent" not in children_node_data
    assert "children" not in children_node_data
    assert "ancestors" not in children_node_data
    assert "descendants" not in children_node_data


def test_hierarchical_node_sync_no_infinite_recursion_with_children(
    client_sync: InfrahubClientSync, hierarchical_schema
) -> None:
    """Test that including children does not cause infinite recursion in sync mode."""
    # Set schema in cache to avoid HTTP request
    cache_data = {
        "version": "1.0",
        "nodes": [hierarchical_schema.model_dump()],
    }
    client_sync.schema.set_cache(cache_data)

    node = InfrahubNodeSync(client=client_sync, schema=hierarchical_schema)

    # This should not cause infinite recursion
    query_data = node.generate_query_data_node(include=["children"])

    # Check that children is in the query
    assert "children" in query_data
    # But hierarchical fields should not be nested in the peer data
    children_node_data = query_data["children"]["edges"]["node"]["...on InfraLocation"]
    assert "parent" not in children_node_data
    assert "children" not in children_node_data
    assert "ancestors" not in children_node_data
    assert "descendants" not in children_node_data
