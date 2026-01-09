import pytest
from httpx import HTTPStatusError
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk import Config, InfrahubClient
from infrahub_sdk.ctl.branch import app, check_git_files_changed, format_timestamp

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)


def test_format_timestamp_valid_iso() -> None:
    """Test format_timestamp with valid ISO timestamp."""
    timestamp = "2025-11-14T12:30:45Z"
    result = format_timestamp(timestamp)
    assert result == "2025-11-14 12:30:45"


def test_format_timestamp_with_timezone() -> None:
    """Test format_timestamp with timezone offset."""
    timestamp = "2025-11-14T12:30:45+00:00"
    result = format_timestamp(timestamp)
    assert result == "2025-11-14 12:30:45"


def test_format_timestamp_invalid() -> None:
    """Test format_timestamp with invalid timestamp returns original."""
    timestamp = "not-a-timestamp"
    with pytest.raises(ValueError):
        format_timestamp(timestamp)


@pytest.fixture
async def mock_git_files_changed_yes(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock REST API response with files changed."""
    response = {
        "test-branch": {
            "repo-id-1": {
                "files": [
                    {"path": "file1.py", "status": "modified"},
                    {"path": "file2.py", "status": "added"},
                ]
            }
        }
    }

    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/diff/files?branch=test-branch",
        json=response,
    )
    return httpx_mock


async def test_check_git_files_changed_with_files(
    mock_git_files_changed_yes: HTTPXMock,
) -> None:
    """Test check_git_files_changed returns True when files exist."""
    client = InfrahubClient(config=Config(address="http://mock"))
    result = await check_git_files_changed(client, branch="test-branch")
    assert result is True


async def test_check_git_files_changed_no_files(httpx_mock: HTTPXMock) -> None:
    """Test check_git_files_changed returns False when no files."""
    response = {"test-branch": {"repo-id-1": {"files": []}}}

    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/diff/files?branch=test-branch",
        json=response,
    )
    client = InfrahubClient(config=Config(address="http://mock"))
    result = await check_git_files_changed(client, branch="test-branch")
    assert result is False


async def test_check_git_files_changed_empty_response(httpx_mock: HTTPXMock) -> None:
    response = {}

    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/diff/files?branch=test-branch",
        json=response,
    )

    """Test check_git_files_changed returns False when branch not in response."""
    client = InfrahubClient(config=Config(address="http://mock"))
    result = await check_git_files_changed(client, branch="test-branch")
    assert result is False


async def test_check_git_files_changed_http_error(httpx_mock: HTTPXMock) -> None:
    """Test check_git_files_changed raises exception on HTTP error."""
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/diff/files?branch=test-branch",
        status_code=404,
    )

    client = InfrahubClient(config=Config(address="http://mock"))
    with pytest.raises(HTTPStatusError):
        await check_git_files_changed(client, branch="test-branch")


@pytest.fixture
def mock_branch_report_default_branch(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock all responses for branch report CLI command."""
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "Branch": [
                    {
                        "id": "default-branch-id",
                        "name": "main",
                        "sync_with_git": True,
                        "is_default": True,
                        "origin_branch": "main",
                        "branched_from": "2025-11-01t10:00:00z",
                        "has_schema_changes": False,
                        "status": "OPEN",
                    },
                ],
            },
        },
        match_headers={"X-Infrahub-Tracker": "query-branch"},
    )
    return httpx_mock


