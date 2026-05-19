from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.branch import (
    BranchData,
    BranchStatus,
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


@pytest.mark.parametrize(
    "status_value",
    ["OPEN", "NEED_REBASE", "NEED_UPGRADE_REBASE", "DELETING", "MERGING", "MERGED"],
)
def test_branch_data_accepts_all_server_statuses(status_value: str) -> None:
    branch = BranchData.model_validate(
        {
            "id": "01J0",
            "name": "test",
            "sync_with_git": False,
            "is_default": False,
            "has_schema_changes": False,
            "status": status_value,
            "branched_from": "2026-01-01T00:00:00Z",
        }
    )
    assert branch.status is BranchStatus(status_value)


@pytest.mark.parametrize("client_type", client_types)
async def test_get_branches(clients: BothClients, mock_branches_list_query: HTTPXMock, client_type: str) -> None:
    if client_type == "standard":
        branches = await clients.standard.branch.all()
    else:
        branches = clients.sync.branch.all()

    assert len(branches) == 2
    assert isinstance(branches["main"], BranchData)
