import ipaddress
import re

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

ARTIFACT_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling artifact_fetch is only supported for nodes that are Artifact Definition target"
)
ARTIFACT_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling artifact_generate is only supported for nodes that are Artifact Definition targets"
)
ARTIFACT_DEFINITION_GENERATE_FEATURE_NOT_SUPPORTED_MESSAGE = (
    "calling generate is only supported for CoreArtifactDefinition nodes"
)

HIERARCHY_FETCH_FEATURE_NOT_SUPPORTED_MESSAGE = "Hierarchical fields are not supported for this node."

HFID_STR_SEPARATOR = "__"
PROFILE_KIND_PREFIX = "Profile"
