from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import httpx

from .exceptions import AuthenticationError, ServerNotReachableError

if TYPE_CHECKING:
    from .client import InfrahubClient, InfrahubClientSync


ALLOWED_TEXT_CONTENT_TYPES = {"application/json", "application/yaml", "application/x-yaml"}


def _extract_content_type(response: httpx.Response) -> str:
    """Extract and normalize the content-type from an HTTP response, stripping parameters."""
    return response.headers.get("content-type", "").split(";")[0].strip().lower()


class ObjectStoreBase:
    @staticmethod
    def _validate_text_content(response: httpx.Response, identifier: str) -> str:
        """Validate that a file response has a text-based content-type and return the text.

        Raises:
            ValueError: If the response content-type is not text-based.

        """
        content_type = _extract_content_type(response)
        if not content_type.startswith("text/") and content_type not in ALLOWED_TEXT_CONTENT_TYPES:
            raise ValueError(
                f"Binary content not supported: content-type '{content_type}' for identifier '{identifier}'"
            )
        return response.text


class ObjectStore(ObjectStoreBase):
    def __init__(self, client: InfrahubClient) -> None:
        self.client = client

    async def get(self, identifier: str, tracker: str | None = None) -> str:
        url = f"{self.client.address}/api/storage/object/{identifier}"
        headers = copy.copy(self.client.headers or {})
        if self.client.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        try:
            resp = await self.client._get(url=url, headers=headers)
            resp.raise_for_status()

        except ServerNotReachableError:
            self.client.log.error(f"Unable to connect to {self.client.address} .. ")
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                response = exc.response.json()
                errors = response.get("errors")
                messages = [error.get("message") for error in errors]
                raise AuthenticationError(" | ".join(messages)) from exc
            raise

        return resp.text

    async def upload(self, content: str, tracker: str | None = None) -> dict[str, str]:
        url = f"{self.client.address}/api/storage/upload/content"
        headers = copy.copy(self.client.headers or {})
        if self.client.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        try:
            resp = await self.client._post(url=url, payload={"content": content}, headers=headers)
            resp.raise_for_status()
        except ServerNotReachableError:
            self.client.log.error(f"Unable to connect to {self.client.address} .. ")
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                response = exc.response.json()
                errors = response.get("errors")
                messages = [error.get("message") for error in errors]
                raise AuthenticationError(" | ".join(messages)) from exc
            raise

        return resp.json()

    async def _get_file(self, url: str, identifier: str, tracker: str | None = None) -> str:
        """Fetch a file endpoint and validate that the response is text-based.

        Raises:
            ServerNotReachableError: If the Infrahub server is not reachable.
            AuthenticationError: If the server returns a 401 or 403 response.
            HTTPStatusError: For other non-2xx HTTP responses.

        """
        headers = copy.copy(self.client.headers or {})
        if self.client.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        try:
            resp = await self.client._get(url=url, headers=headers)
            resp.raise_for_status()
        except ServerNotReachableError:
            self.client.log.error(f"Unable to connect to {self.client.address} .. ")
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                response = exc.response.json()
                errors = response.get("errors")
                messages = [error.get("message") for error in errors]
                raise AuthenticationError(" | ".join(messages)) from exc
            raise

        return self._validate_text_content(response=resp, identifier=identifier)

    async def get_file_by_storage_id(self, storage_id: str, tracker: str | None = None) -> str:
        """Retrieve file object content by storage_id."""
        url = f"{self.client.address}/api/storage/files/by-storage-id/{storage_id}"
        return await self._get_file(url=url, identifier=storage_id, tracker=tracker)

    async def get_file_by_id(self, node_id: str, tracker: str | None = None) -> str:
        """Retrieve file object content by node UUID."""
        url = f"{self.client.address}/api/storage/files/{node_id}"
        return await self._get_file(url=url, identifier=node_id, tracker=tracker)

    async def get_file_by_hfid(self, kind: str, hfid: list[str], tracker: str | None = None) -> str:
        """Retrieve file object content by Human-Friendly ID."""
        params = "&".join(f"hfid={h}" for h in hfid)
        url = f"{self.client.address}/api/storage/files/by-hfid/{kind}?{params}"
        return await self._get_file(url=url, identifier=f"{kind}:{'/'.join(hfid)}", tracker=tracker)


class ObjectStoreSync(ObjectStoreBase):
    def __init__(self, client: InfrahubClientSync) -> None:
        self.client = client

    def get(self, identifier: str, tracker: str | None = None) -> str:
        url = f"{self.client.address}/api/storage/object/{identifier}"
        headers = copy.copy(self.client.headers or {})
        if self.client.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        try:
            resp = self.client._get(url=url, headers=headers)
            resp.raise_for_status()

        except ServerNotReachableError:
            self.client.log.error(f"Unable to connect to {self.client.address} .. ")
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                response = exc.response.json()
                errors = response.get("errors")
                messages = [error.get("message") for error in errors]
                raise AuthenticationError(" | ".join(messages)) from exc
            raise

        return resp.text

    def upload(self, content: str, tracker: str | None = None) -> dict[str, str]:
        url = f"{self.client.address}/api/storage/upload/content"
        headers = copy.copy(self.client.headers or {})
        if self.client.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        try:
            resp = self.client._post(url=url, payload={"content": content}, headers=headers)
            resp.raise_for_status()
        except ServerNotReachableError:
            self.client.log.error(f"Unable to connect to {self.client.address} .. ")
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                response = exc.response.json()
                errors = response.get("errors")
                messages = [error.get("message") for error in errors]
                raise AuthenticationError(" | ".join(messages)) from exc
            raise

        return resp.json()

    def _get_file(self, url: str, identifier: str, tracker: str | None = None) -> str:
        """Fetch a file endpoint and validate that the response is text-based.

        Raises:
            ServerNotReachableError: If the Infrahub server is not reachable.
            AuthenticationError: If the server returns a 401 or 403 response.
            HTTPStatusError: For other non-2xx HTTP responses.

        """
        headers = copy.copy(self.client.headers or {})
        if self.client.insert_tracker and tracker:
            headers["X-Infrahub-Tracker"] = tracker

        try:
            resp = self.client._get(url=url, headers=headers)
            resp.raise_for_status()
        except ServerNotReachableError:
            self.client.log.error(f"Unable to connect to {self.client.address} .. ")
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                response = exc.response.json()
                errors = response.get("errors")
                messages = [error.get("message") for error in errors]
                raise AuthenticationError(" | ".join(messages)) from exc
            raise

        return self._validate_text_content(resp, identifier)

    def get_file_by_storage_id(self, storage_id: str, tracker: str | None = None) -> str:
        """Retrieve file object content by storage_id."""
        url = f"{self.client.address}/api/storage/files/by-storage-id/{storage_id}"
        return self._get_file(url=url, identifier=storage_id, tracker=tracker)

    def get_file_by_id(self, node_id: str, tracker: str | None = None) -> str:
        """Retrieve file object content by node UUID."""
        url = f"{self.client.address}/api/storage/files/{node_id}"
        return self._get_file(url=url, identifier=node_id, tracker=tracker)

    def get_file_by_hfid(self, kind: str, hfid: list[str], tracker: str | None = None) -> str:
        """Retrieve file object content by Human-Friendly ID."""
        params = "&".join(f"hfid={h}" for h in hfid)
        url = f"{self.client.address}/api/storage/files/by-hfid/{kind}?{params}"
        return self._get_file(url=url, identifier=f"{kind}:{'/'.join(hfid)}", tracker=tracker)
