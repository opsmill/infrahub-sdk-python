from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "ApiError",
    "AuthenticationError",
    "BranchNotFoundError",
    "CircularFragmentError",
    "DuplicateFragmentError",
    "Error",
    "FeatureNotSupportedError",
    "FileNotValidError",
    "FragmentFileNotFoundError",
    "FragmentNotFoundError",
    "GraphQLError",
    "GraphQLQueryError",
    "InfrahubCheckNotFoundError",
    "InfrahubTransformNotFoundError",
    "InvalidResponseError",
    "JsonDecodeError",
    "ModuleImportError",
    "NodeInvalidError",
    "NodeNotFoundError",
    "NodeNotSavedError",
    "ObjectValidationError",
    "QuerySyntaxError",
    "RateLimitError",
    "RepositoryFileNotFoundError",
    "ResourceNotDefinedError",
    "SchemaNotFoundError",
    "ServerNotReachableError",
    "ServerNotResponsiveError",
    "TimestampFormatError",
    "URLNotFoundError",
    "UninitializedError",
    "ValidationError",
    "VersionNotSupportedError",
]


class Error(Exception):
    def __init__(self, message: str | None = None) -> None:
        self.message = message
        super().__init__(self.message)


class JsonDecodeError(Error):
    def __init__(self, message: str | None = None, content: str | None = None, url: str | None = None) -> None:
        self.message = message
        self.content = content
        self.url = url
        if not self.message and self.url:
            self.message = f"Unable to decode response as JSON data from {self.url}"
            if self.content:
                self.message += f". Server response: {self.content}"
        super().__init__(self.message)


class RateLimitError(Error):
    """Raised when a request keeps receiving HTTP 429 past the configured retry budget."""

    def __init__(
        self,
        url: str,
        attempts: int,
        retry_after: float | None = None,
        message: str | None = None,
    ) -> None:
        self.url = url
        self.attempts = attempts
        self.retry_after = retry_after
        if message is None:
            message = f"Request to {url} was rate-limited (HTTP 429) after {attempts} attempt(s)."
        super().__init__(message)


class ServerNotReachableError(Error):
    def __init__(self, address: str, message: str | None = None) -> None:
        self.address = address
        self.message = message or f"Unable to connect to '{address}'."
        super().__init__(self.message)


class ServerNotResponsiveError(Error):
    def __init__(self, url: str, timeout: int | None = None, message: str | None = None) -> None:
        self.url = url
        self.timeout = timeout
        self.message = message or f"Unable to read from '{url}'."
        if timeout:
            self.message += f" (timeout: {timeout} sec)"
        super().__init__(self.message)


def as_error_list(errors: Any) -> list[dict[str, Any]]:
    """The subset of a server's `errors` payload that matches the declared shape.

    Anything else keeps its text in the exception message, so the attribute can stay a list of dicts
    and a caller iterating it never has to guard.
    """
    if not isinstance(errors, list):
        return []
    return [error for error in errors if isinstance(error, dict)]


class ApiError(Error):
    """Base for a server-reported failure carrying the parsed response envelope.

    Not every failure the server reports is an ApiError. The ones raised from a status code alone,
    such as URLNotFoundError and RateLimitError, have no envelope to carry and stay under Error.

    The defaults guarantee the attributes exist even on an instance no factory ever touched.
    """

    code: str | None = None
    http_status: int | None = None
    extensions: dict[str, Any] | None = None
    errors: Sequence[dict[str, Any]] = ()


class GraphQLError(ApiError):
    query: str | None = None
    variables: dict | None = None

    def __init__(
        self,
        errors: list[dict[str, Any]],
        query: str | None = None,
        variables: dict | None = None,
    ) -> None:
        self.query = query
        self.variables = variables
        # The message keeps the payload verbatim so a shape we cannot read still reaches the reader.
        self.message = f"An error occurred while executing the GraphQL Query {query}, {errors}"
        self.errors = as_error_list(errors)
        super().__init__(self.message)


class VersionNotSupportedError(Error):
    """Raised when a feature is used against an Infrahub server version that does not support it."""

    def __init__(self, feature: str, required_version: str) -> None:
        self.feature = feature
        self.required_version = required_version
        self.message = f"{feature} requires Infrahub {required_version} or later."
        super().__init__(self.message)


class BranchNotFoundError(Error):
    def __init__(self, identifier: str, message: str | None = None) -> None:
        self.identifier = identifier
        self.message = message or f"Unable to find the branch '{identifier}' in the Database."
        super().__init__(self.message)


class SchemaNotFoundError(Error):
    def __init__(self, identifier: str, message: str | None = None) -> None:
        self.identifier = identifier
        self.message = message or f"Unable to find the schema '{identifier}'."
        super().__init__(self.message)


class ModuleImportError(Error):
    def __init__(self, message: str | None = None) -> None:
        self.message = message or "Unable to import the module"
        super().__init__(self.message)


