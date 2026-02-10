from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.file_object import (
    PDF_MAGIC_BYTES,
    PNG_MAGIC_BYTES,
    TESTING_CIRCUIT,
    TESTING_FILE_CONTRACT,
    TEXT_CONTENT,
    SchemaFileObject,
)

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
    from infrahub_sdk.node.relationship import RelationshipManager, RelationshipManagerSync


@pytest.mark.xfail(reason="Requires Infrahub 1.8+")
class TestFileObjectAsync(TestInfrahubDockerClient, SchemaFileObject):
    """Async integration tests for FileObject functionality."""

    @pytest.fixture(scope="class")
    async def circuit_main(self, client: InfrahubClient, load_file_object_schema: None) -> InfrahubNode:
        obj = await client.create(kind=TESTING_CIRCUIT, circuit_id="CIRCUIT-001", bandwidth=1000)
        await obj.save()
        return obj

    async def test_create_file_object_with_upload(
        self, client: InfrahubClient, load_file_object_schema: None, circuit_main: InfrahubNode
    ) -> None:
        """Test creating FileObject nodes with both upload_from_bytes and upload_from_path."""
        contract_bytes = await client.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-CREATE-BYTES-001",
            description="Test contract with bytes upload",
            circuit=circuit_main,
        )
        contract_bytes.upload_from_bytes(content=PDF_MAGIC_BYTES, name="contract.pdf")
        await contract_bytes.save()

        fetched = await client.get(kind=TESTING_FILE_CONTRACT, id=contract_bytes.id)
        assert fetched.contract_ref.value == "CONTRACT-CREATE-BYTES-001"
        assert fetched.file_name.value == "contract.pdf"
        assert fetched.file_size.value == len(PDF_MAGIC_BYTES)
        assert fetched.checksum.value == hashlib.sha1(PDF_MAGIC_BYTES, usedforsecurity=False).hexdigest()
        assert fetched.storage_id.value

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "upload_test.txt"
            tmp_path.write_bytes(TEXT_CONTENT)

            contract_path = await client.create(
                kind=TESTING_FILE_CONTRACT,
                contract_ref="CONTRACT-CREATE-PATH-001",
                description="Test contract from path",
                circuit=circuit_main,
            )
            contract_path.upload_from_path(path=tmp_path)
            await contract_path.save()

            fetched = await client.get(kind=TESTING_FILE_CONTRACT, id=contract_path.id)
            assert fetched.file_name.value == tmp_path.name
            assert fetched.file_size.value == len(TEXT_CONTENT)
            assert fetched.checksum.value == hashlib.sha1(TEXT_CONTENT, usedforsecurity=False).hexdigest()
            assert fetched.storage_id.value

    async def test_update_file_object_with_new_file(
        self, client: InfrahubClient, load_file_object_schema: None, circuit_main: InfrahubNode
    ) -> None:
        """Test updating a FileObject node with a new file."""
        contract = await client.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-UPDATE-001",
            description="Initial contract",
            circuit=circuit_main,
        )
        contract.upload_from_bytes(content=PDF_MAGIC_BYTES, name="initial.pdf")
        await contract.save()

        contract_to_update = await client.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        contract_to_update.description.value = "Updated contract"
        contract_to_update.upload_from_bytes(content=PNG_MAGIC_BYTES, name="updated.png")
        await contract_to_update.save()

        updated = await client.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        assert updated.description.value == "Updated contract"
        assert updated.file_name.value == "updated.png"
        assert updated.storage_id.value != contract.storage_id.value
        assert updated.checksum.value != contract.checksum.value

    async def test_upsert_file_object_update(
        self, client: InfrahubClient, load_file_object_schema: None, circuit_main: InfrahubNode
    ) -> None:
        """Test upserting an existing FileObject node updates it rather than creating a duplicate."""
        contract = await client.create(
            kind=TESTING_FILE_CONTRACT, contract_ref="CONTRACT-UPSERT-001", description="Original", circuit=circuit_main
        )
        contract.upload_from_bytes(content=PDF_MAGIC_BYTES, name="original.pdf")
        await contract.save()

        contract_upsert = await client.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-UPSERT-001",
            description="Upserted update",
            circuit=circuit_main,
        )
        contract_upsert.upload_from_bytes(content=PNG_MAGIC_BYTES, name="upserted.png")
        await contract_upsert.save(allow_upsert=True)
        assert contract_upsert.id == contract.id

        updated = await client.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        assert updated.description.value == "Upserted update"
        assert updated.file_name.value == "upserted.png"
        assert updated.storage_id.value != contract.storage_id.value

    async def test_download_file(
        self, client: InfrahubClient, load_file_object_schema: None, circuit_main: InfrahubNode
    ) -> None:
        """Test downloading files to memory and to disk."""
        contract = await client.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-DOWNLOAD-001",
            description="Download test",
            circuit=circuit_main,
        )
        contract.upload_from_bytes(content=TEXT_CONTENT, name="download_test.txt")
        await contract.save()

        fetched = await client.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        downloaded_content = await fetched.download_file()
        assert downloaded_content == TEXT_CONTENT

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_path = Path(tmpdir) / "downloaded.txt"
            bytes_written = await fetched.download_file(dest=dest_path)
            assert bytes_written == len(TEXT_CONTENT)
            assert dest_path.read_bytes() == TEXT_CONTENT

    async def test_update_without_file_change(
        self, client: InfrahubClient, load_file_object_schema: None, circuit_main: InfrahubNode
    ) -> None:
        """Test updating FileObject attributes without replacing the file."""
        contract = await client.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-META-001",
            description="Original description",
            circuit=circuit_main,
        )
        contract.upload_from_bytes(content=TEXT_CONTENT, name="unchanged.txt")
        await contract.save()

        contract_to_update = await client.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        contract_to_update.description.value = "Updated description"
        await contract_to_update.save()

        updated = await client.get(kind=TESTING_FILE_CONTRACT, id=contract.id)
        assert updated.description.value == "Updated description"
        assert updated.storage_id.value == contract_to_update.storage_id.value
        assert updated.checksum.value == contract_to_update.checksum.value

    async def test_query_contracts_through_circuit_relationship(
        self, client: InfrahubClient, load_file_object_schema: None, circuit_main: InfrahubNode
    ) -> None:
        """Test that FileObject contracts can be queried through their circuit relationship."""
        for i in range(2):
            contract = await client.create(
                kind=TESTING_FILE_CONTRACT, contract_ref=f"CONTRACT-REL-{i:03d}", circuit=circuit_main
            )
            contract.upload_from_bytes(content=TEXT_CONTENT, name=f"contract_{i}.txt")
            await contract.save()

        circuit = await client.get(kind=TESTING_CIRCUIT, id=circuit_main.id, include=["contracts"])
        contracts: RelationshipManager = circuit.contracts
        contract_refs = {contract.peer.contract_ref.value for contract in contracts}

        assert len(contract_refs) >= 2
        assert "CONTRACT-REL-000" in contract_refs
        assert "CONTRACT-REL-001" in contract_refs


