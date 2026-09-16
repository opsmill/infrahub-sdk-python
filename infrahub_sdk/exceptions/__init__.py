"""The supported import path for every SDK exception.

The class list below is written out rather than star-imported, so reading this file tells you what
the package exports. It has to be kept in step with `base.__all__` by hand; the tests in
`tests/unit/sdk/test_exceptions_public_names.py` fail if the two drift apart, or if a class defined
in `base` is left out of either.

`__all__` is what `import *` hands a caller: the exception classes and nothing else. Without it the
wildcard also carries the `base` and `factory` submodule names, which are an artefact of the layout.
The raise-time factories and `code_names_the_failure` stay importable by name, since what an end user
catches is the classes. Nothing else is re-exported: a name here is a stability promise, so it earns
its place by having a caller rather than by being plausibly useful one day.

Those three are imported below as `X as X`, which is not a typo. The alias is what marks a name as
re-exported rather than merely imported, and is the spelling ruff's F401 accepts for an import
nothing in this file uses; a plain `from .base import X` for a name outside `__all__` fails the lint.
One statement each is isort's doing, which splits aliased imports apart unless `combine-as-imports`
is set.
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
from .factory import authentication_error_from_response as authentication_error_from_response
from .factory import graphql_error_from_response as graphql_error_from_response

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
