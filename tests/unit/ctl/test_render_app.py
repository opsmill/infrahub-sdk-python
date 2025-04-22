import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_httpx._httpx_mock import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app
from tests.helpers.fixtures import read_fixture
from tests.helpers.utils import strip_color, temp_repo_and_cd

runner = CliRunner()


FIXTURE_BASE_DIR = Path(Path(os.path.abspath(__file__)).parent / ".." / ".." / "fixtures" / "repos")

requires_python_310 = pytest.mark.skipif(sys.version_info < (3, 10), reason="Requires Python 3.10 or higher")


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
@requires_python_310
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
