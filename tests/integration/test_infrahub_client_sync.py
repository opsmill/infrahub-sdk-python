from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk import Config, InfrahubClientSync
from infrahub_sdk.branch import BranchData
from infrahub_sdk.constants import InfrahubClientMode
from infrahub_sdk.exceptions import BranchNotFoundError, URLNotFoundError
from infrahub_sdk.node import InfrahubNodeSync
from infrahub_sdk.playback import JSONPlayback
from infrahub_sdk.recorder import JSONRecorder
from infrahub_sdk.schema import GenericSchema, NodeSchema, ProfileSchemaAPI
from infrahub_sdk.task.models import Task, TaskFilter, TaskLog, TaskState
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import TESTING_ANIMAL, TESTING_CAT, TESTING_DOG, TESTING_PERSON, SchemaAnimal
from infrahub_sdk.types import Order

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode


class TestInfrahubClientSync(TestInfrahubDockerClient, SchemaAnimal):
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
        await client.branch.create(branch_name="sync-branch01")

    def test_query_branches(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        branches = client_sync.branch.all()
        main = client_sync.branch.get(branch_name="main")

        with pytest.raises(BranchNotFoundError):
            client_sync.branch.get(branch_name="not-found")

        assert main.name == "main"
        assert "main" in branches
        assert "sync-branch01" in branches

    def test_branch_delete(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        sync_branch = "sync-delete-branch"
        client_sync.branch.create(branch_name=sync_branch)
        pre_delete = client_sync.branch.all()
        client_sync.branch.delete(sync_branch)
        post_delete = client_sync.branch.all()
        assert sync_branch in pre_delete
        assert sync_branch not in post_delete

    def test_get_all(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        nodes = client_sync.all(kind=TESTING_CAT)
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNodeSync)
        assert [node.name.value for node in nodes] == ["Bella", "Luna"]

    def test_get_all_no_order(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        nodes = client_sync.all(kind=TESTING_CAT, order=Order(disable=True))
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNodeSync)
        assert {node.name.value for node in nodes} == {"Bella", "Luna"}

    def test_get_filters_no_order(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        nodes = client_sync.filters(kind=TESTING_CAT, order=Order(disable=True))
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNodeSync)
        assert {node.name.value for node in nodes} == {"Bella", "Luna"}

    def test_get_one(
        self, client_sync: InfrahubClientSync, base_dataset: None, cat_luna: InfrahubNode, person_sophia: InfrahubNode
    ) -> None:
        node1 = client_sync.get(kind=TESTING_CAT, id=cat_luna.id)
        assert isinstance(node1, InfrahubNodeSync)
        assert node1.name.value == "Luna"

        node2 = client_sync.get(kind=TESTING_PERSON, id=person_sophia.id)
        assert isinstance(node2, InfrahubNodeSync)
        assert node2.name.value == "Sophia Walker"

    def test_filters_partial_match(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        nodes = client_sync.filters(kind=TESTING_PERSON, name__value="Walker")
        assert not nodes

        nodes = client_sync.filters(kind=TESTING_PERSON, partial_match=True, name__value="Walker")
        assert len(nodes) == 2
        assert isinstance(nodes[0], InfrahubNodeSync)
        assert sorted([node.name.value for node in nodes]) == ["Liam Walker", "Sophia Walker"]

    def test_get_generic(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        nodes = client_sync.all(kind=TESTING_ANIMAL)
        assert len(nodes) == 4

    def test_get_generic_fragment(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        nodes = client_sync.all(kind=TESTING_ANIMAL, fragment=True)
        assert len(nodes)
        assert nodes[0].typename in {TESTING_DOG, TESTING_CAT}
        assert nodes[0].breed.value is not None

    def test_get_generic_filter_source(
        self, client_sync: InfrahubClientSync, base_dataset: None, person_liam: InfrahubNode
    ) -> None:
        admin = client_sync.get(kind="CoreAccount", name__value="admin")

        obj = client_sync.create(
            kind=TESTING_CAT,
            name={"value": "SyncSourceFilterCat", "source": admin.id},
            breed="Siamese",
            owner=person_liam,
        )
        obj.save()

        nodes = client_sync.filters(kind="CoreNode", any__source__id=admin.id)
        assert len(nodes) == 1
        assert nodes[0].typename == TESTING_CAT
        assert nodes[0].id == obj.id

    def test_get_related_nodes(
        self, client_sync: InfrahubClientSync, base_dataset: None, person_ethan: InfrahubNode
    ) -> None:
        ethan = client_sync.get(kind=TESTING_PERSON, id=person_ethan.id)
        assert ethan

        assert ethan.animals.peers == []
        ethan.animals.fetch()
        assert len(ethan.animals.peers) == 3

    def test_count(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        count = client_sync.count(kind=TESTING_PERSON)
        assert count == 3

    def test_count_with_filter(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        count = client_sync.count(kind=TESTING_PERSON, name__values=["Liam Walker", "Ethan Carter"])
        assert count == 2

    def test_profile(self, client_sync: InfrahubClientSync, base_dataset: None, person_liam: InfrahubNode) -> None:
        profile_schema_kind = f"Profile{TESTING_DOG}"
        profile_schema = client_sync.schema.get(kind=profile_schema_kind)
        assert isinstance(profile_schema, ProfileSchemaAPI)

        profile1 = client_sync.create(
            kind=profile_schema_kind, profile_name="sync-profile1", profile_priority=1000, color="#222222"
        )
        profile1.save()

        obj = client_sync.create(
            kind=TESTING_DOG, name="Sync-Sparky", breed="Poodle", owner=person_liam, profiles=[profile1]
        )
        obj.save()

        obj1 = client_sync.get(kind=TESTING_DOG, id=obj.id)
        assert obj1.color.value == "#222222"

    @pytest.mark.xfail(reason="Require Infrahub v1.7")
    def test_profile_relationship_is_from_profile(
        self, client_sync: InfrahubClientSync, base_dataset: None, person_liam: InfrahubNode
    ) -> None:
        tag = client_sync.create(kind="BuiltinTag", name="sync-profile-tag-test")
        tag.save()

        profile_schema_kind = f"Profile{TESTING_PERSON}"
        profile = client_sync.create(
            kind=profile_schema_kind, profile_name="sync-person-profile-with-tag", profile_priority=1000, tags=[tag]
        )
        profile.save()

        person = client_sync.create(
            kind=TESTING_PERSON, name="Sync Profile Relationship Test Person", profiles=[profile]
        )
        person.save()

        fetched_person = client_sync.get(kind=TESTING_PERSON, id=person.id, property=True, include=["tags"])
        assert fetched_person.tags.initialized
        assert len(fetched_person.tags.peers) == 1
        assert fetched_person.tags.peers[0].id == tag.id
        assert fetched_person.tags.peers[0].is_from_profile
        assert fetched_person.tags.is_from_profile

    def test_create_branch(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        branch = client_sync.branch.create(branch_name="sync-new-branch-1")
        assert isinstance(branch, BranchData)
        assert branch.id is not None

    def test_create_branch_async(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        task_id = client_sync.branch.create(branch_name="sync-new-branch-2", wait_until_completion=False)
        assert isinstance(task_id, str)

    def test_query_unexisting_branch(self, client_sync: InfrahubClientSync) -> None:
        with pytest.raises(URLNotFoundError, match=r"/graphql/unexisting` not found."):
            client_sync.execute_graphql(query="unused", branch_name="unexisting")

    def test_create_generic_rel_with_hfid(
        self,
        client_sync: InfrahubClientSync,
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
        person_sophia_sync = client_sync.get(kind=TESTING_PERSON, id=person_sophia.id)
        person_sophia_sync.favorite_animal = {"hfid": cat_luna.hfid, "kind": TESTING_CAT}
        person_sophia_sync.save()
        person_sophia_sync = client_sync.get(kind=TESTING_PERSON, id=person_sophia.id, prefetch_relationships=True)
        assert person_sophia_sync.favorite_animal.id == cat_luna.id

        # Ensure that nullify it will remove the relationship related node
        person_sophia_sync.favorite_animal = None
        person_sophia_sync.save()
        person_sophia_sync = client_sync.get(kind=TESTING_PERSON, id=person_sophia.id, prefetch_relationships=True)
        assert not person_sophia_sync.favorite_animal.id

    def test_task_query(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        nbr_tasks = client_sync.task.count()
        assert nbr_tasks

        tasks = client_sync.task.filter(filter=TaskFilter(state=[TaskState.COMPLETED]))
        assert tasks
        task_ids = [task.id for task in tasks]

        # Query Tasks using Parallel mode
        tasks_parallel = client_sync.task.filter(filter=TaskFilter(state=[TaskState.COMPLETED]), parallel=True)
        assert tasks_parallel
        task_parallel_ids = [task.id for task in tasks_parallel]

        # Additional tasks might have been completed between the two queries
        # validate that we get at least as many tasks as in the first query
        # and that all task IDs from the first query are present in the second one
        assert len(tasks_parallel) >= len(tasks)
        assert set(task_ids).issubset(set(task_parallel_ids))

        # Query Tasks by ID
        tasks_parallel_filtered = client_sync.task.filter(filter=TaskFilter(ids=task_ids[:2]), parallel=True)
        assert tasks_parallel_filtered
        assert len(tasks_parallel_filtered) == 2

        # Query individual Task
        task = client_sync.task.get(id=tasks[0].id)
        assert task
        assert isinstance(task, Task)
        assert task.logs == []

        # Wait for Task completion
        task = client_sync.task.wait_for_completion(id=tasks[0].id)
        assert task
        assert isinstance(task, Task)

        # Query Tasks with logs
        tasks = client_sync.task.filter(filter=TaskFilter(state=[TaskState.COMPLETED]), include_logs=True)
        all_logs = [log for task in tasks for log in task.logs]
        assert all_logs
        assert isinstance(all_logs[0], TaskLog)
        assert all_logs[0].message
        assert all_logs[0].timestamp
        assert all_logs[0].severity

    def test_tracking_mode(self, client_sync: InfrahubClientSync, base_dataset: None) -> None:
        tag_names = ["BLUE", "RED", "YELLOW"]
        person_name = "SyncTrackingTestPerson"

        def create_person_with_tags(clt: InfrahubClientSync, nbr_tags: int) -> None:
            tags = []
            for idx in range(nbr_tags):
                obj = clt.create(kind="BuiltinTag", name=f"sync-tracking-{tag_names[idx]}")
                obj.save(allow_upsert=True)
                tags.append(obj)

            person = clt.create(kind=TESTING_PERSON, name=person_name, tags=tags)
            person.save(allow_upsert=True)

        # First execution, we create one person with 3 tags
        nbr_tags = 3
        with client_sync.start_tracking(params={"person_name": person_name}, delete_unused_nodes=True) as clt:
            create_person_with_tags(clt=clt, nbr_tags=nbr_tags)

        assert client_sync.mode == InfrahubClientMode.DEFAULT
        group = client_sync.get(
            kind="CoreStandardGroup", name__value=client_sync.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 4  # 1 person + 3 tags

        # Second execution, we create one person with 2 tags but we don't delete the third one
        nbr_tags = 2
        with client_sync.start_tracking(params={"person_name": person_name}, delete_unused_nodes=False) as clt:
            create_person_with_tags(clt=clt, nbr_tags=nbr_tags)

        assert client_sync.mode == InfrahubClientMode.DEFAULT
        group = client_sync.get(
            kind="CoreStandardGroup", name__value=client_sync.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 3  # 1 person + 2 tags (third tag still exists but not in group)

        # Third execution, we create one person with 1 tag and we delete the second one
        nbr_tags = 1
        with client_sync.start_tracking(params={"person_name": person_name}, delete_unused_nodes=True) as clt:
            create_person_with_tags(clt=clt, nbr_tags=nbr_tags)

        assert client_sync.mode == InfrahubClientMode.DEFAULT
        group = client_sync.get(
            kind="CoreStandardGroup", name__value=client_sync.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 2  # 1 person + 1 tag

        # Fourth execution, validate that the group will not be updated if there is an exception
        nbr_tags = 3
        with (
            pytest.raises(ValueError),
            client_sync.start_tracking(params={"person_name": person_name}, delete_unused_nodes=True) as clt,
        ):
            create_person_with_tags(clt=clt, nbr_tags=nbr_tags)
            raise ValueError("something happened")

        # Group should still have 2 members since the exception caused a rollback
        group = client_sync.get(
            kind="CoreStandardGroup", name__value=client_sync.group_context._generate_group_name(), include=["members"]
        )
        assert len(group.members.peers) == 2

    @pytest.mark.xfail(reason="https://github.com/opsmill/infrahub-sdk-python/issues/733")
    def test_recorder_with_playback_rewrite_host(self, base_dataset: None, tmp_path: Path, infrahub_port: int) -> None:
        # Create a fresh client for recording to ensure clean state (no cached schema)
        recorder_config = Config(
            username="admin",
            password="infrahub",
            address=f"http://localhost:{infrahub_port}",
            custom_recorder=JSONRecorder(host="recorder-test", directory=str(tmp_path)),
        )
        recorder_client = InfrahubClientSync(config=recorder_config)

        query = "query { BuiltinTag { edges { node { id name { value } } } } }"
        result = recorder_client.execute_graphql(query=query)

        playback_config = JSONPlayback(directory=str(tmp_path))
        config = Config(address=f"http://recorder-test:{infrahub_port}", sync_requester=playback_config.sync_request)
        playback = InfrahubClientSync(config=config)
        recorded_result = playback.execute_graphql(query=query)

        assert result == recorded_result
        assert result.get("BuiltinTag", {}).get("edges") is not None


class TestHierarchicalSchema(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    def load_hierarchical_schema(self, client_sync: InfrahubClientSync, hierarchical_schema: dict[str, Any]) -> None:
        resp = client_sync.schema.load(schemas=[hierarchical_schema], wait_until_converged=True)
        assert resp.errors == {}

    def test_hierarchical(self, client_sync: InfrahubClientSync, load_hierarchical_schema: None) -> None:
        location_country = client_sync.create(
            kind="LocationCountry", name="country_name", shortname="country_shortname"
        )
        location_country.save()

        location_site = client_sync.create(
            kind="LocationSite", name="site_name", shortname="site_shortname", parent=location_country
        )
        location_site.save()

        nodes = client_sync.all(kind="LocationSite", prefetch_relationships=True, populate_store=True)
        assert len(nodes) == 1
        site_node = nodes[0]
        assert site_node.name.value == "site_name"
        assert site_node.shortname.value == "site_shortname"

        country_node = site_node.parent.get()
        assert country_node.name.value == "country_name"
