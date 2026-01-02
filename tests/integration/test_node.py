from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import NodeNotFoundError, UninitializedError
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.protocols import IpamNamespace
from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI, SchemaRoot
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.car_person import TESTING_CAR, TESTING_MANUFACTURER, SchemaCarPerson

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient


class TestInfrahubNode(TestInfrahubDockerClient, SchemaCarPerson):
    @pytest.fixture(scope="class")
    async def initial_schema(self, default_branch: str, client: InfrahubClient, schema_base: SchemaRoot) -> None:
        await client.schema.wait_until_converged(branch=default_branch)

        resp = await client.schema.load(
            schemas=[schema_base.to_schema_dict()], branch=default_branch, wait_until_converged=True
        )
        assert resp.errors == {}

    async def test_node_create(
        self, client: InfrahubClient, initial_schema: None, schema_manufacturer_base: NodeSchema
    ) -> None:
        schema_manufacturer = NodeSchemaAPI(**schema_manufacturer_base.model_dump(exclude_unset=True))
        data = {
            "name": "Fiat",
            "description": "An italian brand",
        }
        node = InfrahubNode(client=client, schema=schema_manufacturer, data=data)
        await node.save()
        assert node.id is not None

    async def test_node_delete(self, client: InfrahubClient, initial_schema: None) -> None:
        obj = await client.create(kind=TESTING_MANUFACTURER, name="Dacia")
        await obj.save()

        await client.get(kind=TESTING_MANUFACTURER, id=obj.id)

        await obj.delete()

        with pytest.raises(NodeNotFoundError):
            await client.get(kind=TESTING_MANUFACTURER, id=obj.id)

    async def test_node_create_with_relationships(
        self,
        default_branch: str,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
    ) -> None:
        node = await client.create(
            kind=TESTING_CAR, name="CLS", color="Black", manufacturer=manufacturer_mercedes.id, owner=person_joe.id
        )
        await node.save()
        assert node.id is not None

        node_after = await client.get(kind=TESTING_CAR, id=node.id, prefetch_relationships=True)
        assert node_after.name.value == node.name.value
        assert node_after.manufacturer.peer.id == manufacturer_mercedes.id

    async def test_node_create_with_relationships_using_related_node(
        self,
        default_branch: str,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        car_golf: InfrahubNode,
        person_joe: InfrahubNode,
    ) -> None:
        related_node = car_golf.owner
        node = await client.create(
            kind=TESTING_CAR, name="CLS", color="Black", manufacturer=manufacturer_mercedes, owner=related_node
        )
        await node.save(allow_upsert=True)
        assert node.id is not None

        node_after = await client.get(kind=TESTING_CAR, id=node.id, prefetch_relationships=True)
        assert node_after.name.value == node.name.value
        assert node_after.manufacturer.peer.id == manufacturer_mercedes.id
        assert node_after.owner.peer.id == person_joe.id
        assert node_after.owner.peer.typename == "TestingPerson"

    async def test_node_filters_include(
        self,
        default_branch: str,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
        tag_red: InfrahubNode,
    ) -> None:
        car = await client.create(
            kind=TESTING_CAR,
            name="CLS AMG",
            color="Black",
            manufacturer=manufacturer_mercedes,
            owner=person_joe,
            tags=[tag_red],
        )
        await car.save(allow_upsert=True)
        assert car.id is not None

        # Clear store, as when we call `owner.peer`, we actually rely on the peer having being stored in store.
        client.store._branches = {}
        node_after = await client.get(kind=TESTING_CAR, id=car.id)

        with pytest.raises(NodeNotFoundError, match=f"Unable to find the node '{person_joe.id}' in the store"):
            _ = node_after.owner.peer

        assert len(node_after.tags.peers) == 0

        # Test both one and many relationships
        node_after = await client.get(kind=TESTING_CAR, id=car.id, include=["tags", "owner"])
        assert [tag.id for tag in node_after.tags.peers] == [tag_red.id]
        assert node_after.owner.peer.id == person_joe.id, f"{person_joe.id=}"

    async def test_node_update_with_original_data(
        self, default_branch: str, client: InfrahubClient, initial_schema: None
    ) -> None:
        person_marina = await client.create(kind="TestingPerson", name="marina", age=20)
        await person_marina.save()

        person_marina = await client.get(kind="TestingPerson", id=person_marina.id)

        person_marina.age.value = 30
        await person_marina.save()

        person_marina.age.value = 20
        await person_marina.save()
        node = await client.get(kind="TestingPerson", id=person_marina.id)
        assert node.age.value == 20, node.age.value

    async def test_node_generate_input_data_with_relationships(
        self,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
        tag_blue: InfrahubNode,
        tag_red: InfrahubNode,
    ) -> None:
        car = await client.create(
            kind=TESTING_CAR,
            name="InputDataCar",
            color="Silver",
            manufacturer=manufacturer_mercedes.id,
            owner=person_joe.id,
            tags=[tag_blue.id, tag_red.id],
        )
        await car.save()
        assert car.id is not None

        input_data = car._generate_input_data()["data"]["data"]

        assert input_data["name"]["value"] == "InputDataCar"
        assert input_data["color"]["value"] == "Silver"
        assert "manufacturer" in input_data
        assert input_data["manufacturer"]["id"] == manufacturer_mercedes.id

    async def test_node_create_with_properties(
        self,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
    ) -> None:
        data = {
            "name": {"value": "ProtectedCar", "is_protected": True},
            "color": {"value": "Gold"},
            "manufacturer": {"id": manufacturer_mercedes.id},
            "owner": {"id": person_joe.id},
        }

        node = await client.create(kind=TESTING_CAR, data=data)
        await node.save()

        assert node.id is not None
        assert node.name.value == "ProtectedCar"
        assert node.name.is_protected

        node_fetched = await client.get(kind=TESTING_CAR, id=node.id, property=True)
        assert node_fetched.name.value == "ProtectedCar"
        assert node_fetched.name.is_protected

    async def test_node_update(
        self,
        default_branch: str,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
        person_jane: InfrahubNode,
        car_golf: InfrahubNode,
        tag_blue: InfrahubNode,
        tag_red: InfrahubNode,
        tag_green: InfrahubNode,
    ) -> None:
        car_golf.color.value = "White"
        await car_golf.tags.fetch()
        car_golf.tags.add(tag_blue.id)
        car_golf.tags.add(tag_red.id)
        await car_golf.save()

        car2 = await client.get(kind=TESTING_CAR, id=car_golf.id)
        assert car2.color.value == "White"
        await car2.tags.fetch()
        assert len(car2.tags.peers) == 2

        car2.owner = person_jane.id
        car2.tags.add(tag_green.id)
        car2.tags.remove(tag_red.id)
        await car2.save()

        car3 = await client.get(kind=TESTING_CAR, id=car_golf.id)
        await car3.tags.fetch()
        assert sorted([tag.id for tag in car3.tags.peers]) == sorted([tag_green.id, tag_blue.id])

    async def test_relationship_manager_errors_without_fetch(
        self,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
        tag_blue: InfrahubNode,
    ) -> None:
        car = await client.create(
            kind=TESTING_CAR, name="UnfetchedCar", color="Blue", manufacturer=manufacturer_mercedes, owner=person_joe
        )
        await car.save()

        with pytest.raises(UninitializedError, match=r"Must call fetch"):
            car.tags.add(tag_blue)

        await car.tags.fetch()
        car.tags.add(tag_blue)
        await car.save()

        car = await client.get(kind=TESTING_CAR, id=car.id)
        await car.tags.fetch()
        assert {t.id for t in car.tags.peers} == {tag_blue.id}

    async def test_relationships_not_overwritten(
        self,
        client: InfrahubClient,
        initial_schema: None,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
        tag_blue: InfrahubNode,
        tag_red: InfrahubNode,
    ) -> None:
        car = await client.create(
            kind=TESTING_CAR,
            name="RelationshipTestCar",
            color="Green",
            manufacturer=manufacturer_mercedes,
            owner=person_joe,
        )
        await car.save()

        await car.tags.fetch()
        car.tags.add(tag_blue)
        await car.save()

        car_refetch = await client.get(kind=TESTING_CAR, id=car.id)
        car_refetch.color.value = "Red"
        await car_refetch.save()

        # Verify the tag relationship was not overwritten
        refreshed_car = await client.get(kind=TESTING_CAR, id=car.id)
        await refreshed_car.tags.fetch()
        assert [t.id for t in refreshed_car.tags.peers] == [tag_blue.id]

        # Check that we can purposefully remove a tag
        refreshed_car.tags.remove(tag_blue.id)
        await refreshed_car.save()
        car_without_tag = await client.get(kind=TESTING_CAR, id=car.id)
        await car_without_tag.tags.fetch()
        assert car_without_tag.tags.peers == []

        # Check that we can purposefully add a tag
        car_without_tag.tags.add(tag_red)
        await car_without_tag.save()
        car_with_new_tag = await client.get(kind=TESTING_CAR, id=car.id)
        await car_with_new_tag.tags.fetch()
        assert [t.id for t in car_with_new_tag.tags.peers] == [tag_red.id]

    async def test_node_update_idempotency(self, client: InfrahubClient, initial_schema: None) -> None:
        original_query = "query { CoreRepository { edges { node { name { value }}}}}"
        node = await client.create(kind="CoreGraphQLQuery", name="idempotency-query", query=original_query)
        await node.save()

        node = await client.get(kind="CoreGraphQLQuery", name__value="idempotency-query")
        assert node.id is not None

        updated_query = f"\n\n{node.query.value}"
        node.name.value = "idempotency-query-updated"
        node.query.value = updated_query
        first_update = node._generate_input_data(exclude_unmodified=True)
        await node.save()

        # Verify the first update contains the changes
        assert "query" in first_update["data"]["data"]
        assert "value" in first_update["data"]["data"]["query"]
        assert first_update["variables"]

        # Fetch the node again and set the same values
        node = await client.get(kind="CoreGraphQLQuery", name__value="idempotency-query-updated")
        node.name.value = "idempotency-query-updated"
        node.query.value = updated_query
        second_update = node._generate_input_data(exclude_unmodified=True)

        # Verify the second update doesn't contain any data (idempotent)
        assert "query" not in second_update["data"]["data"]
        assert not second_update["variables"]


