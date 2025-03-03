import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.exceptions import GraphQLError
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.schema.main import (
    AttributeKind,
    GenericSchema,
    NodeSchema,
    RelationshipDirection,
    RelationshipKind,
    SchemaRoot,
)
from infrahub_sdk.schema.main import AttributeSchema as Attr
from infrahub_sdk.schema.main import RelationshipSchema as Rel

NAMESPACE = "Testing"

TESTING_ANIMAL = f"{NAMESPACE}Animal"
TESTING_CAT = f"{NAMESPACE}Cat"
TESTING_DOG = f"{NAMESPACE}Dog"
TESTING_PERSON = f"{NAMESPACE}Person"


class SchemaAnimal:
    @pytest.fixture(scope="class")
    def schema_animal(self) -> GenericSchema:
        return GenericSchema(
            name="Animal",
            namespace=NAMESPACE,
            include_in_menu=True,
            human_friendly_id=["owner__name__value", "name__value"],
            uniqueness_constraints=[
                ["owner", "name__value"],
            ],
            attributes=[
                Attr(name="name", kind=AttributeKind.TEXT),
                Attr(name="weight", kind=AttributeKind.NUMBER, optional=True),
            ],
            relationships=[
                Rel(
                    name="owner",
                    kind=RelationshipKind.GENERIC,
                    optional=False,
                    peer=TESTING_PERSON,
                    cardinality="one",
                    identifier="person__animal",
                    direction=RelationshipDirection.OUTBOUND,
                ),
                Rel(
                    name="best_friend",
                    kind=RelationshipKind.GENERIC,
                    optional=True,
                    peer=TESTING_PERSON,
                    cardinality="one",
                    identifier="person__animal_friend",
                    direction=RelationshipDirection.OUTBOUND,
                ),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_dog(self) -> NodeSchema:
        return NodeSchema(
            name="Dog",
            namespace=NAMESPACE,
            include_in_menu=True,
            inherit_from=[TESTING_ANIMAL],
            display_labels=["name__value", "breed__value"],
            attributes=[
                Attr(name="breed", kind=AttributeKind.TEXT, optional=False),
                Attr(name="color", kind=AttributeKind.COLOR, default_value="#444444", optional=True),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_cat(self) -> NodeSchema:
        return NodeSchema(
            name="Cat",
            namespace=NAMESPACE,
            include_in_menu=True,
            inherit_from=[TESTING_ANIMAL],
            human_friendly_id=["owner__name__value", "name__value", "color__value"],
            display_labels=["name__value", "breed__value", "color__value"],
            order_by=["name__value"],
            attributes=[
                Attr(name="breed", kind=AttributeKind.TEXT, optional=False),
                Attr(name="color", kind=AttributeKind.COLOR, default_value="#555555", optional=True),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_person(self) -> NodeSchema:
        return NodeSchema(
            name="Person",
            namespace=NAMESPACE,
            include_in_menu=True,
            display_labels=["name__value"],
            default_filter="name__value",
            human_friendly_id=["name__value"],
            attributes=[
                Attr(name="name", kind=AttributeKind.TEXT, unique=True),
                Attr(name="height", kind=AttributeKind.NUMBER, optional=True),
            ],
            relationships=[
                Rel(
                    name="animals",
                    peer=TESTING_ANIMAL,
                    identifier="person__animal",
                    cardinality="many",
                    direction=RelationshipDirection.INBOUND,
                    max_count=10,
                ),
                Rel(
                    name="favorite_animal",
                    peer=TESTING_ANIMAL,
                    identifier="favorite_animal",
                    cardinality="one",
                    direction=RelationshipDirection.INBOUND,
                ),
                Rel(
                    name="best_friends",
                    peer=TESTING_ANIMAL,
                    identifier="person__animal_friend",
                    cardinality="many",
                    direction=RelationshipDirection.INBOUND,
                ),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_base(
        self,
        schema_animal: GenericSchema,
        schema_person: NodeSchema,
        schema_cat: NodeSchema,
        schema_dog: NodeSchema,
    ) -> SchemaRoot:
        return SchemaRoot(version="1.0", generics=[schema_animal], nodes=[schema_person, schema_cat, schema_dog])

    @pytest.fixture(scope="class")
    async def load_schema(self, client: InfrahubClient, schema_base: SchemaRoot) -> None:
        resp = await client.schema.load(schemas=[schema_base.to_schema_dict()], wait_until_converged=True)
        if resp.errors:
            raise GraphQLError(errors=[resp.errors])

    @pytest.fixture(scope="class")
    async def person_liam(self, client: InfrahubClient) -> InfrahubNode:
        obj = await client.create(kind=TESTING_PERSON, name="Liam Walker", height=178)
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def person_sophia(self, client: InfrahubClient) -> InfrahubNode:
        obj = await client.create(kind=TESTING_PERSON, name="Sophia Walker", height=168)
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def person_ethan(self, client: InfrahubClient) -> InfrahubNode:
        obj = await client.create(kind=TESTING_PERSON, name="Ethan Carter", height=185)
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def cat_bella(self, client: InfrahubClient, person_ethan: InfrahubNode) -> InfrahubNode:
        obj = await client.create(kind=TESTING_CAT, name="Bella", breed="Bengal", color="#123456", owner=person_ethan)
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def cat_luna(self, client: InfrahubClient, person_ethan: InfrahubNode) -> InfrahubNode:
        obj = await client.create(kind=TESTING_CAT, name="Luna", breed="Siamese", color="#FFFFFF", owner=person_ethan)
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def dog_daisy(self, client: InfrahubClient, person_ethan: InfrahubNode) -> InfrahubNode:
        obj = await client.create(
            kind=TESTING_DOG, name="Daisy", breed="French Bulldog", color="#7B7D7D", owner=person_ethan
        )
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    async def dog_rocky(self, client: InfrahubClient, person_sophia: InfrahubNode) -> InfrahubNode:
        obj = await client.create(
            kind=TESTING_DOG, name="Rocky", breed="German Shepherd", color="#784212", owner=person_sophia
        )
        await obj.save()
        return obj
