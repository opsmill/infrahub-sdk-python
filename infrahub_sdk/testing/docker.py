from __future__ import annotations

import os

import pytest
from infrahub_testcontainers.helpers import TestInfrahubDocker
from packaging.version import InvalidVersion, Version

from .. import Config, InfrahubClient, InfrahubClientSync

INFRAHUB_VERSION = os.getenv("INFRAHUB_TESTING_IMAGE_VER")


def skip_version(min_infrahub_version: str | None = None, max_infrahub_version: str | None = None) -> bool:
    """
    Check if a test should be skipped depending on infrahub version.
    """
    if INFRAHUB_VERSION is None:
        return True

    try:
        version = Version(INFRAHUB_VERSION)
    except InvalidVersion:
        # We would typically end up here for development purpose while running a CI test against
        # unreleased versions of infrahub, like `stable` or `develop` branch.
        # For now, we consider this means we are testing against the most recent version of infrahub,
        # so we skip if the test should not be ran against a maximum version.
        return max_infrahub_version is None

    if min_infrahub_version is not None and version < Version(min_infrahub_version):
        return True

    return max_infrahub_version is not None and version > Version(max_infrahub_version)


class TestInfrahubDockerClient(TestInfrahubDocker):
    @pytest.fixture(scope="class")
    def client(self, infrahub_port: int) -> InfrahubClient:
        return InfrahubClient(
            config=Config(username="admin", password="infrahub", address=f"http://localhost:{infrahub_port}")  # noqa: S106
        )

    @pytest.fixture(scope="class")
    def client_sync(self, infrahub_port: int) -> InfrahubClientSync:
        return InfrahubClientSync(
            config=Config(username="admin", password="infrahub", address=f"http://localhost:{infrahub_port}")  # noqa: S106
        )
