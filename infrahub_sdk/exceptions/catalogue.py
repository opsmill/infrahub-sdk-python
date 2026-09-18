# Generated from schema/error-catalogue.json in the opsmill/infrahub repository - DO NOT EDIT.
# Catalogue version: 1
# Regenerate there with: uv run invoke backend.generate
#
# Stability: a "stable" code keeps its payload shape; an "evolving" code may still gain fields.
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict
from typing_extensions import Self

from .base import BranchNotFoundError, GraphQLError, NodeNotFoundError, SchemaNotFoundError

__all__ = [
    "CODE_TO_DATA_MODEL",
    "CODE_TO_EXCEPTION",
    "AttributeConstraintViolationData",
    "AttributeConstraintViolationError",
    "AttributeInvalidTypeData",
    "AttributeInvalidTypeError",
    "AttributeRequiredData",
    "AttributeRequiredError",
    "AuthenticationRequiredData",
    "BranchAlreadyMergedData",
    "BranchAlreadyMergedError",
    "BranchNeedsRebaseData",
    "BranchNeedsRebaseError",
    "BranchNotFoundData",
    "MergeInProgressData",
    "MergeInProgressError",
    "MergeRecoveryRequiredData",
    "MergeRecoveryRequiredError",
    "NodeNotFoundData",
    "PermissionDeniedData",
    "SchemaNotFoundData",
    "TokenExpiredData",
    "UndefinedError",
    "UndefinedErrorData",
    "UniquenessViolationData",
    "UniquenessViolationError",
    "exception_from_payload",
]


class AttributeConstraintViolationData(BaseModel):
    """Payload a server-reported ATTRIBUTE_CONSTRAINT_VIOLATION carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    node_kind: str
    field_name: str
    constraint: str
    detail: str | None = None


class AttributeInvalidTypeData(BaseModel):
    """Payload a server-reported ATTRIBUTE_INVALID_TYPE carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    node_kind: str
    field_name: str
    expected_type: str
    received_type: str


class AttributeRequiredData(BaseModel):
    """Payload a server-reported ATTRIBUTE_REQUIRED carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    node_kind: str
    field_name: str


class AuthenticationRequiredData(BaseModel):
    """Payload a server-reported AUTHENTICATION_REQUIRED carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")


class BranchAlreadyMergedData(BaseModel):
    """Payload a server-reported BRANCH_ALREADY_MERGED carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    branch_name: str


class BranchNeedsRebaseData(BaseModel):
    """Payload a server-reported BRANCH_NEEDS_REBASE carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    branch_name: str


class BranchNotFoundData(BaseModel):
    """Payload a server-reported BRANCH_NOT_FOUND carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    branch_name: str


class MergeInProgressData(BaseModel):
    """Payload a server-reported MERGE_IN_PROGRESS carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    branch_name: str
    merging_branch: str


class MergeRecoveryRequiredData(BaseModel):
    """Payload a server-reported MERGE_RECOVERY_REQUIRED carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    branch_name: str
    merging_branch: str


class NodeNotFoundData(BaseModel):
    """Payload a server-reported NODE_NOT_FOUND carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    node_kind: str
    identifier: str


class PermissionDeniedData(BaseModel):
    """Payload a server-reported PERMISSION_DENIED carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    action: str | None = None
    resource_kind: str | None = None


class SchemaNotFoundData(BaseModel):
    """Payload a server-reported SCHEMA_NOT_FOUND carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    kind: str


class TokenExpiredData(BaseModel):
    """Payload a server-reported TOKEN_EXPIRED carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    expired_at: datetime | None = None


class UndefinedErrorData(BaseModel):
    """Payload a server-reported UNDEFINED_ERROR carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")


class UniquenessViolationData(BaseModel):
    """Payload a server-reported UNIQUENESS_VIOLATION carries."""

    # A newer server may add fields this SDK has never heard of; ignoring them keeps the code
    # resolvable rather than failing validation.
    model_config = ConfigDict(extra="ignore")

    node_kind: str
    fields: list[str]


