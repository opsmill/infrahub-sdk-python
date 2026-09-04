"""Retry behaviour when Infrahub goes away in the middle of a request.

These tests reproduce a failover against a real Infrahub deployment. The API is told to sit on
every GraphQL request for a few seconds, an upsert mutation is started, and containers are killed
while that mutation is still in flight, in each of the two shapes a failover takes:

- The HAProxy load balancer in front of the API servers is restarted, so the connection is dropped
  before a single byte of the response arrives.
- The API servers behind it are restarted while HAProxy stays up, so the connection to the client
  holds and HAProxy answers for them with a transient HTTP status.

The mutation is an upsert on purpose: the server keeps processing a request whose client has gone
away, so the first attempt may well have been applied by the time the retry is sent. Retrying is
at-least-once, and only an idempotent mutation can be replayed safely.

The module is opt-in and skipped by default, so CI never runs it: the tests restart containers,
pin a host port and take several minutes. Run them with::

    INFRAHUB_TESTING_FAILOVER=1 uv run pytest tests/integration/test_retry_on_failover.py
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess  # noqa: S404
import threading
import time
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import TypeVar

import httpx
import pytest
from infrahub_testcontainers.container import PROJECT_ENV_VARIABLES, InfrahubDockerCompose

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync
from infrahub_sdk.exceptions import ServerNotReachableError
from infrahub_sdk.testing.docker import TestInfrahubDockerClient

RESPONSE_DELAY = 10
"""Seconds the API waits before handling each GraphQL request, to widen the in-flight window."""

RESTART_AFTER = 3.0
"""Seconds into the mutation at which the containers are restarted."""

RETRY_TIMEOUT = 180.0
"""Upper bound on a retrying call, so an unlimited retry budget cannot hang the suite."""

LOAD_BALANCER = "infrahub-server-lb"
API_SERVER = "infrahub-server"

ADMIN_TOKEN = PROJECT_ENV_VARIABLES["INFRAHUB_TESTING_INITIAL_ADMIN_TOKEN"]

FAILOVER_TESTS_ENV = "INFRAHUB_TESTING_FAILOVER"
"""Environment variable that opts into these tests; unset, the whole module is skipped."""

pytestmark = pytest.mark.skipif(
    os.environ.get(FAILOVER_TESTS_ENV) != "1",
    reason=f"failover tests restart containers and take minutes; opt in with {FAILOVER_TESTS_ENV}=1",
)

T = TypeVar("T")


def reserve_host_port() -> int:
    """Return a free TCP port on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def restart_containers(container_names: Sequence[str]) -> None:
    """Kill and restart containers, dropping every connection they were carrying."""
    subprocess.run(  # noqa: S603
        ["docker", "restart", "--time", "0", *container_names],  # noqa: S607
        check=True,
        capture_output=True,
    )


async def restart_after(container_names: Sequence[str], delay: float) -> None:
    """Restart containers ``delay`` seconds from now, while the caller has a request in flight."""
    await asyncio.sleep(delay)
    await asyncio.to_thread(restart_containers, container_names)


def run_with_timeout(func: Callable[[], T], timeout: float, on_timeout: Callable[[], None], grace: float = 30.0) -> T:
    """Run ``func`` in a thread and fail the test if it has not returned after ``timeout`` seconds.

    The synchronous client has no counterpart to ``asyncio.wait_for``, and an unlimited retry budget
    against a load balancer that never comes back would otherwise hang the whole suite. On timeout,
    ``on_timeout`` is called to make the call give up, so the thread does not keep retrying against
    the deployment behind the next test, and it gets ``grace`` seconds to end before the test fails.
    The thread is a daemon so, should it not end even then, it cannot block interpreter exit.
    """
    outcome: list[T] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            outcome.append(func())
        except BaseException as exc:  # re-raised in the calling thread below
            failure.append(exc)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        on_timeout()
        worker.join(grace)
        still_running = " and did not stop within the grace period" if worker.is_alive() else ""
        pytest.fail(f"the call was still running after {timeout} seconds{still_running}")
    if failure:
        raise failure[0]
    return outcome[0]


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
    def api_server_containers(self, infrahub_compose: InfrahubDockerCompose, infrahub_port: int) -> list[str]:
        return [
            str(container.Name) for container in infrahub_compose.get_containers() if container.Service == API_SERVER
        ]

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

    @pytest.fixture
    def slow_api_across_api_restart(
        self, infrahub_compose: InfrahubDockerCompose, address: str, slow_api: None
    ) -> Generator[None, None, None]:
        """Re-apply the response delay for a test that restarts the API servers and so clears it.

        The delay lives in the memory of each API worker process, set by a broadcast on the
        message bus, so restarting those processes drops it. Restoring it here keeps the class
        fixture's promise and leaves this test independent of the order tests run in. The
        broadcast only reaches workers that are up, so the teardown first waits for the restarted
        servers to answer again.

        Yields:
            None: with the delay active, as ``slow_api`` leaves it.

        """
        yield
        wait_until_reachable(address)
        infrahub_compose.set_server_response_delay(RESPONSE_DELAY)

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

        restart = asyncio.create_task(restart_after([load_balancer_container], RESTART_AFTER))
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

        restart = asyncio.create_task(restart_after([load_balancer_container], RESTART_AFTER))
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

        def stop_retrying() -> None:
            # With retries off, the next failed attempt raises instead of sleeping again.
            client.retry_on_failure = False

        restart = threading.Timer(RESTART_AFTER, restart_containers, args=([load_balancer_container],))
        restart.start()
        try:
            run_with_timeout(lambda: node.save(allow_upsert=True), timeout=RETRY_TIMEOUT, on_timeout=stop_retrying)
        finally:
            restart.join()

        assert node.id, "the upsert should have returned the id of the saved node"
        assert any("Transient failure" in record.message for record in caplog.records), (
            "the mutation should have been retried, not served on the first attempt"
        )

        saved = client.get(kind="BuiltinTag", name__value="failover-sync")
        assert saved.id == node.id

    async def test_api_server_restart_is_survived_with_unlimited_retries(
        self,
        address: str,
        api_server_containers: list[str],
        slow_api_across_api_restart: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The other shape of a failover: the load balancer survives, the API servers behind it do not.

        Nothing breaks the connection to the client here, so instead of a dropped socket HAProxy
        answers the in-flight request itself with 502, and answers whatever arrives while the
        servers boot with 503. Both are in retry_status_codes, so the mutation only has to wait.
        """
        caplog.set_level("WARNING", logger="infrahub_sdk")
        client = self.build_client(address, retry_on_failure=True)
        await client.schema.all()

        node = await client.create(kind="BuiltinTag", name="failover-api-servers")

        restart = asyncio.create_task(restart_after(api_server_containers, RESTART_AFTER))
        await asyncio.wait_for(node.save(allow_upsert=True), timeout=RETRY_TIMEOUT)
        await restart

        assert node.id, "the upsert should have returned the id of the saved node"
        retries = [record.message for record in caplog.records if "Transient failure" in record.message]
        assert any("HTTP 502" in message for message in retries), (
            f"the request in flight when the API servers died should have been retried on a 502: {retries}"
        )

        saved = await client.get(kind="BuiltinTag", name__value="failover-api-servers")
        assert saved.id == node.id
