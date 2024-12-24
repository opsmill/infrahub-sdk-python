import pytest
from infrahub_testcontainers.helpers import TestInfrahubDocker

from .. import Config, InfrahubClient, InfrahubClientSync


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
