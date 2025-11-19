from typing import Any

import pytest
import ujson
from pytest_httpx import HTTPXMock

from infrahub_sdk.utils import get_fixtures_dir
from tests.unit.sdk.conftest import mock_query_infrahub_user, mock_query_infrahub_version  # noqa: F401


@pytest.fixture
async def schema_query_05_data() -> dict:
    response_text = (get_fixtures_dir() / "schema_05.json").read_text(encoding="UTF-8")
    return ujson.loads(response_text)


@pytest.fixture
async def mock_schema_query_05(httpx_mock: HTTPXMock, schema_query_05_data: dict) -> HTTPXMock:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=schema_query_05_data,
        is_reusable=True,
    )
    return httpx_mock


@pytest.fixture
async def mock_branches_list_query(httpx_mock: HTTPXMock) -> HTTPXMock:
    response = {
        "data": {
            "Branch": [
                {
                    "id": "eca306cf-662e-4e03-8180-2b788b191d3c",
                    "name": "main",
                    "sync_with_git": True,
                    "is_default": True,
                    "origin_branch": "main",
                    "branched_from": "2023-02-17T09:30:17.811719Z",
                    "has_schema_changes": False,
                    "graph_version": 99,
                    "status": "OPEN",
                },
                {
                    "id": "7d9f817a-b958-4e76-8528-8afd0c689ada",
                    "name": "cr1234",
                    "sync_with_git": False,
                    "is_default": False,
                    "origin_branch": "main",
                    "branched_from": "2023-02-17T09:30:17.811719Z",
                    "has_schema_changes": True,
                    "graph_version": None,
                    "status": "NEED_UPGRADE_REBASE",
                },
            ]
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-branch-all"},
    )
    return httpx_mock


@pytest.fixture
async def authentication_error_payload() -> dict[str, Any]:
    return {
        "data": None,
        "errors": [
            {
                "message": "Authentication is required to perform this operation",
                "extensions": {"code": 401},
            }
        ],
    }


@pytest.fixture
async def mock_branch_create_error(httpx_mock: HTTPXMock) -> HTTPXMock:
    response = {
        "data": {"BranchCreate": None},
        "errors": [
            {
                "message": 'invalid field name: string does not match regex "^[a-z][a-z0-9\\-]+$"',
                "locations": [{"line": 2, "column": 3}],
                "path": ["BranchCreate"],
            }
        ],
    }

    httpx_mock.add_response(
        status_code=200,
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "mutation-branch-create"},
    )
    return httpx_mock


@pytest.fixture
async def mock_repositories_query(httpx_mock: HTTPXMock) -> HTTPXMock:
    response1 = {
        "data": {
            "repository": [
                {
                    "id": "9486cfce-87db-479d-ad73-07d80ba96a0f",
                    "name": {"value": "infrahub-demo-edge"},
                    "location": {"value": "git@github.com:dgarros/infrahub-demo-edge.git"},
                    "commit": {"value": "aaaaaaaaaaaaaaaaaaaa"},
                }
            ]
        }
    }
    response2 = {
        "data": {
            "repository": [
                {
                    "id": "9486cfce-87db-479d-ad73-07d80ba96a0f",
                    "name": {"value": "infrahub-demo-edge"},
                    "location": {"value": "git@github.com:dgarros/infrahub-demo-edge.git"},
                    "commit": {"value": "bbbbbbbbbbbbbbbbbbbb"},
                }
            ]
        }
    }

    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=response1)
    httpx_mock.add_response(method="POST", url="http://mock/graphql/cr1234", json=response2)
    return httpx_mock


@pytest.fixture
def mock_repositories_list(httpx_mock: HTTPXMock) -> HTTPXMock:
    response = {
        "data": {
            "CoreGenericRepository": {
                "edges": [
                    {
                        "node": {
                            "__typename": "CoreReadOnlyRepository",
                            "name": {"value": "Demo Edge Repo"},
                            "operational_status": {"value": "unknown"},
                            "sync_status": {"value": "in-sync"},
                            "internal_status": {"value": "active"},
                            "ref": {"value": "5bffc938ba0d00dd111cb19331cdef6aab3729c2"},
                        }
                    },
                    {
                        "node": {
                            "__typename": "CoreRepository",
                            "name": {"value": "My Own Repo"},
                            "operational_status": {"value": "in-sync"},
                            "sync_status": {"value": "in-sync"},
                            "internal_status": {"value": "active"},
                        }
                    },
                ]
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        status_code=200,
        url="http://mock/graphql/main",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-repository-list"},
    )
    return httpx_mock
