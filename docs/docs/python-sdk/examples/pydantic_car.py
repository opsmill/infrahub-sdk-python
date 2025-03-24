from __future__ import annotations

from asyncio import run as aiorun

from typing import Annotated

from pydantic import BaseModel, Field, ConfigDict
from infrahub_sdk import InfrahubClient
from rich import print as rprint
from infrahub_sdk.schema import InfrahubAttributeParam as AttrParam,  InfrahubRelationshipParam as RelParam, AttributeKind, from_pydantic, NodeSchema, NodeModel, GenericModel


class Tag(NodeModel):
    model_config = ConfigDict(
        node_schema=NodeSchema(name="Tag", namespace="Test", human_readable_fields=["name__value"])
    )
    
    name: Annotated[str, AttrParam(unique=True), Field(description="The name of the tag")]
    label: str | None = Field(description="The label of the tag")
    description: Annotated[str | None, AttrParam(kind=AttributeKind.TEXTAREA)] = None


class TestCar(NodeModel):
    name: str = Field(description="The name of the car")
    tags: list[Tag]
    owner: Annotated[TestPerson, RelParam(identifier="car__person")]
    secondary_owner: TestPerson | None = None


class TestPerson(GenericModel):
    name: str

class TestCarOwner(NodeModel, TestPerson):
    cars: Annotated[list[TestCar] | None, RelParam(identifier="car__person")] = None


async def main():
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
