from __future__ import annotations

import asyncio
import os
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
    shared: bool = False
    """Give every user read and write access to the repository, for Infrahub containers that run as another user."""

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
            porcelain.checkout(repo=self._repo.git, target=self.initial_branch)

        if self.shared:
            self._share()

    def _share(self) -> None:
        """Give every user read and write access to the repository, now and to the files Git adds later.

        `core.sharedRepository` makes Git create the files of a later commit or push with the same access.
        The files that exist already, including those copied from `src_directory`, get it here.
        """
        config = self.repo.git.get_config()
        config.set((b"core",), b"sharedRepository", b"0666")
        config.write_to_path()

        root_directory = self.dst_directory / self.name
        root_directory.chmod(0o777)
        for root, directories, files in os.walk(root_directory):
            for directory in directories:
                directory_path = Path(root) / directory
                if not directory_path.is_symlink():
                    directory_path.chmod(0o777)
            for file in files:
                file_path = Path(root) / file
                if file_path.is_symlink():
                    continue
                mode = file_path.stat().st_mode
                file_path.chmod(mode | 0o666 | (0o111 if mode & 0o111 else 0))

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
                kind=CoreGenericRepository,
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