class TestNodeWithPools(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    async def load_ipam_schema(self, default_branch: str, client: InfrahubClient, ipam_schema: dict[str, Any]) -> None:
        await client.schema.wait_until_converged(branch=default_branch)
        resp = await client.schema.load(schemas=[ipam_schema], branch=default_branch, wait_until_converged=True)
        assert resp.errors == {}

    @pytest.fixture(scope="class")
    async def default_ipam_namespace(self, client: InfrahubClient, load_ipam_schema: None) -> IpamNamespace:
        return await client.get(kind=IpamNamespace, name__value="default")

    @pytest.fixture(scope="class")
    async def ip_prefix(self, client: InfrahubClient, load_ipam_schema: None) -> InfrahubNode:
        prefix = await client.create(kind="IpamIPPrefix", prefix="192.0.2.0/24", member_type="address")
        await prefix.save()
        return prefix

    @pytest.fixture(scope="class")
    async def ip_pool(
        self, client: InfrahubClient, ip_prefix: InfrahubNode, default_ipam_namespace: IpamNamespace
    ) -> InfrahubNode:
        pool = await client.create(
            kind="CoreIPAddressPool",
            name="Test IP Pool",
            default_address_type="IpamIPAddress",
            default_prefix_length=32,
            resources=[ip_prefix],
            ip_namespace=default_ipam_namespace,
        )
        await pool.save()
        return pool

    async def test_node_create_from_pool(
        self, client: InfrahubClient, ip_pool: InfrahubNode, load_ipam_schema: None
    ) -> None:
        devices = []
        for i in range(1, 4):
            device = await client.create(kind="InfraDevice", name=f"device-{i:02d}", primary_address=ip_pool)
            await device.save()
            devices.append(device)

        ip_addresses = []
        devices = await client.all(kind="InfraDevice", prefetch_relationships=True)
        for device in devices:
            assert device.primary_address.peer is not None
            ip_addresses.append(device.primary_address.peer.address.value)

        assert len(set(ip_addresses)) == len(devices)

        for ip in ip_addresses:
            assert ip in ipaddress.ip_network("192.0.2.0/24")

    async def test_allocate_next_ip_address_idempotent(
        self, client: InfrahubClient, ip_pool: InfrahubNode, load_ipam_schema: None
    ) -> None:
        identifier = "idempotent-allocation-test"

        # Allocate twice with the same identifier
        ip1 = await client.allocate_next_ip_address(resource_pool=ip_pool, identifier=identifier)
        ip2 = await client.allocate_next_ip_address(resource_pool=ip_pool, identifier=identifier)

        assert ip1.id == ip2.id
        assert ip1.address.value == ip2.address.value

    async def test_node_update_from_pool(
        self, client: InfrahubClient, load_ipam_schema: None, default_ipam_namespace: IpamNamespace
    ) -> None:
        starter_ip_address = await client.create(kind="IpamIPAddress", address="10.0.0.1/32")
        await starter_ip_address.save()

        ip_prefix = await client.create(kind="IpamIPPrefix", prefix="192.168.0.0/24", member_type="address")
        await ip_prefix.save()

        ip_pool = await client.create(
            kind="CoreIPAddressPool",
            name="Update Test Pool",
            default_address_type="IpamIPAddress",
            default_prefix_length=32,
            resources=[ip_prefix],
            ip_namespace=default_ipam_namespace,
        )
        await ip_pool.save()

        device = await client.create(kind="InfraDevice", name="update-device", primary_address=starter_ip_address)
        await device.save()

        device.primary_address = ip_pool
        await device.save()

        fetched_device = await client.get(kind="InfraDevice", id=device.id, prefetch_relationships=True)
        assert fetched_device.primary_address.peer is not None
        assert fetched_device.primary_address.peer.address.value == ipaddress.ip_interface("192.168.0.1/32")
