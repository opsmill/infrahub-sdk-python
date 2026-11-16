from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING

from typing_extensions import Self

from infrahub_sdk.node import InfrahubNodeSync
from infrahub_sdk.store import NodeStoreSync

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClientSync
    from infrahub_sdk.schema import NodeSchemaAPI

    from .conftest import BothClients


class RecordingLock:
    """Re-entrant lock that records when a thread takes it while holding the lock of another branch store."""

    def __init__(self, branch: str, held: threading.local, nested: list[tuple[str, str]]) -> None:
        self.branch = branch
        self._held = held
        self._nested = nested
        self._lock = threading.RLock()

    def _held_branches(self) -> list[str]:
        if not hasattr(self._held, "branches"):
            self._held.branches = []
        return self._held.branches

    def _before_acquire(self, outer: list[str]) -> None:
        """Called when the lock is taken while another branch lock is held."""

    def _acquire(self) -> None:
        self._lock.acquire()

    def __enter__(self) -> Self:
        held = self._held_branches()
        outer = [branch for branch in held if branch != self.branch]
        if outer:
            self._nested.extend((branch, self.branch) for branch in outer)
            self._before_acquire(outer)
        self._acquire()
        held.append(self.branch)
        return self

    def __exit__(self, *exc: object) -> None:
        self._held_branches().pop()
        self._lock.release()


class InterleavingLock(RecordingLock):
    """Waits until both threads hold their first lock before taking a nested one, and gives up instead of hanging."""

    def __init__(
        self,
        branch: str,
        held: threading.local,
        nested: list[tuple[str, str]],
        barrier: threading.Barrier,
        timed_out: list[str],
    ) -> None:
        super().__init__(branch=branch, held=held, nested=nested)
        self._barrier = barrier
        self._timed_out = timed_out

    def _before_acquire(self, outer: list[str]) -> None:
        with contextlib.suppress(threading.BrokenBarrierError):
            self._barrier.wait()

    def _acquire(self) -> None:
        if not self._lock.acquire(timeout=1):
            self._timed_out.append(self.branch)
            raise TimeoutError(f"lock of branch {self.branch!r} not acquired")


def _rack_with_location_on(
    client: InfrahubClientSync, schemas: dict[str, NodeSchemaAPI], branch: str, suffix: str
) -> InfrahubNodeSync:
    location = InfrahubNodeSync(
        client=client,
        schema=schemas["location"],
        branch=branch,
        data={"id": f"location-{suffix}", "name": {"value": f"Site {suffix}"}, "type": {"value": "SITE"}},
    )
    client.store.set(node=location)
    return InfrahubNodeSync(
        client=client,
        schema=schemas["rack"],
        branch=branch,
        data={
            "id": f"rack-{suffix}",
            "facility_id": {"value": f"R{suffix}"},
            "location": {"node": {"id": f"location-{suffix}", "__typename": "BuiltinLocation"}},
        },
    )


def test_node_store_set_does_not_hold_a_branch_lock_while_reading_another_branch(
    clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    held = threading.local()
    nested: list[tuple[str, str]] = []
    client = clients.sync
    client.store = NodeStoreSync(
        default_branch="main", lock_factory=lambda branch: RecordingLock(branch=branch, held=held, nested=nested)
    )
    rack = _rack_with_location_on(client=client, schemas=schema_with_hfid, branch="b1", suffix="1")

    # The rack's HFID reads its location, which is stored in branch b1.
    client.store.set(node=rack, branch="b2")

    assert client.store.get(key=["R1", "Site 1"], kind="BuiltinRack", branch="b2") is rack
    assert nested == []


def test_node_store_set_across_branches_from_two_threads_does_not_deadlock(
    clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    held = threading.local()
    nested: list[tuple[str, str]] = []
    barrier = threading.Barrier(2, timeout=2)
    timed_out: list[str] = []
    client = clients.sync
    client.store = NodeStoreSync(
        default_branch="main",
        lock_factory=lambda branch: InterleavingLock(
            branch=branch, held=held, nested=nested, barrier=barrier, timed_out=timed_out
        ),
    )
    # rack1 and its location are in b1; rack2 and its location are in b2.
    rack1 = _rack_with_location_on(client=client, schemas=schema_with_hfid, branch="b1", suffix="1")
    rack2 = _rack_with_location_on(client=client, schemas=schema_with_hfid, branch="b2", suffix="2")
    errors: list[BaseException] = []

    def store(node: InfrahubNodeSync, branch: str) -> None:
        try:
            client.store.set(node=node, branch=branch)
        except BaseException as exc:
            errors.append(exc)

    # Each node goes into the other branch, so its HFID reads a peer under the other thread's lock.
    threads = [
        threading.Thread(target=store, args=(rack1, "b2")),
        threading.Thread(target=store, args=(rack2, "b1")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert timed_out == []
    assert errors == []
