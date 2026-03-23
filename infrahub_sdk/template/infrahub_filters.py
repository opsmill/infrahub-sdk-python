from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import yaml

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
                filter_name="artifact_content", message=f"permission denied for storage_id: {storage_id}"
            ) from exc
        except Exception as exc:
            raise JinjaFilterError(
                filter_name="artifact_content",
                message=f"failed to retrieve content for storage_id: {storage_id}",
                hint=str(exc),
            ) from exc

    async def file_object_content(self, storage_id: str) -> str:
        """Retrieve file object content by storage_id."""
        if storage_id is None:
            raise JinjaFilterError(
                filter_name="file_object_content",
                message="storage_id is null",
                hint="ensure the GraphQL query returns a valid storage_id value",
            )
        if not storage_id:
            raise JinjaFilterError(
                filter_name="file_object_content",
                message="storage_id is empty",
                hint="ensure the GraphQL query returns a non-empty storage_id value",
            )
        try:
            return await self.client.object_store.get_file_by_storage_id(storage_id=storage_id)
        except AuthenticationError as exc:
            raise JinjaFilterError(
                filter_name="file_object_content", message=f"permission denied for storage_id: {storage_id}"
            ) from exc
        except ValueError as exc:
            raise JinjaFilterError(filter_name="file_object_content", message=str(exc)) from exc
        except Exception as exc:
            raise JinjaFilterError(
                filter_name="file_object_content",
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


def from_json(value: str) -> dict | list:
    """Parse a JSON string into a Python dict or list."""
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise JinjaFilterError(filter_name="from_json", message=f"invalid JSON: {exc}") from exc


def from_yaml(value: str) -> dict | list:
    """Parse a YAML string into a Python dict or list."""
    if not value:
        return {}
    try:
        result = yaml.safe_load(value)
        # yaml.safe_load("") returns None, normalize to {}
        if result is None:
            return {}
        return result
    except yaml.YAMLError as exc:
        raise JinjaFilterError(filter_name="from_yaml", message=f"invalid YAML: {exc}") from exc
