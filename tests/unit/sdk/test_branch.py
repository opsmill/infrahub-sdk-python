from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.branch import (
    BranchData,
    InfrahubBranchManager,
    InfrahubBranchManagerSync,
)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

async_branch_methods = [method for method in dir(InfrahubBranchManager) if not method.startswith("_")]
sync_branch_methods = [method for method in dir(InfrahubBranchManagerSync) if not method.startswith("_")]

client_types = ["standard", "sync"]


def test_method_sanity() -> None:
    """Validate that there is at least one public method and that both clients look the same."""
    assert async_branch_methods
    assert async_branch_methods == sync_branch_methods


@pytest.mark.parametrize("method", async_branch_methods)
def test_validate_method_signature(method: str) -> None:
    async_method = getattr(InfrahubBranchManager, method)
    sync_method = getattr(InfrahubBranchManagerSync, method)
    async_sig = inspect.signature(async_method)
    sync_sig = inspect.signature(sync_method)
    assert async_sig.parameters == sync_sig.parameters
    assert async_sig.return_annotation == sync_sig.return_annotation


@pytest.mark.parametrize("client_type", client_types)
async def test_get_branches(clients: BothClients, mock_branches_list_query: HTTPXMock, client_type: str) -> None:
    if client_type == "standard":
        branches = await clients.standard.branch.all()
    else:
        branches = clients.sync.branch.all()

    assert len(branches) == 2
    assert isinstance(branches["main"], BranchData)


@pytest.mark.parametrize("client_type", client_types)
async def test_branch_validate_query_excludes_removed_fields(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    """validate() must only request fields the BranchValidate mutation still exposes.

    The server removed the `messages` field from BranchValidate, so the rendered
    mutation must not request it, otherwise the server rejects the whole query.
    """
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BranchValidate": {"ok": True}}},
        match_headers={"X-Infrahub-Tracker": "mutation-branch-validate"},
    )

    if client_type == "standard":
        result = await clients.standard.branch.validate(branch_name="branch01")
    else:
        result = clients.sync.branch.validate(branch_name="branch01")

    assert result is True

    post_requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(post_requests) == 1
    assert b"messages" not in post_requests[0].content


@pytest.mark.parametrize("client_type", client_types)
async def test_branch_merge_enforces_minimum_timeout(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    """Both clients must apply the 120s minimum timeout floor when merging a branch.

    The default client timeout is 60s, so a correct merge sends max(120, 60) == 120.
    """
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BranchMerge": {"ok": True}}},
        match_headers={"X-Infrahub-Tracker": "mutation-branch-merge"},
    )

    if client_type == "standard":
        await clients.standard.branch.merge(branch_name="branch01")
    else:
        clients.sync.branch.merge(branch_name="branch01")

    post_requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(post_requests) == 1
    assert post_requests[0].extensions["timeout"]["read"] == 120
