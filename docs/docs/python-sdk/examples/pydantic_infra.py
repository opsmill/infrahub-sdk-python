from __future__ import annotations

from typing import Annotated

from pydantic import ConfigDict, Field
from rich import print as rprint

from infrahub_sdk import InfrahubClient
from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.schema import (
    GenericModel,
    GenericSchema,
    NodeModel,
    NodeSchema,
    RelationshipKind,
    from_pydantic,
)
from infrahub_sdk.schema import (
    InfrahubAttributeParam as AttrParam,
)
from infrahub_sdk.schema import (
    InfrahubRelationshipParam as RelParam,
)

app = AsyncTyper()


class Site(NodeModel):
    model_config = ConfigDict(
        node_schema=NodeSchema(
            name="Site", namespace="Infra", human_friendly_id=["name__value"], display_labels=["name__value"]
        )
    )

    name: Annotated[str, AttrParam(unique=True)] = Field(description="The name of the site")


class Vlan(NodeModel):
    model_config = ConfigDict(
        node_schema=NodeSchema(
            name="Vlan", namespace="Infra", human_friendly_id=["vlan_id__value"], display_labels=["vlan_id__value"]
        )
    )

    name: str
    vlan_id: int
    description: str | None = None


class Device(NodeModel):
    model_config = ConfigDict(
        node_schema=NodeSchema(
            name="Device", namespace="Infra", human_friendly_id=["name__value"], display_labels=["name__value"]
        )
    )

    name: Annotated[str, AttrParam(unique=True)] = Field(description="The name of the car")
    site: Annotated[Site, RelParam(kind=RelationshipKind.ATTRIBUTE, identifier="device__site")]
    interfaces: Annotated[
        list[Interface], RelParam(kind=RelationshipKind.COMPONENT, identifier="device__interfaces")
    ] = Field(default_factory=list)


class Interface(GenericModel):
    model_config = ConfigDict(
        generic_schema=GenericSchema(
            name="Interface",
            namespace="Infra",
            human_friendly_id=["device__name__value", "name__value"],
            display_labels=["name__value"],
        )
    )

    device: Annotated[Device, RelParam(kind=RelationshipKind.PARENT, identifier="device__interfaces")]
    name: str
    description: str | None = None


class L2Interface(Interface):
    model_config = ConfigDict(node_schema=NodeSchema(name="L2Interface", namespace="Infra"))

    vlans: list[Vlan] = Field(default_factory=list)


class LoopbackInterface(Interface):
    model_config = ConfigDict(node_schema=NodeSchema(name="LoopbackInterface", namespace="Infra"))


@app.command()
async def load_schema() -> None:
    client = InfrahubClient()
    schema = from_pydantic(models=[Site, Device, Interface, L2Interface, LoopbackInterface, Vlan])
    rprint(schema.to_schema_dict())
    response = await client.schema.load(schemas=[schema.to_schema_dict()], wait_until_converged=True)
    rprint(response)


@app.command()
async def load_data() -> None:
    client = InfrahubClient()

    atl = await client.create("InfraSite", name="ATL")
    await atl.save(allow_upsert=True)
    cdg = await client.create("InfraSite", name="CDG")
    await cdg.save(allow_upsert=True)

    device1 = await client.create("InfraDevice", name="atl1-dev1", site=atl)
    await device1.save(allow_upsert=True)
    device2 = await client.create("InfraDevice", name="atl1-dev2", site=atl)
    await device2.save(allow_upsert=True)

    lo0dev1 = await client.create("InfraLoopbackInterface", name="lo0", device=device1)
    await lo0dev1.save(allow_upsert=True)
    lo0dev2 = await client.create("InfraLoopbackInterface", name="lo0", device=device2)
    await lo0dev2.save(allow_upsert=True)

    for idx in range(1, 3):
        interface = await client.create("InfraL2Interface", name=f"Ethernet{idx}", device=device1)
        await interface.save(allow_upsert=True)


@app.command()
async def query_data() -> None:
    client = InfrahubClient()
    sites = await client.all(kind=Site)
    rprint(sites)

    devices = await client.all(kind=Device)
    for device in devices:
        rprint(device)


if __name__ == "__main__":
    app()
