from enum import Enum


class ProtocolTarget(str, Enum):
    """Which protocols module is being generated.

    ``USER_SCHEMA`` renders protocols for a user's own schema into a standalone module, one file
    per async/sync variant, importing the core kinds it references from ``infrahub_sdk.protocols``.

    ``SDK_CORE`` renders ``infrahub_sdk.protocols`` itself. Every kind is local, so nothing can be
    imported from that module, both variants share a single file, and the sync classes carry a
    ``Sync`` suffix to keep their names distinct.
    """

    USER_SCHEMA = "user-schema"
    SDK_CORE = "sdk-core"
