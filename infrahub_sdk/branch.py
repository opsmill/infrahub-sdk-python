from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Literal, overload
from urllib.parse import urlencode

from pydantic import BaseModel

from .exceptions import BranchNotFoundError
from .graphql import Mutation, Query
from .utils import decode_json

if TYPE_CHECKING:
    from .client import InfrahubClient, InfrahubClientSync


class BranchData(BaseModel):
    """Represents data associated with a branch."""
    id: str
    name: str
    description: str | None = None
    sync_with_git: bool
    is_default: bool
    has_schema_changes: bool
    origin_branch: str | None = None
    branched_from: str


BRANCH_DATA = {
    "id": None,
    "name": None,
    "description": None,
    "origin_branch": None,
    "branched_from": None,
    "is_default": None,
    "sync_with_git": None,
    "has_schema_changes": None,
}

BRANCH_DATA_FILTER = {"@filters": {"name": "$branch_name"}}


MUTATION_QUERY_DATA = {"ok": None, "object": BRANCH_DATA}
MUTATION_QUERY_TASK = {"ok": None, "task": {"id": None}}

QUERY_ALL_BRANCHES_DATA = {"Branch": BRANCH_DATA}

QUERY_ONE_BRANCH_DATA = {"Branch": {**BRANCH_DATA, **BRANCH_DATA_FILTER}}


class InfraHubBranchManagerBase:
    """Base class for branch management operations."""
    @classmethod
    def generate_diff_data_url(
        cls,
        client: InfrahubClient | InfrahubClientSync,
        branch_name: str,
        branch_only: bool = True,
        time_from: str | None = None,
        time_to: str | None = None,
    ) -> str:
        """Generates the URL for the diff_data function.

        Args:
            client: The Infrahub client (either sync or async).
            branch_name: The name of the branch.
            branch_only: Whether to include only branch data in the diff. Defaults to True.
            time_from: The start time for the diff (ISO 8601 format).
            time_to: The end time for the diff (ISO 8601 format).

        Returns:
            The generated URL string.
        """
        url = f"{client.address}/api/diff/data"
        url_params = {}
        url_params["branch"] = branch_name
        url_params["branch_only"] = str(branch_only).lower()
        if time_from:
            url_params["time_from"] = time_from
        if time_to:
            url_params["time_to"] = time_to

        return url + urlencode(url_params)


