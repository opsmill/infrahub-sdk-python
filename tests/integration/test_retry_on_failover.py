"""Retry behaviour when Infrahub goes away in the middle of a request.

These tests reproduce a load balancer failover against a real Infrahub deployment. The API is
told to sit on every GraphQL request for a few seconds, an upsert mutation is started, and the
HAProxy container fronting the API servers is killed and restarted while that mutation is still
in flight. The client therefore sees the connection drop before any response arrives, which is
what a failover looks like from the outside.

The mutation is an upsert on purpose: the server keeps processing a request whose client has gone
away, so the first attempt may well have been applied by the time the retry is sent. Retrying is
at-least-once, and only an idempotent mutation can be replayed safely.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess  # noqa: S404
import threading
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from infrahub_testcontainers.container import PROJECT_ENV_VARIABLES, InfrahubDockerCompose

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync
from infrahub_sdk.exceptions import ServerNotReachableError
from infrahub_sdk.testing.docker import TestInfrahubDockerClient

RESPONSE_DELAY = 10
"""Seconds the API waits before handling each GraphQL request, to widen the in-flight window."""

RESTART_AFTER = 3.0
"""Seconds into the mutation at which the load balancer is restarted."""

RETRY_TIMEOUT = 180.0
"""Upper bound on a retrying call, so an unlimited retry budget cannot hang the suite."""

LOAD_BALANCER = "infrahub-server-lb"

ADMIN_TOKEN = PROJECT_ENV_VARIABLES["INFRAHUB_TESTING_INITIAL_ADMIN_TOKEN"]


def reserve_host_port() -> int:
    """Return a free TCP port on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def restart_load_balancer(container_name: str) -> None:
    """Kill and restart the load balancer, dropping every connection it was carrying."""
    subprocess.run(  # noqa: S603
        ["docker", "restart", "--time", "0", container_name],  # noqa: S607
        check=True,
        capture_output=True,
    )


def wait_until_reachable(address: str, timeout: float = 120.0) -> None:
    """Block until the load balancer answers again after a restart.

    Raises:
        httpx.HTTPError: If the load balancer is still not answering after ``timeout`` seconds.

    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            httpx.get(f"{address}/api/config", timeout=10).raise_for_status()
            return
        except httpx.HTTPError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


class TestRetryOnFailover(TestInfrahubDockerClient):
    @pytest.fixture(scope="class")
    def infrahub_compose(
        self,
        tmp_directory: Path,
        remote_repos_dir: Path,  # initialize repository before running docker compose to fix permissions issues
        remote_backups_dir: Path,
        infrahub_version: str,
        deployment_type: str | None,
    ) -> Generator[InfrahubDockerCompose, None, None]:
        """Publish the load balancer on a fixed host port.

        Docker picks a new host port every time a container starts, so a restarted load balancer
        would come back at a different address and the client would retry against a dead port.
        Pinning the port keeps the address stable across the restart, the way it is in a real
        failover. The variable has to stay set for as long as compose is driven, so the whole
        fixture lifetime runs inside the patched environment.

        Yields:
            InfrahubDockerCompose: the compose project, with the server port pinned.

        """
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setenv("INFRAHUB_TESTING_SERVER_PORT", str(reserve_host_port()))
            yield InfrahubDockerCompose.init(
                directory=tmp_directory,
                version=infrahub_version,
                deployment_type=deployment_type,
            )

    @pytest.fixture(scope="class")
    def address(self, infrahub_port: int) -> str:
        return f"http://localhost:{infrahub_port}"

    @pytest.fixture(scope="class")
    def load_balancer_container(self, infrahub_compose: InfrahubDockerCompose, infrahub_port: int) -> str:
        return str(infrahub_compose.get_container(service_name=LOAD_BALANCER).Name)

    @pytest.fixture(scope="class")
    def slow_api(
        self, infrahub_compose: InfrahubDockerCompose, address: str, infrahub_port: int
    ) -> Generator[None, None, None]:
        """Make every GraphQL request take RESPONSE_DELAY seconds, on every API worker.

        Yields:
            None: once the delay is active on every worker process.

        """
        infrahub_compose.set_server_response_delay(RESPONSE_DELAY)
        yield
        wait_until_reachable(address)
        infrahub_compose.set_server_response_delay(0)

    def build_client(self, address: str, *, retry_on_failure: bool) -> InfrahubClient:
        return InfrahubClient(config=self.build_config(address, retry_on_failure=retry_on_failure))

    def build_config(self, address: str, *, retry_on_failure: bool) -> Config:
        return Config(
            address=address,
            api_token=ADMIN_TOKEN,
            retry_on_failure=retry_on_failure,
            max_retry_duration=0,  # retry for as long as it takes
            retry_delay=1,
            retry_max_delay=5,
        )

    async def test_failover_aborts_the_mutation_without_retry(
        self, address: str, load_balancer_container: str, slow_api: None
    ) -> None:
        """Without retries, losing the load balancer mid-mutation surfaces as a hard failure."""
        client = self.build_client(address, retry_on_failure=False)
        await client.schema.all()  # warm the schema cache so only the mutation is in flight

        node = await client.create(kind="BuiltinTag", name="failover-no-retry")

        async def restart_once() -> None:
            await asyncio.sleep(RESTART_AFTER)
            await asyncio.to_thread(restart_load_balancer, load_balancer_container)

        restart = asyncio.create_task(restart_once())
        with pytest.raises(ServerNotReachableError):
            await node.save(allow_upsert=True)
        await restart

        wait_until_reachable(address)

    async def test_failover_is_survived_with_unlimited_retries(
        self, address: str, load_balancer_container: str, slow_api: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """With retries enabled the same failover only delays the mutation."""
        caplog.set_level("WARNING", logger="infrahub_sdk")
        client = self.build_client(address, retry_on_failure=True)
        await client.schema.all()

        node = await client.create(kind="BuiltinTag", name="failover-async")

        async def restart_once() -> None:
            await asyncio.sleep(RESTART_AFTER)
            await asyncio.to_thread(restart_load_balancer, load_balancer_container)

        restart = asyncio.create_task(restart_once())
        await asyncio.wait_for(node.save(allow_upsert=True), timeout=RETRY_TIMEOUT)
        await restart

        assert node.id, "the upsert should have returned the id of the saved node"
        assert any("Transient failure" in record.message for record in caplog.records), (
            "the mutation should have been retried, not served on the first attempt"
        )

        saved = await client.get(kind="BuiltinTag", name__value="failover-async")
        assert saved.id == node.id

    def test_failover_is_survived_with_unlimited_retries_sync(
        self, address: str, load_balancer_container: str, slow_api: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The synchronous client retries the same way the asynchronous one does."""
        caplog.set_level("WARNING", logger="infrahub_sdk")
        client = InfrahubClientSync(config=self.build_config(address, retry_on_failure=True))
        client.schema.all()

        node = client.create(kind="BuiltinTag", name="failover-sync")

        restart = threading.Timer(RESTART_AFTER, restart_load_balancer, args=(load_balancer_container,))
        restart.start()
        try:
            node.save(allow_upsert=True)
        finally:
            restart.join()

        assert node.id, "the upsert should have returned the id of the saved node"
        assert any("Transient failure" in record.message for record in caplog.records), (
            "the mutation should have been retried, not served on the first attempt"
        )

        saved = client.get(kind="BuiltinTag", name__value="failover-sync")
        assert saved.id == node.id
