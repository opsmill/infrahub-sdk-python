from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.exceptions import NodeNotFoundError, TrackingGroupCleanupError
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import TESTING_CAT, TESTING_PERSON, SchemaAnimal

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient


class TestTrackingZeroMembers(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    async def base_dataset(self, client: InfrahubClient, load_schema: None) -> None:
        return None

    async def test_zero_member_run_prunes_previous_members(self, client: InfrahubClient, base_dataset: None) -> None:
        person_name = "TrackingZeroMemberPerson"
        tag_name = "tracking-zero-TAG"
        params = {"person_name": person_name}

        async with client.start_tracking(params=params, delete_unused_nodes=True) as clt:
            tag = await clt.create(kind="BuiltinTag", name=tag_name)
            await tag.save(allow_upsert=True)
            person = await clt.create(kind=TESTING_PERSON, name=person_name, tags=[tag])
            await person.save(allow_upsert=True)

        group_name = client.group_context._generate_group_name()
        group = await client.get(kind="CoreStandardGroup", name__value=group_name, include=["members"])
        assert len(group.members.peers) == 2

        # A run that saves nothing must still prune everything the previous run tracked.
        async with client.start_tracking(params=params, delete_unused_nodes=True):
            pass

        group = await client.get(kind="CoreStandardGroup", name__value=group_name, include=["members"])
        assert len(group.members.peers) == 0

        with pytest.raises(NodeNotFoundError):
            await client.get(kind="BuiltinTag", name__value=tag_name)
        with pytest.raises(NodeNotFoundError):
            await client.get(kind=TESTING_PERSON, name__value=person_name)

    async def test_zero_member_run_without_existing_group_creates_nothing(
        self, client: InfrahubClient, base_dataset: None
    ) -> None:
        params = {"person_name": "TrackingNeverAnyMembers"}

        async with client.start_tracking(params=params, delete_unused_nodes=True):
            pass

        group_name = client.group_context._generate_group_name()
        with pytest.raises(NodeNotFoundError):
            await client.get(kind="CoreStandardGroup", name__value=group_name)

    async def test_refused_delete_does_not_abort_remaining_reaps(
        self, client: InfrahubClient, base_dataset: None
    ) -> None:
        person_name = "TrackingRefusedPerson"
        doomed_tag_name = "tracking-refused-DOOMED"
        keeper_tag_name = "tracking-refused-KEEPER"
        params = {"person_name": person_name}

        async with client.start_tracking(params=params, delete_unused_nodes=True) as clt:
            person = await clt.create(kind=TESTING_PERSON, name=person_name)
            await person.save(allow_upsert=True)
            doomed_tag = await clt.create(kind="BuiltinTag", name=doomed_tag_name)
            await doomed_tag.save(allow_upsert=True)

        group_name = client.group_context._generate_group_name()
        group = await client.get(kind="CoreStandardGroup", name__value=group_name, include=["members"])
        assert len(group.members.peers) == 2

        # An animal outside the tracking group makes its owner undeletable,
        # because Animal.owner is a mandatory relationship.
        cat = await client.create(kind=TESTING_CAT, name="TrackingRefusedCat", breed="Bengal", owner=person)
        await cat.save()

        # Second run saves only a new tag, so the person and the first tag both
        # become reap candidates. The person's delete is refused by the server.
        with pytest.raises(TrackingGroupCleanupError) as exc_info:
            async with client.start_tracking(params=params, delete_unused_nodes=True) as clt:
                keeper_tag = await clt.create(kind="BuiltinTag", name=keeper_tag_name)
                await keeper_tag.save(allow_upsert=True)

        assert list(exc_info.value.failures) == [person.id]

        # The refused delete must not prevent the other unused member from being reaped.
        with pytest.raises(NodeNotFoundError):
            await client.get(kind="BuiltinTag", name__value=doomed_tag_name)

        # The person survived, and must still be a group member so a later run can retry it.
        await client.get(kind=TESTING_PERSON, name__value=person_name)
        group = await client.get(kind="CoreStandardGroup", name__value=group_name, include=["members"])
        assert sorted(group.members.peer_ids) == sorted([person.id, keeper_tag.id])


class TestTrackingRefusedDeleteOnZeroMemberRun(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    async def base_dataset(self, client: InfrahubClient, load_schema: None) -> None:
        return None

    async def test_zero_member_run_keeps_undeletable_member(self, client: InfrahubClient, base_dataset: None) -> None:
        person_name = "TrackingRetryPerson"
        params = {"person_name": person_name}

        async with client.start_tracking(params=params, delete_unused_nodes=True) as clt:
            person = await clt.create(kind=TESTING_PERSON, name=person_name)
            await person.save(allow_upsert=True)

        cat = await client.create(kind=TESTING_CAT, name="TrackingRetryCat", breed="Bengal", owner=person)
        await cat.save()

        # A zero-member run now attempts the reap; the person's delete is refused.
        with pytest.raises(TrackingGroupCleanupError):
            async with client.start_tracking(params=params, delete_unused_nodes=True):
                pass

        group_name = client.group_context._generate_group_name()
        group = await client.get(kind="CoreStandardGroup", name__value=group_name, include=["members"])
        assert group.members.peer_ids == [person.id]

        # Once the blocking node is gone, the next zero-member run reaps the person.
        await client.delete(kind=TESTING_CAT, id=cat.id)
        async with client.start_tracking(params=params, delete_unused_nodes=True):
            pass

        group = await client.get(kind="CoreStandardGroup", name__value=group_name, include=["members"])
        assert len(group.members.peers) == 0
        with pytest.raises(NodeNotFoundError):
            await client.get(kind=TESTING_PERSON, name__value=person_name)
