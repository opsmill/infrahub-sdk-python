from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl import config
from infrahub_sdk.ctl.cli_commands import app, generator
from infrahub_sdk.ctl.parameters import load_configuration
from infrahub_sdk.repository import GitRepoManager
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import SchemaAnimal
from tests.helpers.utils import change_directory, strip_color

if TYPE_CHECKING:
    from collections.abc import Generator

    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode

FIXTURE_BASE_DIR = Path(Path(Path(__file__).resolve()).parent / ".." / "fixtures")


runner = CliRunner()


class TestInfrahubCtl(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    async def base_dataset(
        self,
        client: InfrahubClient,
        load_schema: None,
        person_liam: InfrahubNode,
        person_ethan: InfrahubNode,
        person_sophia: InfrahubNode,
        cat_luna: InfrahubNode,
        cat_bella: InfrahubNode,
        dog_daisy: InfrahubNode,
        dog_rocky: InfrahubNode,
        ctl_client_config: Generator[None, None, None],
    ) -> None:
        await client.branch.create(branch_name="branch01")

    @pytest.fixture(scope="class")
    def repository(self) -> Generator[str, None, None]:
        temp_dir = tempfile.mkdtemp()

        try:
            fixture_path = Path(FIXTURE_BASE_DIR / "repos" / "ctl_integration")
            shutil.copytree(fixture_path, temp_dir, dirs_exist_ok=True)
            # Initialize fixture as git repository. This is necessary to run some infrahubctl commands.
            GitRepoManager(temp_dir)

            yield temp_dir

        finally:
            shutil.rmtree(temp_dir)

    @pytest.fixture(scope="class")
    def ctl_client_config(self, client: InfrahubClient) -> Generator[None, None, None]:
        load_configuration(value="infrahubctl.toml")
        assert config.SETTINGS._settings
        config.SETTINGS._settings.server_address = client.config.address
        original_username = os.environ.get("INFRAHUB_USERNAME")
        original_password = os.environ.get("INFRAHUB_PASSWORD")
        if client.config.username and client.config.password:
            os.environ["INFRAHUB_USERNAME"] = client.config.username
            os.environ["INFRAHUB_PASSWORD"] = client.config.password
        yield
        if original_username:
            os.environ["INFRAHUB_USERNAME"] = original_username
        if original_password:
            os.environ["INFRAHUB_PASSWORD"] = original_password

    def test_infrahubctl_transform_cmd_animal_person(self, repository: str, base_dataset: None) -> None:
        """Test infrahubctl transform without converting nodes."""

        with change_directory(repository):
            ethans_output = runner.invoke(app, ["transform", "animal_person", "name=Ethan Carter"])
            structured_ethan_output = json.loads(strip_color(ethans_output.stdout))

            liams_output = runner.invoke(app, ["transform", "animal_person", "name=Liam Walker"])
            structured_liam_output = json.loads(strip_color(liams_output.stdout))

            assert structured_ethan_output == {"person": "Ethan Carter", "pets": ["Bella", "Daisy", "Luna"]}
            assert structured_liam_output == {"person": "Liam Walker", "pets": []}

    def test_infrahubctl_transform_cmd_convert_animal_person(self, repository: str, base_dataset: None) -> None:
        """Test infrahubctl transform when converting nodes."""

        with change_directory(repository):
            ethans_output = runner.invoke(app, ["transform", "animal_person_converted", "name=Ethan Carter"])
            structured_ethan_output = json.loads(strip_color(ethans_output.stdout))

            liams_output = runner.invoke(app, ["transform", "animal_person_converted", "name=Liam Walker"])
            structured_liam_output = json.loads(strip_color(liams_output.stdout))

            assert structured_ethan_output == {
                "animals": [
                    {"name": "Bella", "type": "TestingCat"},
                    {"name": "Daisy", "type": "TestingDog"},
                    {"name": "Luna", "type": "TestingCat"},
                ],
                "herd_size": 3,
                "person": "Ethan Carter",
            }
            assert structured_liam_output == {
                "animals": [],
                "herd_size": 0,
                "person": "Liam Walker",
            }

    async def test_infrahubctl_generator_cmd_animal_tags(
        self, repository: str, base_dataset: None, client: InfrahubClient
    ) -> None:
        """Test infrahubctl generator without converting nodes."""

        expected_generated_tags = ["raw-ethan-carter-bella", "raw-ethan-carter-daisy", "raw-ethan-carter-luna"]
        initial_tags = await client.all(kind="BuiltinTag")

        with change_directory(repository):
            await generator(
                generator_name="animal_tags", variables=["name=Ethan Carter"], list_available=False, path="."
            )

        final_tags = await client.all(kind="BuiltinTag")

        initial_tag_names = [tag.name.value for tag in initial_tags]
        final_tag_names = [tag.name.value for tag in final_tags]

        for tag in expected_generated_tags:
            assert tag not in initial_tag_names
            assert tag in final_tag_names

    async def test_infrahubctl_generator_cmd_animal_tags_convert_query(
        self, repository: str, base_dataset: None, client: InfrahubClient
    ) -> None:
        """Test infrahubctl generator with conversion of nodes."""

        expected_generated_tags = [
            "converted-ethan-carter-bella",
            "converted-ethan-carter-daisy",
            "converted-ethan-carter-luna",
        ]
        initial_tags = await client.all(kind="BuiltinTag")

        with change_directory(repository):
            await generator(
                generator_name="animal_tags_convert", variables=["name=Ethan Carter"], list_available=False, path="."
            )

        final_tags = await client.all(kind="BuiltinTag")

        initial_tag_names = [tag.name.value for tag in initial_tags]
        final_tag_names = [tag.name.value for tag in final_tags]

        for tag in expected_generated_tags:
            assert tag not in initial_tag_names
            assert tag in final_tag_names
