from __future__ import annotations

from pydantic import BaseModel, Field


class ContextAccount(BaseModel):
    id: str = Field(..., description="The ID of the account")


class RequestContext(BaseModel):
    """The context can be used to override settings such as the account within mutations."""

    account: ContextAccount | None = Field(default=None, description="Account tied to the context")
