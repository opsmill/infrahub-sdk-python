from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, cast, overload

import anyio
import httpx

from .exceptions import AuthenticationError, NodeNotFoundError, ServerNotReachableError

if TYPE_CHECKING:
    from .client import InfrahubClient, InfrahubClientSync

_SHA1_CHUNK_BYTES = 64 * 1024


def sha1_of_source(source: bytes | Path | BinaryIO) -> str:
    """Compute the SHA-1 hex digest of an upload/download source.

    Accepts the same shapes as :meth:`FileHandlerBase.prepare_upload` so
    callers can compare local content against a server-stored checksum
    without materialising the full file in memory.

    Args:
        source: The content to hash. ``bytes`` are hashed in one shot.
            A ``Path`` is read in 64 KiB chunks. A ``BinaryIO`` is read
            from its current position, then rewound so downstream
            callers can re-read it.

    Returns:
        Lowercase SHA-1 hex digest, matching the algorithm Infrahub
        stores in ``CoreFileObject.checksum``.

    Raises:
        TypeError: If ``source`` is not one of the supported types.

    """
    hasher = hashlib.sha1(usedforsecurity=False)

    if isinstance(source, bytes):
        hasher.update(source)
        return hasher.hexdigest()

    if isinstance(source, Path):
        with source.open("rb") as fh:
            while chunk := fh.read(_SHA1_CHUNK_BYTES):
                hasher.update(chunk)
        return hasher.hexdigest()

    if hasattr(source, "read") and hasattr(source, "seek"):
        start = source.tell()
        try:
            while chunk := source.read(_SHA1_CHUNK_BYTES):
                hasher.update(chunk)
        finally:
            source.seek(start)
        return hasher.hexdigest()

    raise TypeError(f"sha1_of_source expects bytes, Path, or BinaryIO; got {type(source).__name__}")


@dataclass
class PreparedFile:
    file_object: BinaryIO | None
    filename: str | None
    should_close: bool


