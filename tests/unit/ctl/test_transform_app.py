"""Integration tests for infrahubctl commands."""

import json
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from pytest_httpx._httpx_mock import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app
from infrahub_sdk.repository import GitRepoManager
from tests.helpers.fixtures import read_fixture
from tests.helpers.utils import change_directory, strip_color

runner = CliRunner()


FIXTURE_BASE_DIR = Path(
    Path(Path(__file__).resolve()).parent / ".." / ".." / "fixtures" / "integration" / "test_infrahubctl"
)


@pytest.fixture
def tags_transform_dir() -> Generator[str]:
    temp_dir = tempfile.mkdtemp()

    try:
        fixture_path = Path(FIXTURE_BASE_DIR / "tags_transform")
        shutil.copytree(fixture_path, temp_dir, dirs_exist_ok=True)
        # Initialize fixture as git repo. This is necessary to run some infrahubctl commands.
        GitRepoManager(temp_dir)

        yield temp_dir

    finally:
        shutil.rmtree(temp_dir)


# ---------------------------------------------------------
# infrahubctl transform command tests
# ---------------------------------------------------------


class TestInfrahubctlTransform:
    """Groups the 'infrahubctl transform' test cases."""

    @staticmethod
    def test_transform_not_exist_in_infrahub_yml(tags_transform_dir: str) -> None:
        """Case transform is not specified in the infrahub.yml file."""
        transform_name = "not_existing_transform"
        with change_directory(tags_transform_dir):
            output = runner.invoke(app, ["transform", transform_name, "tag=red"])
            assert f"Unable to find '{transform_name}'" in strip_color(output.stdout)
            assert output.exit_code == 1

    @staticmethod
    def test_transform_python_file_not_defined(tags_transform_dir: str) -> None:
        """Case transform python file not defined."""
        # Remove transform file
        transform_file = Path(Path(tags_transform_dir) / "tags_transform.py")
        Path.unlink(transform_file)

        # Run command and make assertions
        transform_name = "tags_transform"
        with change_directory(tags_transform_dir):
            output = runner.invoke(app, ["transform", transform_name, "tag=red"])
            assert "No module named 'tags_transform' (tags_transform.py)" in strip_color(output.stdout)
            assert output.exit_code == 1

    @staticmethod
    def test_transform_python_class_not_defined(tags_transform_dir: str) -> None:
        """Case transform python class not defined."""
        # Rename transform inside of python file so the class name searched for no longer exists
        transform_file = Path(Path(tags_transform_dir) / "tags_transform.py")
        with Path.open(transform_file, "r", encoding="utf-8") as fhd:
            file_contents = fhd.read()

        with Path.open(transform_file, "w", encoding="utf-8") as fhd:
            new_file_contents = file_contents.replace("TagsTransform", "FunTransform")
            fhd.write(new_file_contents)

        # Run command and make assertions
        transform_name = "tags_transform"
        with change_directory(tags_transform_dir):
            output = runner.invoke(app, ["transform", transform_name, "tag=red"])
            assert "The specified class TagsTransform was not found within the module" in output.stdout
            assert output.exit_code == 1

    @staticmethod
    def test_gql_query_not_defined(tags_transform_dir: str) -> None:
        """Case GraphQL Query is not defined"""
        # Remove GraphQL Query file
        gql_file = Path(Path(tags_transform_dir) / "tags_query.gql")
        Path.unlink(gql_file)

        # Run command and make assertions
        with change_directory(tags_transform_dir):
            output = runner.invoke(app, ["transform", "tags_transform", "tag=red"])
            assert "FileNotFoundError" in output.stdout
            assert output.exit_code == 1

    @staticmethod
    def test_infrahubctl_transform_cmd_success(httpx_mock: HTTPXMock, tags_transform_dir: str) -> None:
        """Case infrahubctl transform command executes successfully"""
        httpx_mock.add_response(
            method="POST",
            url="http://mock/graphql/main",
            json=json.loads(read_fixture("case_success_api_return.json", "integration/test_infrahubctl/transform_cmd")),
        )

        with change_directory(tags_transform_dir):
            output = runner.invoke(app, ["transform", "tags_transform", "tag=red"])
            assert strip_color(output.stdout) == read_fixture(
                "case_success_output.txt", "integration/test_infrahubctl/transform_cmd"
            )
            assert output.exit_code == 0
