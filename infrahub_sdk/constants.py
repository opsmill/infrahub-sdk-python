import enum


class InfrahubClientMode(str, enum.Enum):
    """
    Defines the operational modes for the Infrahub client.

    Attributes:
        DEFAULT: Standard operational mode.
        TRACKING: Mode where client operations can be tracked as part of a group,
                  often used for idempotent operations or cleanup.
    """
    DEFAULT = "default"
    TRACKING = "tracking"
    # IDEMPOTENT = "idempotent" # This mode seems to be commented out.
