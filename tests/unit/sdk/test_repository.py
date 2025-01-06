import tempfile
from pathlib import Path

import pytest
from dulwich.repo import Repo

from infrahub_sdk.repository import GitRepoManager


@pytest.fixture
def temp_dir():
    """Fixture to create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


def test_initialize_repo_creates_new_repo(temp_dir):
    """Test that a new Git repository is created if none exists."""
    manager = GitRepoManager(root_directory=temp_dir, branch="main")

    # Verify .git directory is created
    assert (Path(temp_dir) / ".git").is_dir()

    # Verify the repository is initialized
    assert manager.git is not None
    assert isinstance(manager.git, Repo)


def test_initialize_repo_uses_existing_repo(temp_dir):
    """Test that the GitRepoManager uses an existing repository without an active branch."""
    # Manually initialize a repo
    Repo.init(temp_dir)

    with pytest.raises(ValueError, match="Git repository does not have an active branch."):
        manager = GitRepoManager(temp_dir)
        assert manager.git is not None
        assert isinstance(manager.git, Repo)
        assert (Path(temp_dir) / ".git").is_dir()


def test_create_initial_commit(temp_dir):
    """Test that an initial commit is created."""
    manager = GitRepoManager(temp_dir)

    # Verify there is at least one commit
    assert len(list(manager.git.get_walker())) == 1


def test_active_branch_returns_correct_branch(temp_dir):
    """Test that the active branch is correctly returned."""
    manager = GitRepoManager(temp_dir, branch="develop")

    # Verify the active branch is "develop"
    assert manager.active_branch == "develop"


def test_initialize_repo_raises_error_on_failure(monkeypatch, temp_dir):
    """Test that an error is raised if the repository cannot be initialized."""

    def mock_init(*args, **kwargs):  # noqa: ANN002, ANN003
        return None  # Simulate failure

    monkeypatch.setattr(Repo, "init", mock_init)

    with pytest.raises(ValueError, match="Git repository not initialized."):
        GitRepoManager(temp_dir)


def test_active_branch_raises_error_if_repo_not_initialized(temp_dir):
    """Test that accessing the active branch raises an error if the repo is not initialized."""
    manager = GitRepoManager(temp_dir)

    # Manually unset the repository to simulate uninitialized state
    manager.git = None

    with pytest.raises(ValueError, match="Repository is not initialized."):
        _ = manager.active_branch
