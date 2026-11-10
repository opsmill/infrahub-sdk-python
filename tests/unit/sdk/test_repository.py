import stat
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from dulwich.objects import Commit
from dulwich.repo import Repo

from infrahub_sdk.repository import GitRepoManager
from infrahub_sdk.testing.repository import GitRepo
from infrahub_sdk.utils import get_fixtures_dir


@pytest.fixture
def temp_dir() -> Generator[str]:
    """Fixture to create a temporary directory for testing.

    Yields:
        str: Path to the temporary directory.
    """
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


def test_initialize_repo_uses_existing_repo_in_worktree(temp_dir: str) -> None:
    """A git worktree has a `.git` file (gitlink), not a directory.

    GitRepoManager must open the existing repo via the gitlink instead of trying
    to re-initialize one, which would crash on `mkdir` because the file already exists.
    """
    main_path = Path(temp_dir) / "main"
    worktree_path = Path(temp_dir) / "worktree"
    main_path.mkdir()
    worktree_path.mkdir()
    Repo.init(str(main_path), default_branch=b"main")
    (worktree_path / ".git").write_text(f"gitdir: {main_path}/.git\n")

    manager = GitRepoManager(str(worktree_path))

    assert manager.git is not None
    assert isinstance(manager.git, Repo)
    assert (worktree_path / ".git").is_file()


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
    assert isinstance(commit, Commit)
    assert commit.message.decode("utf-8") == "First commit"


def _private_source(temp_dir: str) -> Path:
    """A source directory that only its owner can access, as pytest's `tmp_path` creates them."""
    source = Path(temp_dir) / "source"
    source.mkdir(mode=0o700)
    (source / ".infrahub.yml").write_text("---\n", encoding="utf-8")
    (source / "script.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (source / "script.sh").chmod(0o700)
    return source


def _permissions(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_gitrepo_keeps_the_permissions_of_the_source_by_default(temp_dir: str) -> None:
    destination = Path(temp_dir) / "remotes"
    repo = GitRepo(name="private", src_directory=_private_source(temp_dir), dst_directory=destination)

    assert _permissions(destination / "private") == 0o700
    with pytest.raises(KeyError):
        repo.repo.git.get_config().get((b"core",), b"sharedRepository")


def test_gitrepo_shared_gives_every_user_read_and_write_access(temp_dir: str) -> None:
    destination = Path(temp_dir) / "remotes"
    repo = GitRepo(name="shared", src_directory=_private_source(temp_dir), dst_directory=destination, shared=True)
    root = destination / "shared"

    assert repo.repo.git.get_config().get((b"core",), b"sharedRepository") == b"0666"
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        if path.is_dir():
            assert _permissions(path) == 0o777, path
        else:
            assert _permissions(path) & 0o666 == 0o666, path
    assert _permissions(root / "script.sh") == 0o777
    assert _permissions(root / ".infrahub.yml") == 0o666
