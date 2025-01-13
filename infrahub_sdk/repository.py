from __future__ import annotations

from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo


class GitRepoManager:
    def __init__(self, root_directory: str, branch: str = "main"):
        self.root_directory = root_directory
        self.branch = branch
        self.git: Repo = self.initialize_repo()

    def initialize_repo(self) -> Repo:
        # Check if the directory already has a repository

        root_path = Path(self.root_directory)

        if root_path.exists() and (root_path / ".git").is_dir():
            repo = Repo(self.root_directory)  # Open existing repo
        else:
            repo = Repo.init(self.root_directory, default_branch=self.branch.encode("utf-8"))

        if not repo:
            raise ValueError("Failed to initialize or open a repository.")

        return repo

    @property
    def active_branch(self) -> str | None:
        active_branch = porcelain.active_branch(self.root_directory).decode("utf-8")
        return active_branch
