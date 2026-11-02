from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schema import RelationshipSchemaAPI

PROPERTIES_FLAG = ["is_protected", "updated_at"]
PROPERTIES_OBJECT = ["source", "owner"]

# Attribute-level metadata object fields (in addition to PROPERTIES_OBJECT)
ATTRIBUTE_METADATA_OBJECT = ["updated_by"]

# Node metadata fields (for node_metadata in GraphQL response)
NODE_METADATA_FIELDS_FLAG = ["created_at", "updated_at"]
NODE_METADATA_FIELDS_OBJECT = ["created_by", "updated_by"]

# Relationship metadata fields (for relationship_metadata in GraphQL response)
RELATIONSHIP_METADATA_FIELDS_FLAG = ["updated_at"]
RELATIONSHIP_METADATA_FIELDS_OBJECT = ["updated_by"]
SAFE_VALUE = re.compile(r"(^[\. /:a-zA-Z0-9_-]+$)|(^$)")

IP_TYPES = ipaddress.IPv4Interface | ipaddress.IPv6Interface | ipaddress.IPv4Network | ipaddress.IPv6Network

# Bare IP addresses (no prefix); serialized with str() rather than with_prefixlen
IP_ADDRESS_TYPES = ipaddress.IPv4Address | ipaddress.IPv6Address

ARTIFACT_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling artifact_fetch is only supported for nodes that are Artifact Definition target"
)
ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling artifact_generate is only supported for nodes that are Artifact Definition targets"
)
ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling generate is only supported for CoreArtifactDefinition nodes"
)
FILE_DOWNLOAD_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling download_file is only supported for nodes that inherit from CoreFileObject"
)
MATCHES_LOCAL_CHECKSUM_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling matches_local_checksum is only supported for nodes that inherit from CoreFileObject"
)
UPLOAD_IF_CHANGED_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling upload_if_changed is only supported for nodes that inherit from CoreFileObject"
)

HIERARCHY_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE = "Hierarchical fields are not supported for this node."

INLINE_INPUT_PEERS_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "The peers of '{name}' cannot be edited one at a time, because the mutation takes the fields of a {peer} "
    "and not a reference to one. To set them, pass the complete list of '{name}' to client.create() and save "
    "the node with allow_upsert=True, or create, update or delete the {peer} node itself."
)

# Relationships whose input in a mutation takes the peer's fields, not a reference to an existing peer,
# as (name, peer) pairs.
INLINE_INPUT_RELATIONSHIPS = frozenset({("ranges", "CoreNumberPoolRange")})


def _peers_are_inline_input(schema: RelationshipSchemaAPI) -> bool:
    """Return whether a mutation takes this relationship's peers as fields instead of as references."""
    return (schema.name, schema.peer) in INLINE_INPUT_RELATIONSHIPS


POOL_ALLOCATED_QUERY_NAME = "InfrahubResourcePoolAllocated"
POOL_ALLOCATION_FIELDS = ["id", "kind", "branch", "display_label", "identifier", "provenance"]
POOL_ALLOCATED_RESOURCE_FIELDS = ["id", "kind", "branch", "identifier"]

HFID_STR_SEPARATOR = "__"
PROFILE_KIND_PREFIX = "Profile"
