from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.ctl.client import initialize_client, initialize_client_sync
from infrahub_sdk.repository import GitRepoManager
from tests.helpers.utils import change_directory

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class BranchCase:
    name: str
    branch: str | None
    expected_branch: str


BRANCH_CASES = [
    BranchCase(name="requested-branch-wins", branch="test", expected_branch="test"),
    BranchCase(name="no-branch-uses-git", branch=None, expected_branch="git-branch"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in BRANCH_CASES])
def test_initialize_client_branch_with_branch_from_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: BranchCase
) -> None:
    GitRepoManager(root_directory=str(tmp_path), branch="git-branch")
    monkeypatch.setenv("INFRAHUB_DEFAULT_BRANCH_FROM_GIT", "true")

    with change_directory(str(tmp_path)):
        assert initialize_client(branch=case.branch).default_branch == case.expected_branch
        assert initialize_client_sync(branch=case.branch).default_branch == case.expected_branch
