from __future__ import annotations

from asyncio import run as aiorun
from typing import Annotated

from pydantic import ConfigDict, Field
from rich import print as rprint

from infrahub_sdk import InfrahubClient
from infrahub_sdk.schema import (
    AttributeKind,
    GenericModel,
    NodeModel,
    NodeSchema,
    from_pydantic,
)
from infrahub_sdk.schema.pydantic_utils import (
    Attribute,
    GenericModel,
    InfrahubConfig,
    NodeModel,
    Relationship,
    SchemaModel,
    analyze_field,
    field_to_attribute,
    field_to_relationship,
    from_pydantic,
    get_attribute_kind,
    get_kind,
    model_to_node,
)


class Tag(NodeModel):
    model_config = InfrahubConfig(namespace="Test", human_readable_fields=["name__value"])

    name: str = Attribute(unique=True, description="The name of the tag")
    label: str | None = Field(description="The label of the tag")
    description: str | None = Attribute(None, kind=AttributeKind.TEXTAREA)


class TestCar(NodeModel):
    name: str = Field(description="The name of the car")
    tags: list[Tag]
    owner: TestPerson = Relationship(identifier="car__person")]
    secondary_owner: TestPerson | None = None


class TestPerson(GenericModel):
    name: str


class TestCarOwner(NodeModel, TestPerson):
    cars: list[TestCar] = Relationship(identifier="car__person")


async def main() -> None:
    client = InfrahubClient()
    schema = from_pydantic(models=[TestPerson, TestCar, Tag, TestPerson, TestCarOwner])
    rprint(schema.to_schema_dict())
    response = await client.schema.load(schemas=[schema.to_schema_dict()], wait_until_converged=True)
    rprint(response)

    # Create a Tag
    tag = await client.create("TestTag", name="Blue", label="Blue")
    await tag.save(allow_upsert=True)


if __name__ == "__main__":
    aiorun(main())
