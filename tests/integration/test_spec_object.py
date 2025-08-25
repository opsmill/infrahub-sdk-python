from pathlib import Path

import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.schema import SchemaRoot
from infrahub_sdk.spec.menu import MenuFile
from infrahub_sdk.spec.object import ObjectFile
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import SchemaAnimal
from infrahub_sdk.utils import get_fixtures_dir
from infrahub_sdk.yaml import YamlFile


def load_object_file(name: str) -> ObjectFile:
    files = ObjectFile.load_from_disk(paths=[get_fixtures_dir() / "spec_objects" / name])
    assert len(files) == 1
    return files[0]


def load_menu_file(name: str) -> MenuFile:
    files = MenuFile.load_from_disk(paths=[get_fixtures_dir() / "spec_objects" / name])
    assert len(files) == 1
    return files[0]


def test_load_nested_folders_order() -> None:
    files = YamlFile.load_from_disk(paths=[get_fixtures_dir() / "nested_spec_objects"])
    assert len(files) == 6
    assert Path(files[0].location).name == "3_file.yml"
    assert Path(files[1].location).name == "5_file.yml"
    assert Path(files[2].location).name == "6_file.yml"
    assert Path(files[3].location).name == "0_file.yml"
    assert Path(files[4].location).name == "1_file.yml"
    assert Path(files[5].location).name == "4_file.yml"


class TestSpecObject(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    def branch_name(self) -> str:
        return "branch2"

    @pytest.fixture(scope="class")
    def spec_objects_fixtures_dir(self) -> Path:
        return get_fixtures_dir() / "spec_objects"

    @pytest.fixture(scope="class")
    async def initial_schema(self, default_branch: str, client: InfrahubClient, schema_base: SchemaRoot) -> None:
        await client.schema.wait_until_converged(branch=default_branch)

        resp = await client.schema.load(
            schemas=[schema_base.to_schema_dict()], branch=default_branch, wait_until_converged=True
        )
        assert resp.errors == {}

    async def test_create_branch(self, client: InfrahubClient, initial_schema: None, branch_name: str) -> None:
        await client.branch.create(branch_name=branch_name, sync_with_git=False)

    async def test_load_tags(self, client: InfrahubClient, branch_name: str, initial_schema: None) -> None:
        obj_file = load_object_file("animal_tags01.yml")
        await obj_file.validate_format(client=client, branch=branch_name)

        # Check that the nodes are not present in the database before loading the file
        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 0

        await obj_file.process(client=client, branch=branch_name)

        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 3

    async def test_update_tags(self, client: InfrahubClient, branch_name: str, initial_schema: None) -> None:
        obj_file = load_object_file("animal_tags02.yml")
        await obj_file.validate_format(client=client, branch=branch_name)

        # Check that the nodes are not present in the database before loading the file
        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 3

        await obj_file.process(client=client, branch=branch_name)

        tags = await client.all(kind=obj_file.spec.kind, branch=branch_name)
        tags_by_name = {"__".join(tag.get_human_friendly_id()): tag for tag in tags}
        assert len(tags_by_name) == 4
        assert tags_by_name["Veterinarian"].description.value == "Licensed animal healthcare professional"

    async def test_load_persons(self, client: InfrahubClient, branch_name: str, initial_schema: None) -> None:
        obj_file = load_object_file("animal_person01.yml")
        await obj_file.validate_format(client=client, branch=branch_name)

        # Check that the nodes are not present in the database before loading the file
        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 0

        await obj_file.process(client=client, branch=branch_name)

        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 3

    async def test_load_dogs(self, client: InfrahubClient, branch_name: str, initial_schema: None) -> None:
        obj_file = load_object_file("animal_dog01.yml")
        await obj_file.validate_format(client=client, branch=branch_name)

        # Check that the nodes are not present in the database before loading the file
        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 0

        await obj_file.process(client=client, branch=branch_name)

        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 4

    async def test_load_persons02(self, client: InfrahubClient, branch_name: str, initial_schema: None) -> None:
        obj_file = load_object_file("animal_person02.yml")
        await obj_file.validate_format(client=client, branch=branch_name)

        # Check that the nodes are not present in the database before loading the file
        assert len(await client.all(kind=obj_file.spec.kind, branch=branch_name)) == 4

        await obj_file.process(client=client, branch=branch_name)

        persons = await client.all(kind=obj_file.spec.kind, branch=branch_name)
        person_by_name = {"__".join(person.get_human_friendly_id()): person for person in persons}
        assert len(persons) == 6

        # Validate that the best_friends relationship is correctly populated
        await person_by_name["Mike Johnson"].best_friends.fetch()
        friends = [peer.hfid for peer in person_by_name["Mike Johnson"].best_friends.peers]
        assert friends == [["Jane Smith", "Max"], ["Sarah Williams", "Charlie"]]

        # Validate the tags relationship is correctly populated for both Alex Thompson and Mike Johnson
        await person_by_name["Alex Thompson"].tags.fetch()
        tags_alex = [tag.hfid for tag in person_by_name["Alex Thompson"].tags.peers]
        assert tags_alex == [["Dog Lover"]]

        await person_by_name["Mike Johnson"].tags.fetch()
        tags_mike = [tag.hfid for tag in person_by_name["Mike Johnson"].tags.peers]
        assert sorted(tags_mike) == sorted([["Veterinarian"], ["Breeder"]])

        # Validate that animals for Emily Parler have been correctly created
        await person_by_name["Emily Parker"].animals.fetch()
        animals_emily = [animal.display_label for animal in person_by_name["Emily Parker"].animals.peers]
        assert sorted(animals_emily) == sorted(["Max Golden Retriever", "Whiskers Siamese #FFD700"])

    async def test_load_menu(self, client: InfrahubClient, branch_name: str, initial_schema: None) -> None:
        menu_file = load_menu_file("animal_menu01.yml")
        await menu_file.validate_format(client=client, branch=branch_name)

        await menu_file.process(client=client, branch=branch_name)

        menu = await client.filters(kind=menu_file.spec.kind, protected__value=False, branch=branch_name)
        assert len(menu) == 3

        menu_by_name = {menu.display_label: menu for menu in menu}
        await menu_by_name["Animals"].children.fetch()
        peer_labels = [peer.display_label for peer in menu_by_name["Animals"].children.peers]
        assert sorted(peer_labels) == sorted(["Dog", "Cat"])
