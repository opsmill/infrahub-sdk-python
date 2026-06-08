"""Unit tests for infrahub_sdk.graphql.query_renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrahub_sdk.exceptions import FragmentNotFoundError
from infrahub_sdk.graphql.query_renderer import render_query
from infrahub_sdk.schema.repository import (
    InfrahubRepositoryConfig,
    InfrahubRepositoryFragmentConfig,
    InfrahubRepositoryGraphQLConfig,
)
from tests.constants import FIXTURE_REPOS_DIR

FIXTURE_REPO = str(FIXTURE_REPOS_DIR / "fragment_inlining")


@pytest.fixture
def repo_config() -> InfrahubRepositoryConfig:
    return InfrahubRepositoryConfig(
        graphql_fragments=[
            InfrahubRepositoryFragmentConfig(name="interfaces", file_path=Path("fragments/interfaces.gql")),
            InfrahubRepositoryFragmentConfig(name="devices", file_path=Path("fragments/devices.gql")),
        ],
        queries=[
            InfrahubRepositoryGraphQLConfig(name="query_two_files", file_path=Path("queries/query_two_files.gql")),
            InfrahubRepositoryGraphQLConfig(
                name="query_no_fragments", file_path=Path("queries/query_no_fragments.gql")
            ),
            InfrahubRepositoryGraphQLConfig(
                name="query_missing_fragment", file_path=Path("queries/query_missing_fragment.gql")
            ),
        ],
    )


def test_render_query_inlines_fragments(repo_config: InfrahubRepositoryConfig) -> None:
    result = render_query(name="query_two_files", config=repo_config, relative_path=FIXTURE_REPO)
    assert "interfaceFragment" in result
    assert "deviceFragment" in result


def test_render_query_no_fragments_unchanged(repo_config: InfrahubRepositoryConfig) -> None:
    original = (Path(FIXTURE_REPO) / "queries" / "query_no_fragments.gql").read_text(encoding="UTF-8")
    result = render_query(name="query_no_fragments", config=repo_config, relative_path=FIXTURE_REPO)
    assert result.count("fragment ") == original.count("fragment ")


def test_render_query_missing_fragment_raises(repo_config: InfrahubRepositoryConfig) -> None:
    with pytest.raises(FragmentNotFoundError):
        render_query(name="query_missing_fragment", config=repo_config, relative_path=FIXTURE_REPO)