class InfrahubBranchManager(InfraHubBranchManagerBase):
    """Manages branches in Infrahub (asynchronous operations)."""
    def __init__(self, client: InfrahubClient):
        """Initializes the asynchronous branch manager.

        Args:
            client: An instance of InfrahubClient.
        """
        self.client = client

    @overload
    async def create(
        self,
        branch_name: str,
        sync_with_git: bool = True,
        description: str = "",
        wait_until_completion: Literal[True] = True,
        background_execution: bool | None = False,
    ) -> BranchData: ...

    @overload
    async def create(
        self,
        branch_name: str,
        sync_with_git: bool = True,
        description: str = "",
        wait_until_completion: Literal[False] = False,
        background_execution: bool | None = False,
    ) -> str: ...

    async def create(
        self,
        branch_name: str,
        sync_with_git: bool = True,
        description: str = "",
        wait_until_completion: bool = True,
        background_execution: bool | None = False,
    ) -> BranchData | str:
        """Creates a new branch.

        Args:
            branch_name: The name for the new branch.
            sync_with_git: Whether to synchronize the branch with Git. Defaults to True.
            description: An optional description for the branch.
            wait_until_completion: If True (default), waits for the branch creation to complete
                                   and returns BranchData. If False, returns a task ID string.
            background_execution: Deprecated. Use `wait_until_completion=False` instead.

        Returns:
            BranchData if `wait_until_completion` is True, otherwise a task ID string.
        """
        if background_execution is not None:
            warnings.warn(
                "`background_execution` is deprecated, please use `wait_until_completion` instead.",
                DeprecationWarning,
                stacklevel=1,
            )

        background_execution = background_execution or not wait_until_completion
        input_data = {
            # Should be switched to `wait_until_completion` once `background_execution` is removed server side.
            "background_execution": background_execution,
            "data": {
                "name": branch_name,
                "description": description,
                "sync_with_git": sync_with_git,
            },
        }

        mutation_query = MUTATION_QUERY_TASK if background_execution else MUTATION_QUERY_DATA
        query = Mutation(mutation="BranchCreate", input_data=input_data, query=mutation_query)
        response = await self.client.execute_graphql(query=query.render(), tracker="mutation-branch-create")

        # Make sure server version is recent enough to support background execution, as previously
        # using background_execution=True had no effect.
        if background_execution and "task" in response["BranchCreate"]:
            return response["BranchCreate"]["task"]["id"]
        return BranchData(**response["BranchCreate"]["object"])

    async def delete(self, branch_name: str) -> bool:
        """Deletes a branch.

        Args:
            branch_name: The name of the branch to delete.

        Returns:
            True if the deletion was successful, False otherwise.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }
        query = Mutation(mutation="BranchDelete", input_data=input_data, query={"ok": None})
        response = await self.client.execute_graphql(query=query.render(), tracker="mutation-branch-delete")
        return response["BranchDelete"]["ok"]

    async def rebase(self, branch_name: str) -> BranchData:
        """Rebases a branch onto its origin branch.

        Args:
            branch_name: The name of the branch to rebase.

        Returns:
            BranchData for the rebased branch.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }
        query = Mutation(mutation="BranchRebase", input_data=input_data, query=MUTATION_QUERY_DATA)
        response = await self.client.execute_graphql(query=query.render(), tracker="mutation-branch-rebase")
        return response["BranchRebase"]["ok"]

    async def validate(self, branch_name: str) -> BranchData:
        """Validates a branch.

        Args:
            branch_name: The name of the branch to validate.

        Returns:
            True if the branch validation was successful, False otherwise.
            Actually returns BranchData from the response, but the 'ok' field indicates success.
            The return type should ideally be `bool` or a more specific validation result type.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }

        query_data = {
            "ok": None,
            "messages": None,
            "object": {
                "id": None,
                "name": None,
            },
        }

        query = Mutation(mutation="BranchValidate", input_data=input_data, query=query_data)
        response = await self.client.execute_graphql(query=query.render(), tracker="mutation-branch-validate")

        return response["BranchValidate"]["ok"]

    async def merge(self, branch_name: str) -> bool:
        """Merges a branch into its origin branch.

        Args:
            branch_name: The name of the branch to merge.

        Returns:
            True if the merge was successful, False otherwise.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }
        query = Mutation(mutation="BranchMerge", input_data=input_data, query=MUTATION_QUERY_DATA)
        response = await self.client.execute_graphql(
            query=query.render(), tracker="mutation-branch-merge", timeout=max(120, self.client.default_timeout)
        )

        return response["BranchMerge"]["ok"]

    async def all(self) -> dict[str, BranchData]:
        """Retrieves all branches.

        Returns:
            A dictionary mapping branch names to BranchData objects.
        """
        query = Query(name="GetAllBranch", query=QUERY_ALL_BRANCHES_DATA)
        data = await self.client.execute_graphql(query=query.render(), tracker="query-branch-all")

        branches = {branch["name"]: BranchData(**branch) for branch in data["Branch"]}

        return branches

    async def get(self, branch_name: str) -> BranchData:
        """Retrieves a specific branch by name.

        Args:
            branch_name: The name of the branch to retrieve.

        Returns:
            BranchData for the specified branch.

        Raises:
            BranchNotFoundError: If the branch with the given name is not found.
        """
        query = Query(name="GetBranch", query=QUERY_ONE_BRANCH_DATA, variables={"branch_name": str})
        data = await self.client.execute_graphql(
            query=query.render(),
            variables={"branch_name": branch_name},
            tracker="query-branch",
        )

        if not data["Branch"]:
            raise BranchNotFoundError(identifier=branch_name)
        return BranchData(**data["Branch"][0])

    async def diff_data(
        self,
        branch_name: str,
        branch_only: bool = True,
        time_from: str | None = None,
        time_to: str | None = None,
    ) -> dict[Any, Any]:
        """Retrieves the data differences for a branch.

        This typically involves changes made on the branch compared to its origin.

        Args:
            branch_name: The name of the branch.
            branch_only: Whether to include only branch data in the diff. Defaults to True.
            time_from: The start time for the diff (ISO 8601 format).
            time_to: The end time for the diff (ISO 8601 format).

        Returns:
            A dictionary representing the diff data.
        """
        url = self.generate_diff_data_url(
            client=self.client,
            branch_name=branch_name,
            branch_only=branch_only,
            time_from=time_from,
            time_to=time_to,
        )
        response = await self.client._get(url=url, headers=self.client.headers)
        return decode_json(response=response)


