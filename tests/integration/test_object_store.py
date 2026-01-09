from __future__ import annotations

from typing import TYPE_CHECKING

from infrahub_sdk.testing.docker import TestInfrahubDockerClient

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient

FILE_CONTENT_01 = """
    any content
    another content
    """


class TestObjectStore(TestInfrahubDockerClient):
    async def test_upload_and_get(self, client: InfrahubClient) -> None:
        response = await client.object_store.upload(content=FILE_CONTENT_01)

        assert sorted(response.keys()) == ["checksum", "identifier"]
        assert response["checksum"] == "aa19b96860ec59a73906dd8660bb3bad"
        assert response["identifier"]

        content = await client.object_store.get(identifier=response["identifier"])
        assert content == FILE_CONTENT_01
