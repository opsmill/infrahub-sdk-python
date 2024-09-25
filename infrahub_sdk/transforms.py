from __future__ import annotations

import asyncio
import importlib
import os
import warnings
from abc import abstractmethod
from functools import cached_property
from typing import TYPE_CHECKING, Any, Optional

import httpx
from git import Repo

from infrahub_sdk import InfrahubClient

from .exceptions import InfrahubTransformNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

    from .schema import InfrahubPythonTransformConfig, InfrahubRepositoryConfig

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
        repository_config: Optional[InfrahubRepositoryConfig] = None,
    ):
        self.git: Repo

        self.branch = branch

        self.server_url = server_url or os.environ.get("INFRAHUB_URL", "http://127.0.0.1:8000")
        self.root_directory = root_directory or os.getcwd()
        self.repository_config = repository_config

        self.client: InfrahubClient

        if not self.name:
            self.name = self.__class__.__name__

        if not self.query:
            raise ValueError("A query must be provided")

    @cached_property
    def client(self) -> InfrahubClient:
        return InfrahubClient(address=self.server_url)

    @classmethod
    async def init(cls, client: Optional[InfrahubClient] = None, *args: Any, **kwargs: Any) -> InfrahubTransform:
        """Async init method, If an existing InfrahubClient client hasn't been provided, one will be created automatically."""
        warnings.warn(
            "InfrahubClient.init has been deprecated and will be removed in Infrahub SDK 0.14.0 or the next major version",
            DeprecationWarning,
            stacklevel=1,
        )

        item = cls(*args, **kwargs)

        if client:
            item.client = client

        return item

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

    async def collect_data(self, variables: Optional[dict] = None) -> dict:
        """Query the result of the GraphQL Query defined in self.query and return the result"""

        if not variables:
            variables = {}

        # Try getting data from stored graphql query endpoint
        try:
            return await self.client.query_gql_query(name=self.query, branch_name=self.branch_name, variables=variables)
        # If we run into an error, the stored graphql query may not exist. Try to query the GraphQL API directly instead.
        except httpx.HTTPStatusError:
            if not self.repository_config:
                raise
            query_str = self.repository_config.get_query(name=self.query).load_query()
            return await self.client.execute_graphql(query=query_str, variables=variables, branch_name=self.branch_name)

    async def run(self, data: Optional[dict] = None, variables: Optional[dict] = None) -> Any:
        """Execute the transformation after collecting the data from the GraphQL query.

        The result of the check is determined based on the presence or not of ERROR log messages.

        Args:
            data: The data on which to run the transform. Data will be queried from the API if not provided
            variables: Variables to use in the graphQL query to filter returned data

        Returns: Transformed data
        """

        if not variables:
            variables = {}

        if not data:
            data = await self.collect_data(variables=variables)

        unpacked = data.get("data") or data

        if asyncio.iscoroutinefunction(self.transform):
            return await self.transform(data=unpacked)

        return self.transform(data=unpacked)


def get_transform_class_instance(
    transform_config: InfrahubPythonTransformConfig,
    search_path: Optional[Path] = None,
    branch: str = "",
    repository_config: Optional[InfrahubRepositoryConfig] = None,
) -> InfrahubTransform:
    """Gets an instance of the InfrahubTransform class.

    Args:
        transform_config: A config object with information required to find and load the transform.
        search_path: The path in which to search for a python file containing the transform. The current directory is
            assumed if not speicifed.
        branch: Infrahub branch which will be targeted in graphql query used to acquire data for transformation.
        repository_config: Repository config object. This is dpendency injected into the InfrahubTransform instance
            providing it with the ability to interact with other data in the repository where the transform is defined
            (e.g. a graphql query file).
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
        transform_instance = transform_class(branch=branch, repository_config=repository_config)

    except (FileNotFoundError, AttributeError) as exc:
        raise InfrahubTransformNotFoundError(name=transform_config.name) from exc

    return transform_instance
