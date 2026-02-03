import tempfile
from pathlib import Path

import anyio
import pytest
from pytest_httpx import HTTPXMock

from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema import NodeSchemaAPI
from tests.unit.sdk.conftest import BothClients

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

client_types = ["standard", "sync"]

FILE_CONTENT = b"Test file content"
FILE_NAME = "contract.pdf"
FILE_MIME_TYPE = "application/pdf"


@pytest.fixture
def mock_node_save_with_file(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock the HTTP response for node.save() with file upload."""
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "NetworkCircuitContractCreate": {
                    "ok": True,
                    "object": {
                        "id": "new-file-node-123",
                        "display_label": FILE_NAME,
                        "file_name": {"value": FILE_NAME},
                        "checksum": {"value": "abc123checksum"},
                        "file_size": {"value": len(FILE_CONTENT)},
                        "file_type": {"value": FILE_MIME_TYPE},
                        "storage_id": {"value": "storage-xyz-789"},
                        "contract_start": {"value": "2024-01-01T00:00:00Z"},
                        "contract_end": {"value": "2024-12-31T23:59:59Z"},
                    },
                }
            }
        },
        is_reusable=True,
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_node_save_with_file_uses_multipart(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI, mock_node_save_with_file: HTTPXMock
) -> None:
    """Test that node.save() with file content sends a multipart request."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]
    node.set_file(content=FILE_CONTENT, name=FILE_NAME)

    if isinstance(node, InfrahubNode):
        await node.save()
    else:
        node.save()

    requests = mock_node_save_with_file.get_requests()
    assert len(requests) == 1
    assert requests[0].headers.get("x-infrahub-tracker") == "mutation-networkcircuitcontract-create"
    assert requests[0].headers.get("content-type").startswith("multipart/form-data;")
    assert b"Content-Disposition: form-data" in requests[0].content
    assert f'filename="{FILE_NAME}"'.encode() in requests[0].content


@pytest.mark.parametrize("client_type", client_types)
async def test_node_create_file_object_without_file_raises(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test that creating a FileObject node without file content raises an error."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]

    with pytest.raises(ValueError, match=r"Cannot create .* without file content"):
        if isinstance(node, InfrahubNode):
            await node.save()
        else:
            node.save()


@pytest.mark.parametrize("client_type", client_types)
async def test_node_save_clears_file_after_upload(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI, mock_node_save_with_file: HTTPXMock
) -> None:
    """Test that file content is cleared after successful save."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]

    node.set_file(content=FILE_CONTENT, name=FILE_NAME)
    assert node._file_content is not None
    assert node._file_name is not None

    if isinstance(node, InfrahubNode):
        await node.save()
    else:
        node.save()

    # File content should be cleared after save
    assert node._file_content is None
    assert node._file_name is None


@pytest.fixture
def mock_download_file(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/storage/files/file-node-123?branch=main",
        content=FILE_CONTENT,
        headers={"Content-Type": FILE_MIME_TYPE, "Content-Disposition": f'attachment; filename="{FILE_NAME}"'},
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

    assert content == FILE_CONTENT


@pytest.fixture
def mock_download_file_to_disk(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/storage/files/file-node-stream?branch=main",
        content=FILE_CONTENT,
        headers={"Content-Type": FILE_MIME_TYPE, "Content-Disposition": f'attachment; filename="{FILE_NAME}"'},
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
    with tempfile.TemporaryDirectory() as tmpdir:
        dest_path = Path(tmpdir) / "downloaded.bin"

        if isinstance(node, InfrahubNode):
            bytes_written = await node.download_file(dest=dest_path)
        else:
            bytes_written = node.download_file(dest=dest_path)

        assert bytes_written == len(FILE_CONTENT)
        assert await anyio.Path(dest_path).read_bytes() == FILE_CONTENT


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
