import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app
from tests.helpers.fixtures import read_fixture
from tests.helpers.utils import strip_color, temp_repo_and_cd

runner = CliRunner()


FIXTURE_BASE_DIR = Path(Path(Path(__file__).resolve()).parent / ".." / ".." / "fixtures" / "repos")


@dataclass
class RenderAppFailure:
    name: str
    template: str
    error: str


RENDER_APP_FAIL_TEST_CASES = [
    RenderAppFailure(
        name="main-template-not-found",
        template="tag_format_missing",
        error="Missing template: tag_format.file-is-missing",
    ),
    RenderAppFailure(
        name="has-undefined-variables",
        template="undefined_variables",
        error="'host' is undefined",
    ),
    RenderAppFailure(
        name="has-syntax-error",
        template="syntax_error",
        error="unexpected '}'",
    ),
    RenderAppFailure(
        name="invalid-filter",
        template="missing_filter",
        error="No filter named 'my_filter_is_missing'.",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in RENDER_APP_FAIL_TEST_CASES],
)
def test_validate_template_not_found(test_case: RenderAppFailure, httpx_mock: HTTPXMock) -> None:
    """Ensure that the correct errors are caught"""
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=json.loads(
            read_fixture(
                "red_tag.json",
                "unit/test_infrahubctl/red_tags_query",
            )
        ),
    )

    with temp_repo_and_cd(source_dir=FIXTURE_BASE_DIR / "missing_template_file"):
        output = runner.invoke(app, ["render", test_case.template, "name=red"])
        assert test_case.error in strip_color(output.stdout)
        assert output.exit_code == 1


@pytest.mark.parametrize(
    "cli_branch,env_branch,from_git,expected_branch",
    [
        ("cli-branch", None, False, "cli-branch"),
        (None, "env-branch", False, "env-branch"),
        (None, None, True, "git-branch"),
    ],
)
def test_render_branch_selection(
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
    cli_branch: str | None,
    env_branch: str | None,
    from_git: bool,
    expected_branch: str,
) -> None:
    """Test that the render command uses the correct branch source."""

    if from_git:
        monkeypatch.setattr("dulwich.porcelain.active_branch", lambda _: b"git-branch")

    httpx_mock.add_response(
        method="POST",
        url=f"http://mock/graphql/{expected_branch}",
        json=json.loads(
            read_fixture(
                "red_tag.json",
                "unit/test_infrahubctl/red_tags_query",
            )
        ),
    )

    with temp_repo_and_cd(source_dir=FIXTURE_BASE_DIR / "ctl_integration"):
        args = ["render", "tags", "name=red"]
        env = {}
        # Add test-specific variables
        if cli_branch:
            args.extend(["--branch", cli_branch])
        if env_branch:
            env["INFRAHUB_DEFAULT_BRANCH"] = env_branch
            env["INFRAHUB_DEFAULT_BRANCH_FROM_GIT"] = "false"
        if from_git:
            env["INFRAHUB_DEFAULT_BRANCH_FROM_GIT"] = "true"
        output = runner.invoke(app, args, env=env)
        assert output.exit_code == 0