class FileHandlerBase:
    """Base class for file handling operations.

    Provides common functionality for both async and sync file handlers, including upload preparation and error handling.
    """

    @staticmethod
    async def prepare_upload(content: bytes | Path | BinaryIO | None, name: str | None = None) -> PreparedFile:
        """Prepare file content for upload (async version).

        Converts various content types to a consistent BinaryIO interface for streaming uploads.
        For Path inputs, opens the file handle in a thread pool to avoid blocking the event loop.
        The actual file reading is streamed by httpx during the HTTP request.

        Args:
            content: The file content as bytes, a Path to a file, or a file-like object.
                     Can be None if no file is set.
            name: Optional filename. If not provided and content is a Path,
                  the filename will be derived from the path.

        Returns:
            A PreparedFile containing the file object, filename, and whether it should be closed.

        """
        if content is None:
            return PreparedFile(file_object=None, filename=None, should_close=False)

        if name is None and isinstance(content, Path):
            name = content.name

        filename = name or "uploaded_file"

        if isinstance(content, bytes):
            return PreparedFile(file_object=BytesIO(content), filename=filename, should_close=False)
        if isinstance(content, Path):
            # Open file in thread pool to avoid blocking the event loop
            # Returns a sync file handle that httpx can stream from in chunks
            file_obj = await anyio.to_thread.run_sync(content.open, "rb")
            return PreparedFile(file_object=cast("BinaryIO", file_obj), filename=filename, should_close=True)

        # At this point, content must be a BinaryIO (file-like object)
        return PreparedFile(file_object=cast("BinaryIO", content), filename=filename, should_close=False)

    @staticmethod
    def prepare_upload_sync(content: bytes | Path | BinaryIO | None, name: str | None = None) -> PreparedFile:
        """Prepare file content for upload (sync version).

        Converts various content types to a consistent BinaryIO interface for streaming uploads.

        Args:
            content: The file content as bytes, a Path to a file, or a file-like object.
                     Can be None if no file is set.
            name: Optional filename. If not provided and content is a Path,
                  the filename will be derived from the path.

        Returns:
            A PreparedFile containing the file object, filename, and whether it should be closed.

        """
        if content is None:
            return PreparedFile(file_object=None, filename=None, should_close=False)

        if name is None and isinstance(content, Path):
            name = content.name

        filename = name or "uploaded_file"

        if isinstance(content, bytes):
            return PreparedFile(file_object=BytesIO(content), filename=filename, should_close=False)
        if isinstance(content, Path):
            return PreparedFile(file_object=content.open("rb"), filename=filename, should_close=True)

        # At this point, content must be a BinaryIO (file-like object)
        return PreparedFile(file_object=cast("BinaryIO", content), filename=filename, should_close=False)

    @staticmethod
    def handle_error_response(exc: httpx.HTTPStatusError, branch: str, node_id: str) -> None:
        """Handle HTTP error responses for file operations.

        Args:
            exc: The HTTP status error from httpx.
            branch: The branch name used for the request.
            node_id: The ID of the FileObject node being accessed.

        Raises:
            AuthenticationError: If authentication fails (401/403).
            NodeNotFoundError: If the file/node is not found (404).
            httpx.HTTPStatusError: For other HTTP errors.

        """
        if exc.response.status_code in {401, 403}:
            response = exc.response.json()
            errors = response.get("errors", [])
            messages = [error.get("message") for error in errors]
            raise AuthenticationError(" | ".join(messages)) from exc
        if exc.response.status_code == 404:
            response = exc.response.json()
            detail = response.get("detail", "File not found")
            raise NodeNotFoundError(
                branch_name=branch,
                node_type="FileObject",
                identifier={"id": [node_id]},
                message=detail,
            ) from exc
        raise exc

    @staticmethod
    def handle_response(resp: httpx.Response, branch: str, node_id: str) -> bytes:
        """Handle the HTTP response and return file content as bytes.

        Args:
            resp: The HTTP response from httpx.
            branch: The branch name used for the request.
            node_id: The ID of the FileObject node being accessed.

        Returns:
            The file content as bytes.

        Raises:
            AuthenticationError: If authentication fails.
            NodeNotFoundError: If the file is not found.

        """
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            FileHandlerBase.handle_error_response(exc=exc, branch=branch, node_id=node_id)
        return resp.content


