from __future__ import annotations

import os
import subprocess  # noqa: S404
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from invoke import Context, Exit

import tasks

if TYPE_CHECKING:
    from pytest import MonkeyPatch

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
    "PATH": os.environ.get("PATH", ""),
    "HOME": os.environ.get("HOME", ""),
}


def _git(repo: Path, *args: str) -> None:
    """Run a git command inside *repo* with deterministic author info."""
    subprocess.check_call(["git", *args], cwd=repo, env={**_GIT_ENV, "HOME": str(repo)})  # noqa: S603, S607


@pytest.fixture
def git_repo_with_docs(tmp_path: Path) -> Path:
    """Create a temporary git repo with a committed docs/ directory."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "generated.mdx").write_text("# Original content\n")

    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


class TestDocsValidate:
    """Ensure docs_validate() detects drift between committed and regenerated documentation."""

    def test_passes_when_generation_produces_no_changes(
        self, git_repo_with_docs: Path, monkeypatch: MonkeyPatch
    ) -> None:
        # Arrange
        monkeypatch.setattr(tasks, "docs_generate", lambda context: None)  # noqa: ARG005
        monkeypatch.setattr(tasks, "DOCUMENTATION_DIRECTORY", git_repo_with_docs)

        # Act / Assert — no exception means docs are in sync
        tasks.docs_validate(Context())

    def test_fails_when_generation_modifies_existing_file(
        self, git_repo_with_docs: Path, monkeypatch: MonkeyPatch
    ) -> None:
        # Arrange
        def fake_generate(context: Context) -> None:
            (git_repo_with_docs / "docs" / "generated.mdx").write_text("# Modified content\n")

        monkeypatch.setattr(tasks, "docs_generate", fake_generate)
        monkeypatch.setattr(tasks, "DOCUMENTATION_DIRECTORY", git_repo_with_docs)

        # Act / Assert
        with pytest.raises(Exit, match="out of sync"):
            tasks.docs_validate(Context())

    def test_fails_when_generation_deletes_tracked_file(
        self, git_repo_with_docs: Path, monkeypatch: MonkeyPatch
    ) -> None:
        # Arrange
        def fake_generate(context: Context) -> None:
            (git_repo_with_docs / "docs" / "generated.mdx").unlink()

        monkeypatch.setattr(tasks, "docs_generate", fake_generate)
        monkeypatch.setattr(tasks, "DOCUMENTATION_DIRECTORY", git_repo_with_docs)

        # Act / Assert
        with pytest.raises(Exit, match="Modified or deleted files"):
            tasks.docs_validate(Context())

    def test_fails_when_generation_creates_new_file(self, git_repo_with_docs: Path, monkeypatch: MonkeyPatch) -> None:
        # Arrange
        def fake_generate(context: Context) -> None:
            (git_repo_with_docs / "docs" / "new_file.mdx").write_text("# New\n")

        monkeypatch.setattr(tasks, "docs_generate", fake_generate)
        monkeypatch.setattr(tasks, "DOCUMENTATION_DIRECTORY", git_repo_with_docs)

        # Act / Assert
        with pytest.raises(Exit, match="New untracked files"):
            tasks.docs_validate(Context())
