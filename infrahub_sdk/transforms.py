from __future__ import annotations

import asyncio
import importlib
import os
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from git import Repo

from .exceptions import InfrahubTransformNotFoundError, UninitializedError

if TYPE_CHECKING:
    from pathlib import Path

    from . import InfrahubClient
    from .schema import InfrahubPythonTransformConfig

INFRAHUB_TRANSFORM_VARIABLE_TO_IMPORT = "INFRAHUB_TRANSFORMS"


class InfrahubTransform:
    name: Optional[str] = None
    query: str
    timeout: int = 10

    def __init__(
        self,
        branch: str = "",
        root_directory: str = "",
        server_url: str = "",
        client: Optional[InfrahubClient] = None,
    ):
        self.git: Repo

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
            self.git = Repo(self.root_directory)

        self.branch = str(self.git.active_branch)

        return self.branch

    @abstractmethod
    def transform(self, data: dict) -> Any:
        pass

    async def collect_data(self) -> dict:
        """Query the result of the GraphQL Query defined in self.query and return the result"""

        return await self.client.query_gql_query(name=self.query, branch_name=self.branch_name)

    async def run(self, data: Optional[dict] = None) -> Any:
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


def get_transform_class_instance(
    transform_config: InfrahubPythonTransformConfig,
    search_path: Optional[Path] = None,
    branch: str = "",
    client: Optional[InfrahubClient] = None,
) -> InfrahubTransform:
    """Gets an instance of the InfrahubTransform class.

    Args:
        transform_config: A config object with information required to find and load the transform.
        search_path: The path in which to search for a python file containing the transform. The current directory is
            assumed if not speicifed.
        branch: Infrahub branch which will be targeted in graphql query used to acquire data for transformation.
        client: InfrahubClient used to interact with infrahub API.
    """
    if transform_config.file_path.is_absolute() or search_path is None:
        search_location = transform_config.file_path
    else:
        search_location = search_path / transform_config.file_path

    try:
        spec = importlib.util.spec_from_file_location(transform_config.class_name, search_location)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        # Get the specified class from the module
        transform_class = getattr(module, transform_config.class_name)

        # Create an instance of the class
        transform_instance = transform_class(branch=branch, client=client)

    except (FileNotFoundError, AttributeError) as exc:
        raise InfrahubTransformNotFoundError(name=transform_config.name) from exc

    return transform_instance