class InfrahubBranchManagerSync(InfraHubBranchManagerBase):
    """Manages branches in Infrahub (synchronous operations)."""
    def __init__(self, client: InfrahubClientSync):
        """Initializes the synchronous branch manager.

        Args:
            client: An instance of InfrahubClientSync.
        """
        self.client = client

    def all(self) -> dict[str, BranchData]:
        """Retrieves all branches.

        Returns:
            A dictionary mapping branch names to BranchData objects.
        """
        query = Query(name="GetAllBranch", query=QUERY_ALL_BRANCHES_DATA)
        data = self.client.execute_graphql(query=query.render(), tracker="query-branch-all")

        branches = {branch["name"]: BranchData(**branch) for branch in data["Branch"]}

        return branches

    def get(self, branch_name: str) -> BranchData:
        """Retrieves a specific branch by name.

        Args:
            branch_name: The name of the branch to retrieve.

        Returns:
            BranchData for the specified branch.

        Raises:
            BranchNotFoundError: If the branch with the given name is not found.
        """
        query = Query(name="GetBranch", query=QUERY_ONE_BRANCH_DATA, variables={"branch_name": str})
        data = self.client.execute_graphql(
            query=query.render(),
            variables={"branch_name": branch_name},
            tracker="query-branch",
        )

        if not data["Branch"]:
            raise BranchNotFoundError(identifier=branch_name)
        return BranchData(**data["Branch"][0])

    @overload
    def create(
        self,
        branch_name: str,
        sync_with_git: bool = True,
        description: str = "",
        wait_until_completion: Literal[True] = True,
        background_execution: bool | None = False,
    ) -> BranchData: ...

    @overload
    def create(
        self,
        branch_name: str,
        sync_with_git: bool = True,
        description: str = "",
        wait_until_completion: Literal[False] = False,
        background_execution: bool | None = False,
    ) -> str: ...

    def create(
        self,
        branch_name: str,
        sync_with_git: bool = True,
        description: str = "",
        wait_until_completion: bool = True,
        background_execution: bool | None = False,
    ) -> BranchData | str:
        """Creates a new branch.

        Args:
            branch_name: The name for the new branch.
            sync_with_git: Whether to synchronize the branch with Git. Defaults to True.
            description: An optional description for the branch.
            wait_until_completion: If True (default), waits for the branch creation to complete
                                   and returns BranchData. If False, returns a task ID string.
            background_execution: Deprecated. Use `wait_until_completion=False` instead.

        Returns:
            BranchData if `wait_until_completion` is True, otherwise a task ID string.
        """
        if background_execution is not None:
            warnings.warn(
                "`background_execution` is deprecated, please use `wait_until_completion` instead.",
                DeprecationWarning,
                stacklevel=1,
            )

        background_execution = background_execution or not wait_until_completion
        input_data = {
            # Should be switched to `wait_until_completion` once `background_execution` is removed server side.
            "background_execution": background_execution,
            "data": {
                "name": branch_name,
                "description": description,
                "sync_with_git": sync_with_git,
            },
        }

        query = Mutation(mutation="BranchCreate", input_data=input_data, query=MUTATION_QUERY_DATA)
        response = self.client.execute_graphql(query=query.render(), tracker="mutation-branch-create")

        # Make sure server version is recent enough to support background execution, as previously
        # using background_execution=True had no effect.
        if background_execution and "task" in response["BranchCreate"]:
            return BranchData(**response["BranchCreate"]["task"]["id"])
        return BranchData(**response["BranchCreate"]["object"])

    def delete(self, branch_name: str) -> bool:
        """Deletes a branch.

        Args:
            branch_name: The name of the branch to delete.

        Returns:
            True if the deletion was successful, False otherwise.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }
        query = Mutation(mutation="BranchDelete", input_data=input_data, query={"ok": None})
        response = self.client.execute_graphql(query=query.render(), tracker="mutation-branch-delete")
        return response["BranchDelete"]["ok"]

    def diff_data(
        self,
        branch_name: str,
        branch_only: bool = True,
        time_from: str | None = None,
        time_to: str | None = None,
    ) -> dict[Any, Any]:
        """Retrieves the data differences for a branch.

        This typically involves changes made on the branch compared to its origin.

        Args:
            branch_name: The name of the branch.
            branch_only: Whether to include only branch data in the diff. Defaults to True.
            time_from: The start time for the diff (ISO 8601 format).
            time_to: The end time for the diff (ISO 8601 format).

        Returns:
            A dictionary representing the diff data.
        """
        url = self.generate_diff_data_url(
            client=self.client,
            branch_name=branch_name,
            branch_only=branch_only,
            time_from=time_from,
            time_to=time_to,
        )
        response = self.client._get(url=url, headers=self.client.headers)
        return decode_json(response=response)

    def merge(self, branch_name: str) -> bool:
        """Merges a branch into its origin branch.

        Args:
            branch_name: The name of the branch to merge.

        Returns:
            True if the merge was successful, False otherwise.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }
        query = Mutation(mutation="BranchMerge", input_data=input_data, query=MUTATION_QUERY_DATA)
        response = self.client.execute_graphql(query=query.render(), tracker="mutation-branch-merge")

        return response["BranchMerge"]["ok"]

    def rebase(self, branch_name: str) -> BranchData:
        """Rebases a branch onto its origin branch.

        Args:
            branch_name: The name of the branch to rebase.

        Returns:
            BranchData for the rebased branch.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }
        query = Mutation(mutation="BranchRebase", input_data=input_data, query=MUTATION_QUERY_DATA)
        response = self.client.execute_graphql(query=query.render(), tracker="mutation-branch-rebase")
        return response["BranchRebase"]["ok"]

    def validate(self, branch_name: str) -> BranchData:
        """Validates a branch.

        Args:
            branch_name: The name of the branch to validate.

        Returns:
            True if the branch validation was successful, False otherwise.
            Actually returns BranchData from the response, but the 'ok' field indicates success.
            The return type should ideally be `bool` or a more specific validation result type.
        """
        input_data = {
            "data": {
                "name": branch_name,
            }
        }

        query_data = {
            "ok": None,
            "messages": None,
            "object": {
                "id": None,
                "name": None,
            },
        }

        query = Mutation(mutation="BranchValidate", input_data=input_data, query=query_data)
        response = self.client.execute_graphql(query=query.render(), tracker="mutation-branch-validate")

        return response["BranchValidate"]["ok"]
