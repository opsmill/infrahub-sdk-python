from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.exceptions import FieldNotLoadedError
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import TESTING_ANIMAL, TESTING_CAT, TESTING_DOG, SchemaAnimal

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.node import InfrahubNode

BREED_NOT_FETCHED = re.escape("TestingDog.breed was not fetched: the node was queried with only=['name', 'owner'].")
HEIGHT_NOT_FETCHED = re.escape("TestingPerson.height was not fetched: the node was queried with only=['name'].")
BREED_BY_ANIMAL = {
    "Bella": (TESTING_CAT, "Bengal"),
    "Luna": (TESTING_CAT, "Siamese"),
    "Daisy": (TESTING_DOG, "French Bulldog"),
    "Rocky": (TESTING_DOG, "German Shepherd"),
}
BELLA_HFID = ["Ethan Carter", "Bella", "#123456"]
ROCKY_WEIGHT = 32


class TestNodeOnly(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    def base_dataset(
        self,
        load_schema: None,
        person_ethan: InfrahubNode,
        person_sophia: InfrahubNode,
        cat_bella: InfrahubNode,
        cat_luna: InfrahubNode,
        dog_daisy: InfrahubNode,
        dog_rocky: InfrahubNode,
    ) -> None:
        pass

    async def test_all_with_only_reads_the_named_fields(
        self,
        client: InfrahubClient,
        base_dataset: None,
        person_ethan: InfrahubNode,
        person_sophia: InfrahubNode,
    ) -> None:
        dogs = await client.all(kind=TESTING_DOG, only=["name", "owner"])

        assert {dog.name.value: dog.owner.id for dog in dogs} == {
            "Daisy": person_ethan.id,
            "Rocky": person_sophia.id,
        }
        for dog in dogs:
            with pytest.raises(FieldNotLoadedError, match=BREED_NOT_FETCHED):
                _ = dog.breed.value

    async def test_all_on_generic_with_only_reads_fields_of_each_kind(
        self, client: InfrahubClient, base_dataset: None
    ) -> None:
        animals = await client.all(kind=TESTING_ANIMAL, only=["name", "breed"])

        assert {animal.name.value: (animal.get_kind(), animal.breed.value) for animal in animals} == BREED_BY_ANIMAL

    async def test_hfid_in_only_gives_the_hfid_of_the_kind(
        self, client: InfrahubClient, base_dataset: None, cat_bella: InfrahubNode
    ) -> None:
        cat = await client.get(kind=TESTING_CAT, id=cat_bella.id, only=["hfid"])

        assert cat.hfid == BELLA_HFID

    async def test_fetch_with_only_on_owner_reads_its_name(
        self, client: InfrahubClient, base_dataset: None, dog_rocky: InfrahubNode
    ) -> None:
        dog = await client.get(kind=TESTING_DOG, id=dog_rocky.id, only=["name", "owner"])

        await dog.owner.fetch(only=["name"])

        owner = dog.owner.peer
        assert owner.name.value == "Sophia Walker"
        with pytest.raises(FieldNotLoadedError, match=HEIGHT_NOT_FETCHED):
            _ = owner.height.value

    async def test_save_of_node_from_only_keeps_its_other_fields(
        self, client: InfrahubClient, base_dataset: None, dog_rocky: InfrahubNode, person_sophia: InfrahubNode
    ) -> None:
        dog = await client.get(kind=TESTING_DOG, id=dog_rocky.id, only=["weight"])
        dog.weight.value = ROCKY_WEIGHT

        await dog.save()

        saved = await client.get(kind=TESTING_DOG, id=dog_rocky.id)
        assert [saved.name.value, saved.breed.value, saved.color.value, saved.owner.id, saved.weight.value] == [
            "Rocky",
            "German Shepherd",
            "#784212",
            person_sophia.id,
            ROCKY_WEIGHT,
        ]


class TestNodeOnlySync(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    def base_dataset(
        self,
        load_schema: None,
        person_ethan: InfrahubNode,
        person_sophia: InfrahubNode,
        cat_bella: InfrahubNode,
        cat_luna: InfrahubNode,
        dog_daisy: InfrahubNode,
        dog_rocky: InfrahubNode,
    ) -> None:
        pass

    def test_all_with_only_reads_the_named_fields(
        self,
        client_sync: InfrahubClientSync,
        base_dataset: None,
        person_ethan: InfrahubNode,
        person_sophia: InfrahubNode,
    ) -> None:
        dogs = client_sync.all(kind=TESTING_DOG, only=["name", "owner"])

        assert {dog.name.value: dog.owner.id for dog in dogs} == {
            "Daisy": person_ethan.id,
            "Rocky": person_sophia.id,
        }
        for dog in dogs:
            with pytest.raises(FieldNotLoadedError, match=BREED_NOT_FETCHED):
                _ = dog.breed.value

    def test_all_on_generic_with_only_reads_fields_of_each_kind(
        self, client_sync: InfrahubClientSync, base_dataset: None
    ) -> None:
        animals = client_sync.all(kind=TESTING_ANIMAL, only=["name", "breed"])

        assert {animal.name.value: (animal.get_kind(), animal.breed.value) for animal in animals} == BREED_BY_ANIMAL

    def test_hfid_in_only_gives_the_hfid_of_the_kind(
        self, client_sync: InfrahubClientSync, base_dataset: None, cat_bella: InfrahubNode
    ) -> None:
        cat = client_sync.get(kind=TESTING_CAT, id=cat_bella.id, only=["hfid"])

        assert cat.hfid == BELLA_HFID

    def test_fetch_with_only_on_owner_reads_its_name(
        self, client_sync: InfrahubClientSync, base_dataset: None, dog_rocky: InfrahubNode
    ) -> None:
        dog = client_sync.get(kind=TESTING_DOG, id=dog_rocky.id, only=["name", "owner"])

        dog.owner.fetch(only=["name"])

        owner = dog.owner.peer
        assert owner.name.value == "Sophia Walker"
        with pytest.raises(FieldNotLoadedError, match=HEIGHT_NOT_FETCHED):
            _ = owner.height.value

    def test_save_of_node_from_only_keeps_its_other_fields(
        self,
        client_sync: InfrahubClientSync,
        base_dataset: None,
        dog_rocky: InfrahubNode,
        person_sophia: InfrahubNode,
    ) -> None:
        dog = client_sync.get(kind=TESTING_DOG, id=dog_rocky.id, only=["weight"])
        dog.weight.value = ROCKY_WEIGHT

        dog.save()

        saved = client_sync.get(kind=TESTING_DOG, id=dog_rocky.id)
        assert [saved.name.value, saved.breed.value, saved.color.value, saved.owner.id, saved.weight.value] == [
            "Rocky",
            "German Shepherd",
            "#784212",
            person_sophia.id,
            ROCKY_WEIGHT,
        ]
