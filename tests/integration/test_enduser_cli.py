"""Integration tests for the ``infrahubctl`` end-user CLI.

Requires a running Infrahub instance with the TestingAnimal schema loaded.
Uses the same ``TestInfrahubDockerClient`` + ``SchemaAnimal`` fixtures as
the existing ``test_infrahubctl.py`` integration tests.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import yaml
from typer.testing import CliRunner

from infrahub_sdk.ctl import config
from infrahub_sdk.ctl.cli_commands import app
from infrahub_sdk.ctl.parameters import load_configuration
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import SchemaAnimal

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path
    from typing import Any

    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode

runner = CliRunner()


class _EnduserCliBase(TestInfrahubDockerClient, SchemaAnimal):
    """Shared fixtures for end-user CLI integration tests."""

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
        """Ensure schema and test data are loaded before running tests."""

    @pytest.fixture(scope="class")
    def ctl_client_config(self, client: InfrahubClient) -> Generator[None, None, None]:
        """Configure the CLI to talk to the test Infrahub instance."""
        load_configuration(value="infrahubctl.toml")
        assert config.SETTINGS._settings
        original_server_address = config.SETTINGS._settings.server_address
        config.SETTINGS._settings.server_address = client.config.address
        original_username = os.environ.get("INFRAHUB_USERNAME")
        original_password = os.environ.get("INFRAHUB_PASSWORD")
        try:
            if client.config.username and client.config.password:
                os.environ["INFRAHUB_USERNAME"] = client.config.username
                os.environ["INFRAHUB_PASSWORD"] = client.config.password
            yield
        finally:
            config.SETTINGS._settings.server_address = original_server_address
            if original_username is not None:
                os.environ["INFRAHUB_USERNAME"] = original_username
            else:
                os.environ.pop("INFRAHUB_USERNAME", None)
            if original_password is not None:
                os.environ["INFRAHUB_PASSWORD"] = original_password
            else:
                os.environ.pop("INFRAHUB_PASSWORD", None)


class TestEnduserCliRead(_EnduserCliBase):
    """Read-only CLI tests: version, schema discovery, and get queries."""

    def test_version(self) -> None:
        """Verify the version subcommand works without a server."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "SDK" in result.stdout

    def test_schema_list(self, base_dataset: None) -> None:
        """List schema kinds and verify TestingPerson is present."""
        result = runner.invoke(app, ["schema", "list"])
        assert result.exit_code == 0
        assert "TestingPerson" in result.stdout

    def test_schema_list_with_filter(self, base_dataset: None) -> None:
        """Filter schema list by substring."""
        result = runner.invoke(app, ["schema", "list", "--filter", "Dog"])
        assert result.exit_code == 0
        assert "TestingDog" in result.stdout
        assert "TestingCat" not in result.stdout

    def test_schema_show(self, base_dataset: None) -> None:
        """Show details of a schema kind including attributes and relationships."""
        result = runner.invoke(app, ["schema", "show", "TestingPerson"])
        assert result.exit_code == 0
        assert "TestingPerson" in result.stdout
        assert "name" in result.stdout
        assert "height" in result.stdout
        assert "animals" in result.stdout

    def test_get_list_table(self, base_dataset: None) -> None:
        """Query all persons and verify table output contains known names."""
        result = runner.invoke(app, ["object", "get", "TestingPerson"])
        assert result.exit_code == 0
        assert "Ethan Carter" in result.stdout
        assert "Liam Walker" in result.stdout

    def test_get_list_json(self, base_dataset: None) -> None:
        """Query all persons with JSON output and verify valid JSON array."""
        result = runner.invoke(app, ["object", "get", "TestingPerson", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 3
        names = [item.get("name", "") for item in data]
        assert "Ethan Carter" in names

    def test_get_list_csv(self, base_dataset: None) -> None:
        """Query all persons with CSV output."""
        result = runner.invoke(app, ["object", "get", "TestingPerson", "--output", "csv"])
        assert result.exit_code == 0
        assert "name" in result.stdout
        assert "Ethan Carter" in result.stdout

    def test_get_list_yaml(self, base_dataset: None) -> None:
        """Query all persons with YAML output in Infrahub object format."""
        result = runner.invoke(app, ["object", "get", "TestingPerson", "--output", "yaml"])
        assert result.exit_code == 0
        doc = yaml.safe_load(result.stdout)
        assert doc["apiVersion"] == "infrahub.app/v1"
        assert doc["kind"] == "Object"
        assert doc["spec"]["kind"] == "TestingPerson"
        assert isinstance(doc["spec"]["data"], list)
        names = [item.get("name", "") for item in doc["spec"]["data"]]
        assert "Ethan Carter" in names

    def test_get_list_with_filter(self, base_dataset: None) -> None:
        """Query persons filtered by name."""
        result = runner.invoke(
            app, ["object", "get", "TestingPerson", "--filter", "name__value=Liam Walker", "--output", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["name"] == "Liam Walker"

    def test_get_list_with_limit(self, base_dataset: None) -> None:
        """Query persons with a limit on results."""
        result = runner.invoke(app, ["object", "get", "TestingPerson", "--limit", "1", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1

    def test_get_detail(self, base_dataset: None) -> None:
        """Get detail view of a single person by display name."""
        result = runner.invoke(app, ["object", "get", "TestingPerson", "Ethan Carter"])
        assert result.exit_code == 0
        assert "Ethan Carter" in result.stdout
        assert "185" in result.stdout

    def test_get_detail_json(self, base_dataset: None) -> None:
        """Get detail view in JSON format."""
        result = runner.invoke(app, ["object", "get", "TestingPerson", "Ethan Carter", "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["kind"] == "TestingPerson"
        assert data["display_label"]

    def test_get_invalid_kind(self, base_dataset: None) -> None:
        """Querying an invalid kind returns an error."""
        result = runner.invoke(app, ["object", "get", "NonExistentKind"])
        assert result.exit_code != 0


class TestEnduserCliWrite(_EnduserCliBase):
    """Write CLI tests: create, update, delete operations.

    TODO: These tests depend on execution order (e.g. test_create_inline_verify
    depends on test_create_inline having run first). Ideally each test should be
    self-contained with its own setup/teardown.
    """

    def test_create_inline(self, base_dataset: None) -> None:
        """Create a person using inline --set flags."""
        result = runner.invoke(
            app,
            ["object", "create", "TestingPerson", "--set", "name=Integration Test Person", "--set", "height=190"],
        )
        assert result.exit_code == 0, f"create failed: {result.output}"
        assert "Saved" in result.stdout

    async def test_create_inline_verify(self, base_dataset: None, client: InfrahubClient) -> None:
        """Verify the object created by test_create_inline exists."""
        node = await client.get(kind="TestingPerson", id="Integration Test Person")
        assert node.name.value == "Integration Test Person"  # type: ignore[union-attr]
        assert node.height.value == 190  # type: ignore[union-attr]

    def test_create_missing_args(self, base_dataset: None) -> None:
        """Create without --set or --file fails."""
        result = runner.invoke(app, ["object", "create", "TestingPerson"])
        assert result.exit_code != 0

    async def test_get_yaml_round_trips_attribute_many_relationship(
        self,
        base_dataset: None,
        client: InfrahubClient,
        schema_extension_01: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Round-trip cardinality-many attribute relationships through the CLI."""
        response = await client.schema.load(schemas=[schema_extension_01], wait_until_converged=True)
        assert not response.errors

        suffix = uuid4().hex
        tag_names = [f"yaml-round-trip-{suffix}-one", f"yaml-round-trip-{suffix}-two"]
        tags = []
        for tag_name in tag_names:
            tag = await client.create(kind="BuiltinTag", name=tag_name)
            await tag.save()
            tags.append(tag)

        rack_name = f"yaml-round-trip-rack-{suffix}"
        rack = await client.create(kind="InfraRack", name=rack_name, tags=tags)
        await rack.save()

        get_result = await asyncio.to_thread(
            runner.invoke,
            app,
            ["object", "get", "InfraRack", "--filter", f"name__value={rack_name}", "--output", "yaml"],
        )
        assert get_result.exit_code == 0, f"object get failed: {get_result.output}"

        object_file = tmp_path / "infra-rack.yaml"
        object_file.write_text(get_result.stdout, encoding="utf-8")
        load_result = await asyncio.to_thread(runner.invoke, app, ["object", "load", str(object_file)])
        assert load_result.exit_code == 0, f"object load failed: {load_result.output}"

        fetched_rack = await client.get(kind="InfraRack", id=rack.id)
        fetched_tags = fetched_rack._get_relationship_many(name="tags")
        await fetched_tags.fetch()
        assert sorted(peer.hfid or [] for peer in fetched_tags.peers) == sorted([[name] for name in tag_names])

    def test_update_inline(self, base_dataset: None) -> None:
        """Update a person's height using --set."""
        result = runner.invoke(
            app,
            ["object", "update", "TestingPerson", "Sophia Walker", "--set", "height=175"],
        )
        assert result.exit_code == 0, f"update failed: {result.output}"
        assert "Updated" in result.stdout

    async def test_update_inline_verify(self, base_dataset: None, client: InfrahubClient) -> None:
        """Verify the update from test_update_inline persisted."""
        node = await client.get(kind="TestingPerson", id="Sophia Walker")
        assert node.height.value == 175  # type: ignore[union-attr]

    async def test_delete_setup(self, base_dataset: None, client: InfrahubClient) -> None:
        """Create a throwaway object for the delete test."""
        obj = await client.create(kind="TestingPerson", name="Delete Me", height=100)
        await obj.save()

    def test_delete_with_yes(self, base_dataset: None) -> None:
        """Delete a person using --yes to skip confirmation."""
        result = runner.invoke(app, ["object", "delete", "TestingPerson", "Delete Me", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.stdout

    async def test_delete_verify(self, base_dataset: None, client: InfrahubClient) -> None:
        """Verify the object from test_delete_with_yes is gone."""
        node = await client.get(kind="TestingPerson", id="Delete Me", raise_when_missing=False)
        assert node is None
