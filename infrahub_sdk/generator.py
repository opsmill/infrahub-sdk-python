from __future__ import annotations

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING

from .exceptions import UninitializedError
from .operation import InfrahubOperation

if TYPE_CHECKING:
    from .client import InfrahubClient
    from .context import RequestContext
    from .node import InfrahubNode


class InfrahubGenerator(InfrahubOperation):
    """Infrahub Generator class"""

    def __init__(
        self,
        query: str,
        client: InfrahubClient,
        infrahub_node: type[InfrahubNode],
        branch: str = "",
        root_directory: str = "",
        generator_instance: str = "",
        params: dict | None = None,
        convert_query_response: bool = False,
        logger: logging.Logger | None = None,
        request_context: RequestContext | None = None,
    ) -> None:
        self.query = query

        super().__init__(
            client=client,
            infrahub_node=infrahub_node,
            convert_query_response=convert_query_response,
            branch=branch,
            root_directory=root_directory,
        )

        self.params = params or {}
        self.generator_instance = generator_instance
        self._client: InfrahubClient | None = None
        self.logger = logger if logger else logging.getLogger("infrahub.tasks")
        self.request_context = request_context

    @property
    def subscribers(self) -> list[str] | None:
        if self.generator_instance:
            return [self.generator_instance]
        return None

    @property
    def client(self) -> InfrahubClient:
        if self._client:
            return self._client
        raise UninitializedError("The client has not been initialized")

    @client.setter
    def client(self, value: InfrahubClient) -> None:
        self._client = value

    async def collect_data(self) -> dict:
        """Query the result of the GraphQL Query defined in self.query and return the result"""

        data = await self._init_client.query_gql_query(
            name=self.query,
            branch_name=self.branch_name,
            variables=self.params,
            update_group=True,
            subscribers=self.subscribers,
        )
        return data.get("data") or data

    async def run(self, identifier: str, data: dict | None = None) -> None:
        """Execute the generator after collecting the data from the GraphQL query."""

        if not data:
            data = await self.collect_data()
        unpacked = data.get("data") or data
        await self.process_nodes(data=unpacked)

        async with self._init_client.start_tracking(
            identifier=identifier, params=self.params, delete_unused_nodes=True, group_type="CoreGeneratorGroup"
        ) as self.client:
            await self.generate(data=unpacked)

    @abstractmethod
    async def generate(self, data: dict) -> None:
        """Code to run the generator

        Any child class of the InfrahubGenerator us expected to provide this method. The method is expected
        to use the provided InfrahubClient contained in self.client to create or update any nodes in an idempotent
        way as the method could be executed multiple times. Typically this would be done by using:

        await new_or_updated_object.save(allow_upsert=True)

        The tracking system will be responsible for deleting nodes that are no longer required.
        """
