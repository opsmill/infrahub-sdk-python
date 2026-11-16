from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import TESTING_CAT, TESTING_PERSON, SchemaAnimal
from infrahub_sdk.transforms import InfrahubTransform

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from infrahub_sdk import InfrahubClient

NAME_PREFIX = "store-copies-"
# Cats are deleted before persons: an animal holds a mandatory relationship to its owner.
CREATED_KINDS = (TESTING_CAT, TESTING_PERSON, "BuiltinTag", "CoreStandardGroup")


class PersonFromStoreTransform(InfrahubTransform):
    query = "person_with_animals"
    person_name = ""

    async def transform(self, data: dict) -> dict[str, Any]:
        person = self.store.get(key=self.person_name, kind=TESTING_PERSON)
        return {"name": person._get_attribute("name").value, "height": person._get_attribute("height").value}


class TestStoreRelatedCopies(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    async def base_dataset(self, client: InfrahubClient, load_schema: None) -> AsyncGenerator[None, None]:
        yield
        for kind in CREATED_KINDS:
            for node in await client.filters(kind=kind):
                if str(node._get_attribute("name").value or "").startswith(NAME_PREFIX):
                    await node.delete()

    async def _person_with_cat(self, client: InfrahubClient, suffix: str) -> tuple[InfrahubNode, InfrahubNode]:
        person = await client.create(kind=TESTING_PERSON, name=f"{NAME_PREFIX}person-{suffix}", height=180)
        await person.save()
        cat = await client.create(
            kind=TESTING_CAT, name=f"{NAME_PREFIX}cat-{suffix}", breed="Siamese", color="#123456", owner=person
        )
        await cat.save()
        return person, cat

    async def test_tracking_session_keeps_values_of_node_stored_under_a_key(
        self, client: InfrahubClient, base_dataset: None
    ) -> None:
        tag_name = f"{NAME_PREFIX}tag-tracking"
        params = {"run": "store-copies"}

        # The first run creates the tracking group, so the second run reads it back with its members.
        for _ in range(2):
            async with client.start_tracking(
                identifier=f"{NAME_PREFIX}tracking", params=params, delete_unused_nodes=True
            ):
                tag = await client.create(kind="BuiltinTag", name=tag_name)
                await tag.save(allow_upsert=True)
                client.store.set(key="tracked-tag", node=tag)

        assert client.store.get(key="tracked-tag")._get_attribute("name").value == tag_name

    async def test_transform_store_returns_person_by_hfid_when_its_animal_references_it_back(
        self, client: InfrahubClient, base_dataset: None
    ) -> None:
        person, _ = await self._person_with_cat(client=client, suffix="transform")
        person_name = person._get_attribute("name").value
        query = (
            """
        query {
          TestingPerson(name__value: "%s") {
            edges { node {
              id __typename
              name { value }
              height { value }
              animals { edges { node { id __typename name { value } owner { node { id __typename } } } } }
            } }
          }
        }
        """
            % person_name
        )
        data = await client.execute_graphql(query=query)
        transform = PersonFromStoreTransform(
            client=client, infrahub_node=InfrahubNode, convert_query_response=True, branch="main"
        )
        transform.person_name = person_name

        assert await transform.run(data=data) == {"name": person_name, "height": 180}

    async def test_saved_node_is_replaced_by_its_copy_from_a_prefetch_query(
        self, client: InfrahubClient, base_dataset: None
    ) -> None:
        person, cat = await self._person_with_cat(client=client, suffix="prefetch")
        person_name = person._get_attribute("name").value

        await client.filters(
            kind=TESTING_CAT, name__value=cat._get_attribute("name").value, prefetch_relationships=True
        )

        by_id = client.store.get(key=person.id)
        assert by_id is not person
        assert client.store.get(key=[person_name], kind=TESTING_PERSON) is by_id
        assert by_id._get_attribute("height").value == 180

    async def test_query_with_only_and_no_prefetch_does_not_replace_the_stored_peer(
        self, client: InfrahubClient, base_dataset: None
    ) -> None:
        person, cat = await self._person_with_cat(client=client, suffix="only")

        await client.filters(kind=TESTING_CAT, name__value=cat._get_attribute("name").value, only=["name", "owner"])

        assert client.store.get(key=person.id) is person
