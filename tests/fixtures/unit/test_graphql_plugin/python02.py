from typing import Optional

from pydantic import Field, BaseModel


class CreateDevice(BaseModel):
    infra_device_upsert: Optional["CreateDeviceInfraDeviceUpsert"] = Field(alias="InfraDeviceUpsert")


class CreateDeviceInfraDeviceUpsert(BaseModel):
    ok: Optional[bool]
    object: Optional[dict]


CreateDevice.model_rebuild()
CreateDeviceInfraDeviceUpsert.model_rebuild()
