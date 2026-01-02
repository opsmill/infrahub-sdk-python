from __future__ import annotations

from typing import TYPE_CHECKING

from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.repository import GitRepo
from infrahub_sdk.utils import get_fixtures_dir

if TYPE_CHECKING:
    from pathlib import Path

    from infrahub_sdk import InfrahubClient


class TestInfrahubRepository(TestInfrahubDockerClient):
    async def test_add_repository(self, client: InfrahubClient, remote_repos_dir: Path) -> None:
        src_directory = get_fixtures_dir() / "integration/mock_repo"
        repo = GitRepo(name="mock_repo", src_directory=src_directory, dst_directory=remote_repos_dir)
        commit = repo._repo.git[repo._repo.git.head()]
        assert len(list(repo._repo.git.get_walker())) == 1
        assert commit.message.decode("utf-8") == "First commit"

        response = await repo.add_to_infrahub(client=client)
        assert response.get(f"{repo.type.value}Create", {}).get("ok")

        repos = await client.all(kind=repo.type)
        assert repos
