from __future__ import annotations

from typing import Optional

from pydantic import Field, BaseModel


class CreateDevice(BaseModel):
    infra_device_upsert: Optional[CreateDeviceInfraDeviceUpsert] = Field(alias="InfraDeviceUpsert")


class CreateDeviceInfraDeviceUpsert(BaseModel):
    ok: Optional[bool]
    object: Optional[CreateDeviceInfraDeviceUpsertObject]


class CreateDeviceInfraDeviceUpsertObject(BaseModel):
    id: str
    name: Optional[CreateDeviceInfraDeviceUpsertObjectName]
    description: Optional[CreateDeviceInfraDeviceUpsertObjectDescription]
    status: Optional[CreateDeviceInfraDeviceUpsertObjectStatus]


class CreateDeviceInfraDeviceUpsertObjectName(BaseModel):
    value: Optional[str]


class CreateDeviceInfraDeviceUpsertObjectDescription(BaseModel):
    value: Optional[str]


class CreateDeviceInfraDeviceUpsertObjectStatus(BaseModel):
    value: Optional[str]


CreateDevice.model_rebuild()
CreateDeviceInfraDeviceUpsert.model_rebuild()
CreateDeviceInfraDeviceUpsertObject.model_rebuild()
