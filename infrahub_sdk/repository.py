from __future__ import annotations

from pathlib import Path

from dulwich.objects import Tree
from dulwich.repo import Repo


class GitRepoManager:
    def __init__(self, root_directory: str, branch: str = "main"):
        self.root_directory = root_directory
        self.git: Repo | None = None
        self.branch = branch

        self.initialize_repo()

    def initialize_repo(self) -> None:
        # Check if the directory already has a repository

        root_path = Path(self.root_directory)

        if root_path.exists() and (root_path / ".git").is_dir():
            self.git = Repo(self.root_directory)  # Open existing repo
        else:
            self.git = Repo.init(self.root_directory, default_branch=self.branch.encode("utf-8"))
            self.create_initial_commit()
        # Ensure the repository is valid
        if not self.git:
            raise ValueError("Failed to initialize or open a repository.")

    def create_initial_commit(self) -> None:
        if not self.git:
            raise ValueError("Git repository not initialized.")

        """Create an initial commit if no commits exist."""
        # Create an empty tree object
        tree = Tree()
        self.git.object_store.add_object(tree)

        # Create the initial commit without an index (use empty tree)
        author = committer = b"Initial Commit <no-reply@example.com>"
        commit_msg = b"Initial commit"

        ref = f"refs/heads/{self.branch}".encode()

        self.git.do_commit(author=author, committer=committer, message=commit_msg, ref=ref)

        # Set HEAD reference to point to the main branch
        self.git.refs.set_symbolic_ref(b"HEAD", ref)

    @property
    def active_branch(self) -> str | None:
        """Get the name of the current active branch."""
        if not self.git:
            raise ValueError("Repository is not initialized.")

        # Read the symbolic reference of HEAD to get the current commit SHA
        head_ref = self.git.refs[b"HEAD"]
        if head_ref:
            commit_sha = head_ref.decode("utf-8")  # Commit SHA from HEAD
            # Now look for the branch that points to this commit SHA
            for ref in self.git.refs.as_dict().keys():
                if ref.startswith(b"refs/heads/"):
                    branch_ref = ref.decode("utf-8")
                    # Check if this branch points to the same commit SHA
                    if self.git.refs[ref] == commit_sha.encode("utf-8"):
                        return branch_ref.split("/")[-1]
            return None  # If no matching branch is found
        raise ValueError("No HEAD reference found, cannot determine active branch.")
