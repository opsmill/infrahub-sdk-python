from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from infrahub_sdk import Config, InfrahubClient
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.transforms import InfrahubTransform

if TYPE_CHECKING:
    import pytest


class DummyTransform(InfrahubTransform):
    query = "my_query"

    def transform(self, data: dict) -> dict:
        return data


def _build_transform(client: InfrahubClient, branch: str = "", root_directory: str = "") -> DummyTransform:
    return DummyTransform(client=client, infrahub_node=InfrahubNode, branch=branch, root_directory=root_directory)


def _stub_git_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Git lookup so tests never depend on the state of the local checkout.

    The stub encodes the directory it was asked about, so callers can assert which repository
    the branch was resolved from.
    """

    def fake_get_branch(branch: str | None = None, directory: str = ".") -> str:
        return branch or f"git:{directory}"

    monkeypatch.setattr("infrahub_sdk.config.get_branch", fake_get_branch)


async def test_branch_name_uses_explicit_branch() -> None:
    client = InfrahubClient(config=Config(address="http://mock", default_branch="test"))

    transform = _build_transform(client=client, branch="explicit")

    assert transform.branch_name == "explicit"
    assert transform._init_client.default_branch == "explicit"


async def test_branch_name_falls_back_to_configured_default_branch() -> None:
    """Without an explicit branch, the configured default branch wins over the local Git branch."""
    client = InfrahubClient(config=Config(address="http://mock", default_branch="test"))

    transform = _build_transform(client=client)

    assert transform.branch_name == "test"
    assert transform._init_client.default_branch == "test"


async def test_branch_name_falls_back_to_git_branch_when_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_git_branch(monkeypatch)
    client = InfrahubClient(config=Config(address="http://mock", default_branch="test", default_branch_from_git=True))

    transform = _build_transform(client=client)

    assert transform.branch_name == f"git:{pathlib.Path.cwd()}"


async def test_git_branch_is_read_from_the_root_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_git_branch(monkeypatch)
    client = InfrahubClient(config=Config(address="http://mock", default_branch="test", default_branch_from_git=True))

    transform = _build_transform(client=client, root_directory="/some/repository")

    assert transform.branch_name == "git:/some/repository"
