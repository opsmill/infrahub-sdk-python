import pytest
from pathlib import Path
from infrahub_sdk import InfrahubClient
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.protocols import CoreGenericRepository
from infrahub_sdk.testing.repository import GitRepo


class TestInfrahub(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    def infrahub_version(self) -> str:
        """Required to define the version of infrahub to use."""
        return "1.1.8"

    @pytest.mark.asyncio
    async def test_load_schema(
        self, default_branch: str, client: InfrahubClient, schemas
    ):
        await client.schema.wait_until_converged(branch=default_branch)

        resp = await client.schema.load(
            schemas=schemas, branch=default_branch, wait_until_converged=True
        )
        assert resp.errors == {}
