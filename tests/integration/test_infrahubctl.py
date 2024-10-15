"""Integration tests for infrahubctl commands."""

import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pytest
from git import Repo
from pytest_httpx._httpx_mock import HTTPXMock
from typer.testing import Any, CliRunner

from infrahub_sdk.ctl.cli_commands import app

runner = CliRunner()


FIXTURE_BASE_DIR = Path(Path(os.path.abspath(__file__)).parent / ".." / "fixtures" / "integration" / "test_infrahubctl")


@contextmanager
def change_directory(new_directory: str) -> Generator[None, None, None]:
    """Helper function used to change directories in a with block."""
    # Save the current working directory
    original_directory = os.getcwd()

    # Change to the new directory
    try:
        os.chdir(new_directory)
        yield  # Yield control back to the with block

    finally:
        # Change back to the original directory
        os.chdir(original_directory)


def read_fixture(file_name: str, fixture_subdir: str = ".") -> Any:
    """Read the contents of a fixture."""
    with Path(FIXTURE_BASE_DIR / fixture_subdir / file_name).open("r", encoding="utf-8") as fhd:
        fixture_contents = fhd.read()

    return fixture_contents


def strip_color(text: str) -> str:
    ansi_escape = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


@pytest.fixture
def tags_transform_dir():
    temp_dir = tempfile.mkdtemp()

    try:
        fixture_path = Path(FIXTURE_BASE_DIR / "tags_transform")
        shutil.copytree(fixture_path, temp_dir, dirs_exist_ok=True)
        # Initialize fixture as git repo. This is necessary to run some infrahubctl commands.
        with change_directory(temp_dir):
            Repo.init(".")

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
            assert f"Unable to find requested transform: {transform_name}" in output.stdout
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
            assert f"Unable to load {transform_name} from python_transforms" in output.stdout
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
            assert f"Unable to load {transform_name} from python_transforms" in output.stdout
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
            json=json.loads(read_fixture("case_success_api_return.json", "transform_cmd")),
        )

        with change_directory(tags_transform_dir):
            output = runner.invoke(app, ["transform", "tags_transform", "tag=red"])
            assert strip_color(output.stdout) == read_fixture("case_success_output.txt", "transform_cmd")
            assert output.exit_code == 0
