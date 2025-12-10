import ipaddress
import re

PROPERTIES_FLAG = ["is_protected", "updated_at"]
PROPERTIES_OBJECT = ["source", "owner"]
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
