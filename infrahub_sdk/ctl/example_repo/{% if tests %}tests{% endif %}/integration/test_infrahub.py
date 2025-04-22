from pathlib import Path

import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.protocols import CoreGenericRepository
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.repository import GitRepo


class TestInfrahub(TestInfrahubDockerClient):
    @pytest.mark.asyncio
    async def test_load_schema(self, default_branch: str, client: InfrahubClient, schemas: list[dict]):
        await client.schema.wait_until_converged(branch=default_branch)

        resp = await client.schema.load(schemas=schemas, branch=default_branch, wait_until_converged=True)
        assert resp.errors == {}

    @pytest.mark.asyncio
    async def test_load_repository(
        self,
        client: InfrahubClient,
        remote_repos_dir: Path,
        root_directory: Path,
    ) -> None:
        """Add the local directory as a repository in Infrahub and wait for the import to be complete"""

        repo = GitRepo(
            name="local-repository",
            src_directory=root_directory,
            dst_directory=remote_repos_dir,
        )
        await repo.add_to_infrahub(client=client)
        in_sync = await repo.wait_for_sync_to_complete(client=client)
        assert in_sync

        repos = await client.all(kind=CoreGenericRepository)

        # A breakpoint can be added to pause the tests from running and keep the test containers active
        # breakpoint()

        assert repos
