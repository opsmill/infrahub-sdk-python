from __future__ import annotations

import asyncio
import os
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from infrahub_sdk.repository import GitRepoManager

from .exceptions import UninitializedError

if TYPE_CHECKING:
    from . import InfrahubClient

INFRAHUB_TRANSFORM_VARIABLE_TO_IMPORT = "INFRAHUB_TRANSFORMS"


class InfrahubTransform:
    name: str | None = None
    query: str
    timeout: int = 10

    def __init__(
        self,
        branch: str = "",
        root_directory: str = "",
        server_url: str = "",
        client: InfrahubClient | None = None,
    ):
        self.git: GitRepoManager

        self.branch = branch
        self.server_url = server_url or os.environ.get("INFRAHUB_URL", "http://127.0.0.1:8000")
        self.root_directory = root_directory or os.getcwd()

        self._client = client

        if not self.name:
            self.name = self.__class__.__name__

        if not self.query:
            raise ValueError("A query must be provided")

    @property
    def client(self) -> InfrahubClient:
        if self._client:
            return self._client

        raise UninitializedError("The client has not been initialized")

    @property
    def branch_name(self) -> str:
        """Return the name of the current git branch."""

        if self.branch:
            return self.branch

        if not hasattr(self, "git") or not self.git:
            self.git = GitRepoManager(self.root_directory)

        self.branch = str(self.git.active_branch)

        return self.branch

    @abstractmethod
    def transform(self, data: dict) -> Any:
        pass

    async def collect_data(self) -> dict:
        """Query the result of the GraphQL Query defined in self.query and return the result"""

        return await self.client.query_gql_query(name=self.query, branch_name=self.branch_name)

    async def run(self, data: dict | None = None) -> Any:
        """Execute the transformation after collecting the data from the GraphQL query.

        The result of the check is determined based on the presence or not of ERROR log messages.

        Args:
            data: The data on which to run the transform. Data will be queried from the API if not provided

        Returns: Transformed data
        """

        if not data:
            data = await self.collect_data()

        unpacked = data.get("data") or data

        if asyncio.iscoroutinefunction(self.transform):
            return await self.transform(data=unpacked)

        return self.transform(data=unpacked)
