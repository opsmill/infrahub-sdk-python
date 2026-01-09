from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import ujson

from infrahub_sdk.exceptions import SchemaNotFoundError
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.car_person import TESTING_CAR, TESTING_MANUFACTURER, TESTING_PERSON, SchemaCarPerson
from infrahub_sdk.transfer.exceptions import TransferFileNotFoundError
from infrahub_sdk.transfer.exporter.json import LineDelimitedJSONExporter
from infrahub_sdk.transfer.importer.json import LineDelimitedJSONImporter
from infrahub_sdk.transfer.schema_sorter import InfrahubSchemaTopologicalSorter

if TYPE_CHECKING:
    from pytest import TempPathFactory

    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode
    from infrahub_sdk.schema import SchemaRoot


class TestSchemaExportImportBase(TestInfrahubDockerClient, SchemaCarPerson):
    @pytest.fixture(scope="class")
    def temporary_directory(self, tmp_path_factory: TempPathFactory) -> Path:
        return tmp_path_factory.mktemp("infrahub-integration-tests")

    @pytest.fixture(scope="class")
    async def load_schema(self, client: InfrahubClient, schema_base: SchemaRoot) -> None:
        resp = await client.schema.load(schemas=[schema_base.to_schema_dict()], wait_until_converged=True)
        assert resp.errors == {}

    @pytest.fixture(scope="class")
    async def initial_dataset(
        self,
        client: InfrahubClient,
        load_schema: None,
        person_joe: InfrahubNode,
        person_jane: InfrahubNode,
        tag_blue: InfrahubNode,
        tag_red: InfrahubNode,
    ) -> dict[str, Any]:
        honda = await client.create(kind=TESTING_MANUFACTURER, name="Honda", description="Honda Motor Co., Ltd")
        await honda.save()

        renault = await client.create(kind=TESTING_MANUFACTURER, name="Renault", description="Groupe Renault")
        await renault.save()

        accord = await client.create(
            kind=TESTING_CAR,
            name="Accord",
            description="Honda Accord",
            color="#3443eb",
            manufacturer=honda,
            owner=person_jane,
        )
        await accord.save()

        civic = await client.create(
            kind=TESTING_CAR,
            name="Civic",
            description="Honda Civic",
            color="#c9eb34",
            manufacturer=honda,
            owner=person_jane,
        )
        await civic.save()

        megane = await client.create(
            kind=TESTING_CAR,
            name="Megane",
            description="Renault Megane",
            color="#c93420",
            manufacturer=renault,
            owner=person_joe,
        )
        await megane.save()

        await accord.tags.fetch()
        accord.tags.add(tag_blue)
        await accord.save()

        await civic.tags.fetch()
        civic.tags.add(tag_blue)
        await civic.save()

        return {
            "joe": person_joe.id,
            "jane": person_jane.id,
            "honda": honda.id,
            "renault": renault.id,
            "accord": accord.id,
            "civic": civic.id,
            "megane": megane.id,
            "blue": tag_blue.id,
            "red": tag_red.id,
        }

    def reset_export_directory(self, temporary_directory: Path) -> None:
        for file in temporary_directory.iterdir():
            if file.is_file():
                file.unlink()

    async def test_step01_export_no_schema(self, client: InfrahubClient, temporary_directory: Path) -> None:
        exporter = LineDelimitedJSONExporter(client=client)
        await exporter.export(export_directory=temporary_directory, branch="main", namespaces=[])

        nodes_file = temporary_directory / "nodes.json"
        relationships_file = temporary_directory / "relationships.json"

        assert nodes_file.exists()
        assert relationships_file.exists()

        admin_found = False
        with nodes_file.open() as f:
            for line in f:
                node_dump = ujson.loads(line)
                if node_dump.get("kind") == "CoreAccount":
                    graphql_data = ujson.loads(node_dump["graphql_json"])
                    if graphql_data.get("name", {}).get("value") == "admin":
                        admin_found = True
                        break
        assert admin_found, "Admin account not found in exported nodes"

    async def test_step02_import_no_schema(self, client: InfrahubClient, temporary_directory: Path) -> None:
        importer = LineDelimitedJSONImporter(client=client, topological_sorter=InfrahubSchemaTopologicalSorter())
        await importer.import_data(import_directory=temporary_directory, branch="main")

        for kind in (TESTING_PERSON, TESTING_CAR, TESTING_MANUFACTURER):
            with pytest.raises(SchemaNotFoundError):
                await client.all(kind=kind)

        self.reset_export_directory(temporary_directory)

    async def test_step03_export_initial_dataset(
        self, client: InfrahubClient, temporary_directory: Path, initial_dataset: dict[str, Any]
    ) -> None:
        exporter = LineDelimitedJSONExporter(client=client)
        await exporter.export(export_directory=temporary_directory, branch="main", namespaces=[])

        nodes_file = temporary_directory / "nodes.json"
        relationships_file = temporary_directory / "relationships.json"

        assert nodes_file.exists()
        assert relationships_file.exists()

        nodes_dump = []
        with nodes_file.open() as reader:
            while line := reader.readline():
                nodes_dump.append(ujson.loads(line))
        assert len(nodes_dump) >= len(initial_dataset)

        relationships_dump = ujson.loads(relationships_file.read_text())
        assert relationships_dump

    async def test_step04_import_initial_dataset(
        self, client: InfrahubClient, temporary_directory: Path, load_schema: None
    ) -> None:
        importer = LineDelimitedJSONImporter(client=client, topological_sorter=InfrahubSchemaTopologicalSorter())
        await importer.import_data(import_directory=temporary_directory, branch="main")

        for kind in (TESTING_PERSON, TESTING_CAR, TESTING_MANUFACTURER):
            assert await client.all(kind=kind)

    async def test_step05_import_initial_dataset_with_existing_data(
        self, client: InfrahubClient, temporary_directory: Path, initial_dataset: dict[str, Any]
    ) -> None:
        counters: dict[str, int] = {}
        for kind in (TESTING_PERSON, TESTING_CAR, TESTING_MANUFACTURER):
            nodes = await client.all(kind=kind)
            counters[kind] = len(nodes)

        importer = LineDelimitedJSONImporter(client=client, topological_sorter=InfrahubSchemaTopologicalSorter())
        await importer.import_data(import_directory=temporary_directory, branch="main")

        for kind in (TESTING_PERSON, TESTING_CAR, TESTING_MANUFACTURER):
            nodes = await client.all(kind=kind)
            assert len(nodes) == counters[kind]

        self.reset_export_directory(temporary_directory)

    async def test_step99_import_wrong_directory(self, client: InfrahubClient) -> None:
        importer = LineDelimitedJSONImporter(client=client, topological_sorter=InfrahubSchemaTopologicalSorter())
        with pytest.raises(TransferFileNotFoundError):
            await importer.import_data(import_directory=Path("this_directory_does_not_exist"), branch="main")


