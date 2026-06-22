from __future__ import annotations

import enum
from logging import Logger
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from infrahub_sdk.enums import OrderDirection

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
        """Send a debug event."""

    def info(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send an info event."""

    def warning(self, event: str | None = None, *args: Any, **kw: Any) -> Any:
        """Send a warning event."""

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


class OrderByEntry(BaseModel):
    field: str = Field(
        description=(
            "Field to order by: an attribute (`name__value`), a relationship attribute "
            "(`owner__name__value`), or node metadata (`node_metadata__created_at`)"
        )
    )
    direction: OrderDirection = Field(default=OrderDirection.ASC, description="Sort direction (default ASC)")


class Order(BaseModel):
    disable: bool | None = Field(
        default=None, description="Disable default ordering, can be used to improve performance"
    )
    by: list[OrderByEntry] | None = Field(default=None, description="Ordered list of fields to order results by")
    node_metadata: NodeMetaOrder | None = Field(
        default=None,
        description="Deprecated: order by node meta fields. Use `by` with `node_metadata__created_at` instead",
        deprecated=True,
    )

    @model_validator(mode="after")
    def validate_selection(self) -> Order:
        # Read node_metadata via __dict__ to avoid triggering its deprecation warning here;
        # the warning should fire when a caller actually accesses the deprecated field.
        if self.by and self.__dict__.get("node_metadata"):
            raise ValueError("'by' and 'node_metadata' are mutually exclusive; use 'by' instead of 'node_metadata'")
        return self
