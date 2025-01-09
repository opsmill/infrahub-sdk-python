from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.repository import GitRepo
from infrahub_sdk.utils import get_fixtures_dir

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient


class TestInfrahubRepository(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    def infrahub_version(self) -> str:
        return "1.1.0"

    async def test_add_repository(self, client: InfrahubClient, remote_repos_dir, infrahub_compose):
        src_directory = get_fixtures_dir() / "integration/mock_repo"
        repo = GitRepo(name="mock_repo", src_directory=src_directory, dst_directory=remote_repos_dir)
        print()
        print(infrahub_compose._run_command(cmd=["ls", "-la", str(remote_repos_dir)]))
        print()
        print(infrahub_compose.get_config())
        print()
        print(infrahub_compose.get_logs("task-worker"))
        print()
        # print(infrahub_compose._run_command(cmd="echo $INFRAHUB_TESTING_LOCAL_REMOTE_GIT_DIRECTORY"))
        print(infrahub_compose.exec_in_container(["ls", "-la", "/remote"], "task-worker"))
        commit = repo._repo.git[repo._repo.git.head()]
        assert len(list(repo._repo.git.get_walker())) == 1
        assert commit.message.decode("utf-8") == "First commit"
        response = await repo.add_to_infrahub(client=client)
        repos = await client.all(kind=repo.type)
        assert response.get(f"{repo.type.value}Create", {}).get("ok")
        assert len(repos) == 1
