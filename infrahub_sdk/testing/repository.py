from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from dulwich import porcelain

from infrahub_sdk.graphql import Mutation
from infrahub_sdk.protocols import CoreGenericRepository
from infrahub_sdk.repository import GitRepoManager

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient


# NOTE we shouldn't duplicate this, need to figure out a better solution
class RepositorySyncStatus(str, Enum):
    UNKNOWN = "unknown"
    IN_SYNC = "in-sync"
    ERROR_IMPORT = "error-import"
    SYNCING = "syncing"


class GitRepoType(str, Enum):
    INTEGRATED = "CoreRepository"
    READ_ONLY = "CoreReadOnlyRepository"


@dataclass
class GitRepo:
    name: str
    src_directory: Path
    dst_directory: Path

    type: GitRepoType = GitRepoType.INTEGRATED

    _repo: GitRepoManager | None = None
    initial_branch: str = "main"
    directories_to_ignore: list[str] = field(default_factory=list)
    remote_directory_name: str = "/remote"
    _branches: list[str] = field(default_factory=list)

    @property
    def repo(self) -> GitRepoManager:
        if self._repo:
            return self._repo
        raise ValueError("Repo hasn't been initialized yet")

    def __post_init__(self) -> None:
        self.init()

    @property
    def path(self) -> str:
        return str(self.src_directory / self.name)

    def init(self) -> None:
        shutil.copytree(
            src=self.src_directory,
            dst=self.dst_directory / self.name,
            ignore=shutil.ignore_patterns(".git"),
        )

        self._repo = GitRepoManager(str(Path(self.dst_directory / self.name)), branch=self.initial_branch)

        files = list(
            porcelain.get_untracked_paths(self._repo.git.path, self._repo.git.path, self._repo.git.open_index())
        )
        files_to_add = [str(Path(self._repo.git.path) / t) for t in files]
        if files_to_add:
            porcelain.add(repo=self._repo.git.path, paths=files_to_add)
            porcelain.commit(repo=self._repo.git.path, message="First commit")
            porcelain.checkout_branch(self._repo.git, self.initial_branch.encode("utf-8"))

    async def add_to_infrahub(self, client: InfrahubClient, branch: str | None = None) -> dict:
        input_data = {
            "data": {
                "name": {"value": self.name},
                "location": {"value": f"{self.remote_directory_name}/{self.name}"},
            },
        }

        query = Mutation(
            mutation=f"{self.type.value}Create",
            input_data=input_data,
            query={"ok": None},
        )

        return await client.execute_graphql(
            query=query.render(), branch_name=branch or self.initial_branch, tracker="mutation-repository-create"
        )

    async def wait_for_sync_to_complete(
        self, client: InfrahubClient, branch: str | None = None, interval: int = 5, retries: int = 6
    ) -> bool:
        for _ in range(retries):
            repo = await client.get(
                kind=CoreGenericRepository,  # type: ignore[type-abstract]
                name__value=self.name,
                branch=branch or self.initial_branch,
            )
            status = repo.sync_status.value
            if status == RepositorySyncStatus.IN_SYNC.value:
                return True
            if status == RepositorySyncStatus.ERROR_IMPORT.value:
                return False

            await asyncio.sleep(interval)

        return False