class NodeNotFoundError(Error):
    def __init__(
        self,
        identifier: Mapping[str, list[str]],
        message: str = "Unable to find the node in the database.",
        branch_name: str | None = None,
        node_type: str | None = None,
    ) -> None:
        self.node_type = node_type or "unknown"
        self.identifier = identifier
        self.branch_name = branch_name

        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"""
        {self.message}
        {self.branch_name} | {self.node_type} | {self.identifier}
        """


class NodeInvalidError(NodeNotFoundError):
    pass


class NodeNotSavedError(Error):
    """Raised when an operation requires a node that has been saved (has an id) but it has not."""

    def __init__(self, message: str | None = None) -> None:
        self.message = message or "The node has not been saved yet and does not have an id."
        super().__init__(self.message)


class ResourceNotDefinedError(Error):
    """Raised when trying to access a resource that hasn't been defined."""

    def __init__(self, message: str | None = None) -> None:
        self.message = message or "The requested resource was not found"
        super().__init__(self.message)


class InfrahubCheckNotFoundError(Error):
    def __init__(self, name: str, message: str | None = None) -> None:
        self.message = message or f"The requested InfrahubCheck '{name}' was not found."
        super().__init__(self.message)


class InfrahubTransformNotFoundError(Error):
    def __init__(self, name: str, message: str | None = None) -> None:
        self.message = message or f"The requested InfrahubTransform '{name}' was not found."
        super().__init__(self.message)


class ValidationError(Error):
    def __init__(self, identifier: str, message: str | None = None, messages: list[str] | None = None) -> None:
        self.identifier = identifier
        self.message = message
        self.messages = messages
        if not messages and not message:
            self.message = f"Validation Error for {self.identifier}"
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.messages:
            return f"{self.identifier}: {', '.join(self.messages)}"
        return f"{self.identifier}: {self.message}"


class ObjectValidationError(Error):
    def __init__(self, position: list[int | str], message: str) -> None:
        self.position = position
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{'.'.join(str(p) for p in self.position)}: {self.message}"


class AuthenticationError(ApiError):
    def __init__(self, message: str | None = None) -> None:
        self.message = message or "Authentication Error, unable to execute the query."
        super().__init__(self.message)


class URLNotFoundError(Error):
    def __init__(self, url: str) -> None:
        self.message = f"`{url}` not found."
        super().__init__(self.message)


class FeatureNotSupportedError(Error):
    """Raised when trying to use a method on a node that doesn't support it."""


class UninitializedError(Error):
    """Raised when an object requires an initialization step before use."""


class InvalidResponseError(Error):
    """Raised when an object requires an initialization step before use."""


class RepositoryFileNotFoundError(Error):
    def __init__(self, file_path: str, message: str | None = None) -> None:
        self.file_path = file_path
        self.message = message or f"File '{file_path}' does not exist."
        super().__init__(self.message)


class FileNotValidError(Error):
    def __init__(self, name: str, message: str = "") -> None:
        self.message = message or f"Cannot parse '{name}' content."
        super().__init__(self.message)


class TimestampFormatError(Error):
    def __init__(self, message: str | None = None) -> None:
        self.message = message or "Invalid timestamp format"
        super().__init__(self.message)


class GraphQLQueryError(Error):
    """Base class for errors raised during GraphQL query rendering (fragment resolution)."""


class QuerySyntaxError(GraphQLQueryError):
    def __init__(self, syntax_error: str) -> None:
        self.message = f"GraphQL syntax error: {syntax_error}"
        super().__init__(self.message)


class FragmentNotFoundError(GraphQLQueryError):
    def __init__(self, fragment_name: str, query_file: str | None = None, message: str | None = None) -> None:
        self.fragment_name = fragment_name
        self.query_file = query_file
        if message:
            self.message = message
        elif query_file:
            self.message = f"Fragment '{fragment_name}' not found (referenced in '{query_file}')."
        else:
            self.message = f"Fragment '{fragment_name}' not found."
        super().__init__(self.message)


class DuplicateFragmentError(GraphQLQueryError):
    def __init__(self, fragment_name: str, message: str | None = None) -> None:
        self.fragment_name = fragment_name
        self.message = (
            message or f"Fragment '{fragment_name}' is defined more than once across declared fragment files."
        )
        super().__init__(self.message)


class CircularFragmentError(GraphQLQueryError):
    def __init__(self, cycle: list[str], message: str | None = None) -> None:
        self.cycle = cycle
        self.message = message or f"Circular fragment dependency detected: {' -> '.join(cycle)}."
        super().__init__(self.message)


class FragmentFileNotFoundError(GraphQLQueryError):
    def __init__(self, file_path: str, message: str | None = None) -> None:
        self.file_path = file_path
        self.message = message or f"Fragment file '{file_path}' declared in graphql_fragments does not exist."
        super().__init__(self.message)