@pytest.mark.xfail(reason="Requires Infrahub 1.8+")
class TestFileObjectSync(TestInfrahubDockerClient, SchemaFileObject):
    """Sync integration tests for FileObject functionality."""

    @pytest.fixture(scope="class")
    def circuit_main_sync(
        self, client_sync: InfrahubClientSync, load_file_object_schema_sync: None
    ) -> InfrahubNodeSync:
        obj = client_sync.create(kind=TESTING_CIRCUIT, circuit_id="CIRCUIT-SYNC-001", bandwidth=2000)
        obj.save()
        return obj

    def test_create_file_object_with_upload_sync(
        self, client_sync: InfrahubClientSync, load_file_object_schema_sync: None, circuit_main_sync: InfrahubNodeSync
    ) -> None:
        """Test creating FileObject nodes with both upload_from_bytes and upload_from_path (sync)."""
        contract_bytes = client_sync.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-CREATE-BYTES-SYNC-001",
            description="Test contract with bytes upload (sync)",
            circuit=circuit_main_sync,
        )
        contract_bytes.upload_from_bytes(content=PDF_MAGIC_BYTES, name="contract_sync.pdf")
        contract_bytes.save()

        fetched = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract_bytes.id)
        assert fetched.contract_ref.value == "CONTRACT-CREATE-BYTES-SYNC-001"
        assert fetched.file_name.value == "contract_sync.pdf"
        assert fetched.file_size.value == len(PDF_MAGIC_BYTES)
        assert fetched.checksum.value == hashlib.sha1(PDF_MAGIC_BYTES, usedforsecurity=False).hexdigest()
        assert fetched.storage_id.value

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "upload_test_sync.txt"
            tmp_path.write_bytes(TEXT_CONTENT)

            contract_path = client_sync.create(
                kind=TESTING_FILE_CONTRACT,
                contract_ref="CONTRACT-CREATE-PATH-SYNC-001",
                description="Test contract from path (sync)",
                circuit=circuit_main_sync,
            )
            contract_path.upload_from_path(path=tmp_path)
            contract_path.save()

            fetched = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract_path.id)
            assert fetched.file_name.value == tmp_path.name
            assert fetched.file_size.value == len(TEXT_CONTENT)
            assert fetched.checksum.value == hashlib.sha1(TEXT_CONTENT, usedforsecurity=False).hexdigest()
            assert fetched.storage_id.value

    def test_update_file_object_with_new_file_sync(
        self, client_sync: InfrahubClientSync, load_file_object_schema_sync: None, circuit_main_sync: InfrahubNodeSync
    ) -> None:
        """Test updating a FileObject node with a new file (sync)."""
        contract = client_sync.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-UPDATE-SYNC-001",
            description="Initial contract sync",
            circuit=circuit_main_sync,
        )
        contract.upload_from_bytes(content=PDF_MAGIC_BYTES, name="initial_sync.pdf")
        contract.save()

        contract_to_update = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        contract_to_update.description.value = "Updated contract sync"
        contract_to_update.upload_from_bytes(content=PNG_MAGIC_BYTES, name="updated_sync.png")
        contract_to_update.save()

        updated = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        assert updated.description.value == "Updated contract sync"
        assert updated.file_name.value == "updated_sync.png"
        assert updated.storage_id.value != contract.storage_id.value
        assert updated.checksum.value != contract.checksum.value

    def test_upsert_file_object_update_sync(
        self, client_sync: InfrahubClientSync, load_file_object_schema_sync: None, circuit_main_sync: InfrahubNodeSync
    ) -> None:
        """Test upserting an existing FileObject node updates it rather than creating a duplicate (sync)."""
        contract = client_sync.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-UPSERT-SYNC-001",
            description="Original sync",
            circuit=circuit_main_sync,
        )
        contract.upload_from_bytes(content=PDF_MAGIC_BYTES, name="original_sync.pdf")
        contract.save()

        contract_upsert = client_sync.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-UPSERT-SYNC-001",
            description="Upserted update sync",
            circuit=circuit_main_sync,
        )
        contract_upsert.upload_from_bytes(content=PNG_MAGIC_BYTES, name="upserted_sync.png")
        contract_upsert.save(allow_upsert=True)
        assert contract_upsert.id == contract.id

        updated = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        assert updated.description.value == "Upserted update sync"
        assert updated.file_name.value == "upserted_sync.png"
        assert updated.storage_id.value != contract.storage_id.value

    def test_download_file_sync(
        self, client_sync: InfrahubClientSync, load_file_object_schema_sync: None, circuit_main_sync: InfrahubNodeSync
    ) -> None:
        """Test downloading files to memory and to disk (sync)."""
        contract = client_sync.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-DOWNLOAD-SYNC-001",
            description="Download test sync",
            circuit=circuit_main_sync,
        )
        contract.upload_from_bytes(content=TEXT_CONTENT, name="download_sync.txt")
        contract.save()

        fetched = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        downloaded_content = fetched.download_file()
        assert downloaded_content == TEXT_CONTENT

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_path = Path(tmpdir) / "downloaded_sync.txt"
            bytes_written = fetched.download_file(dest=dest_path)
            assert bytes_written == len(TEXT_CONTENT)
            assert dest_path.read_bytes() == TEXT_CONTENT

    def test_update_without_file_change_sync(
        self, client_sync: InfrahubClientSync, load_file_object_schema_sync: None, circuit_main_sync: InfrahubNodeSync
    ) -> None:
        """Test updating FileObject attributes without replacing the file (sync)."""
        contract = client_sync.create(
            kind=TESTING_FILE_CONTRACT,
            contract_ref="CONTRACT-META-SYNC-001",
            description="Original description sync",
            circuit=circuit_main_sync,
        )
        contract.upload_from_bytes(content=TEXT_CONTENT, name="unchanged_sync.txt")
        contract.save()

        contract_to_update = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract.id, populate_store=False)
        contract_to_update.description.value = "Updated description sync"
        contract_to_update.save()

        updated = client_sync.get(kind=TESTING_FILE_CONTRACT, id=contract.id)
        assert updated.description.value == "Updated description sync"
        assert updated.storage_id.value == contract_to_update.storage_id.value
        assert updated.checksum.value == contract_to_update.checksum.value

    def test_query_contracts_through_circuit_relationship_sync(
        self, client_sync: InfrahubClientSync, load_file_object_schema_sync: None, circuit_main_sync: InfrahubNodeSync
    ) -> None:
        """Test that FileObject contracts can be queried through their circuit relationship (sync)."""
        for i in range(2):
            contract = client_sync.create(
                kind=TESTING_FILE_CONTRACT, contract_ref=f"CONTRACT-REL-SYNC-{i:03d}", circuit=circuit_main_sync
            )
            contract.upload_from_bytes(content=TEXT_CONTENT, name=f"contract_sync_{i}.txt")
            contract.save()

        circuit = client_sync.get(kind=TESTING_CIRCUIT, id=circuit_main_sync.id, include=["contracts"])
        contracts: RelationshipManagerSync = circuit.contracts
        contract_refs = {contract.peer.contract_ref.value for contract in contracts}

        assert len(contract_refs) >= 2
        assert "CONTRACT-REL-SYNC-000" in contract_refs
        assert "CONTRACT-REL-SYNC-001" in contract_refs
