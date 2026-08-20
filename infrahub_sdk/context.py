from __future__ import annotations

from pydantic import BaseModel, Field

from .constants import Priority  # noqa: TC001  (pydantic needs this at runtime to build the model schema)


class ContextAccount(BaseModel):
    id: str = Field(..., description="The ID of the account")


class RequestContext(BaseModel):
    """The context can be used to override settings such as the account within mutations."""

    account: ContextAccount | None = Field(default=None, description="Account tied to the context")
    priority: Priority | None = Field(
        default=None, description="Request priority emitted as the X-Priority header (not part of the mutation body)"
    )
