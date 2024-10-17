from __future__ import annotations

import importlib.metadata

from .analyzer import GraphQLOperation, GraphQLQueryAnalyzer, GraphQLQueryVariable
from .batch import InfrahubBatch
from .branch import InfrahubBranchManager, InfrahubBranchManagerSync
from .client import InfrahubClient, InfrahubClientSync
from .config import Config
from .exceptions import (
    AuthenticationError,
    Error,
    GraphQLError,
    NodeNotFoundError,
    ServerNotReachableError,
    ServerNotResponsiveError,
    ValidationError,
)
from .graphql import Mutation, Query
from .node import InfrahubNode, InfrahubNodeSync
from .schema import (
    AttributeSchema,
    GenericSchema,
    InfrahubRepositoryConfig,
    InfrahubSchema,
    MainSchemaTypes,
    NodeSchema,
    ProfileSchema,
    RelationshipCardinality,
    RelationshipKind,
    RelationshipSchema,
    SchemaRoot,
)
from .store import NodeStore, NodeStoreSync
from .timestamp import Timestamp
from .uuidt import UUIDT, generate_uuid

__all__ = [
    "AttributeSchema",
    "AuthenticationError",
    "Config",
    "Error",
    "InfrahubBatch",
    "InfrahubBranchManager",
    "InfrahubBranchManagerSync",
    "InfrahubClient",
    "InfrahubClientSync",
    "InfrahubNode",
    "InfrahubNodeSync",
    "InfrahubRepositoryConfig",
    "InfrahubSchema",
    "generate_uuid",
    "GenericSchema",
    "GraphQLQueryAnalyzer",
    "GraphQLQueryVariable",
    "GraphQLError",
    "GraphQLOperation",
    "MainSchemaTypes",
    "NodeNotFoundError",
    "NodeSchema",
    "Mutation",
    "NodeStore",
    "NodeStoreSync",
    "ProfileSchema",
    "Query",
    "RelationshipSchema",
    "RelationshipCardinality",
    "RelationshipKind",
    "SchemaRoot",
    "ServerNotReachableError",
    "ServerNotResponsiveError",
    "Timestamp",
    "UUIDT",
    "ValidationError",
]

try:
    __version__ = importlib.metadata.version("infrahub-sdk")
except importlib.metadata.PackageNotFoundError:
    __version__ = importlib.metadata.version("infrahub-server")
