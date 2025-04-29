from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .repository import GitRepoManager

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
    ):
        self.branch = branch
        self.convert_query_response = convert_query_response
        self.root_directory = root_directory or os.getcwd()
        self.infrahub_node = infrahub_node
        self._nodes: list[InfrahubNode] = []
        self._related_nodes: list[InfrahubNode] = []
        self._init_client = client.clone(branch=self.branch_name)
        self.git: GitRepoManager | None = None

    @property
    def branch_name(self) -> str:
        """Return the name of the current git branch."""

        if self.branch:
            return self.branch

        if not hasattr(self, "git") or not self.git:
            self.git = GitRepoManager(self.root_directory)

        self.branch = str(self.git.active_branch)

        return self.branch

    @property
    def store(self) -> NodeStore:
        """The store will be populated with nodes based on the query during the collection of data if activated"""
        return self._init_client.store

    @property
    def nodes(self) -> list[InfrahubNode]:
        """Returns nodes collected and parsed during the data collection process if this feature is enabled"""
        return self._nodes

    @property
    def related_nodes(self) -> list[InfrahubNode]:
        """Returns nodes collected and parsed during the data collection process if this feature is enabled"""
        return self._related_nodes

    async def process_nodes(self, data: dict) -> None:
        if not self.convert_query_response:
            return

        await self._init_client.schema.all(branch=self.branch_name)

        for kind in data:
            if kind in self._init_client.schema.cache[self.branch_name].nodes.keys():
                for result in data[kind].get("edges", []):
                    node = await self.infrahub_node.from_graphql(
                        client=self._init_client, branch=self.branch_name, data=result
                    )
                    self._nodes.append(node)
                    await node._process_relationships(
                        node_data=result, branch=self.branch_name, related_nodes=self._related_nodes
                    )

        for node in self._nodes + self._related_nodes:
            if node.id:
                self._init_client.store.set(node=node)
