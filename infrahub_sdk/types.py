from __future__ import annotations

import enum
from logging import Logger
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from infrahub_sdk.enums import OrderDirection  # noqa: TC001

if TYPE_CHECKING:
    import httpx


class HTTPMethod(str, enum.Enum):
    GET = "get"
    POST = "post"


class RequesterTransport(str, enum.Enum):
    HTTPX = "httpx"
    JSON = "json"


@runtime_checkable
class SyncRequester(Protocol):
    def __call__(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response: ...


@runtime_checkable
class AsyncRequester(Protocol):
    async def __call__(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response: ...


@runtime_checkable
class InfrahubLogger(Protocol):
    def debug(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send a debug event"""

    def info(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send an info event"""

    def warning(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send a warning event"""

    def error(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send an error event."""

    def critical(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send a critical event."""

    def exception(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send an exception event."""


InfrahubLoggers = InfrahubLogger | Logger


class NodeMetaOrder(BaseModel):
    created_at: OrderDirection | None = None
    updated_at: OrderDirection | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> NodeMetaOrder:
        if self.created_at and self.updated_at:
            raise ValueError("'created_at' and 'updated_at' are mutually exclusive")
        return self


class Order(BaseModel):
    disable: bool | None = Field(
        default=None, description="Disable default ordering, can be used to improve performance"
    )
    node_metadata: NodeMetaOrder | None = Field(default=None, description="Order by node meta fields")
