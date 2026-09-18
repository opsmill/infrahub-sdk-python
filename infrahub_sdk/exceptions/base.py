from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Protocol, TypeGuard

from typing_extensions import Self

# The code the server reports where its own catalogue has no entry for the failure.
UNDEFINED_ERROR_CODE = "UNDEFINED_ERROR"

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


def code_names_the_failure(code: str | None) -> TypeGuard[str]:
    """Whether a catalogue code tells the reader something the server's message does not.

    The server codes every error it reports, falling back to `UNDEFINED_ERROR` wherever its own
    catalogue has no entry, so "carries a code" is not the same question as "was described". That
    fallback names nothing, and letting it displace the query text and the later errors the way a
    described code does would lose detail and gain none. It stays readable on `exc.code` either way.
    """
    return code is not None and code != UNDEFINED_ERROR_CODE


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

    # The catalogue code this class represents, for the classes that adopted one. Optional so that a
    # subclass of an adopted class can clear it rather than inherit a code it does not represent.
    CODE: ClassVar[str | None] = None

    code: str | None = None
    http_status: int | None = None
    extensions: dict[str, Any] | None = None
    errors: Sequence[dict[str, Any]] = ()


def graphql_default_message(query: str | None, errors: Any) -> str:
    """The message the GraphQL path produces where the server described nothing better.

    Lives beside the class rather than inside it because a class built from a payload alone carries
    this text with neither the query nor the errors in it, and the factory has to recognise that and
    fill in the envelope the class never saw.
    """
    return f"An error occurred while executing the GraphQL Query {query}, {errors}"


class GraphQLError(ApiError):
    query: str | None = None
    variables: dict | None = None

    def __init__(
        self,
        errors: list[dict[str, Any]],
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.query = query
        self.variables = variables
        # `is not None` rather than `or`: an empty message is a deliberate one, not a request for
        # the default.
        default = graphql_default_message(query=query, errors=errors)
        self.message = message if message is not None else default
        self.errors = as_error_list(errors)
        super().__init__(self.message)


class VersionNotSupportedError(Error):
    """Raised when a feature is used against an Infrahub server version that does not support it."""

    def __init__(self, feature: str, required_version: str) -> None:
        self.feature = feature
        self.required_version = required_version
        self.message = f"{feature} requires Infrahub {required_version} or later."
        super().__init__(self.message)


class BranchNotFoundPayload(Protocol):
    """The fields a server-reported BRANCH_NOT_FOUND carries."""

    branch_name: str


class BranchNotFoundError(GraphQLError):
    CODE: ClassVar[str | None] = "BRANCH_NOT_FOUND"

    def __init__(self, identifier: str, message: str | None = None) -> None:
        self.identifier = identifier
        super().__init__(
            errors=[],
            query=None,
            variables=None,
            message=message or f"Unable to find the branch '{identifier}' in the Database.",
        )

    @classmethod
    def from_payload(cls, payload: BranchNotFoundPayload) -> Self:
        """Build the exception from the payload a server-reported failure carries.

        The mapping onto `identifier` is hand-written because the attribute predates the catalogue
        and keeps its own name.
        """
        return cls(identifier=payload.branch_name)


class SchemaNotFoundPayload(Protocol):
    """The fields a server-reported SCHEMA_NOT_FOUND carries."""

    kind: str


class SchemaNotFoundError(GraphQLError):
    CODE: ClassVar[str | None] = "SCHEMA_NOT_FOUND"

    def __init__(self, identifier: str, message: str | None = None) -> None:
        self.identifier = identifier
        super().__init__(
            errors=[],
            query=None,
            variables=None,
            message=message or f"Unable to find the schema '{identifier}'.",
        )

    @classmethod
    def from_payload(cls, payload: SchemaNotFoundPayload) -> Self:
        return cls(identifier=payload.kind)


class ModuleImportError(Error):
    def __init__(self, message: str | None = None) -> None:
        self.message = message or "Unable to import the module"
        super().__init__(self.message)


class NodeNotFoundPayload(Protocol):
    """The fields a server-reported NODE_NOT_FOUND carries."""

    node_kind: str
    identifier: str


class NodeNotFoundError(GraphQLError):
    CODE: ClassVar[str | None] = "NODE_NOT_FOUND"

    def __init__(
        self,
        # A plain string is admitted because the file handler names the missing file that way, and
        # the identifier is only ever interpolated into the message.
        identifier: Mapping[str, list[str]] | str,
        message: str = "Unable to find the node in the database.",
        branch_name: str | None = None,
        node_type: str | None = None,
    ) -> None:
        self.node_type = node_type or "unknown"
        self.identifier = identifier
        self.branch_name = branch_name

        super().__init__(errors=[], query=None, variables=None, message=message)

    def __str__(self) -> str:
        return f"""
        {self.message}
        {self.branch_name} | {self.node_type} | {self.identifier}
        """

    @classmethod
    def from_payload(cls, payload: NodeNotFoundPayload) -> Self:
        """`node_kind` lands on `node_type`, the name this class has always used for it."""
        return cls(identifier=payload.identifier, node_type=payload.node_kind)


class NodeInvalidError(NodeNotFoundError):
    """Raised when a node was found but is not of the kind that was asked for.

    That is not a lookup miss, so it claims no catalogue code and clears the one it would otherwise
    inherit. `from_payload` is inherited and unused: nothing dispatches a payload to a class that
    represents no code.
    """

    CODE: ClassVar[str | None] = None


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
