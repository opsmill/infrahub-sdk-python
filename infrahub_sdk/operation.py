from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import InfrahubClient
    from .node import InfrahubNode
    from .store import NodeStore


class InfrahubOperation:
    def __init__(
        self,
        client: InfrahubClient,
        infrahub_node: type[InfrahubNode],
        convert_query_response: bool,
        branch: str,
        root_directory: str,
    ) -> None:
        # The client default already honours the `default_branch_from_git` config flag.
        self.branch = branch or client.default_branch
        self.convert_query_response = convert_query_response
        self.root_directory = root_directory or str(pathlib.Path.cwd())
        self.infrahub_node = infrahub_node
        self._nodes: list[InfrahubNode] = []
        self._related_nodes: list[InfrahubNode] = []
        self._init_client = client.clone(branch=self.branch)

    @property
    def branch_name(self) -> str:
        """Return the name of the Infrahub branch this operation targets."""
        return self.branch

    @property
    def store(self) -> NodeStore:
        """The store will be populated with nodes based on the query during the collection of data if activated."""
        return self._init_client.store

    @property
    def nodes(self) -> list[InfrahubNode]:
        """Returns nodes collected and parsed during the data collection process if this feature is enabled."""
        return self._nodes

    @property
    def related_nodes(self) -> list[InfrahubNode]:
        """Returns nodes collected and parsed during the data collection process if this feature is enabled."""
        return self._related_nodes

    async def process_nodes(self, data: dict) -> None:
        if not self.convert_query_response:
            return

        await self._init_client.schema.all(branch=self.branch_name)

        for kind, kind_data in data.items():
            if kind in self._init_client.schema.cache[self.branch_name].nodes:
                for result in kind_data.get("edges", []):
                    node = await self.infrahub_node.from_graphql(
                        client=self._init_client, branch=self.branch_name, data=result
                    )
                    self._nodes.append(node)
                    await node._process_relationships(
                        node_data=result, branch=self.branch_name, related_nodes=self._related_nodes, recursive=True
                    )

        for node in self._nodes + self._related_nodes:
            if node.id:
                self._init_client.store.set(node=node)
