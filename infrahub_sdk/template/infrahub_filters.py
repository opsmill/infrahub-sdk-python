from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from infrahub_sdk.exceptions import AuthenticationError
from infrahub_sdk.template.exceptions import JinjaFilterError

if TYPE_CHECKING:
    from infrahub_sdk.client import InfrahubClient


class InfrahubFilters:
    """Holds an InfrahubClient and exposes async filter methods for Jinja2 templates."""

    def __init__(self, client: InfrahubClient) -> None:
        self.client = client

    async def artifact_content(self, storage_id: str) -> str:
        """Retrieve artifact content by storage_id."""
        # Validate input
        if storage_id is None:
            raise JinjaFilterError(
                filter_name="artifact_content",
                message="storage_id is null",
                hint="ensure the GraphQL query returns a valid storage_id value",
            )
        if not storage_id:
            raise JinjaFilterError(
                filter_name="artifact_content",
                message="storage_id is empty",
                hint="ensure the GraphQL query returns a non-empty storage_id value",
            )
        try:
            return await self.client.object_store.get(identifier=storage_id)
        except AuthenticationError as exc:
            raise JinjaFilterError(
                filter_name="artifact_content",
                message=f"permission denied for storage_id: {storage_id}",
            ) from exc
        except Exception as exc:
            raise JinjaFilterError(
                filter_name="artifact_content",
                message=f"failed to retrieve content for storage_id: {storage_id}",
                hint=str(exc),
            ) from exc


def no_client_filter(filter_name: str) -> Callable[[str], Coroutine[Any, Any, str]]:
    """Create a filter function that raises JinjaFilterError because no client was provided."""

    async def _filter(storage_id: str) -> str:  # noqa: ARG001
        raise JinjaFilterError(
            filter_name=filter_name,
            message="requires an InfrahubClient",
            hint="pass a client via Jinja2Template(client=...)",
        )

    return _filter
