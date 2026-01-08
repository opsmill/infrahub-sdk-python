from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest

from infrahub_sdk import Config, InfrahubClient
from infrahub_sdk.branch import BranchData
from infrahub_sdk.constants import InfrahubClientMode
from infrahub_sdk.exceptions import BranchNotFoundError, URLNotFoundError
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.playback import JSONPlayback
from infrahub_sdk.recorder import JSONRecorder
from infrahub_sdk.schema import GenericSchema, NodeSchema, ProfileSchemaAPI
from infrahub_sdk.task.models import Task, TaskFilter, TaskLog, TaskState
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import TESTING_ANIMAL, TESTING_CAT, TESTING_DOG, TESTING_PERSON, SchemaAnimal
from infrahub_sdk.types import Order


class TestInfrahubNode(TestInfrahubDockerClient, SchemaAnimal):
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
    ) -> None:
        await client.branch.create(branch_name="branch01")

    @pytest.fixture
    async def set_pagination_size3(self, client: InfrahubClient) -> AsyncGenerator:
        original_pagination_size = client.pagination_size
        client.pagination_size = 3
        yield
        client.pagination_size = original_pagination_size

    async def test_query_branches(self, client: InfrahubClient, base_dataset: None) -> None:
        branches = await client.branch.all()
        main = await client.branch.get(branch_name="main")

        with pytest.raises(BranchNotFoundError):
            await client.branch.get(branch_name="not-found")

        assert main.name == "main"
        assert "main" in branches
        assert "branch01" in branches

    async def test_branch_delete(self, client: InfrahubClient, base_dataset: None) -> None:
        async_branch = "async-delete-branch"
        await client.branch.create(branch_name=async_branch)
        pre_delete = await client.branch.all()
        await client.branch.delete(async_branch)
        post_delete = await client.branch.all()
        assert async_branch in pre_delete
        assert async_branch not in post_delete

    async def test_get_all(self, client: InfrahubClient, base_dataset: None) -> None:
        nodes = await client.all(kind=TESTING_CAT)
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNode)
        assert [node.name.value for node in nodes] == ["Bella", "Luna"]

    async def test_get_all_no_order(self, client: InfrahubClient, base_dataset: None) -> None:
        nodes = await client.all(kind=TESTING_CAT, order=Order(disable=True))
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNode)
        assert {node.name.value for node in nodes} == {"Bella", "Luna"}

    async def test_get_filters_no_order(self, client: InfrahubClient, base_dataset: None) -> None:
        nodes = await client.filters(kind=TESTING_CAT, order=Order(disable=True))
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNode)
        assert {node.name.value for node in nodes} == {"Bella", "Luna"}

    async def test_get_one(
        self, client: InfrahubClient, base_dataset: None, cat_luna: InfrahubNode, person_sophia: InfrahubNode
    ) -> None:
        node1 = await client.get(kind=TESTING_CAT, id=cat_luna.id)
        assert isinstance(node1, InfrahubNode)
        assert node1.name.value == "Luna"

        node2 = await client.get(kind=TESTING_PERSON, id=person_sophia.id)
        assert isinstance(node2, InfrahubNode)
        assert node2.name.value == "Sophia Walker"

    async def test_filters_partial_match(self, client: InfrahubClient, base_dataset: None) -> None:
        nodes = await client.filters(kind=TESTING_PERSON, name__value="Walker")
        assert not nodes

        nodes = await client.filters(kind=TESTING_PERSON, partial_match=True, name__value="Walker")
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNode)
        assert sorted([node.name.value for node in nodes]) == ["Liam Walker", "Sophia Walker"]

    async def test_get_generic(self, client: InfrahubClient, base_dataset: None) -> None:
        nodes = await client.all(kind=TESTING_ANIMAL)
        assert len(nodes) == 4

    async def test_get_generic_fragment(self, client: InfrahubClient, base_dataset: None) -> None:
        nodes = await client.all(kind=TESTING_ANIMAL, fragment=True)
        assert len(nodes)
        assert nodes[0].typename in {TESTING_DOG, TESTING_CAT}
        assert nodes[0].breed.value is not None

    async def test_get_generic_filter_source(
        self, client: InfrahubClient, base_dataset: None, person_liam: InfrahubNode
    ) -> None:
        admin = await client.get(kind="CoreAccount", name__value="admin")

        obj = await client.create(
            kind=TESTING_CAT, name={"value": "SourceFilterCat", "source": admin.id}, breed="Siamese", owner=person_liam
        )
        await obj.save()

        nodes = await client.filters(kind="CoreNode", any__source__id=admin.id)
        assert len(nodes) == 1
        assert nodes[0].typename == TESTING_CAT
        assert nodes[0].id == obj.id

    async def test_get_related_nodes(
        self, client: InfrahubClient, base_dataset: None, person_ethan: InfrahubNode
    ) -> None:
        ethan = await client.get(kind=TESTING_PERSON, id=person_ethan.id)
        assert ethan

        assert ethan.animals.peers == []
        await ethan.animals.fetch()
        assert len(ethan.animals.peers) == 3

    async def test_count(self, client: InfrahubClient, base_dataset: None) -> None:
        count = await client.count(kind=TESTING_PERSON)
        assert count == 3

    async def test_count_with_filter(self, client: InfrahubClient, base_dataset: None) -> None:
        count = await client.count(kind=TESTING_PERSON, name__values=["Liam Walker", "Ethan Carter"])
        assert count == 2

    async def test_profile(self, client: InfrahubClient, base_dataset: None, person_liam: InfrahubNode) -> None:
        profile_schema_kind = f"Profile{TESTING_DOG}"
        profile_schema = await client.schema.get(kind=profile_schema_kind)
        assert isinstance(profile_schema, ProfileSchemaAPI)

        profile1 = await client.create(
            kind=profile_schema_kind, profile_name="profile1", profile_priority=1000, color="#111111"
        )
        await profile1.save()

        obj = await client.create(
            kind=TESTING_DOG, name="Sparky", breed="Border Collie", owner=person_liam, profiles=[profile1]
        )
        await obj.save()

        obj1 = await client.get(kind=TESTING_DOG, id=obj.id)
        assert obj1.color.value == "#111111"

    @pytest.mark.xfail(reason="Require Infrahub v1.7")
    async def test_profile_relationship_is_from_profile(
        self, client: InfrahubClient, base_dataset: None, person_liam: InfrahubNode
    ) -> None:
        tag = await client.create(kind="BuiltinTag", name="profile-tag-test")
        await tag.save()

        profile_schema_kind = f"Profile{TESTING_PERSON}"
        profile = await client.create(
            kind=profile_schema_kind, profile_name="person-profile-with-tag", profile_priority=1000, tags=[tag]
        )
        await profile.save()

        person = await client.create(kind=TESTING_PERSON, name="Profile Relationship Test Person", profiles=[profile])
        await person.save()

        fetched_person = await client.get(kind=TESTING_PERSON, id=person.id, property=True, include=["tags"])
        assert fetched_person.tags.initialized
        assert len(fetched_person.tags.peers) == 1
        assert fetched_person.tags.peers[0].id == tag.id
        assert fetched_person.tags.peers[0].is_from_profile
        assert fetched_person.tags.is_from_profile

    async def test_create_branch(self, client: InfrahubClient, base_dataset: None) -> None:
        branch = await client.branch.create(branch_name="new-branch-1")
        assert isinstance(branch, BranchData)
        assert branch.id is not None

    async def test_create_branch_async(self, client: InfrahubClient, base_dataset: None) -> None:
        task_id = await client.branch.create(branch_name="new-branch-2", wait_until_completion=False)
        assert isinstance(task_id, str)

    async def test_query_unexisting_branch(self, client: InfrahubClient) -> None:
        with pytest.raises(URLNotFoundError, match=r"/graphql/unexisting` not found."):
            await client.execute_graphql(query="unused", branch_name="unexisting")

    async def test_create_generic_rel_with_hfid(
        self,
        client: InfrahubClient,
        base_dataset: None,
        cat_luna: InfrahubNode,
        person_sophia: InfrahubNode,
        schema_animal: GenericSchema,
        schema_cat: NodeSchema,
    ) -> None:
        # See https://github.com/opsmill/infrahub-sdk-python/issues/277
        assert schema_animal.human_friendly_id != schema_cat.human_friendly_id, (
            "Inherited node schema should have a different hfid than generic one for this test to be relevant"
        )
        person_sophia.favorite_animal = {"hfid": cat_luna.hfid, "kind": TESTING_CAT}
        await person_sophia.save()
        person_sophia = await client.get(kind=TESTING_PERSON, id=person_sophia.id, prefetch_relationships=True)
        assert person_sophia.favorite_animal.id == cat_luna.id

        # Ensure that nullify it will remove the relationship related node
        person_sophia.favorite_animal = None
        await person_sophia.save()
        person_sophia = await client.get(kind=TESTING_PERSON, id=person_sophia.id, prefetch_relationships=True)
        assert not person_sophia.favorite_animal.id

    async def test_task_query(
        self, client: InfrahubClient, base_dataset: None, set_pagination_size3: AsyncGenerator[None, None]
    ) -> None:
        nbr_tasks = await client.task.count()
        assert nbr_tasks

        tasks = await client.task.filter(filter=TaskFilter(state=[TaskState.COMPLETED]))
        assert tasks
        task_ids = [task.id for task in tasks]

        # Query Tasks using Parallel mode
        tasks_parallel = await client.task.filter(filter=TaskFilter(state=[TaskState.COMPLETED]), parallel=True)
        assert tasks_parallel
        task_parallel_ids = [task.id for task in tasks_parallel]

        # Additional tasks might have been completed between the two queries
        # validate that we get at least as many tasks as in the first query
        # and that all task IDs from the first query are present in the second one
        assert len(tasks_parallel) >= len(tasks)
        assert set(task_ids).issubset(set(task_parallel_ids))

        # Query Tasks by ID
        tasks_parallel_filtered = await client.task.filter(filter=TaskFilter(ids=task_ids[:2]), parallel=True)
        assert tasks_parallel_filtered
        assert len(tasks_parallel_filtered) == 2

        # Query individual Task
        task = await client.task.get(id=tasks[0].id)
        assert task
        assert isinstance(task, Task)
        assert task.logs == []

        # Wait for Task completion
        task = await client.task.wait_for_completion(id=tasks[0].id)
        assert task
        assert isinstance(task, Task)

        # Query Tasks with logs
        tasks = await client.task.filter(filter=TaskFilter(state=[TaskState.COMPLETED]), include_logs=True)
        all_logs = [log for task in tasks for log in task.logs]
        assert all_logs
        assert isinstance(all_logs[0], TaskLog)
        assert all_logs[0].message
        assert all_logs[0].timestamp
        assert all_logs[0].severity

    async def test_tracking_mode(self, client: InfrahubClient, base_dataset: None) -> None:
        tag_names = ["BLUE", "RED", "YELLOW"]
        person_name = "TrackingTestPerson"

        async def create_person_with_tags(clt: InfrahubClient, nbr_tags: int) -> None:
            tags = []
            for idx in range(nbr_tags):
                obj = await clt.create(kind="BuiltinTag", name=f"tracking-{tag_names[idx]}")
                await obj.save(allow_upsert=True)
                tags.append(obj)

            person = await clt.create(kind=TESTING_PERSON, name=person_name, tags=tags)
            await person.save(allow_upsert=True)

        # First execution, we create one person with 3 tags
        nbr_tags = 3
        async with client.start_tracking(params={"person_name": person_name}, delete_unused_nodes=True) as clt:
            await create_person_with_tags(clt=clt, nbr_tags=nbr_tags)

        assert client.mode == InfrahubClientMode.DEFAULT
        group = await client.get(
            kind="CoreStandardGroup", name__value=client.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 4  # 1 person + 3 tags

        # Second execution, we create one person with 2 tags but we don't delete the third one
        nbr_tags = 2
        async with client.start_tracking(params={"person_name": person_name}, delete_unused_nodes=False) as clt:
            await create_person_with_tags(clt=clt, nbr_tags=nbr_tags)

        assert client.mode == InfrahubClientMode.DEFAULT
        group = await client.get(
            kind="CoreStandardGroup", name__value=client.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 3  # 1 person + 2 tags (third tag still exists but not in group)

        # Third execution, we create one person with 1 tag and we delete the second one
        nbr_tags = 1
        async with client.start_tracking(params={"person_name": person_name}, delete_unused_nodes=True) as clt:
            await create_person_with_tags(clt=clt, nbr_tags=nbr_tags)

        assert client.mode == InfrahubClientMode.DEFAULT
        group = await client.get(
            kind="CoreStandardGroup", name__value=client.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 2  # 1 person + 1 tag

        # Fourth execution, validate that the group will not be updated if there is an exception
        nbr_tags = 3
        with pytest.raises(ValueError):
            async with client.start_tracking(params={"person_name": person_name}, delete_unused_nodes=True) as clt:
                await create_person_with_tags(clt=clt, nbr_tags=nbr_tags)
                raise ValueError("something happened")

        # Group should still have 2 members since the exception caused a rollback
        group = await client.get(
            kind="CoreStandardGroup", name__value=client.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 2

    @pytest.mark.xfail(reason="https://github.com/opsmill/infrahub-sdk-python/issues/733")
    async def test_recorder_with_playback_rewrite_host(
        self, base_dataset: None, tmp_path: Path, infrahub_port: int
    ) -> None:
        # Create a fresh client for recording to ensure clean state (no cached schema)
        recorder_config = Config(
            username="admin",
            password="infrahub",
            address=f"http://localhost:{infrahub_port}",
            custom_recorder=JSONRecorder(host="recorder-test", directory=str(tmp_path)),
        )
        recorder_client = InfrahubClient(config=recorder_config)

        query = "query { BuiltinTag { edges { node { id name { value } } } } }"
        result = await recorder_client.execute_graphql(query=query)

        playback_config = JSONPlayback(directory=str(tmp_path))
        config = Config(address=f"http://recorder-test:{infrahub_port}", requester=playback_config.async_request)
        playback = InfrahubClient(config=config)
        recorded_result = await playback.execute_graphql(query=query)

        assert result == recorded_result
        assert result.get("BuiltinTag", {}).get("edges") is not None


class TestHierarchicalSchema(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    async def load_hierarchical_schema(self, client: InfrahubClient, hierarchical_schema: dict[str, Any]) -> None:
        resp = await client.schema.load(schemas=[hierarchical_schema], wait_until_converged=True)
        assert resp.errors == {}

    async def test_hierarchical(self, client: InfrahubClient, load_hierarchical_schema: None) -> None:
        location_country = await client.create(
            kind="LocationCountry", name="country_name", shortname="country_shortname"
        )
        await location_country.save()

        location_site = await client.create(
            kind="LocationSite", name="site_name", shortname="site_shortname", parent=location_country
        )
        await location_site.save()

        nodes = await client.all(kind="LocationSite", prefetch_relationships=True, populate_store=True)
        assert len(nodes) == 1
        site_node = nodes[0]
        assert site_node.name.value == "site_name"
        assert site_node.shortname.value == "site_shortname"

        country_node = site_node.parent.get()
        assert country_node.name.value == "country_name"
