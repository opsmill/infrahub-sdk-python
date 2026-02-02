from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

from infrahub_sdk.exceptions import AuthenticationError, NodeNotFoundError
from infrahub_sdk.file_handler import FileHandler, FileHandlerBase, FileHandlerSync, PreparedFile

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients


FILE_CONTENT_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
NODE_ID = "test-node-123"


def test_prepare_upload_with_bytes() -> None:
    """Test preparing upload with bytes content."""
    content = b"test file content"
    prepared = FileHandlerBase.prepare_upload(content=content, name="test.txt")

    assert isinstance(prepared, PreparedFile)
    assert prepared.file_object is not None
    assert isinstance(prepared.file_object, BytesIO)
    assert prepared.filename == "test.txt"
    assert prepared.should_close is False
    assert prepared.file_object.read() == content


def test_prepare_upload_with_bytes_default_name() -> None:
    """Test preparing upload with bytes content and no name."""
    content = b"test file content"
    prepared = FileHandlerBase.prepare_upload(content=content)

    assert prepared.file_object is not None
    assert prepared.filename == "uploaded_file"
    assert prepared.should_close is False


def test_prepare_upload_with_path() -> None:
    """Test preparing upload with Path content."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        tmp.write(b"test content from file")
        tmp_path = Path(tmp.name)

    try:
        prepared = FileHandlerBase.prepare_upload(content=tmp_path)

        assert prepared.file_object is not None
        assert prepared.filename == tmp_path.name
        assert prepared.should_close is True
        assert prepared.file_object.read() == b"test content from file"
        prepared.file_object.close()
    finally:
        tmp_path.unlink()


def test_prepare_upload_with_path_custom_name() -> None:
    """Test preparing upload with Path content and custom name."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        tmp.write(b"test content")
        tmp_path = Path(tmp.name)

    try:
        prepared = FileHandlerBase.prepare_upload(content=tmp_path, name="custom_name.txt")

        assert prepared.filename == "custom_name.txt"
        assert prepared.file_object
        prepared.file_object.close()
    finally:
        tmp_path.unlink()


def test_prepare_upload_with_binary_io() -> None:
    """Test preparing upload with BinaryIO content."""
    content = BytesIO(b"binary io content")
    prepared = FileHandlerBase.prepare_upload(content=content, name="binary.bin")

    assert prepared.file_object is content
    assert prepared.filename == "binary.bin"
    assert prepared.should_close is False


def test_prepare_upload_with_none() -> None:
    """Test preparing upload with None content."""
    prepared = FileHandlerBase.prepare_upload(content=None)

    assert prepared.file_object is None
    assert prepared.filename is None
    assert prepared.should_close is False


def test_handle_error_response_401() -> None:
    """Test handling 401 authentication error."""
    response = httpx.Response(status_code=401, json={"errors": [{"message": "Invalid token"}]})
    exc = httpx.HTTPStatusError(message="Unauthorized", request=httpx.Request("GET", "http://test"), response=response)

    with pytest.raises(AuthenticationError) as excinfo:
        FileHandlerBase.handle_error_response(exc=exc)

    assert "Invalid token" in str(excinfo.value)


def test_handle_error_response_403() -> None:
    """Test handling 403 forbidden error."""
    response = httpx.Response(status_code=403, json={"errors": [{"message": "Access denied"}]})
    exc = httpx.HTTPStatusError(message="Forbidden", request=httpx.Request("GET", "http://test"), response=response)

    with pytest.raises(AuthenticationError) as excinfo:
        FileHandlerBase.handle_error_response(exc=exc)

    assert "Access denied" in str(excinfo.value)


def test_handle_error_response_404() -> None:
    """Test handling 404 not found error."""
    response = httpx.Response(status_code=404, json={"detail": "File not found with ID abc123"})
    exc = httpx.HTTPStatusError(message="Not Found", request=httpx.Request("GET", "http://test"), response=response)

    with pytest.raises(NodeNotFoundError) as excinfo:
        FileHandlerBase.handle_error_response(exc=exc)

    assert "File not found with ID abc123" in str(excinfo.value)


def test_handle_error_response_500() -> None:
    """Test handling 500 server error (re-raises)."""
    response = httpx.Response(status_code=500, json={"error": "Internal server error"})
    exc = httpx.HTTPStatusError(message="Server Error", request=httpx.Request("GET", "http://test"), response=response)

    with pytest.raises(httpx.HTTPStatusError):
        FileHandlerBase.handle_error_response(exc=exc)


def test_handle_response_success() -> None:
    """Test handling successful response."""
    request = httpx.Request("GET", "http://test")
    response = httpx.Response(status_code=200, content=FILE_CONTENT_BYTES, request=request)

    result = FileHandlerBase.handle_response(resp=response)

    assert result == FILE_CONTENT_BYTES


@pytest.fixture
def mock_download_success(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock successful file download."""
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/storage/files/test-node-123?branch=main",
        content=FILE_CONTENT_BYTES,
        headers={"Content-Type": "application/octet-stream"},
    )
    return httpx_mock


@pytest.fixture
def mock_download_stream(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock successful streaming file download."""
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/storage/files/stream-node?branch=main",
        content=FILE_CONTENT_BYTES,
        headers={"Content-Type": "application/octet-stream"},
    )
    return httpx_mock


client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
async def test_file_handler_download_to_memory(
    client_type: str, clients: BothClients, mock_download_success: HTTPXMock
) -> None:
    """Test downloading file to memory via FileHandler."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        handler = FileHandler(client=client)
        content = await handler.download(node_id=NODE_ID, branch="main")
    else:
        handler = FileHandlerSync(client=client)
        content = handler.download(node_id=NODE_ID, branch="main")

    assert content == FILE_CONTENT_BYTES


@pytest.mark.parametrize("client_type", client_types)
async def test_file_handler_download_to_disk(
    client_type: str, clients: BothClients, mock_download_stream: HTTPXMock
) -> None:
    """Test streaming file download to disk via FileHandler."""
    client = getattr(clients, client_type)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        dest_path = Path(tmp.name)

    try:
        if client_type == "standard":
            handler = FileHandler(client=client)
            bytes_written = await handler.download(node_id="stream-node", branch="main", dest=dest_path)
        else:
            handler = FileHandlerSync(client=client)
            bytes_written = handler.download(node_id="stream-node", branch="main", dest=dest_path)

        assert bytes_written == len(FILE_CONTENT_BYTES)
        assert dest_path.read_bytes() == FILE_CONTENT_BYTES
    finally:
        dest_path.unlink()


@pytest.mark.parametrize("client_type", client_types)
async def test_file_handler_build_url_with_branch(client_type: str, clients: BothClients) -> None:
    """Test URL building with branch parameter."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        handler = FileHandler(client=client)
    else:
        handler = FileHandlerSync(client=client)

    url = handler._build_url(node_id="node-123", branch="feature-branch")
    assert url == "http://mock/api/storage/files/node-123?branch=feature-branch"


@pytest.mark.parametrize("client_type", client_types)
async def test_file_handler_build_url_without_branch(client_type: str, clients: BothClients) -> None:
    """Test URL building without branch parameter."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        handler = FileHandler(client=client)
    else:
        handler = FileHandlerSync(client=client)

    url = handler._build_url(node_id="node-456", branch=None)
    assert url == "http://mock/api/storage/files/node-456"
