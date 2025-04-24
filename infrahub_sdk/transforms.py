from __future__ import annotations

import asyncio
import os
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from .operation import InfrahubOperation

if TYPE_CHECKING:
    from . import InfrahubClient
    from .node import InfrahubNode

INFRAHUB_TRANSFORM_VARIABLE_TO_IMPORT = "INFRAHUB_TRANSFORMS"


class InfrahubTransform(InfrahubOperation):
    name: str | None = None
    query: str
    timeout: int = 10

    def __init__(
        self,
        client: InfrahubClient,
        infrahub_node: type[InfrahubNode],
        convert_query_response: bool = False,
        branch: str = "",
        root_directory: str = "",
        server_url: str = "",
    ):
        super().__init__(
            client=client,
            infrahub_node=infrahub_node,
            convert_query_response=convert_query_response,
            branch=branch,
            root_directory=root_directory,
        )

        self.server_url = server_url or os.environ.get("INFRAHUB_URL", "http://127.0.0.1:8000")
        self._client = client

        if not self.name:
            self.name = self.__class__.__name__

        if not self.query:
            raise ValueError("A query must be provided")

    @property
    def client(self) -> InfrahubClient:
        return self._init_client

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
        await self.process_nodes(data=unpacked)

        if asyncio.iscoroutinefunction(self.transform):
            return await self.transform(data=unpacked)

        return self.transform(data=unpacked)