class FileHandler(FileHandlerBase):
    """Async file handler for download operations.

    Handles file downloads with support for streaming to disk
    for memory-efficient handling of large files.
    """

    def __init__(self, client: InfrahubClient) -> None:
        """Initialize the async file handler.

        Args:
            client: The async Infrahub client instance.

        """
        self._client = client

    def _build_url(self, node_id: str, branch: str | None) -> str:
        """Build the download URL for a file.

        Args:
            node_id: The ID of the FileObject node.
            branch: Optional branch name.

        Returns:
            The complete URL for downloading the file.

        """
        url = f"{self._client.address}/api/storage/files/{node_id}"
        if branch:
            url = f"{url}?branch={branch}"
        return url

    @overload
    async def download(self, node_id: str, branch: str | None) -> bytes: ...

    @overload
    async def download(self, node_id: str, branch: str | None, dest: Path) -> int: ...

    @overload
    async def download(self, node_id: str, branch: str | None, dest: None) -> bytes: ...

    async def download(self, node_id: str, branch: str | None, dest: Path | None = None) -> bytes | int:
        """Download file content from a FileObject node.

        Args:
            node_id: The ID of the FileObject node.
            branch: Optional branch name. Uses client default if not provided.
            dest: Optional destination path. If provided, streams to disk.

        Returns:
            If dest is None: The file content as bytes.
            If dest is provided: The number of bytes written.

        Raises:
            ServerNotReachableError: If the server is not reachable.
            AuthenticationError: If authentication fails.
            NodeNotFoundError: If the node/file is not found.

        """
        effective_branch = branch or self._client.default_branch
        url = self._build_url(node_id=node_id, branch=effective_branch)

        if dest is not None:
            return await self._stream_to_file(url=url, dest=dest, branch=effective_branch, node_id=node_id)

        try:
            resp = await self._client._get(url=url)
        except ServerNotReachableError:
            self._client.log.error(f"Unable to connect to {self._client.address}")
            raise

        return self.handle_response(resp=resp, branch=effective_branch, node_id=node_id)

    async def _stream_to_file(self, url: str, dest: Path, branch: str, node_id: str) -> int:
        """Stream download directly to a file without loading into memory.

        Args:
            url: The URL to download from.
            dest: The destination path to write to.
            branch: The branch name used for the request.
            node_id: The ID of the FileObject node being downloaded.

        Returns:
            The number of bytes written to the file.

        Raises:
            ServerNotReachableError: If the server is not reachable.
            AuthenticationError: If authentication fails.
            NodeNotFoundError: If the file is not found.

        """
        try:
            async with self._client._get_streaming(url=url) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    # Need to read the response body for error details
                    await resp.aread()
                    self.handle_error_response(exc=exc, branch=branch, node_id=node_id)

                bytes_written = 0
                async with await anyio.Path(dest).open("wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        await f.write(chunk)
                        bytes_written += len(chunk)
                return bytes_written
        except ServerNotReachableError:
            self._client.log.error(f"Unable to connect to {self._client.address}")
            raise


class FileHandlerSync(FileHandlerBase):
    """Sync file handler for download operations.

    Handles file downloads with support for streaming to disk
    for memory-efficient handling of large files.
    """

    def __init__(self, client: InfrahubClientSync) -> None:
        """Initialize the sync file handler.

        Args:
            client: The sync Infrahub client instance.

        """
        self._client = client

    def _build_url(self, node_id: str, branch: str | None) -> str:
        """Build the download URL for a file.

        Args:
            node_id: The ID of the FileObject node.
            branch: Optional branch name.

        Returns:
            The complete URL for downloading the file.

        """
        url = f"{self._client.address}/api/storage/files/{node_id}"
        if branch:
            url = f"{url}?branch={branch}"
        return url

    @overload
    def download(self, node_id: str, branch: str | None) -> bytes: ...

    @overload
    def download(self, node_id: str, branch: str | None, dest: Path) -> int: ...

    @overload
    def download(self, node_id: str, branch: str | None, dest: None) -> bytes: ...

    def download(self, node_id: str, branch: str | None, dest: Path | None = None) -> bytes | int:
        """Download file content from a FileObject node.

        Args:
            node_id: The ID of the FileObject node.
            branch: Optional branch name. Uses client default if not provided.
            dest: Optional destination path. If provided, streams to disk.

        Returns:
            If dest is None: The file content as bytes.
            If dest is provided: The number of bytes written.

        Raises:
            ServerNotReachableError: If the server is not reachable.
            AuthenticationError: If authentication fails.
            NodeNotFoundError: If the node/file is not found.

        """
        effective_branch = branch or self._client.default_branch
        url = self._build_url(node_id=node_id, branch=effective_branch)

        if dest is not None:
            return self._stream_to_file(url=url, dest=dest, branch=effective_branch, node_id=node_id)

        try:
            resp = self._client._get(url=url)
        except ServerNotReachableError:
            self._client.log.error(f"Unable to connect to {self._client.address}")
            raise

        return self.handle_response(resp=resp, branch=effective_branch, node_id=node_id)

    def _stream_to_file(self, url: str, dest: Path, branch: str, node_id: str) -> int:
        """Stream download directly to a file without loading into memory.

        Args:
            url: The URL to download from.
            dest: The destination path to write to.
            branch: The branch name used for the request.
            node_id: The ID of the FileObject node being downloaded.

        Returns:
            The number of bytes written to the file.

        Raises:
            ServerNotReachableError: If the server is not reachable.
            AuthenticationError: If authentication fails.
            NodeNotFoundError: If the file is not found.

        """
        try:
            with self._client._get_streaming(url=url) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    # Need to read the response body for error details
                    resp.read()
                    self.handle_error_response(exc=exc, branch=branch, node_id=node_id)

                bytes_written = 0
                with dest.open("wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        bytes_written += len(chunk)
                return bytes_written
        except ServerNotReachableError:
            self._client.log.error(f"Unable to connect to {self._client.address}")
            raise
