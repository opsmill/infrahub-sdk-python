from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class Error(Exception):
    def __init__(self, message: str | None = None) -> None:
        self.message = message
        super().__init__(self.message)


@dataclass(frozen=True)
class GraphQLErrorDetail:
    """Structured view of a single entry from a GraphQL response's `errors` array.

    `code`, `http_status` and `data` come from the error catalogue extensions
    that the Infrahub server attaches to each error (`extensions.code`,
    `extensions.http_status`, `extensions.data`). They are `None` when the
    server did not provide them.

    The raw `locations` field is intentionally not exposed here; the unparsed
    entry remains available through the exception's `errors` attribute.
    """

    message: str | None = None
    code: str | None = None
    http_status: int | None = None
    data: dict[str, Any] | None = None
    path: list[str | int] | None = None


def _parse_graphql_error_details(errors: Any) -> list[GraphQLErrorDetail]:
    entries = errors if isinstance(errors, list) else [errors]
    details: list[GraphQLErrorDetail] = []
    for entry in entries:
        if isinstance(entry, dict):
            extensions = entry.get("extensions")
            if not isinstance(extensions, dict):
                extensions = {}
            message = entry.get("message")
            code = extensions.get("code")
            http_status = extensions.get("http_status")
            data = extensions.get("data")
            path = entry.get("path")
            details.append(
                GraphQLErrorDetail(
                    message=str(message) if message is not None else None,
                    code=code if isinstance(code, str) else None,
                    http_status=http_status if isinstance(http_status, int) else None,
                    data=data if isinstance(data, dict) else None,
                    path=path if isinstance(path, list) else None,
                )
            )
        elif entry is not None:
            details.append(GraphQLErrorDetail(message=str(entry)))
    return details


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


class GraphQLError(Error):
    """Raised when a GraphQL response contains entries in its `errors` array.

    The exception message only carries the server-provided error messages; the
    executed query and its variables stay available on the `query` and
    `variables` attributes so they never leak into logs or tracebacks by
    default. Catalogue metadata attached by the server is exposed through
    `details` and `codes`.
    """

    def __init__(self, errors: list[dict[str, Any]], query: str | None = None, variables: dict | None = None) -> None:
        self.query = query
        self.variables = variables
        self.errors = errors
        self.details = _parse_graphql_error_details(errors)
        detail_messages = "; ".join(detail.message for detail in self.details if detail.message)
        self.message = "An error occurred while executing the GraphQL Query"
        if detail_messages:
            self.message += f": {detail_messages}"
        super().__init__(self.message)

    @property
    def codes(self) -> list[str]:
        """Return the catalogue error codes reported by the server, one per error that carried one."""
        return [detail.code for detail in self.details if detail.code]


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


class AuthenticationError(Error):
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
