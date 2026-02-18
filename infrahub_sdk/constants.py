import enum

# Namespaces reserved by the Infrahub server — mirrored from
# backend/infrahub/core/constants/__init__.py in the opsmill/infrahub repo.
# The server should eventually consume this list from the SDK.
RESTRICTED_NAMESPACES: list[str] = [
    "Account",
    "Branch",
    "Builtin",
    "Core",
    "Deprecated",
    "Diff",
    "Infrahub",
    "Internal",
    "Lineage",
    "Schema",
    "Profile",
    "Template",
]


class InfrahubClientMode(str, enum.Enum):
    DEFAULT = "default"
    TRACKING = "tracking"
    # IDEMPOTENT = "idempotent"
