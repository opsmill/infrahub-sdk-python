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
    """Information about the originator of the check."""

    proposed_change_id: str = Field(
        default="", description="If available the ID of the proposed change that requested the check"
    )


class InfrahubCheck:
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
        if self._client:
            return self._client

        raise UninitializedError(message="This check has not been initialized with a client")

    @client.setter
    def client(self, value: InfrahubClient) -> None:
        self._client = value

    @classmethod
    async def init(cls, client: InfrahubClient | None = None, *args: Any, **kwargs: Any) -> InfrahubCheck:
        """Async init method, If an existing InfrahubClient client hasn't been provided, one will be created automatically."""
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
        return [log for log in self.logs if log["level"] == "ERROR"]

    def _write_log_entry(
        self, message: str, level: str, object_id: str | None = None, object_type: str | None = None
    ) -> None:
        log_message = {"level": level, "message": message, "branch": self.branch_name}
        if object_id:
            log_message["object_id"] = object_id
        if object_type:
            log_message["object_type"] = object_type
        self.logs.append(log_message)

        if self.output == "stdout":
            print(ujson.dumps(log_message))

    def log_error(self, message: str, object_id: str | None = None, object_type: str | None = None) -> None:
        self._write_log_entry(message=message, level="ERROR", object_id=object_id, object_type=object_type)

    def log_info(self, message: str, object_id: str | None = None, object_type: str | None = None) -> None:
        self._write_log_entry(message=message, level="INFO", object_id=object_id, object_type=object_type)

    @property
    def log_entries(self) -> str:
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
        """Code to validate the status of this check."""

    async def collect_data(self) -> dict:
        """Query the result of the GraphQL Query defined in self.query and return the result"""

        return await self.client.query_gql_query(name=self.query, branch_name=self.branch_name, variables=self.params)

    async def run(self, data: dict | None = None) -> bool:
        """Execute the check after collecting the data from the GraphQL query.
        The result of the check is determined based on the presence or not of ERROR log messages."""

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
