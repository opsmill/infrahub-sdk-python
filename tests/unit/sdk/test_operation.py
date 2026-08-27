from __future__ import annotations

from infrahub_sdk import Config, InfrahubClient
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.transforms import InfrahubTransform
from infrahub_sdk.utils import get_branch


class DummyTransform(InfrahubTransform):
    query = "my_query"

    def transform(self, data: dict) -> dict:
        return data


def _build_transform(client: InfrahubClient, branch: str = "") -> DummyTransform:
    return DummyTransform(client=client, infrahub_node=InfrahubNode, branch=branch)


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


async def test_branch_name_falls_back_to_git_branch_when_opted_in() -> None:
    client = InfrahubClient(config=Config(address="http://mock", default_branch="test", default_branch_from_git=True))

    transform = _build_transform(client=client)

    assert transform.branch_name == get_branch()
