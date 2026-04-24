import hashlib
import tempfile
from pathlib import Path

import anyio
import pytest
from pytest_httpx import HTTPXMock

from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync, UploadResult
from infrahub_sdk.schema import NodeSchemaAPI
from tests.unit.sdk.conftest import BothClients

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

client_types = ["standard", "sync"]

FILE_CONTENT = b"Test file content"
FILE_NAME = "contract.pdf"
FILE_MIME_TYPE = "application/pdf"


@pytest.fixture
def mock_node_create_with_file(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock the HTTP response for node create with file upload."""
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


@pytest.fixture
def mock_node_update_with_file(httpx_mock: HTTPXMock) -> HTTPXMock:
    """Mock the HTTP response for node update with file upload."""
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "NetworkCircuitContractUpdate": {
                    "ok": True,
                    "object": {
                        "id": "existing-file-node-456",
                        "display_label": FILE_NAME,
                        "file_name": {"value": FILE_NAME},
                        "checksum": {"value": "updated123checksum"},
                        "file_size": {"value": len(FILE_CONTENT)},
                        "file_type": {"value": FILE_MIME_TYPE},
                        "storage_id": {"value": "storage-updated-789"},
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
async def test_node_create_with_file_uses_multipart(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI, mock_node_create_with_file: HTTPXMock
) -> None:
    """Test that node.save() for create with file content sends a multipart request."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]
    node.upload_from_bytes(content=FILE_CONTENT, name=FILE_NAME)

    if isinstance(node, InfrahubNode):
        await node.save()
    else:
        node.save()

    requests = mock_node_create_with_file.get_requests()
    assert len(requests) == 1
    assert requests[0].headers.get("x-infrahub-tracker") == "mutation-networkcircuitcontract-create"
    assert requests[0].headers.get("content-type").startswith("multipart/form-data;")
    assert b"Content-Disposition: form-data" in requests[0].content
    assert f'filename="{FILE_NAME}"'.encode() in requests[0].content


@pytest.mark.parametrize("client_type", client_types)
async def test_node_update_with_file_uses_multipart(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI, mock_node_update_with_file: HTTPXMock
) -> None:
    """Test that node.save() for update with file content sends a multipart request."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    # Simulate an existing node
    node.id = "existing-file-node-456"
    node._existing = True
    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]
    node.upload_from_bytes(content=FILE_CONTENT, name=FILE_NAME)

    if isinstance(node, InfrahubNode):
        await node.save()
    else:
        node.save()

    requests = mock_node_update_with_file.get_requests()
    assert len(requests) == 1
    assert requests[0].headers.get("x-infrahub-tracker") == "mutation-networkcircuitcontract-update"
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
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI, mock_node_create_with_file: HTTPXMock
) -> None:
    """Test that file content is cleared after successful save."""
    client = getattr(clients, client_type)

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]

    node.upload_from_bytes(content=FILE_CONTENT, name=FILE_NAME)
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


class TestUploadResult:
    def test_carries_was_uploaded_and_checksum(self) -> None:
        result = UploadResult(was_uploaded=True, checksum="abc123")
        assert result.was_uploaded is True
        assert result.checksum == "abc123"

    def test_checksum_optional(self) -> None:
        result = UploadResult(was_uploaded=False, checksum=None)
        assert result.checksum is None


@pytest.mark.parametrize("client_type", client_types)
class TestMatchesLocalChecksum:
    async def test_bytes_match(self, client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI) -> None:
        payload = b"matching content"
        digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest()

        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "node-1"
        node.checksum.value = digest  # type: ignore[attr-defined]

        if isinstance(node, InfrahubNode):
            assert await node.matches_local_checksum(payload) is True
        else:
            assert node.matches_local_checksum(payload) is True

    async def test_bytes_differ(
        self, client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
    ) -> None:
        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "node-1"
        node.checksum.value = "different-digest"  # type: ignore[attr-defined]

        if isinstance(node, InfrahubNode):
            assert await node.matches_local_checksum(b"hello world") is False
        else:
            assert node.matches_local_checksum(b"hello world") is False

    async def test_path_source(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        tmp_path: Path,
    ) -> None:
        payload = b"file on disk"
        target = tmp_path / "f.bin"
        target.write_bytes(payload)
        digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest()

        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "node-1"
        node.checksum.value = digest  # type: ignore[attr-defined]

        if isinstance(node, InfrahubNode):
            assert await node.matches_local_checksum(target) is True
        else:
            assert node.matches_local_checksum(target) is True

    async def test_raises_for_non_file_object(
        self, client_type: str, clients: BothClients, non_file_object_schema: NodeSchemaAPI
    ) -> None:
        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=non_file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=non_file_object_schema, branch="main")

        if isinstance(node, InfrahubNode):
            with pytest.raises(
                FeatureNotSupportedError,
                match=r"calling matches_local_checksum is only supported",
            ):
                await node.matches_local_checksum(b"anything")
        else:
            with pytest.raises(
                FeatureNotSupportedError,
                match=r"calling matches_local_checksum is only supported",
            ):
                node.matches_local_checksum(b"anything")

    async def test_raises_when_no_server_checksum(
        self, client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
    ) -> None:
        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "node-1"
        # Do NOT set node.checksum.value — default is None.

        if isinstance(node, InfrahubNode):
            with pytest.raises(ValueError, match=r"has no server-side checksum"):
                await node.matches_local_checksum(b"anything")
        else:
            with pytest.raises(ValueError, match=r"has no server-side checksum"):
                node.matches_local_checksum(b"anything")


@pytest.mark.parametrize("client_type", client_types)
class TestUploadIfChanged:
    async def test_skips_when_checksum_matches(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        httpx_mock: HTTPXMock,
    ) -> None:
        payload = b"unchanged content"
        digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest()

        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "already-on-server"
        node._existing = True
        node.checksum.value = digest  # type: ignore[attr-defined, union-attr]

        if isinstance(node, InfrahubNode):
            result = await node.upload_if_changed(source=payload, name="f.bin")
        else:
            result = node.upload_if_changed(source=payload, name="f.bin")

        assert isinstance(result, UploadResult)
        assert result.was_uploaded is False
        assert result.checksum == digest
        # No HTTP request should have been issued.
        assert httpx_mock.get_requests() == []

    async def test_uploads_when_checksum_differs(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        mock_node_update_with_file: HTTPXMock,
    ) -> None:
        new_content = b"new content"
        expected_digest = hashlib.sha1(new_content, usedforsecurity=False).hexdigest()

        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "existing-file-node-456"
        node._existing = True
        node.checksum.value = "old-server-digest"  # type: ignore[attr-defined, union-attr]

        if isinstance(node, InfrahubNode):
            result = await node.upload_if_changed(source=new_content, name="f.bin")
        else:
            result = node.upload_if_changed(source=new_content, name="f.bin")

        assert result.was_uploaded is True
        # Post-save checksum is the locally computed SHA-1 of the uploaded content.
        assert result.checksum == expected_digest
        # Positive-path HTTP verification: the update mutation must have been dispatched.
        requests = mock_node_update_with_file.get_requests()
        assert len(requests) > 0
        # At least one request should be a POST to the GraphQL endpoint (the update mutation).
        assert any(r.method == "POST" for r in requests)

    async def test_uploads_when_node_unsaved(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        mock_node_create_with_file: HTTPXMock,
    ) -> None:
        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        # Do NOT set node.id — unsaved.

        if isinstance(node, InfrahubNode):
            result = await node.upload_if_changed(source=b"initial content", name=FILE_NAME)
        else:
            result = node.upload_if_changed(source=b"initial content", name=FILE_NAME)

        assert result.was_uploaded is True
        assert result.checksum is not None
        # Positive-path HTTP verification: the create mutation must have been dispatched.
        requests = mock_node_create_with_file.get_requests()
        assert len(requests) > 0
        assert any(r.method == "POST" for r in requests)

    async def test_derives_name_from_path(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        mock_node_update_with_file: HTTPXMock,
        tmp_path: Path,
    ) -> None:
        target = tmp_path / "derived-name.bin"
        target.write_bytes(b"content")

        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "existing-file-node-456"
        node._existing = True
        node.checksum.value = "old-server-digest"  # type: ignore[attr-defined, union-attr]

        # No explicit name — should derive from target.name internally.
        if isinstance(node, InfrahubNode):
            result = await node.upload_if_changed(source=target)
        else:
            result = node.upload_if_changed(source=target)

        assert result.was_uploaded is True

    async def test_requires_name_for_bytes(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
    ) -> None:
        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "some-id"
        node.checksum.value = "x"  # type: ignore[attr-defined, union-attr]

        if isinstance(node, InfrahubNode):
            with pytest.raises(ValueError, match=r"name is required"):
                await node.upload_if_changed(source=b"bytes content")  # no name supplied
        else:
            with pytest.raises(ValueError, match=r"name is required"):
                node.upload_if_changed(source=b"bytes content")  # no name supplied

    async def test_raises_for_non_file_object(
        self,
        client_type: str,
        clients: BothClients,
        non_file_object_schema: NodeSchemaAPI,
    ) -> None:
        client = getattr(clients, client_type)
        if client_type == "standard":
            node = InfrahubNode(client=client, schema=non_file_object_schema, branch="main")
        else:
            node = InfrahubNodeSync(client=client, schema=non_file_object_schema, branch="main")

        if isinstance(node, InfrahubNode):
            with pytest.raises(
                FeatureNotSupportedError,
                match=r"calling upload_if_changed is only supported",
            ):
                await node.upload_if_changed(source=b"x", name="f.bin")
        else:
            with pytest.raises(
                FeatureNotSupportedError,
                match=r"calling upload_if_changed is only supported",
            ):
                node.upload_if_changed(source=b"x", name="f.bin")


@pytest.mark.parametrize("client_type", client_types)
class TestDownloadSkipIfUnchanged:
    async def test_skip_when_local_matches(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
    ) -> None:
        payload = b"identical content"
        digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest()
        dest = tmp_path / "local.bin"
        dest.write_bytes(payload)

        client = getattr(clients, client_type)
        if client_type == "standard":
            node: InfrahubNode | InfrahubNodeSync = InfrahubNode(
                client=client, schema=file_object_schema, branch="main"
            )
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "file-node-skip"
        node.checksum.value = digest  # type: ignore[attr-defined, union-attr]

        if isinstance(node, InfrahubNode):
            bytes_written = await node.download_file(dest=dest, skip_if_unchanged=True)
        else:
            bytes_written = node.download_file(dest=dest, skip_if_unchanged=True)

        assert bytes_written == 0
        # pytest-httpx raises if any unregistered request is attempted; this also asserts
        # that zero requests were made at all.
        assert httpx_mock.get_requests() == []

    async def test_downloads_when_local_differs(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        tmp_path: Path,
        mock_download_file_to_disk: HTTPXMock,  # existing fixture
    ) -> None:
        dest = tmp_path / "local.bin"
        dest.write_bytes(b"stale content")  # different from FILE_CONTENT

        client = getattr(clients, client_type)
        if client_type == "standard":
            node: InfrahubNode | InfrahubNodeSync = InfrahubNode(
                client=client, schema=file_object_schema, branch="main"
            )
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "file-node-stream"  # id matches mock_download_file_to_disk
        node.checksum.value = "server-digest-different-from-local"  # type: ignore[attr-defined, union-attr]

        if isinstance(node, InfrahubNode):
            bytes_written = await node.download_file(dest=dest, skip_if_unchanged=True)
        else:
            bytes_written = node.download_file(dest=dest, skip_if_unchanged=True)

        assert bytes_written == len(FILE_CONTENT)
        assert dest.read_bytes() == FILE_CONTENT
        # Positive-path HTTP verification: the GET to the storage endpoint must have fired.
        download_requests = [
            r
            for r in mock_download_file_to_disk.get_requests()
            if r.method == "GET" and "/api/storage/files/" in r.url.path
        ]
        assert len(download_requests) == 1

    async def test_downloads_when_dest_missing(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        tmp_path: Path,
        mock_download_file_to_disk: HTTPXMock,
    ) -> None:
        dest = tmp_path / "missing.bin"  # does not exist
        assert not dest.exists()

        client = getattr(clients, client_type)
        if client_type == "standard":
            node: InfrahubNode | InfrahubNodeSync = InfrahubNode(
                client=client, schema=file_object_schema, branch="main"
            )
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "file-node-stream"
        node.checksum.value = "any-digest"  # type: ignore[attr-defined, union-attr]

        if isinstance(node, InfrahubNode):
            bytes_written = await node.download_file(dest=dest, skip_if_unchanged=True)
        else:
            bytes_written = node.download_file(dest=dest, skip_if_unchanged=True)

        assert bytes_written == len(FILE_CONTENT)
        assert dest.exists()

    async def test_raises_when_skip_without_dest(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
    ) -> None:
        client = getattr(clients, client_type)
        if client_type == "standard":
            node: InfrahubNode | InfrahubNodeSync = InfrahubNode(
                client=client, schema=file_object_schema, branch="main"
            )
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "file-node-1"
        node.checksum.value = "any-digest"  # type: ignore[attr-defined, union-attr]

        with pytest.raises(ValueError, match=r"skip_if_unchanged requires dest"):
            if isinstance(node, InfrahubNode):
                await node.download_file(dest=None, skip_if_unchanged=True)
            else:
                node.download_file(dest=None, skip_if_unchanged=True)

    async def test_default_behavior_unchanged(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        mock_download_file: HTTPXMock,  # existing fixture for in-memory download
    ) -> None:
        # skip_if_unchanged defaults to False — download always occurs.
        client = getattr(clients, client_type)
        if client_type == "standard":
            node: InfrahubNode | InfrahubNodeSync = InfrahubNode(
                client=client, schema=file_object_schema, branch="main"
            )
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        node.id = "file-node-123"  # matches mock_download_file

        if isinstance(node, InfrahubNode):
            content = await node.download_file()  # no flag
        else:
            content = node.download_file()  # no flag

        assert isinstance(content, bytes)
        assert content == FILE_CONTENT

    async def test_skip_raises_for_unsaved_node(
        self,
        client_type: str,
        clients: BothClients,
        file_object_schema: NodeSchemaAPI,
        tmp_path: Path,
    ) -> None:
        # Unsaved node (no id) with a dest whose checksum happens to match
        # the node's checksum attribute should still raise the unsaved-node
        # ValueError, not silently return 0.
        payload = b"content"
        digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest()
        dest = tmp_path / "local.bin"
        dest.write_bytes(payload)

        client = getattr(clients, client_type)
        if client_type == "standard":
            node: InfrahubNode | InfrahubNodeSync = InfrahubNode(
                client=client, schema=file_object_schema, branch="main"
            )
        else:
            node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")
        # Do NOT set node.id — unsaved.
        node.checksum.value = digest  # type: ignore[attr-defined, union-attr]

        with pytest.raises(ValueError, match=r"hasn't been saved yet"):
            if isinstance(node, InfrahubNode):
                await node.download_file(dest=dest, skip_if_unchanged=True)
            else:
                node.download_file(dest=dest, skip_if_unchanged=True)
