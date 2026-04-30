from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .. import InfrahubClientSync
    from ..schema.repository import InfrahubRepositoryConfig


INFRAHUB_CLIENT_KEY: pytest.StashKey[InfrahubClientSync] = pytest.StashKey()
INFRAHUB_CONFIG_PATH_KEY: pytest.StashKey[Path] = pytest.StashKey()
INFRAHUB_REPO_CONFIG_KEY: pytest.StashKey[InfrahubRepositoryConfig] = pytest.StashKey()
