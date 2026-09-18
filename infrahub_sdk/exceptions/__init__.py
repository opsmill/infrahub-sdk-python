"""The supported import path for every SDK exception.

The class lists below are written out rather than star-imported, so reading this file tells you what
the package exports. They have to be kept in step by hand with `base.__all__` and with the exception
classes `catalogue` generates; the tests in `tests/unit/sdk/test_exceptions_public_names.py` fail if
they drift apart, or if a class defined in `base` is left out of either.

Only `catalogue`'s exception classes are re-exported. Its payload models, its lookup maps and its
dispatch helper are the factory's business and stay importable from the module itself.

`__all__` is what `import *` hands a caller: the exception classes and nothing else. Without it the
wildcard also carries the `base` and `factory` submodule names, which are an artefact of the layout.
The raise-time factories and `code_names_the_failure` stay importable by name, since what an end user
catches is the classes. Nothing else is re-exported: a name here is a stability promise, so it earns
its place by having a caller rather than by being plausibly useful one day.
"""

from .base import (
    ApiError,
    AuthenticationError,
    BranchNotFoundError,
    CircularFragmentError,
    DuplicateFragmentError,
    Error,
    FeatureNotSupportedError,
    FileNotValidError,
    FragmentFileNotFoundError,
    FragmentNotFoundError,
    GraphQLError,
    GraphQLQueryError,
    InfrahubCheckNotFoundError,
    InfrahubTransformNotFoundError,
    InvalidResponseError,
    JsonDecodeError,
    ModuleImportError,
    NodeInvalidError,
    NodeNotFoundError,
    NodeNotSavedError,
    ObjectValidationError,
    QuerySyntaxError,
    RateLimitError,
    RepositoryFileNotFoundError,
    ResourceNotDefinedError,
    SchemaNotFoundError,
    ServerNotReachableError,
    ServerNotResponsiveError,
    TimestampFormatError,
    UninitializedError,
    URLNotFoundError,
    ValidationError,
    VersionNotSupportedError,
)
from .base import code_names_the_failure as code_names_the_failure
from .catalogue import (
    AttributeConstraintViolationError,
    AttributeInvalidTypeError,
    AttributeRequiredError,
    BranchAlreadyMergedError,
    BranchNeedsRebaseError,
    MergeInProgressError,
    MergeRecoveryRequiredError,
    UndefinedError,
    UniquenessViolationError,
)
from .factory import authentication_error_from_response as authentication_error_from_response
from .factory import graphql_error_from_response as graphql_error_from_response

__all__ = [
    "ApiError",
    "AttributeConstraintViolationError",
    "AttributeInvalidTypeError",
    "AttributeRequiredError",
    "AuthenticationError",
    "BranchAlreadyMergedError",
    "BranchNeedsRebaseError",
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
    "MergeInProgressError",
    "MergeRecoveryRequiredError",
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
    "UndefinedError",
    "UninitializedError",
    "UniquenessViolationError",
    "ValidationError",
    "VersionNotSupportedError",
]
