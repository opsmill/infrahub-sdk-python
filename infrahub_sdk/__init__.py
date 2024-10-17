from __future__ import annotations

import importlib.metadata

from .client import InfrahubClient, InfrahubClientSync
from .config import Config

__all__ = [
    "Config",
    "InfrahubClient",
    "InfrahubClientSync",
]

try:
    __version__ = importlib.metadata.version("infrahub-sdk")
except importlib.metadata.PackageNotFoundError:
    __version__ = importlib.metadata.version("infrahub-server")
