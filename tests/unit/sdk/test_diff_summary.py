from datetime import datetime, timezone

import pytest
from pytest_httpx import HTTPXMock

from infrahub_sdk import InfrahubClient
from infrahub_sdk.diff import get_diff_tree_query
from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.fixture
async def mock_diff_tree_query(httpx_mock: HTTPXMock, client: InfrahubClient) -> HTTPXMock:
    response = {
        "data": {
            "DiffTree": {
                "nodes": [
                    {
                        "attributes": [],
                        "kind": "TestCar",
                        "label": "nolt #444444",
                        "num_added": 0,
                        "num_removed": 0,
                        "num_updated": 1,
                        "relationships": [
                            {
                                "cardinality": "ONE",
                                "elements": [{"num_added": 0, "num_removed": 0, "num_updated": 1, "status": "UPDATED"}],
                                "name": "owner",
                                "num_added": 0,
                                "num_removed": 0,
                                "num_updated": 1,
                                "status": "UPDATED",
                            }
                        ],
                        "status": "UPDATED",
                        "uuid": "17fbadf0-6637-4fa2-43e6-1677ea170e0f",
                    },
                    {
                        "attributes": [],
                        "kind": "TestPerson",
                        "label": "Jane",
                        "num_added": 0,
                        "num_removed": 0,
                        "num_updated": 1,
                        "relationships": [
                            {
                                "cardinality": "MANY",
                                "elements": [{"num_added": 0, "num_removed": 3, "num_updated": 0, "status": "REMOVED"}],
                                "name": "cars",
                                "num_added": 0,
                                "num_removed": 1,
                                "num_updated": 0,
                                "status": "UPDATED",
                            }
                        ],
                        "status": "UPDATED",
                        "uuid": "17fbadf0-634f-05a8-43e4-1677e744d4c0",
                    },
                    {
                        "attributes": [
                            {"name": "name", "num_added": 0, "num_removed": 0, "num_updated": 1, "status": "UPDATED"}
                        ],
                        "kind": "TestPerson",
                        "label": "Jonathan",
                        "num_added": 0,
                        "num_removed": 0,
                        "num_updated": 2,
                        "relationships": [
                            {
                                "cardinality": "MANY",
                                "elements": [{"num_added": 3, "num_removed": 0, "num_updated": 0, "status": "ADDED"}],
                                "name": "cars",
                                "num_added": 1,
                                "num_removed": 0,
                                "num_updated": 0,
                                "status": "UPDATED",
                            }
                        ],
                        "status": "UPDATED",
                        "uuid": "17fbadf0-6243-5d3c-43ee-167718ff8dac",
                    },
                ]
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-difftree"},
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_diffsummary(clients: BothClients, mock_diff_tree_query, client_type) -> None:
    if client_type == "standard":
        node_diffs = await clients.standard.get_diff_summary(
            branch="branch2",
            tracker="query-difftree",
        )
    else:
        node_diffs = clients.sync.get_diff_summary(
            branch="branch2",
            tracker="query-difftree",
        )

    assert len(node_diffs) == 3
    assert {
        "branch": "branch2",
        "kind": "TestCar",
        "id": "17fbadf0-6637-4fa2-43e6-1677ea170e0f",
        "action": "UPDATED",
        "display_label": "nolt #444444",
        "elements": [
            {
                "action": "UPDATED",
                "element_type": "RELATIONSHIP_ONE",
                "name": "owner",
                "summary": {"added": 0, "removed": 0, "updated": 1},
            }
        ],
    } in node_diffs
    assert {
        "branch": "branch2",
        "kind": "TestPerson",
        "id": "17fbadf0-634f-05a8-43e4-1677e744d4c0",
        "action": "UPDATED",
        "display_label": "Jane",
        "elements": [
            {
                "action": "UPDATED",
                "element_type": "RELATIONSHIP_MANY",
                "name": "cars",
                "summary": {"added": 0, "removed": 1, "updated": 0},
                "peers": [{"action": "REMOVED", "summary": {"added": 0, "removed": 3, "updated": 0}}],
            }
        ],
    } in node_diffs
    assert {
        "branch": "branch2",
        "kind": "TestPerson",
        "id": "17fbadf0-6243-5d3c-43ee-167718ff8dac",
        "action": "UPDATED",
        "display_label": "Jonathan",
        "elements": [
            {
                "action": "UPDATED",
                "element_type": "ATTRIBUTE",
                "name": "name",
                "summary": {"added": 0, "removed": 0, "updated": 1},
            },
            {
                "action": "UPDATED",
                "element_type": "RELATIONSHIP_MANY",
                "name": "cars",
                "summary": {"added": 1, "removed": 0, "updated": 0},
                "peers": [{"action": "ADDED", "summary": {"added": 3, "removed": 0, "updated": 0}}],
            },
        ],
    } in node_diffs


def test_get_diff_tree_query_structure() -> None:
    """Test that get_diff_tree_query returns proper Query object."""
    query = get_diff_tree_query()

    assert query.name == "GetDiffTree"

    rendered = query.render()
    assert "query GetDiffTree" in rendered
    assert "$branch_name: String!" in rendered
    assert "$name: String" in rendered
    assert "$from_time: DateTime" in rendered
    assert "$to_time: DateTime" in rendered
    assert "DiffTree" in rendered
    assert "num_added" in rendered
    assert "num_updated" in rendered
    assert "num_removed" in rendered
    assert "num_conflicts" in rendered
    assert "to_time" in rendered
    assert "from_time" in rendered
    assert "base_branch" in rendered
    assert "diff_branch" in rendered
    assert "nodes" in rendered


@pytest.fixture
async def mock_diff_tree_with_metadata(httpx_mock: HTTPXMock, client: InfrahubClient) -> HTTPXMock:
    """Mock diff tree response with complete metadata."""
    response = {
        "data": {
            "DiffTree": {
                "num_added": 10,
                "num_updated": 5,
                "num_removed": 2,
                "num_conflicts": 0,
                "to_time": "2025-11-14T12:00:00Z",
                "from_time": "2025-11-01T00:00:00Z",
                "base_branch": "main",
                "diff_branch": "feature-branch",
                "name": "my-diff",
                "nodes": [
                    {
                        "attributes": [
                            {"name": "name", "num_added": 0, "num_removed": 0, "num_updated": 1, "status": "UPDATED"}
                        ],
                        "kind": "TestPerson",
                        "label": "John",
                        "num_added": 0,
                        "num_removed": 0,
                        "num_updated": 1,
                        "relationships": [],
                        "status": "UPDATED",
                        "uuid": "17fbadf0-1111-1111-1111-111111111111",
                    },
                    {
                        "attributes": [],
                        "kind": "TestDevice",
                        "label": "Router1",
                        "num_added": 1,
                        "num_removed": 0,
                        "num_updated": 0,
                        "relationships": [],
                        "status": "ADDED",
                        "uuid": "17fbadf0-2222-2222-2222-222222222222",
                    },
                ],
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-difftree-metadata"},
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_get_diff_tree(clients: BothClients, mock_diff_tree_with_metadata, client_type) -> None:
    """Test get_diff_tree returns complete DiffTreeData with metadata."""
    if client_type == "standard":
        diff_tree = await clients.standard.get_diff_tree(
            branch="feature-branch",
            tracker="query-difftree-metadata",
        )
    else:
        diff_tree = clients.sync.get_diff_tree(
            branch="feature-branch",
            tracker="query-difftree-metadata",
        )

    # Verify diff_tree is not None
    assert diff_tree is not None

    # Verify metadata
    assert diff_tree["num_added"] == 10
    assert diff_tree["num_updated"] == 5
    assert diff_tree["num_removed"] == 2
    assert diff_tree["num_conflicts"] == 0
    assert diff_tree["to_time"] == "2025-11-14T12:00:00Z"
    assert diff_tree["from_time"] == "2025-11-01T00:00:00Z"
    assert diff_tree["base_branch"] == "main"
    assert diff_tree["diff_branch"] == "feature-branch"
    assert diff_tree["name"] == "my-diff"

    # Verify nodes
    assert len(diff_tree["nodes"]) == 2

    # Verify first node
    assert diff_tree["nodes"][0]["branch"] == "feature-branch"
    assert diff_tree["nodes"][0]["kind"] == "TestPerson"
    assert diff_tree["nodes"][0]["id"] == "17fbadf0-1111-1111-1111-111111111111"
    assert diff_tree["nodes"][0]["action"] == "UPDATED"
    assert diff_tree["nodes"][0]["display_label"] == "John"
    assert len(diff_tree["nodes"][0]["elements"]) == 1

    # Verify second node
    assert diff_tree["nodes"][1]["kind"] == "TestDevice"
    assert diff_tree["nodes"][1]["action"] == "ADDED"


@pytest.fixture
async def mock_diff_tree_none(httpx_mock: HTTPXMock, client: InfrahubClient) -> HTTPXMock:
    """Mock diff tree response when no diff exists."""
    response = {"data": {"DiffTree": None}}

    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-difftree-none"},
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_get_diff_tree_none(clients: BothClients, mock_diff_tree_none, client_type) -> None:
    """Test get_diff_tree returns None when no diff exists."""
    if client_type == "standard":
        diff_tree = await clients.standard.get_diff_tree(
            branch="no-diff-branch",
            tracker="query-difftree-none",
        )
    else:
        diff_tree = clients.sync.get_diff_tree(
            branch="no-diff-branch",
            tracker="query-difftree-none",
        )

    assert diff_tree is None


@pytest.fixture
async def mock_diff_tree_with_params(httpx_mock: HTTPXMock, client: InfrahubClient) -> HTTPXMock:
    """Mock diff tree response for testing with name and time parameters."""
    response = {
        "data": {
            "DiffTree": {
                "num_added": 3,
                "num_updated": 1,
                "num_removed": 0,
                "num_conflicts": 0,
                "to_time": "2025-11-14T18:00:00Z",
                "from_time": "2025-11-14T12:00:00Z",
                "base_branch": "main",
                "diff_branch": "test-branch",
                "name": "named-diff",
                "nodes": [],
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-difftree-params"},
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_get_diff_tree_with_parameters(clients: BothClients, mock_diff_tree_with_params, client_type) -> None:
    """Test get_diff_tree with name and time range parameters."""
    from_time = datetime(2025, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
    to_time = datetime(2025, 11, 14, 18, 0, 0, tzinfo=timezone.utc)

    if client_type == "standard":
        diff_tree = await clients.standard.get_diff_tree(
            branch="test-branch",
            name="named-diff",
            from_time=from_time,
            to_time=to_time,
            tracker="query-difftree-params",
        )
    else:
        diff_tree = clients.sync.get_diff_tree(
            branch="test-branch",
            name="named-diff",
            from_time=from_time,
            to_time=to_time,
            tracker="query-difftree-params",
        )

    assert diff_tree is not None
    assert diff_tree["name"] == "named-diff"
    assert diff_tree["to_time"] == "2025-11-14T18:00:00Z"
    assert diff_tree["from_time"] == "2025-11-14T12:00:00Z"
    assert diff_tree["num_added"] == 3


@pytest.mark.parametrize("client_type", client_types)
async def test_get_diff_tree_time_validation(clients: BothClients, client_type) -> None:
    """Test get_diff_tree raises error when from_time > to_time."""
    from_time = datetime(2025, 11, 14, 18, 0, 0, tzinfo=timezone.utc)
    to_time = datetime(2025, 11, 14, 12, 0, 0, tzinfo=timezone.utc)  # Earlier than from_time

    with pytest.raises(ValueError, match="from_time must be <= to_time"):
        if client_type == "standard":
            await clients.standard.get_diff_tree(
                branch="test-branch",
                from_time=from_time,
                to_time=to_time,
            )
        else:
            clients.sync.get_diff_tree(
                branch="test-branch",
                from_time=from_time,
                to_time=to_time,
            )
