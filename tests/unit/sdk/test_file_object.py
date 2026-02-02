import tempfile
from pathlib import Path

import anyio
import pytest
from pytest_httpx import HTTPXMock

from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema import NodeSchemaAPI
from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

FILE_CONTENT_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."


@pytest.fixture
def mock_download_file(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/storage/files/file-node-123?branch=main",
        content=FILE_CONTENT_BYTES,
        headers={"Content-Type": "image/png", "Content-Disposition": 'attachment; filename="test.png"'},
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_node_download_file(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI, mock_download_file: HTTPXMock
) -> None:
    """Test downloading a file from a FileObject node."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.id = "file-node-123"
    if isinstance(node, InfrahubNode):
        content = await node.download_file()
    else:
        content = node.download_file()

    assert content == FILE_CONTENT_BYTES


@pytest.fixture
def mock_download_file_to_disk(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/storage/files/file-node-stream?branch=main",
        content=FILE_CONTENT_BYTES,
        headers={"Content-Type": "image/png", "Content-Disposition": 'attachment; filename="test.png"'},
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_node_download_file_to_disk(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI, mock_download_file_to_disk: HTTPXMock
) -> None:
    """Test downloading a file from a FileObject node directly to disk."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.id = "file-node-stream"
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        dest_path = Path(tmp.name)

    try:
        if isinstance(node, InfrahubNode):
            bytes_written = await node.download_file(dest=dest_path)
        else:
            bytes_written = node.download_file(dest=dest_path)

        assert bytes_written == len(FILE_CONTENT_BYTES)
        assert await anyio.Path(dest_path).read_bytes() == FILE_CONTENT_BYTES
    finally:
        await anyio.Path(dest_path).unlink()


@pytest.mark.parametrize("client_type", client_types)
async def test_node_download_file_not_file_object_raises(
    client_type: str, clients: BothClients, non_file_object_schema: NodeSchemaAPI
) -> None:
    """Test that download_file raises error on non-FileObject nodes."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=non_file_object_schema, branch="main")
        with pytest.raises(
            FeatureNotSupportedError,
            match=r"calling download_file is only supported for nodes that inherit from CoreFileObject",
        ):
            await node.download_file()
    else:
        node = InfrahubNodeSync(client=client, schema=non_file_object_schema, branch="main")
        with pytest.raises(
            FeatureNotSupportedError,
            match=r"calling download_file is only supported for nodes that inherit from CoreFileObject",
        ):
            node.download_file()


@pytest.mark.parametrize("client_type", client_types)
async def test_node_download_file_unsaved_node_raises(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test that download_file raises error on unsaved nodes."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        with pytest.raises(ValueError, match=r"Cannot download file for a node that hasn't been saved yet"):
            await node.download_file()
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        with pytest.raises(ValueError, match=r"Cannot download file for a node that hasn't been saved yet"):
            node.download_file()
