import pytest
from pytest_httpx import HTTPXMock

from infrahub_sdk import InfrahubClient
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
async def test_diffsummary(clients: BothClients, mock_diff_tree_query, client_type):
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
        "action": "None",
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
        "action": "None",
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
        "action": "None",
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
