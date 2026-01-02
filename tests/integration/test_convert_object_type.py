from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.convert_object_type import ConversionFieldInput, ConversionFieldValue
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from tests.constants import CLIENT_TYPE_ASYNC, CLIENT_TYPES

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient, InfrahubClientSync

SCHEMA: dict[str, Any] = {
    "version": "1.0",
    "generics": [
        {
            "name": "PersonGeneric",
            "namespace": "Testconv",
            "human_friendly_id": ["name__value"],
            "attributes": [
                {"name": "name", "kind": "Text", "unique": True},
            ],
        },
    ],
    "nodes": [
        {
            "name": "Person1",
            "namespace": "Testconv",
            "inherit_from": ["TestconvPersonGeneric"],
        },
        {
            "name": "Person2",
            "namespace": "Testconv",
            "inherit_from": ["TestconvPersonGeneric"],
            "attributes": [
                {"name": "age", "kind": "Number"},
            ],
            "relationships": [
                {
                    "name": "worst_car",
                    "peer": "TestconvCar",
                    "cardinality": "one",
                    "identifier": "person__mandatory_owner",
                },
                {
                    "name": "fastest_cars",
                    "peer": "TestconvCar",
                    "cardinality": "many",
                    "identifier": "person__fastest_cars",
                },
            ],
        },
        {
            "name": "Car",
            "namespace": "Testconv",
            "human_friendly_id": ["name__value"],
            "attributes": [
                {"name": "name", "kind": "Text"},
            ],
        },
    ],
}


class TestConvertObjectType(TestInfrahubDockerClient):
    @pytest.mark.parametrize("client_type", CLIENT_TYPES)
    async def test_convert_object_type(
        self, client: InfrahubClient, client_sync: InfrahubClientSync, client_type: str
    ) -> None:
        resp = await client.schema.load(schemas=[SCHEMA], wait_until_converged=True)
        assert not resp.errors

        person_1 = await client.create(kind="TestconvPerson1", name=f"person_{uuid.uuid4()}")
        await person_1.save()
        car_1 = await client.create(kind="TestconvCar", name=f"car_{uuid.uuid4()}")
        await car_1.save()

        new_age = 25
        fields_mapping = {
            "name": ConversionFieldInput(source_field="name"),
            "age": ConversionFieldInput(data=ConversionFieldValue(attribute_value=new_age)),
            "worst_car": ConversionFieldInput(data=ConversionFieldValue(peer_id=car_1.id)),
            "fastest_cars": ConversionFieldInput(data=ConversionFieldValue(peers_ids=[car_1.id])),
        }

        if client_type == CLIENT_TYPE_ASYNC:
            person_2 = await client.convert_object_type(
                node_id=person_1.id,
                target_kind="TestconvPerson2",
                branch=client.default_branch,
                fields_mapping=fields_mapping,
            )
        else:
            person_2 = client_sync.convert_object_type(
                node_id=person_1.id,
                target_kind="TestconvPerson2",
                branch=client.default_branch,
                fields_mapping=fields_mapping,
            )

        assert person_2.get_kind() == "TestconvPerson2"
        assert person_2.name.value == person_1.name.value
        assert person_2.age.value == new_age

        # Fetch relationships of new node
        person_2 = await client.get(
            kind="TestconvPerson2", id=person_2.id, branch=client.default_branch, prefetch_relationships=True
        )
        assert person_2.worst_car.peer.id == car_1.id
        await person_2.fastest_cars.fetch()
        assert {related_node.peer.id for related_node in person_2.fastest_cars.peers} == {car_1.id}
