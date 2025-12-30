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