class AttributeConstraintViolationError(GraphQLError):
    """Raised when the server reports ATTRIBUTE_CONSTRAINT_VIOLATION.

    A node attribute value failed a schema-defined constraint (e.g. regex, length, range).

    Stability: evolving.
    """

    CODE: ClassVar[str | None] = "ATTRIBUTE_CONSTRAINT_VIOLATION"
    DATA_MODEL: ClassVar[type[BaseModel]] = AttributeConstraintViolationData

    code: str | None = "ATTRIBUTE_CONSTRAINT_VIOLATION"
    http_status: int | None = 422

    def __init__(
        self,
        *,
        node_kind: str,
        field_name: str,
        constraint: str,
        detail: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.node_kind = node_kind
        self.field_name = field_name
        self.constraint = constraint
        self.detail = detail
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: AttributeConstraintViolationData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(
            node_kind=payload.node_kind,
            field_name=payload.field_name,
            constraint=payload.constraint,
            detail=payload.detail,
        )


class AttributeInvalidTypeError(GraphQLError):
    """Raised when the server reports ATTRIBUTE_INVALID_TYPE.

    A node attribute received a value that does not match its declared type.

    Stability: stable.
    """

    CODE: ClassVar[str | None] = "ATTRIBUTE_INVALID_TYPE"
    DATA_MODEL: ClassVar[type[BaseModel]] = AttributeInvalidTypeData

    code: str | None = "ATTRIBUTE_INVALID_TYPE"
    http_status: int | None = 422

    def __init__(
        self,
        *,
        node_kind: str,
        field_name: str,
        expected_type: str,
        received_type: str,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.node_kind = node_kind
        self.field_name = field_name
        self.expected_type = expected_type
        self.received_type = received_type
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: AttributeInvalidTypeData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(
            node_kind=payload.node_kind,
            field_name=payload.field_name,
            expected_type=payload.expected_type,
            received_type=payload.received_type,
        )


class AttributeRequiredError(GraphQLError):
    """Raised when the server reports ATTRIBUTE_REQUIRED.

    A mandatory node attribute was not provided.

    Stability: stable.
    """

    CODE: ClassVar[str | None] = "ATTRIBUTE_REQUIRED"
    DATA_MODEL: ClassVar[type[BaseModel]] = AttributeRequiredData

    code: str | None = "ATTRIBUTE_REQUIRED"
    http_status: int | None = 422

    def __init__(
        self,
        *,
        node_kind: str,
        field_name: str,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.node_kind = node_kind
        self.field_name = field_name
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: AttributeRequiredData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(node_kind=payload.node_kind, field_name=payload.field_name)


class BranchAlreadyMergedError(GraphQLError):
    """Raised when the server reports BRANCH_ALREADY_MERGED.

    The target branch has been merged and is permanently read-only.

    Stability: stable.
    """

    CODE: ClassVar[str | None] = "BRANCH_ALREADY_MERGED"
    DATA_MODEL: ClassVar[type[BaseModel]] = BranchAlreadyMergedData

    code: str | None = "BRANCH_ALREADY_MERGED"
    http_status: int | None = 400

    def __init__(
        self,
        *,
        branch_name: str,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.branch_name = branch_name
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: BranchAlreadyMergedData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(branch_name=payload.branch_name)


class BranchNeedsRebaseError(GraphQLError):
    """Raised when the server reports BRANCH_NEEDS_REBASE.

    The target branch must be rebased before it accepts new changes.

    Stability: stable.
    """

    CODE: ClassVar[str | None] = "BRANCH_NEEDS_REBASE"
    DATA_MODEL: ClassVar[type[BaseModel]] = BranchNeedsRebaseData

    code: str | None = "BRANCH_NEEDS_REBASE"
    http_status: int | None = 400

    def __init__(
        self,
        *,
        branch_name: str,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.branch_name = branch_name
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: BranchNeedsRebaseData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(branch_name=payload.branch_name)


class MergeInProgressError(GraphQLError):
    """Raised when the server reports MERGE_IN_PROGRESS.

    The write was rejected because a branch merge is in progress. The block is transient; retry once the
    merge completes.

    Stability: evolving.
    """

    CODE: ClassVar[str | None] = "MERGE_IN_PROGRESS"
    DATA_MODEL: ClassVar[type[BaseModel]] = MergeInProgressData

    code: str | None = "MERGE_IN_PROGRESS"
    http_status: int | None = 423

    def __init__(
        self,
        *,
        branch_name: str,
        merging_branch: str,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.branch_name = branch_name
        self.merging_branch = merging_branch
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: MergeInProgressData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(branch_name=payload.branch_name, merging_branch=payload.merging_branch)


class MergeRecoveryRequiredError(GraphQLError):
    """Raised when the server reports MERGE_RECOVERY_REQUIRED.

    The write was rejected because a previous branch merge failed and left the default branch protected.
    Recovery is required: an administrator must run `infrahub recover merge`. Unlike MERGE_IN_PROGRESS
    this is not retryable.

    Stability: evolving.
    """

    CODE: ClassVar[str | None] = "MERGE_RECOVERY_REQUIRED"
    DATA_MODEL: ClassVar[type[BaseModel]] = MergeRecoveryRequiredData

    code: str | None = "MERGE_RECOVERY_REQUIRED"
    http_status: int | None = 423

    def __init__(
        self,
        *,
        branch_name: str,
        merging_branch: str,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.branch_name = branch_name
        self.merging_branch = merging_branch
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: MergeRecoveryRequiredData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(branch_name=payload.branch_name, merging_branch=payload.merging_branch)


class UndefinedError(GraphQLError):
    """Raised when the server reports UNDEFINED_ERROR.

    An error not yet covered by the catalogue. Its occurrence indicates a catalogue gap and should be
    triaged.

    Stability: stable.
    """

    CODE: ClassVar[str | None] = "UNDEFINED_ERROR"
    DATA_MODEL: ClassVar[type[BaseModel]] = UndefinedErrorData

    code: str | None = "UNDEFINED_ERROR"
    http_status: int | None = 500

    def __init__(
        self,
        *,
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: UndefinedErrorData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        del payload
        return cls()


class UniquenessViolationError(GraphQLError):
    """Raised when the server reports UNIQUENESS_VIOLATION.

    The submitted values collide with an existing object on a uniqueness constraint. The constraint members
    may be relationships as well as attributes.

    Stability: evolving.
    """

    CODE: ClassVar[str | None] = "UNIQUENESS_VIOLATION"
    DATA_MODEL: ClassVar[type[BaseModel]] = UniquenessViolationData

    code: str | None = "UNIQUENESS_VIOLATION"
    http_status: int | None = 422

    def __init__(
        self,
        *,
        node_kind: str,
        fields: list[str],
        errors: list[dict[str, Any]] | None = None,
        query: str | None = None,
        variables: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.node_kind = node_kind
        self.fields = fields
        super().__init__(errors=errors or [], query=query, variables=variables, message=message)

    @classmethod
    def from_payload(cls, payload: UniquenessViolationData) -> Self:
        """Build the exception from the validated payload of a server-reported failure."""
        return cls(node_kind=payload.node_kind, fields=payload.fields)


# Codes that map to a dedicated exception class. Authentication and permission codes are absent: the
# SDK raises a generic class for those and carries the code on the instance.
CODE_TO_EXCEPTION: dict[str, type[GraphQLError]] = {
    "ATTRIBUTE_CONSTRAINT_VIOLATION": AttributeConstraintViolationError,
    "ATTRIBUTE_INVALID_TYPE": AttributeInvalidTypeError,
    "ATTRIBUTE_REQUIRED": AttributeRequiredError,
    "BRANCH_ALREADY_MERGED": BranchAlreadyMergedError,
    "BRANCH_NEEDS_REBASE": BranchNeedsRebaseError,
    "BRANCH_NOT_FOUND": BranchNotFoundError,
    "MERGE_IN_PROGRESS": MergeInProgressError,
    "MERGE_RECOVERY_REQUIRED": MergeRecoveryRequiredError,
    "NODE_NOT_FOUND": NodeNotFoundError,
    "SCHEMA_NOT_FOUND": SchemaNotFoundError,
    "UNDEFINED_ERROR": UndefinedError,
    "UNIQUENESS_VIOLATION": UniquenessViolationError,
}

# Every code's payload model, including the codes that get no class, so a caller that observes one
# can still validate what it carries.
CODE_TO_DATA_MODEL: dict[str, type[BaseModel]] = {
    "ATTRIBUTE_CONSTRAINT_VIOLATION": AttributeConstraintViolationData,
    "ATTRIBUTE_INVALID_TYPE": AttributeInvalidTypeData,
    "ATTRIBUTE_REQUIRED": AttributeRequiredData,
    "AUTHENTICATION_REQUIRED": AuthenticationRequiredData,
    "BRANCH_ALREADY_MERGED": BranchAlreadyMergedData,
    "BRANCH_NEEDS_REBASE": BranchNeedsRebaseData,
    "BRANCH_NOT_FOUND": BranchNotFoundData,
    "MERGE_IN_PROGRESS": MergeInProgressData,
    "MERGE_RECOVERY_REQUIRED": MergeRecoveryRequiredData,
    "NODE_NOT_FOUND": NodeNotFoundData,
    "PERMISSION_DENIED": PermissionDeniedData,
    "SCHEMA_NOT_FOUND": SchemaNotFoundData,
    "TOKEN_EXPIRED": TokenExpiredData,
    "UNDEFINED_ERROR": UndefinedErrorData,
    "UNIQUENESS_VIOLATION": UniquenessViolationData,
}


def _build_attribute_constraint_violation(data: Mapping[str, Any]) -> GraphQLError:
    return AttributeConstraintViolationError.from_payload(AttributeConstraintViolationData.model_validate(data))


def _build_attribute_invalid_type(data: Mapping[str, Any]) -> GraphQLError:
    return AttributeInvalidTypeError.from_payload(AttributeInvalidTypeData.model_validate(data))


def _build_attribute_required(data: Mapping[str, Any]) -> GraphQLError:
    return AttributeRequiredError.from_payload(AttributeRequiredData.model_validate(data))


def _build_branch_already_merged(data: Mapping[str, Any]) -> GraphQLError:
    return BranchAlreadyMergedError.from_payload(BranchAlreadyMergedData.model_validate(data))


def _build_branch_needs_rebase(data: Mapping[str, Any]) -> GraphQLError:
    return BranchNeedsRebaseError.from_payload(BranchNeedsRebaseData.model_validate(data))


def _build_branch_not_found(data: Mapping[str, Any]) -> GraphQLError:
    return BranchNotFoundError.from_payload(BranchNotFoundData.model_validate(data))


def _build_merge_in_progress(data: Mapping[str, Any]) -> GraphQLError:
    return MergeInProgressError.from_payload(MergeInProgressData.model_validate(data))


def _build_merge_recovery_required(data: Mapping[str, Any]) -> GraphQLError:
    return MergeRecoveryRequiredError.from_payload(MergeRecoveryRequiredData.model_validate(data))


def _build_node_not_found(data: Mapping[str, Any]) -> GraphQLError:
    return NodeNotFoundError.from_payload(NodeNotFoundData.model_validate(data))


def _build_schema_not_found(data: Mapping[str, Any]) -> GraphQLError:
    return SchemaNotFoundError.from_payload(SchemaNotFoundData.model_validate(data))


def _build_undefined_error(data: Mapping[str, Any]) -> GraphQLError:
    return UndefinedError.from_payload(UndefinedErrorData.model_validate(data))


def _build_uniqueness_violation(data: Mapping[str, Any]) -> GraphQLError:
    return UniquenessViolationError.from_payload(UniquenessViolationData.model_validate(data))


# Each builder validates against its own code's model, so the payload type is never widened on the
# way to the constructor that consumes it.
_CODE_TO_BUILDER: dict[str, Callable[[Mapping[str, Any]], GraphQLError]] = {
    "ATTRIBUTE_CONSTRAINT_VIOLATION": _build_attribute_constraint_violation,
    "ATTRIBUTE_INVALID_TYPE": _build_attribute_invalid_type,
    "ATTRIBUTE_REQUIRED": _build_attribute_required,
    "BRANCH_ALREADY_MERGED": _build_branch_already_merged,
    "BRANCH_NEEDS_REBASE": _build_branch_needs_rebase,
    "BRANCH_NOT_FOUND": _build_branch_not_found,
    "MERGE_IN_PROGRESS": _build_merge_in_progress,
    "MERGE_RECOVERY_REQUIRED": _build_merge_recovery_required,
    "NODE_NOT_FOUND": _build_node_not_found,
    "SCHEMA_NOT_FOUND": _build_schema_not_found,
    "UNDEFINED_ERROR": _build_undefined_error,
    "UNIQUENESS_VIOLATION": _build_uniqueness_violation,
}


def exception_from_payload(code: str, data: Mapping[str, Any]) -> GraphQLError | None:
    """Build the exception a catalogued code names, or None where the SDK has no class for it.

    Raises:
        pydantic.ValidationError: when the payload does not match what the code declares.

    """
    builder = _CODE_TO_BUILDER.get(code)
    return None if builder is None else builder(data)