class TestSchemaExportImportManyRelationships(TestInfrahubDockerClient, SchemaCarPerson):
    @pytest.fixture(scope="class")
    def temporary_directory(self, tmp_path_factory: TempPathFactory) -> Path:
        return tmp_path_factory.mktemp("infrahub-integration-tests-many")

    @pytest.fixture(scope="class")
    async def load_schema(self, client: InfrahubClient, schema_base: SchemaRoot) -> None:
        resp = await client.schema.load(schemas=[schema_base.to_schema_dict()], wait_until_converged=True)
        assert resp.errors == {}

    @pytest.fixture(scope="class")
    async def initial_dataset(
        self,
        client: InfrahubClient,
        load_schema: None,
        person_joe: InfrahubNode,
        person_jane: InfrahubNode,
        tag_blue: InfrahubNode,
        tag_red: InfrahubNode,
        tag_green: InfrahubNode,
    ) -> dict[str, Any]:
        bmw = await client.create(
            kind=TESTING_MANUFACTURER,
            name="BMW",
            description="Bayerische Motoren Werke AG is a German multinational manufacturer",
        )
        await bmw.save()

        fiat = await client.create(
            kind=TESTING_MANUFACTURER,
            name="Fiat",
            description="Fiat Automobiles S.p.A. is an Italian automobile manufacturer",
        )
        await fiat.save()

        five_series = await client.create(
            kind=TESTING_CAR,
            name="5 series",
            description="BMW 5 series",
            color="#000000",
            manufacturer=bmw,
            owner=person_joe,
        )
        await five_series.save()

        five_hundred = await client.create(
            kind=TESTING_CAR,
            name="500",
            description="Fiat 500",
            color="#540302",
            manufacturer=fiat,
            owner=person_jane,
        )
        await five_hundred.save()

        await five_series.tags.fetch()
        five_series.tags.add(tag_blue)
        five_series.tags.add(tag_green)
        await five_series.save()

        await five_hundred.tags.fetch()
        five_hundred.tags.add(tag_red)
        five_hundred.tags.add(tag_green)
        await five_hundred.save()

        return {
            "bmw": bmw.id,
            "fiat": fiat.id,
            "5series": five_series.id,
            "500": five_hundred.id,
            "blue": tag_blue.id,
            "red": tag_red.id,
            "green": tag_green.id,
        }

    def reset_export_directory(self, temporary_directory: Path) -> None:
        for file in temporary_directory.iterdir():
            if file.is_file():
                file.unlink()

    async def test_step01_export_initial_dataset(
        self, client: InfrahubClient, temporary_directory: Path, initial_dataset: dict[str, Any]
    ) -> None:
        exporter = LineDelimitedJSONExporter(client=client)
        await exporter.export(export_directory=temporary_directory, branch="main", namespaces=[])

        nodes_file = temporary_directory / "nodes.json"
        relationships_file = temporary_directory / "relationships.json"

        assert nodes_file.exists()
        assert relationships_file.exists()

        nodes_dump = []
        with nodes_file.open() as reader:
            while line := reader.readline():
                nodes_dump.append(ujson.loads(line))
        assert len(nodes_dump) >= len(initial_dataset)

        relationships_dump = ujson.loads(relationships_file.read_text())
        assert relationships_dump

    async def test_step02_import_initial_dataset(
        self, client: InfrahubClient, temporary_directory: Path, initial_dataset: dict[str, Any]
    ) -> None:
        importer = LineDelimitedJSONImporter(client=client, topological_sorter=InfrahubSchemaTopologicalSorter())
        await importer.import_data(import_directory=temporary_directory, branch="main")

        for kind in (TESTING_CAR, TESTING_MANUFACTURER):
            assert await client.all(kind=kind)

        relationship_count = 0
        for node in await client.all(kind=TESTING_CAR):
            await node.tags.fetch()
            relationship_count += len(node.tags.peers)
        assert relationship_count >= 4

    async def test_step03_import_initial_dataset_with_existing_data(
        self, client: InfrahubClient, temporary_directory: Path, initial_dataset: dict[str, Any]
    ) -> None:
        relationship_count_before = 0
        for node in await client.all(kind=TESTING_CAR):
            await node.tags.fetch()
            relationship_count_before += len(node.tags.peers)

        importer = LineDelimitedJSONImporter(client=client, topological_sorter=InfrahubSchemaTopologicalSorter())
        await importer.import_data(import_directory=temporary_directory, branch="main")

        for kind in (TESTING_CAR, TESTING_MANUFACTURER):
            assert await client.all(kind=kind)

        relationship_count_after = 0
        for node in await client.all(kind=TESTING_CAR):
            await node.tags.fetch()
            relationship_count_after += len(node.tags.peers)

        assert relationship_count_after == relationship_count_before

        self.reset_export_directory(temporary_directory)
