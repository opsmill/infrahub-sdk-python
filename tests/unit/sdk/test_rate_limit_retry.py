"""Client-level tests for transparent HTTP 429 retry on the async and sync clients.

Covers (in later implementation chunks): transparent 429->200 retry, honouring
``Retry-After``, clean ``RateLimitError`` on exhaustion, the disabled path, async/sync
parity, all-paths coverage (regular request, multipart, streaming init), and the E2/X1
multipart body re-read regression. This module currently holds the shared imports/skeleton.
"""

from __future__ import annotations

import httpx
import pytest

from infrahub_sdk import InfrahubClient, InfrahubClientSync
from infrahub_sdk.config import Config
from infrahub_sdk.exceptions import RateLimitError

__all__ = [
    "Config",
    "InfrahubClient",
    "InfrahubClientSync",
    "RateLimitError",
    "httpx",
    "pytest",
]
