from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import yaml

from infrahub_sdk.exceptions import AuthenticationError
from infrahub_sdk.template.exceptions import JinjaFilterError

if TYPE_CHECKING:
    from infrahub_sdk.client import InfrahubClient


class InfrahubFilters:
    """Holds an optional InfrahubClient and exposes async filter methods for Jinja2 templates."""

    @classmethod
    def get_filter_names(cls) -> tuple[str, ...]:
        """Return all public async filter method names by convention."""
        return tuple(
            name
            for name in sorted(vars(cls))
            if not name.startswith("_") and inspect.iscoroutinefunction(vars(cls)[name])
        )

    def __init__(self, client: InfrahubClient | None = None) -> None:
        self._client = client

    def set_client(self, client: InfrahubClient) -> None:
        self._client = client

    def _require_client(self, filter_name: str) -> InfrahubClient:
        if self._client is None:
            raise JinjaFilterError(
                filter_name=filter_name,
                message="requires an InfrahubClient",
                hint="pass a client via Jinja2Template(client=...)",
            )
        return self._client

    async def artifact_content(self, storage_id: str) -> str:
        """Retrieve artifact content by storage_id."""
        client = self._require_client(filter_name="artifact_content")
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
            return await client.object_store.get(identifier=storage_id)
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

    async def _fetch_file_object(
        self, filter_name: str, identifier: str | list[str], label: str, fetch: Callable[[], Coroutine[Any, Any, str]]
    ) -> str:
        if identifier is None:
            raise JinjaFilterError(
                filter_name=filter_name,
                message=f"{label} is null",
                hint=f"ensure the GraphQL query returns a valid {label} value",
            )
        if not identifier:
            raise JinjaFilterError(
                filter_name=filter_name,
                message=f"{label} is empty",
                hint=f"ensure the GraphQL query returns a non-empty {label} value",
            )
        try:
            return await fetch()
        except AuthenticationError as exc:
            raise JinjaFilterError(
                filter_name=filter_name, message=f"permission denied for {label}: {identifier}"
            ) from exc
        except ValueError as exc:
            raise JinjaFilterError(filter_name=filter_name, message=str(exc)) from exc
        except JinjaFilterError:
            raise
        except Exception as exc:
            raise JinjaFilterError(
                filter_name=filter_name, message=f"failed to retrieve content for {label}: {identifier}", hint=str(exc)
            ) from exc

    async def file_object_content(self, storage_id: str) -> str:
        """Retrieve file object content by storage_id."""
        client = self._require_client(filter_name="file_object_content")
        return await self._fetch_file_object(
            filter_name="file_object_content",
            identifier=storage_id,
            label="storage_id",
            fetch=lambda: client.object_store.get_file_by_storage_id(storage_id=storage_id),
        )

    async def file_object_content_by_id(self, node_id: str) -> str:
        """Retrieve file object content by node UUID."""
        client = self._require_client(filter_name="file_object_content_by_id")
        return await self._fetch_file_object(
            filter_name="file_object_content_by_id",
            identifier=node_id,
            label="node_id",
            fetch=lambda: client.object_store.get_file_by_id(node_id=node_id),
        )

    async def file_object_content_by_hfid(self, hfid: str | list[str], kind: str = "") -> str:
        """Retrieve file object content by Human-Friendly ID."""
        client = self._require_client(filter_name="file_object_content_by_hfid")
        if not kind:
            raise JinjaFilterError(
                filter_name="file_object_content_by_hfid",
                message="'kind' argument is required",
                hint='use {{ hfid | file_object_content_by_hfid(kind="MyKind") }}',
            )
        hfid_list = hfid if isinstance(hfid, list) else [hfid]
        if not all(hfid_list):
            raise JinjaFilterError(
                filter_name="file_object_content_by_hfid",
                message="hfid contains empty elements",
                hint="ensure all HFID components are non-empty strings",
            )
        return await self._fetch_file_object(
            filter_name="file_object_content_by_hfid",
            identifier=hfid,
            label="hfid",
            fetch=lambda: client.object_store.get_file_by_hfid(kind=kind, hfid=hfid_list),
        )


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
