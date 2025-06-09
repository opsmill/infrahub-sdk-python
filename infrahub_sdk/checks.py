from __future__ import annotations

import asyncio
import importlib
import os
import warnings
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

import ujson
from pydantic import BaseModel, Field

from infrahub_sdk.repository import GitRepoManager

from .exceptions import UninitializedError

if TYPE_CHECKING:
    from . import InfrahubClient

INFRAHUB_CHECK_VARIABLE_TO_IMPORT = "INFRAHUB_CHECKS"

_client_class = "InfrahubClient"


class InfrahubCheckInitializer(BaseModel):
    """Information about the originator of a check run.

    This data is typically provided by the system initiating the check.
    """

    proposed_change_id: str = Field(
        default="", description="If available the ID of the proposed change that requested the check"
    )


class InfrahubCheck:
    """
    Base class for defining custom checks to be executed against Infrahub data.

    Attributes:
        name: The name of the check. Defaults to the class name.
        query: The GraphQL query string used to fetch data for the check.
        timeout: Timeout in seconds for the check execution.
    """
    name: str | None = None
    query: str = ""
    timeout: int = 10

    def __init__(
        self,
        branch: str | None = None,
        root_directory: str = "",
        output: str | None = None,
        initializer: InfrahubCheckInitializer | None = None,
        params: dict | None = None,
        client: InfrahubClient | None = None,
    ):
        """
        Initializes an InfrahubCheck instance.

        Args:
            branch: The name of the branch to run the check against.
                    If None, it will try to determine the active git branch.
            root_directory: The root directory of the repository. Defaults to the current working directory.
            output: If "stdout", logs will be printed to standard output.
            initializer: Information about the check's originator.
            params: Parameters to be passed as variables to the GraphQL query.
            client: An InfrahubClient instance. If not provided, one might be
                    created later or an UninitializedError will be raised when accessed.
        """
        self.git: GitRepoManager | None = None
        self.initializer = initializer or InfrahubCheckInitializer()

        self.logs: list[dict[str, Any]] = []
        self.passed = False

        self.output = output

        self.branch = branch
        self.params = params or {}

        self.root_directory = root_directory or os.getcwd()

        self._client = client

        if not self.name:
            self.name = self.__class__.__name__

        if not self.query:
            raise ValueError("A query must be provided")

    def __str__(self) -> str:
        return self.__class__.__name__

    @property
    def client(self) -> InfrahubClient:
        """
        The InfrahubClient instance for interacting with the Infrahub API.

        Raises:
            UninitializedError: If the client has not been set.
        """
        if self._client:
            return self._client

        raise UninitializedError(message="This check has not been initialized with a client")

    @client.setter
    def client(self, value: InfrahubClient) -> None:
        """
        Sets the InfrahubClient instance.

        Args:
            value: The InfrahubClient instance.
        """
        self._client = value

    @classmethod
    async def init(cls, client: InfrahubClient | None = None, *args: Any, **kwargs: Any) -> InfrahubCheck:
        """
        Asynchronously initializes an instance of the check.

        If an existing InfrahubClient client hasn't been provided, one will be created automatically.

        Args:
            client: An optional InfrahubClient instance.
            *args: Additional arguments to pass to the check's constructor.
            **kwargs: Additional keyword arguments to pass to the check's constructor.

        Returns:
            An initialized instance of the InfrahubCheck subclass.

        Deprecated:
            This method is deprecated and will be removed in version 2.0.0.
            Instantiate the class directly and manage the client lifecycle separately.
        """
        warnings.warn(
            "InfrahubCheck.init has been deprecated and will be removed in version 2.0.0 of the Infrahub Python SDK",
            DeprecationWarning,
            stacklevel=1,
        )
        if not client:
            client_module = importlib.import_module("infrahub_sdk.client")
            client_class = getattr(client_module, _client_class)
            client = client_class()
        kwargs["client"] = client
        return cls(*args, **kwargs)

    @property
    def errors(self) -> list[dict[str, Any]]:
        """A list of all error log entries recorded by the check."""
        return [log for log in self.logs if log["level"] == "ERROR"]

    def _write_log_entry(
        self, message: str, level: str, object_id: str | None = None, object_type: str | None = None
    ) -> None:
        """
        Writes a structured log entry.

        Args:
            message: The log message.
            level: The log level (e.g., "INFO", "ERROR").
            object_id: Optional ID of the object related to the log entry.
            object_type: Optional type of the object related to the log entry.
        """
        log_message = {"level": level, "message": message, "branch": self.branch_name}
        if object_id:
            log_message["object_id"] = object_id
        if object_type:
            log_message["object_type"] = object_type
        self.logs.append(log_message)

        if self.output == "stdout":
            print(ujson.dumps(log_message))

    def log_error(self, message: str, object_id: str | None = None, object_type: str | None = None) -> None:
        """
        Logs an error message.

        Args:
            message: The error message.
            object_id: Optional ID of the object related to the error.
            object_type: Optional type of the object related to the error.
        """
        self._write_log_entry(message=message, level="ERROR", object_id=object_id, object_type=object_type)

    def log_info(self, message: str, object_id: str | None = None, object_type: str | None = None) -> None:
        """
        Logs an informational message.

        Args:
            message: The informational message.
            object_id: Optional ID of the object related to the message.
            object_type: Optional type of the object related to the message.
        """
        self._write_log_entry(message=message, level="INFO", object_id=object_id, object_type=object_type)

    @property
    def log_entries(self) -> str:
        """A formatted string containing all log entries."""
        output = ""
        for log in self.logs:
            output += "-----------------------\n"
            output += f"Message: {log['message']}\n"
            output += f"Level: {log['level']}\n"
            if "object_id" in log:
                output += f"Object ID: {log['object_id']}\n"
            if "object_type" in log:
                output += f"Object ID: {log['object_type']}\n"
        return output

    @property
    def branch_name(self) -> str:
        """Return the name of the current git branch."""

        if self.branch:
            return self.branch

        if not self.git:
            self.git = GitRepoManager(self.root_directory)

        self.branch = str(self.git.active_branch)
        return self.branch

    @abstractmethod
    def validate(self, data: dict) -> None:
        """
        Abstract method to be implemented by subclasses to perform the actual validation logic.

        This method should use `log_error` to record any validation failures.
        The overall check status (passed/failed) is determined by the presence of error logs.

        Args:
            data: The data fetched by the GraphQL query, to be validated.
        """

    async def collect_data(self) -> dict:
        """
        Queries the Infrahub API using the GraphQL query defined in `self.query`.

        Returns:
            The data returned by the GraphQL query.
        """

        return await self.client.query_gql_query(name=self.query, branch_name=self.branch_name, variables=self.params)

    async def run(self, data: dict | None = None) -> bool:
        """
        Executes the check.

        This involves:
        1. Collecting data using `collect_data()` if not provided.
        2. Running the `validate()` method with the collected data.
        3. Determining the check's success based on whether any errors were logged.

        Args:
            data: Optional pre-fetched data to use for validation. If None,
                  `collect_data()` will be called.

        Returns:
            True if the check passed (no errors logged), False otherwise.
        """

        if not data:
            data = await self.collect_data()
        unpacked = data.get("data") or data

        if asyncio.iscoroutinefunction(self.validate):
            await self.validate(data=unpacked)
        else:
            self.validate(data=unpacked)

        nbr_errors = len([log for log in self.logs if log["level"] == "ERROR"])

        self.passed = bool(nbr_errors == 0)

        if self.passed:
            self.log_info("Check succesfully completed")

        return self.passed
