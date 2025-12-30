import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from dulwich.repo import Repo

from infrahub_sdk.repository import GitRepoManager
from infrahub_sdk.testing.repository import GitRepo
from infrahub_sdk.utils import get_fixtures_dir


@pytest.fixture
def temp_dir() -> Generator[str]:
    """Fixture to create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


def test_initialize_repo_creates_new_repo(temp_dir: str) -> None:
    """Test that a new Git repository is created if none exists."""
    manager = GitRepoManager(root_directory=temp_dir, branch="main")

    # Verify .git directory is created
    assert (Path(temp_dir) / ".git").is_dir()

    # Verify the repository is initialized
    assert manager.git is not None
    assert isinstance(manager.git, Repo)


def test_initialize_repo_uses_existing_repo(temp_dir: str) -> None:
    """Test that the GitRepoManager uses an existing repository without an active branch."""
    # Manually initialize a repo
    Repo.init(temp_dir, default_branch=b"main")

    manager = GitRepoManager(temp_dir)
    assert manager.git is not None
    assert isinstance(manager.git, Repo)
    assert (Path(temp_dir) / ".git").is_dir()


def test_active_branch_returns_correct_branch(temp_dir: str) -> None:
    """Test that the active branch is correctly returned."""
    manager = GitRepoManager(temp_dir, branch="develop")

    # Verify the active branch is "develop"
    assert manager.active_branch == "develop"


def test_initialize_repo_raises_error_on_failure(monkeypatch: pytest.MonkeyPatch, temp_dir: str) -> None:
    """Test that an error is raised if the repository cannot be initialized."""

    def mock_init(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
        return None  # Simulate failure

    monkeypatch.setattr(Repo, "init", mock_init)

    with pytest.raises(ValueError, match=r"Failed to initialize or open a repository\."):
        GitRepoManager(temp_dir)


def test_gitrepo_init(temp_dir: str) -> None:
    src_directory = get_fixtures_dir() / "integration/mock_repo"
    repo = GitRepo(name="mock_repo", src_directory=src_directory, dst_directory=Path(temp_dir))
    assert len(list(repo._repo.git.get_walker())) == 1
    commit = repo._repo.git[repo._repo.git.head()]
    assert commit.message.decode("utf-8") == "First commit"
