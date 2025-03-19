from __future__ import annotations

from asyncio import run as aiorun

from typing import Annotated

from pydantic import BaseModel, Field
from infrahub_sdk import InfrahubClient
from rich import print as rprint
from infrahub_sdk.schema import InfrahubAttributeParam as AttrParam,  InfrahubRelationshipParam as RelParam, AttributeKind, from_pydantic


class Tag(BaseModel):
    name: Annotated[str, AttrParam(unique=True), Field(description="The name of the tag")]
    label: str | None = Field(description="The label of the tag")
    description: Annotated[str | None, AttrParam(kind=AttributeKind.TEXTAREA)] = None


class Car(BaseModel):
    name: str = Field(description="The name of the car")
    tags: list[Tag]
    owner: Annotated[Person, RelParam(identifier="car__person")]
    secondary_owner: Person | None = None


class Person(BaseModel):
    name: str
    cars: Annotated[list[Car] | None, RelParam(identifier="car__person")] = None


async def main():
    client = InfrahubClient()
    schema = from_pydantic(models=[Person, Car, Tag])
    rprint(schema.to_schema_dict())
    response = await client.schema.load(schemas=[schema.to_schema_dict()], wait_until_converged=True)
    rprint(response)

if __name__ == "__main__":
    aiorun(main())
