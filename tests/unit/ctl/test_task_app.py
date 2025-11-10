from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.task import app

runner = CliRunner()

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


def _task_response() -> dict:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    return {
        "data": {
            "InfrahubTask": {
                "edges": [
                    {
                        "node": {
                            "id": "task-1",
                            "title": "Sync repositories",
                            "state": "RUNNING",
                            "progress": 0.5,
                            "workflow": "RepositorySync",
                            "branch": "main",
                            "created_at": now,
                            "updated_at": now,
                            "logs": {"edges": []},
                            "related_nodes": [],
                        }
                    }
                ],
                "count": 1,
            }
        }
    }


def _empty_task_response() -> dict:
    return {"data": {"InfrahubTask": {"edges": [], "count": 0}}}


def test_task_list_command(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_task_response(),
        match_headers={"X-Infrahub-Tracker": "query-tasks-page1"},
    )

    result = runner.invoke(app=app, args=["list"])

    assert result.exit_code == 0
    assert "Infrahub Tasks" in result.stdout
    assert "Sync repositories" in result.stdout


def test_task_list_json_output(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_task_response(),
        match_headers={"X-Infrahub-Tracker": "query-tasks-page1"},
    )

    result = runner.invoke(app=app, args=["list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["state"] == "RUNNING"
    assert payload[0]["title"] == "Sync repositories"


def test_task_list_with_state_filter(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_empty_task_response(),
        match_headers={"X-Infrahub-Tracker": "query-tasks-page1"},
    )

    result = runner.invoke(app=app, args=["list", "--state", "running"])

    assert result.exit_code == 0
    assert "No tasks found" in result.stdout


def test_task_list_invalid_state() -> None:
    result = runner.invoke(app=app, args=["list", "--state", "invalid"])

    assert result.exit_code != 0
    assert "Unsupported state" in result.stdout
