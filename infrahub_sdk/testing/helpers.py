from pathlib import Path

import pytest
from infrahub.testing.container import InfrahubDockerCompose

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync


class TestInfrahub:
    @pytest.fixture(scope="class")
    def tmp_directory(self, tmpdir_factory: pytest.TempdirFactory) -> Path:
        directory = Path(str(tmpdir_factory.getbasetemp().strpath))
        return directory

    @pytest.fixture(scope="class")
    def default_branch(self) -> str:
        return "main"

    @pytest.fixture(scope="class")
    def infrahub_app(self, request: pytest.FixtureRequest, tmp_directory: Path) -> dict[str, int]:
        app = InfrahubDockerCompose.init(directory=tmp_directory)

        def cleanup() -> None:
            app.stop()

        app.start()
        request.addfinalizer(cleanup)

        return app.get_services_port()

    @pytest.fixture(scope="class")
    def infrahub_port(self, infrahub_app: dict[str, int]) -> int:
        return infrahub_app["server"]

    @pytest.fixture(scope="class")
    def infrahub_client(self, infrahub_app: dict[str, int], infrahub_port: int) -> InfrahubClient:
        return InfrahubClient(config=Config(address=f"http://localhost:{infrahub_port}"))

    @pytest.fixture(scope="class")
    def infrahub_client_sync(self, infrahub_app: dict[str, int], infrahub_port: int) -> InfrahubClientSync:
        return InfrahubClientSync(config=Config(address=f"http://localhost:{infrahub_port}"))