@pytest.fixture
def mock_branch_report_command(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock all responses for branch report CLI command."""
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "Branch": [
                    {
                        "id": "test-branch-id",
                        "name": "test-branch",
                        "sync_with_git": True,
                        "is_default": False,
                        "origin_branch": "main",
                        "branched_from": "2025-11-01t10:00:00Z",
                        "has_schema_changes": False,
                        "status": "OPEN",
                    }
                ]
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-branch"},
    )

    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "DiffTree": {
                    "num_added": 5,
                    "num_updated": 3,
                    "num_removed": 1,
                    "num_conflicts": 0,
                    "to_time": "2025-11-14T18:00:00Z",
                    "from_time": "2025-11-01T10:00:00Z",
                    "base_branch": "main",
                    "diff_branch": "test-branch",
                    "name": None,
                    "nodes": [],
                }
            }
        },
    )

    httpx_mock.add_response(
        method="GET",
        json={"test-branch": {"repo-1": {"files": [{"path": "test.py"}]}}},
    )

    httpx_mock.add_response(
        method="POST",
        json={"data": {"CoreProposedChange": {"count": 0, "edges": []}}},
    )

    return httpx_mock


def test_branch_report_command_without_proposed_change(
    mock_branch_report_command: HTTPXMock,
    mock_schema_query_05: HTTPXMock,
) -> None:
    """Test branch report CLI command with no proposed changes."""
    runner = CliRunner()
    result = runner.invoke(app, ["report", "test-branch"])

    assert result.exit_code == 0, f"Command failed: {result.stdout}"
    assert "Branch: test-branch" in result.stdout
    assert "2025-11-01 10:00:00" in result.stdout
    assert "OPEN" in result.stdout
    assert "Amount of additions" in result.stdout
    assert "5" in result.stdout
    assert "No proposed changes for this branch" in result.stdout


def test_branch_report_command_main_branch(mock_branch_report_default_branch: HTTPXMock) -> None:
    """Test branch report CLI command on main branch."""
    runner = CliRunner()
    result = runner.invoke(app, ["report", "main"])

    assert result.exit_code == 1
    assert "Cannot create a report for the default branch!" in result.stdout


@pytest.fixture
async def schema_with_proposed_change() -> dict:
    """Schema fixture that includes CoreProposedChange with is_draft."""
    return {
        "nodes": [
            {
                "name": "ProposedChange",
                "namespace": "Core",
                "default_filter": "name__value",
                "attributes": [
                    {"name": "name", "kind": "Text"},
                    {"name": "state", "kind": "Text"},
                    {"name": "is_draft", "kind": "Boolean"},
                ],
                "relationships": [
                    {"name": "created_by", "peer": "CoreAccount", "cardinality": "one"},
                    {"name": "approved_by", "peer": "CoreAccount", "cardinality": "many"},
                    {"name": "rejected_by", "peer": "CoreAccount", "cardinality": "many"},
                ],
            },
            {
                "name": "Account",
                "namespace": "Core",
                "default_filter": "name__value",
                "attributes": [
                    {"name": "name", "kind": "Text"},
                    {"name": "updated_at", "kind": "DateTime"},
                ],
                "relationships": [],
            },
        ]
    }


@pytest.fixture
def mock_schema_with_proposed_change(httpx_mock: HTTPXMock, schema_with_proposed_change: dict) -> HTTPXMock:
    """Mock schema endpoint with CoreProposedChange."""
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=schema_with_proposed_change,
        is_reusable=True,
    )
    return httpx_mock


@pytest.fixture
def mock_branch_report_with_proposed_changes(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock all responses for branch report with proposed changes."""
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "Branch": [
                    {
                        "id": "test-branch-id",
                        "name": "test-branch",
                        "sync_with_git": True,
                        "is_default": False,
                        "origin_branch": "main",
                        "branched_from": "2025-11-01T10:00:00Z",
                        "has_schema_changes": False,
                        "status": "OPEN",
                    }
                ]
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-branch"},
    )

    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "DiffTree": {
                    "num_added": 5,
                    "num_updated": 3,
                    "num_removed": 1,
                    "num_conflicts": 0,
                    "to_time": "2025-11-14T18:00:00Z",
                    "from_time": "2025-11-01T10:00:00Z",
                    "base_branch": "main",
                    "diff_branch": "test-branch",
                    "name": None,
                    "nodes": [],
                }
            }
        },
    )

    httpx_mock.add_response(
        method="GET",
        json={"test-branch": {"repo-1": {"files": [{"path": "test.py"}]}}},
    )

    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "CoreProposedChange": {
                    "count": 2,
                    "edges": [
                        {
                            "node": {
                                "id": "18789937-1263-f1cb-3615-c51259b5cd8c",
                                "hfid": None,
                                "display_label": "Add new feature",
                                "__typename": "CoreProposedChange",
                                "is_draft": {"value": False},
                                "name": {"value": "Add new feature"},
                                "state": {"value": "open"},
                                "approved_by": {
                                    "count": 2,
                                    "edges": [
                                        {
                                            "node": {
                                                "id": "user-1",
                                                "__typename": "CoreAccount",
                                            }
                                        },
                                        {
                                            "node": {
                                                "id": "user-2",
                                                "__typename": "CoreAccount",
                                            }
                                        },
                                    ],
                                },
                                "rejected_by": {"count": 0, "edges": []},
                                "created_by": {
                                    "node": {
                                        "id": "187895d8-723e-8f5d-3614-c517ac8e761c",
                                        "hfid": ["johndoe"],
                                        "display_label": "John Doe",
                                        "__typename": "CoreAccount",
                                        "name": {"value": "John Doe"},
                                    },
                                    "properties": {
                                        "updated_at": "2025-11-10T14:30:00Z",
                                    },
                                },
                            }
                        },
                        {
                            "node": {
                                "id": "28789937-1263-f1cb-3615-c51259b5cd8d",
                                "hfid": None,
                                "display_label": "Fix bug in network module",
                                "__typename": "CoreProposedChange",
                                "is_draft": {"value": True},
                                "name": {"value": "Fix bug in network module"},
                                "state": {"value": "merged"},
                                "approved_by": {
                                    "count": 1,
                                    "edges": [
                                        {
                                            "node": {
                                                "id": "user-3",
                                                "__typename": "CoreAccount",
                                            }
                                        },
                                    ],
                                },
                                "rejected_by": {
                                    "count": 2,
                                    "edges": [
                                        {
                                            "node": {
                                                "id": "user-4",
                                                "__typename": "CoreAccount",
                                            }
                                        },
                                        {
                                            "node": {
                                                "id": "user-5",
                                                "__typename": "CoreAccount",
                                            }
                                        },
                                    ],
                                },
                                "created_by": {
                                    "node": {
                                        "id": "287895d8-723e-8f5d-3614-c517ac8e762c",
                                        "hfid": ["janesmith"],
                                        "display_label": "Jane Smith",
                                        "__typename": "CoreAccount",
                                        "name": {"value": "Jane Smith"},
                                    },
                                    "properties": {
                                        "updated_at": "2025-11-10T14:30:00Z",
                                    },
                                },
                            }
                        },
                    ],
                }
            }
        },
    )

    return httpx_mock


def test_branch_report_command_with_proposed_changes(
    mock_branch_report_with_proposed_changes: HTTPXMock,
    mock_schema_with_proposed_change: HTTPXMock,
) -> None:
    """Test branch report CLI command with proposed changes."""
    runner = CliRunner()
    result = runner.invoke(app, ["report", "test-branch"])

    assert result.exit_code == 0, f"Command failed: {result.stdout}"
    assert "Branch: test-branch" in result.stdout

    assert "Proposed change: Add new feature" in result.stdout
    assert "Proposed change: Fix bug in network module" in result.stdout

    assert "open" in result.stdout
    assert "merged" in result.stdout

    assert "Is draft                     No" in result.stdout
    assert "Is draft                          Yes" in result.stdout

    assert "John Doe" in result.stdout
    assert "Jane Smith" in result.stdout

    assert "Approvals                     2" in result.stdout
    assert "Rejections                    0" in result.stdout
    assert "Approvals                           1" in result.stdout
    assert "Rejections                          2" in result.stdout
