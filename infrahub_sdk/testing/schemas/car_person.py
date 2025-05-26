from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.schema.main import AttributeKind, NodeSchema, RelationshipKind, SchemaRoot
from infrahub_sdk.schema.main import AttributeSchema as Attr
from infrahub_sdk.schema.main import RelationshipSchema as Rel

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode

NAMESPACE = "Testing"

TESTING_MANUFACTURER = f"{NAMESPACE}Manufacturer"
TESTING_PERSON = f"{NAMESPACE}Person"
TESTING_CAR = f"{NAMESPACE}Car"
BUILTIN_TAG = "BuiltinTag"


@dataclass
class TestingPersonData:
    name: str
    kind: str = TESTING_PERSON


@dataclass
class TestingManufacturerData:
    name: str
    kind: str = TESTING_MANUFACTURER


@dataclass
class TestingCarData:
    name: str
    color: str | None = None
    kind: str = TESTING_CAR


class SchemaCarPerson:
    @pytest.fixture(scope="class")
    def schema_person_base(self) -> NodeSchema:
        return NodeSchema(
            name="Person",
            namespace=NAMESPACE,
            include_in_menu=True,
            label="Person",
            default_filter="name__value",
            human_friendly_id=["name__value"],
            attributes=[
                Attr(name="name", kind=AttributeKind.TEXT, unique=True),
                Attr(name="description", kind=AttributeKind.TEXT, optional=True),
                Attr(name="height", kind=AttributeKind.NUMBER, optional=True),
                Attr(name="age", kind=AttributeKind.NUMBER, optional=True),
            ],
            relationships=[
                Rel(name="cars", kind=RelationshipKind.GENERIC, optional=True, peer=TESTING_CAR, cardinality="many")
            ],
        )

    @pytest.fixture(scope="class")
    def schema_car_base(self) -> NodeSchema:
        return NodeSchema(
            name="Car",
            namespace=NAMESPACE,
            include_in_menu=True,
            default_filter="name__value",
            human_friendly_id=["owner__name__value", "name__value"],
            label="Car",
            attributes=[
                Attr(name="name", kind=AttributeKind.TEXT),
                Attr(name="description", kind=AttributeKind.TEXT, optional=True),
                Attr(name="color", kind=AttributeKind.TEXT),
            ],
            relationships=[
                Rel(
                    name="owner",
                    kind=RelationshipKind.ATTRIBUTE,
                    optional=False,
                    peer=TESTING_PERSON,
                    cardinality="one",
                ),
                Rel(
                    name="manufacturer",
                    kind=RelationshipKind.ATTRIBUTE,
                    optional=False,
                    peer=TESTING_MANUFACTURER,
                    cardinality="one",
                    identifier="car__manufacturer",
                ),
                Rel(
                    name="tags",
                    optional=True,
                    peer=BUILTIN_TAG,
                    cardinality="many",
                ),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_manufacturer_base(self) -> NodeSchema:
        return NodeSchema(
            name="Manufacturer",
            namespace=NAMESPACE,
            include_in_menu=True,
            label="Manufacturer",
            human_friendly_id=["name__value"],
            attributes=[
                Attr(name="name", kind=AttributeKind.TEXT),
                Attr(name="description", kind=AttributeKind.TEXT, optional=True),
            ],
            relationships=[
                Rel(
                    name="cars",
                    kind=RelationshipKind.GENERIC,
                    optional=True,
                    peer=TESTING_CAR,
                    cardinality="many",
                    identifier="car__manufacturer",
                ),
                Rel(
                    name="customers",
                    kind=RelationshipKind.GENERIC,
                    optional=True,
                    peer=TESTING_PERSON,
                    cardinality="many",
                    identifier="person__manufacturer",
                ),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_base(
        self,
        schema_car_base: NodeSchema,
        schema_person_base: NodeSchema,
        schema_manufacturer_base: NodeSchema,
    ) -> SchemaRoot:
        return SchemaRoot(version="1.0", nodes=[schema_car_base, schema_person_base, schema_manufacturer_base])

    @pytest.fixture(scope="class")
    async def person_joe_data(self) -> TestingPersonData:
        return TestingPersonData(name="Joe Doe")

    @pytest.fixture(scope="class")
    async def person_jane_data(self) -> TestingPersonData:
        return TestingPersonData(name="Jane Doe")

    @pytest.fixture(scope="class")
    async def manufacturer_vw_data(self) -> TestingManufacturerData:
        return TestingManufacturerData(name="Volkswagen")

    @pytest.fixture(scope="class")
    async def manufacturer_renault_data(self) -> TestingManufacturerData:
        return TestingManufacturerData(name="Renault")

    @pytest.fixture(scope="class")
    async def manufacturer_mercedes_data(self) -> TestingManufacturerData:
        return TestingManufacturerData(name="Mercedes")

    @pytest.fixture(scope="class")
    async def car_golf_data(self) -> TestingCarData:
        return TestingCarData(name="Golf", color="Black")

    @pytest.fixture(scope="class")
    async def person_joe(self, client: InfrahubClient, person_joe_data: TestingPersonData) -> InfrahubNode:
        obj = await client.create(**asdict(person_joe_data))
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def person_jane(self, client: InfrahubClient, person_jane_data: TestingPersonData) -> InfrahubNode:
        obj = await client.create(**asdict(person_jane_data))
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def manufacturer_mercedes(
        self, client: InfrahubClient, manufacturer_mercedes_data: TestingManufacturerData
    ) -> InfrahubNode:
        obj = await client.create(**asdict(manufacturer_mercedes_data))
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def car_golf(
        self,
        client: InfrahubClient,
        car_golf_data: TestingCarData,
        manufacturer_mercedes: InfrahubNode,
        person_joe: InfrahubNode,
    ) -> InfrahubNode:
        obj = await client.create(**asdict(car_golf_data), manufacturer=manufacturer_mercedes, owner=person_joe)
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def tag_blue(self, client: InfrahubClient) -> InfrahubNode:
        obj = await client.create(kind=BUILTIN_TAG, name="Blue")
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def tag_red(self, client: InfrahubClient) -> InfrahubNode:
        obj = await client.create(kind=BUILTIN_TAG, name="Red")
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def tag_green(self, client: InfrahubClient) -> InfrahubNode:
        obj = await client.create(kind=BUILTIN_TAG, name="Green")
        await obj.save()
        return obj

    async def create_persons(self, client: InfrahubClient, branch: str) -> list[InfrahubNode]:
        john = await client.create(kind=TESTING_PERSON, name="John Doe", branch=branch)
        await john.save()

        jane = await client.create(kind=TESTING_PERSON, name="Jane Doe", branch=branch)
        await jane.save()

        return [john, jane]

    async def create_manufacturers(self, client: InfrahubClient, branch: str) -> list[InfrahubNode]:
        obj1 = await client.create(kind=TESTING_MANUFACTURER, name="Volkswagen", branch=branch)
        await obj1.save()

        obj2 = await client.create(kind=TESTING_MANUFACTURER, name="Renault", branch=branch)
        await obj2.save()

        obj3 = await client.create(kind=TESTING_MANUFACTURER, name="Mercedes", branch=branch)
        await obj3.save()

        return [obj1, obj2, obj3]

    async def create_initial_data(self, client: InfrahubClient, branch: str) -> dict[str, list[InfrahubNode]]:
        persons = await self.create_persons(client=client, branch=branch)
        manufacturers = await self.create_manufacturers(client=client, branch=branch)

        car10 = await client.create(
            kind=TESTING_CAR, name="Golf", color="Black", manufacturer=manufacturers[0].id, owner=persons[0].id
        )
        await car10.save()

        car20 = await client.create(
            kind=TESTING_CAR, name="Megane", color="Red", manufacturer=manufacturers[1].id, owner=persons[1].id
        )
        await car20.save()

        return {TESTING_PERSON: persons, TESTING_CAR: [car10, car20], TESTING_MANUFACTURER: manufacturers}
