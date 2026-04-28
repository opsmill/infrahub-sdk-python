"""Tests for `infrahubctl graphql query-report`."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.graphql import app
from tests.constants import FIXTURE_REPOS_DIR
from tests.helpers.utils import strip_color, temp_repo_and_cd

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


def _flatten(text: str) -> str:
    """Strip ANSI colors and collapse whitespace so wrapped Rich output can be substring-matched."""
    return re.sub(r"\s+", " ", strip_color(text)).strip()


pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

runner = CliRunner()

CTL_INTEGRATION_FIXTURE = FIXTURE_REPOS_DIR / "ctl_integration"

REPORT_RESPONSE_TRUE = {"data": {"InfrahubGraphQLQueryReport": {"targets_unique_nodes": True}}}
REPORT_RESPONSE_FALSE = {"data": {"InfrahubGraphQLQueryReport": {"targets_unique_nodes": False}}}


def test_query_report_local_returns_true(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=REPORT_RESPONSE_TRUE,
        match_headers={"X-Infrahub-Tracker": "query-graphql-query-report"},
    )

    with temp_repo_and_cd(source_dir=CTL_INTEGRATION_FIXTURE):
        result = runner.invoke(app, ["query-report", "tags_query"])

    assert result.exit_code == 0, strip_color(result.stdout)
    output = _flatten(result.stdout)
    assert "Query 'tags_query' (local: templates/tags_query.gql)" in output
    assert "branch:" not in output
    assert "Targets unique nodes: true" in output
    assert "limit artifact regeneration to changed nodes only" in output


def test_query_report_local_returns_false(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=REPORT_RESPONSE_FALSE,
        match_headers={"X-Infrahub-Tracker": "query-graphql-query-report"},
    )

    with temp_repo_and_cd(source_dir=CTL_INTEGRATION_FIXTURE):
        result = runner.invoke(app, ["query-report", "tags_query"])

    assert result.exit_code == 0, strip_color(result.stdout)
    output = _flatten(result.stdout)
    assert "Targets unique nodes: false" in output
    assert "all artifacts for the definition will be regenerated" in output


def test_query_report_local_uses_branch(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/feature-x",
        json=REPORT_RESPONSE_TRUE,
        match_headers={"X-Infrahub-Tracker": "query-graphql-query-report"},
    )

    with temp_repo_and_cd(source_dir=CTL_INTEGRATION_FIXTURE):
        result = runner.invoke(app, ["query-report", "tags_query", "--branch", "feature-x"])

    assert result.exit_code == 0, strip_color(result.stdout)
    output = _flatten(result.stdout)
    assert "branch: feature-x" in output
    assert "local: templates/tags_query.gql" in output
    assert "Targets unique nodes: true" in output


def test_query_report_local_unknown_query(httpx_mock: HTTPXMock) -> None:
    with temp_repo_and_cd(source_dir=CTL_INTEGRATION_FIXTURE):
        result = runner.invoke(app, ["query-report", "does_not_exist"])

    assert result.exit_code == 1
    assert "does_not_exist" in strip_color(result.stdout)


def test_query_report_local_inlines_fragments(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """When the query uses fragments, the rendered query sent to the server has them inlined."""
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=REPORT_RESPONSE_TRUE,
        match_headers={"X-Infrahub-Tracker": "query-graphql-query-report"},
    )

    config_file = tmp_path / ".infrahub.yml"
    config_file.write_text(
        """
queries:
  - name: with_fragment
    file_path: queries/with_fragment.gql
graphql_fragments:
  - name: tag_fields
    file_path: fragments/tag_fields.gql
""".strip(),
        encoding="UTF-8",
    )
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    (queries_dir / "with_fragment.gql").write_text(
        "query WithFragment { BuiltinTag { edges { node { ...tag_fields } } } }",
        encoding="UTF-8",
    )
    fragments_dir = tmp_path / "fragments"
    fragments_dir.mkdir()
    (fragments_dir / "tag_fields.gql").write_text(
        "fragment tag_fields on BuiltinTag { id name { value } }",
        encoding="UTF-8",
    )

    with temp_repo_and_cd(source_dir=tmp_path):
        result = runner.invoke(app, ["query-report", "with_fragment"])

    assert result.exit_code == 0, strip_color(result.stdout)

    requests = httpx_mock.get_requests(
        method="POST",
        url="http://mock/graphql/main",
        match_headers={"X-Infrahub-Tracker": "query-graphql-query-report"},
    )
    assert len(requests) == 1
    sent_body = requests[0].content.decode("utf-8")
    assert "fragment tag_fields" in sent_body
    assert "...tag_fields" in sent_body


@pytest.fixture
def mock_core_graphql_query_lookup(httpx_mock: HTTPXMock) -> HTTPXMock:
    response = {
        "data": {
            "CoreGraphQLQuery": {
                "count": 1,
                "edges": [
                    {
                        "node": {
                            "id": "11111111-1111-1111-1111-111111111111",
                            "display_label": "remote_query",
                            "__typename": "CoreGraphQLQuery",
                            "name": {
                                "value": "remote_query",
                                "is_default": False,
                                "is_from_profile": False,
                                "source": None,
                                "owner": None,
                            },
                            "query": {
                                "value": "query Remote { BuiltinTag { edges { node { id } } } }",
                                "is_default": False,
                                "is_from_profile": False,
                                "source": None,
                                "owner": None,
                            },
                        }
                    }
                ],
            }
        }
    }
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-coregraphqlquery-page1"},
        is_reusable=True,
    )
    return httpx_mock


def test_query_report_online_happy_path(
    mock_schema_query_05: HTTPXMock,
    mock_core_graphql_query_lookup: HTTPXMock,
) -> None:
    mock_core_graphql_query_lookup.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=REPORT_RESPONSE_TRUE,
        match_headers={"X-Infrahub-Tracker": "query-graphql-query-report"},
    )

    result = runner.invoke(app, ["query-report", "remote_query", "--online"])

    assert result.exit_code == 0, strip_color(result.stdout)
    output = _flatten(result.stdout)
    assert "Query 'remote_query' (online: id=11111111-1111-1111-1111-111111111111)" in output
    assert "branch:" not in output
    assert "Targets unique nodes: true" in output


def test_query_report_online_not_found(
    mock_schema_query_05: HTTPXMock,
) -> None:
    mock_schema_query_05.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {"CoreGraphQLQuery": {"count": 0, "edges": []}}},
        match_headers={"X-Infrahub-Tracker": "query-coregraphqlquery-page1"},
    )

    result = runner.invoke(app, ["query-report", "missing", "--online"])

    assert result.exit_code == 1
    output = strip_color(result.stdout)
    assert "missing" in output
    assert "not found" in output
