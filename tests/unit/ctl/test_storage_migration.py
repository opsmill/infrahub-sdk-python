from __future__ import annotations

import asyncio
import json
import os
import random
import re
import threading
import time
from dataclasses import dataclass
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest

from infrahub_sdk.ctl.storage.migration import (
    BATCH_MAX_SIZE,
    RETRY_AFTER_MAX_SECONDS,
    UNANSWERED_MAX_RETRIES,
    AdaptiveLimit,
    MigrationError,
    Options,
    StorageEncryptor,
    backoff_delay,
    parse_retry_after,
    parse_timestamp,
    server_detail,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from pytest_httpx import HTTPXMock

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

BASE = "http://mock"
LIST_URL = f"{BASE}/api/storage/objects"
BATCH_URL = f"{BASE}/api/storage/objects/encrypt"
OLD = "2026-01-01T00:00:00Z"


class FakeTime:
    """A clock that advances only when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


def stored(identifier: str, size: int = 100, modified: str = OLD) -> dict[str, Any]:
    return {"identifier": identifier, "size": size, "last_modified": modified}


def page(*identifiers: str, next_start_after: str | None = None) -> dict[str, Any]:
    return {"objects": [stored(identifier) for identifier in identifiers], "next_start_after": next_start_after}


def answer(*identifiers: str, outcome: str = "encrypted", size: int = 100) -> dict[str, Any]:
    return {"results": [{"identifier": i, "outcome": outcome, "size": size, "reason": None} for i in identifiers]}


def make(
    tmp_path: Path,
    *,
    fake: FakeTime | None = None,
    address: str = BASE,
    **overrides: Any,  # noqa: ANN401
) -> tuple[StorageEncryptor, FakeTime]:
    fake = fake or FakeTime()
    settings: dict[str, Any] = {
        "state_file": tmp_path / "state.json",
        "report": tmp_path / "report.jsonl",
        "concurrency": 4,
        "batch_size": 2,
    }
    settings.update(overrides)
    encryptor = StorageEncryptor(
        options=Options(**settings), address=address, clock=fake.clock, sleep=fake.sleep, rng=random.Random(1)
    )
    return encryptor, fake


async def run(encryptor: StorageEncryptor, headers: dict[str, str] | None = None) -> None:
    async with httpx.AsyncClient(base_url=BASE, headers=headers) as http:
        await encryptor.run(http)


def sent_bodies(httpx_mock: HTTPXMock) -> list[dict[str, Any]]:
    return [json.loads(r.content) for r in httpx_mock.get_requests(method="POST", url=BATCH_URL)]


def sent_listing_params(httpx_mock: HTTPXMock) -> list[dict[str, str]]:
    return [dict(r.url.params) for r in httpx_mock.get_requests(method="GET") if r.url.path == "/api/storage/objects"]


async def test_pages_through_the_listing_and_sends_batches_of_the_given_size(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=3", json=page("a", "b", "c", next_start_after="c"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=3&start_after=c", json=page("d", "e"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json=answer("a", "b"),
        match_json={"identifiers": ["a", "b"], "allow_unverified": False},
    )
    httpx_mock.add_response(
        method="POST", url=BATCH_URL, json=answer("c"), match_json={"identifiers": ["c"], "allow_unverified": False}
    )
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json=answer("d", "e"),
        match_json={"identifiers": ["d", "e"], "allow_unverified": False},
    )
    encryptor, _ = make(tmp_path, page_size=3)

    await run(encryptor)

    assert encryptor.totals.counts == {"encrypted": 5}
    assert encryptor.totals.objects_listed == 5
    assert encryptor.totals.encrypt_requests == 3
    assert encryptor.completed is True


async def test_allow_unverified_is_sent_to_the_server(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, _ = make(tmp_path, allow_unverified=True, page_size=5000)

    await run(encryptor)

    assert sent_bodies(httpx_mock) == [{"identifiers": ["a"], "allow_unverified": True}]


async def test_counts_every_outcome_and_reports_the_objects_that_were_not_encrypted(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", "d"))
    results = [
        {"identifier": "a", "outcome": "encrypted", "size": 10, "reason": None},
        {"identifier": "b", "outcome": "already_encrypted", "size": 20, "reason": None},
        {"identifier": "c", "outcome": "skipped_unverified", "size": 30, "reason": "no checksum"},
        {"identifier": "d", "outcome": "failed", "size": 0, "reason": "disk full"},
    ]
    httpx_mock.add_response(method="POST", url=BATCH_URL, json={"results": results[:2]})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json={"results": results[2:]})
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert encryptor.totals.counts == {"encrypted": 1, "already_encrypted": 1, "skipped_unverified": 1, "failed": 1}
    assert encryptor.totals.bytes_encrypted == 10
    lines = [json.loads(line) for line in (tmp_path / "report.jsonl").read_text().splitlines()]
    assert sorted(line["identifier"] for line in lines) == ["b", "c", "d"]
    assert next(line for line in lines if line["identifier"] == "c")["reason"] == "no checksum"


async def test_dry_run_sends_no_batch_and_writes_no_state_or_report(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    encryptor, _ = make(tmp_path, dry_run=True)

    await run(encryptor)

    assert httpx_mock.get_requests(method="POST") == []
    assert encryptor.totals.objects_listed == 2
    assert encryptor.totals.bytes_listed == 200
    assert encryptor.totals.counts == {}
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "report.jsonl").exists()


async def test_objects_modified_after_before_are_not_sent(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    objects = [stored("old", modified="2026-01-01T00:00:00Z"), stored("new", modified="2026-06-01T12:00:00Z")]
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json={"objects": objects, "next_start_after": None})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("old"))
    encryptor, _ = make(tmp_path, before=parse_timestamp("2026-03-01T00:00:00"))

    await run(encryptor)

    assert sent_bodies(httpx_mock) == [{"identifiers": ["old"], "allow_unverified": False}]
    assert encryptor.totals.skipped_newer == 1
    assert encryptor.totals.objects_listed == 2


async def test_limit_stops_the_run_after_that_many_objects(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", next_start_after="c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    encryptor, _ = make(tmp_path, limit=2)

    await run(encryptor)

    assert sent_bodies(httpx_mock) == [{"identifiers": ["a", "b"], "allow_unverified": False}]
    assert encryptor.completed is False
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["start_after"] == "b"


@dataclass
class TimestampCase:
    name: str
    text: str
    expected: str


TIMESTAMP_CASES = [
    TimestampCase(name="z-suffix", text="2026-11-14T10:00:00Z", expected="2026-11-14T10:00:00+00:00"),
    TimestampCase(name="offset", text="2026-11-14T10:00:00+01:00", expected="2026-11-14T10:00:00+01:00"),
    TimestampCase(name="no-offset-is-utc", text="2026-11-14T10:00:00", expected="2026-11-14T10:00:00+00:00"),
    TimestampCase(
        name="microseconds-z", text="2026-11-14T10:00:00.123456Z", expected="2026-11-14T10:00:00.123456+00:00"
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in TIMESTAMP_CASES])
def test_parse_timestamp(case: TimestampCase) -> None:
    assert parse_timestamp(case.text).isoformat() == case.expected


def test_parse_retry_after_reads_seconds_and_a_date_and_ignores_anything_else() -> None:
    assert parse_retry_after("7") == pytest.approx(7.0)
    assert parse_retry_after("2.5") == pytest.approx(2.5)
    assert parse_retry_after(None) == pytest.approx(0.0)
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") == pytest.approx(0.0)
    assert parse_retry_after("-3") == pytest.approx(0.0)
    assert parse_retry_after("not a number") == pytest.approx(0.0)


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "1e999"])
def test_parse_retry_after_ignores_a_value_that_is_not_finite(value: str) -> None:
    assert parse_retry_after(value) == pytest.approx(0.0)


def test_parse_retry_after_reads_an_http_date_in_the_future() -> None:
    value = formatdate(time.time() + 60, usegmt=True)

    assert 50.0 < parse_retry_after(value) <= 60.0


# State file


async def test_state_file_records_the_position_after_every_page(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    encryptor, _ = make(tmp_path, page_size=2)

    await run(encryptor)

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["address"] == BASE
    assert state["start_after"] == "c"
    assert state["completed"] is True
    assert state["totals"]["counts"] == {"encrypted": 3}
    assert not (tmp_path / "state.json.tmp").exists()


async def test_a_rerun_resumes_after_the_saved_position_and_adds_up_the_counters(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json=answer("a", "b"),
        match_json={"identifiers": ["a", "b"], "allow_unverified": False},
    )
    first, _ = make(tmp_path, page_size=2, limit=2)
    await run(first)
    httpx_mock.add_response(
        method="POST", url=BATCH_URL, json=answer("c"), match_json={"identifiers": ["c"], "allow_unverified": False}
    )

    second, _ = make(tmp_path, page_size=2)
    await run(second)

    assert second.resumed is True
    assert sent_listing_params(httpx_mock) == [{"limit": "2"}, {"limit": "2", "start_after": "b"}]
    assert second.totals.counts == {"encrypted": 3}
    assert second.handled_this_run == 1
    assert second.completed is True


async def test_a_finished_pass_is_not_resumed_and_the_next_run_starts_again(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    await run(make(tmp_path)[0])

    again, _ = make(tmp_path)
    await run(again)

    assert sent_listing_params(httpx_mock) == [{"limit": "5000"}, {"limit": "5000"}]
    assert again.resumed is False
    assert again.totals.counts == {"encrypted": 1}


async def test_restart_ignores_the_state_file(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"address": BASE, "start_after": "m", "completed": False, "totals": {"counts": {"encrypted": 9}}})
    )
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, _ = make(tmp_path, restart=True)

    await run(encryptor)

    assert sent_listing_params(httpx_mock) == [{"limit": "5000"}]
    assert encryptor.totals.counts == {"encrypted": 1}


async def test_a_dry_run_starts_at_the_saved_position_without_loading_the_counters(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"address": BASE, "start_after": "m", "completed": False, "totals": {"counts": {"encrypted": 9}}})
    )
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=m", json=page("n"))
    encryptor, _ = make(tmp_path, dry_run=True)

    await run(encryptor)

    assert encryptor.totals.counts == {}
    assert encryptor.totals.objects_listed == 1


async def test_a_state_file_of_another_server_is_refused(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"address": "http://other", "start_after": "m", "completed": False, "totals": {}})
    )
    encryptor, _ = make(tmp_path)

    with pytest.raises(MigrationError, match=r"belongs to http://other, not to http://mock"):
        await run(encryptor)


@pytest.mark.parametrize("content", ["not json", "{}", '{"address": "http://mock"}'])
async def test_an_unreadable_state_file_is_refused(tmp_path: Path, content: str) -> None:
    (tmp_path / "state.json").write_text(content)
    encryptor, _ = make(tmp_path)

    with pytest.raises(MigrationError, match=r"state file .* cannot be read"):
        await run(encryptor)


async def test_a_failed_page_leaves_the_state_at_the_last_complete_page(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c", "d"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json=answer("a", "b"),
        match_json={"identifiers": ["a", "b"], "allow_unverified": False},
    )
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        status_code=403,
        json={"detail": "no"},
        match_json={"identifiers": ["c", "d"], "allow_unverified": False},
    )
    encryptor, _ = make(tmp_path, page_size=2)

    with pytest.raises(MigrationError, match="HTTP 403"):
        await run(encryptor)

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["start_after"] == "b"
    assert state["totals"]["counts"] == {"encrypted": 2}
    assert encryptor.start_after == "b"


async def test_cancelling_the_run_keeps_the_state_of_the_last_complete_page(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    async def never_answers(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(3600)
        raise AssertionError("not reached")

    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c", "d"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json=answer("a", "b"),
        match_json={"identifiers": ["a", "b"], "allow_unverified": False},
    )
    httpx_mock.add_callback(
        never_answers, method="POST", url=BATCH_URL, match_json={"identifiers": ["c", "d"], "allow_unverified": False}
    )
    encryptor, _ = make(tmp_path, page_size=2)

    task = asyncio.create_task(run(encryptor))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(httpx_mock.get_requests(method="POST")) == 2:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError, match=r"^$"):
        await task

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["start_after"] == "b"
    assert state["totals"]["counts"] == {"encrypted": 2}
    assert encryptor.totals.counts == {"encrypted": 2}


async def test_what_the_server_confirmed_in_an_interrupted_page_is_kept_apart_and_never_counted(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    async def never_answers(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(3600)
        raise AssertionError("not reached")

    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", "d"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json={
            "results": [
                {"identifier": "a", "outcome": "encrypted", "size": 100, "reason": None},
                {"identifier": "b", "outcome": "already_encrypted", "size": 0, "reason": None},
            ]
        },
        match_json={"identifiers": ["a", "b"], "allow_unverified": False},
    )
    httpx_mock.add_callback(
        never_answers, method="POST", url=BATCH_URL, match_json={"identifiers": ["c", "d"], "allow_unverified": False}
    )
    encryptor, _ = make(tmp_path, concurrency=1)

    task = asyncio.create_task(run(encryptor))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(httpx_mock.get_requests(method="POST")) == 2:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError, match=r"^$"):
        await task

    assert encryptor.page_interrupted is True
    assert encryptor.interrupted_counts == {"encrypted": 1, "already_encrypted": 1}
    assert encryptor.interrupted_bytes_encrypted == 100
    assert encryptor.objects_confirmed == 2
    assert encryptor.totals.counts == {}
    assert encryptor.totals.bytes_encrypted == 0
    assert not (tmp_path / "state.json").exists()


async def test_an_error_in_a_page_keeps_what_the_server_confirmed_before_it_apart(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", "d"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json=answer("a", "b"),
        match_json={"identifiers": ["a", "b"], "allow_unverified": False},
    )
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        status_code=403,
        json={"detail": "no"},
        match_json={"identifiers": ["c", "d"], "allow_unverified": False},
    )
    encryptor, _ = make(tmp_path, concurrency=1)

    with pytest.raises(MigrationError, match="HTTP 403"):
        await run(encryptor)

    assert encryptor.interrupted_counts == {"encrypted": 2}
    assert encryptor.interrupted_bytes_encrypted == 200
    assert encryptor.totals.counts == {}
    assert encryptor.start_after is None


async def test_a_complete_page_leaves_nothing_in_the_interrupted_figures(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert encryptor.page_interrupted is False
    assert encryptor.interrupted_counts == {}
    assert encryptor.interrupted_bytes_encrypted == 0
    assert encryptor.totals.counts == {"encrypted": 2}


# 429 answers


async def test_a_429_answer_holds_the_requests_for_retry_after_and_lowers_the_limit(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"Retry-After": "7"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path, concurrency=8)
    assert encryptor.limit.limit == 4

    await run(encryptor)

    assert encryptor.totals.shed_429 == 1
    assert encryptor.totals.shed_429_admission == 0
    assert encryptor.limit.limit == 2
    assert encryptor.limit.decreases == 1
    assert fake.sleeps[0] == pytest.approx(7.0)
    assert encryptor.totals.counts == {"encrypted": 1}


async def test_a_429_answer_without_retry_after_waits_the_backoff(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429)
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path)

    await run(encryptor)

    assert 0.5 <= fake.sleeps[0] <= 0.5 * 1.25


async def test_the_admission_marker_is_counted_apart(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"X-Infrahub-Admission": "shed"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429)
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert encryptor.totals.shed_429 == 2
    assert encryptor.totals.shed_429_admission == 1


async def test_it_waits_out_more_429_answers_than_the_sdk_client_would(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    for _ in range(25):
        httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"Retry-After": "1"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert encryptor.totals.shed_429 == 25
    assert encryptor.totals.counts == {"encrypted": 1}


async def test_a_retry_after_longer_than_the_backoff_cap_is_honoured(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"Retry-After": "120"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path)

    await run(encryptor)

    assert fake.sleeps[0] == pytest.approx(120.0)


async def test_the_backoff_after_repeated_429_answers_grows_and_stops_at_its_cap(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    for _ in range(9):
        httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429)
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path)

    await run(encryptor)

    waits = fake.sleeps[:9]
    assert waits[0] < waits[1] < waits[2] < waits[3]
    assert all(wait <= 30.0 * 1.25 for wait in waits)
    assert waits[-1] >= 30.0


async def test_the_limit_halves_at_most_once_per_cooldown(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"Retry-After": "0"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"Retry-After": "0"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, _ = make(tmp_path, concurrency=16)

    await run(encryptor)

    assert encryptor.limit.decreases == 1
    assert encryptor.limit.limit == 4


# Adaptive limit


def test_the_limit_starts_at_half_the_maximum_and_never_below_the_minimum() -> None:
    fake = FakeTime()

    assert AdaptiveLimit(maximum=8, minimum=1, slow_factor=2.0, clock=fake.clock).limit == 4
    assert AdaptiveLimit(maximum=1, minimum=1, slow_factor=2.0, clock=fake.clock).limit == 1
    assert AdaptiveLimit(maximum=8, minimum=6, slow_factor=2.0, clock=fake.clock).limit == 6


def test_the_limit_rises_by_one_after_as_many_quiet_requests_as_the_limit() -> None:
    fake = FakeTime()
    limit = AdaptiveLimit(maximum=8, minimum=1, slow_factor=2.0, clock=fake.clock)

    for _ in range(3):
        limit.observe(0.01)
    assert limit.limit == 4
    limit.observe(0.01)
    assert limit.limit == 5
    assert limit.increases == 1
    for _ in range(100):
        limit.observe(0.01)
    assert limit.limit == 8


def test_a_slow_signal_halves_the_limit_and_the_limit_rises_again_when_it_is_quiet() -> None:
    fake = FakeTime()
    limit = AdaptiveLimit(maximum=8, minimum=1, slow_factor=2.0, clock=fake.clock)
    for _ in range(4):
        limit.observe(0.01)
    assert limit.limit == 5

    for _ in range(10):
        limit.observe(0.5)
    assert limit.limit == 2
    assert limit.decreases >= 1

    fake.now += 10_000
    for _ in range(40):
        limit.observe(0.5)
    assert limit.limit > 2


def test_the_limit_does_not_fall_below_the_minimum() -> None:
    fake = FakeTime()
    limit = AdaptiveLimit(maximum=8, minimum=3, slow_factor=2.0, clock=fake.clock)

    for _ in range(5):
        limit.shed()
        fake.now += 10

    assert limit.limit == 3


def test_a_second_decrease_inside_the_cooldown_is_ignored() -> None:
    fake = FakeTime()
    limit = AdaptiveLimit(maximum=16, minimum=1, slow_factor=2.0, clock=fake.clock)

    limit.shed()
    limit.shed()
    assert limit.limit == 4
    fake.now += 2.5
    limit.shed()
    assert limit.limit == 2


async def test_no_more_requests_are_in_flight_than_the_limit_allows() -> None:
    fake = FakeTime()
    limit = AdaptiveLimit(maximum=4, minimum=1, slow_factor=2.0, clock=fake.clock)
    assert limit.limit == 2
    await limit.acquire()
    await limit.acquire()

    with pytest.raises(asyncio.TimeoutError, match=r"^$"):
        await asyncio.wait_for(limit.acquire(), timeout=0.05)
    await limit.release()
    await asyncio.wait_for(limit.acquire(), timeout=1)


# Transient errors


async def test_a_503_answer_is_retried_after_a_backoff(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=503)
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=502)
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path)

    await run(encryptor)

    assert encryptor.totals.retries == 2
    assert encryptor.totals.counts == {"encrypted": 1}
    assert 0.5 <= fake.sleeps[0] <= 0.5 * 1.25
    assert 1.0 <= fake.sleeps[1] <= 1.0 * 1.25


async def test_a_connection_error_during_the_run_is_retried(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_exception(httpx.ReadError("connection reset"), method="POST", url=BATCH_URL)
    httpx_mock.add_exception(httpx.ConnectError("refused"), method="POST", url=BATCH_URL)
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert encryptor.totals.retries == 2
    assert encryptor.totals.counts == {"encrypted": 1}


async def test_retries_stop_after_max_retries(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    for _ in range(4):
        httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=503)
    encryptor, _ = make(tmp_path, max_retries=3)

    with pytest.raises(MigrationError, match=r"still fails after 3 retries: HTTP 503"):
        await run(encryptor)

    assert encryptor.totals.retries == 3


async def test_a_500_answer_is_not_retried(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=500, text="boom")

    with pytest.raises(MigrationError, match=r"HTTP 500"):
        await run(make(tmp_path)[0])

    assert len(httpx_mock.get_requests(method="POST")) == 1


async def test_a_server_that_never_answers_fails_after_a_few_retries(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_exception(httpx.ConnectError("refused"), is_reusable=True)
    encryptor, _ = make(tmp_path, max_retries=10)

    with pytest.raises(
        MigrationError, match=rf"cannot be reached .*ConnectError.*after {UNANSWERED_MAX_RETRIES} retries"
    ):
        await run(encryptor)

    assert encryptor.totals.retries == UNANSWERED_MAX_RETRIES


async def test_a_server_that_went_away_after_answering_gets_the_full_retries(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_exception(httpx.ConnectError("refused"), method="POST", url=BATCH_URL, is_reusable=True)
    encryptor, _ = make(tmp_path, max_retries=6)

    with pytest.raises(MigrationError, match=r"still fails after 6 retries"):
        await run(encryptor)

    assert encryptor.totals.retries == 6


# Refusals


@dataclass
class RefusalCase:
    name: str
    method: str
    status: int
    body: dict[str, Any] | str
    expected: str


REFUSAL_CASES = [
    RefusalCase(
        name="token-rejected",
        method="GET",
        status=401,
        body={"detail": "bad token"},
        expected="HTTP 401: the server does not accept the token",
    ),
    RefusalCase(
        name="no-super-admin-listing",
        method="GET",
        status=403,
        body={"detail": "no"},
        expected="HTTP 403: the account of this token does not have the super admin permission",
    ),
    RefusalCase(
        name="no-super-admin-batch",
        method="POST",
        status=403,
        body={"errors": [{"message": "Permission denied"}]},
        expected="Server answer: Permission denied",
    ),
    RefusalCase(
        name="no-routes",
        method="GET",
        status=404,
        body={"detail": "Not Found"},
        expected="does not have the storage encryption routes (/api/storage/objects)",
    ),
    RefusalCase(
        name="not-enabled",
        method="POST",
        status=409,
        body={"detail": "Storage encryption is not enabled"},
        expected="HTTP 409: storage encryption is not enabled on the server, or the server has no storage key",
    ),
    RefusalCase(
        name="invalid-batch",
        method="POST",
        status=422,
        body={"detail": "An identifier is listed twice."},
        expected="HTTP 422. Server answer: An identifier is listed twice.",
    ),
    RefusalCase(
        name="plain-text-body",
        method="GET",
        status=400,
        body="gateway says no",
        expected="HTTP 400. Server answer: gateway says no",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in REFUSAL_CASES])
async def test_a_refusal_is_explained(case: RefusalCase, httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    body: dict[str, Any] = {"json": case.body} if isinstance(case.body, dict) else {"text": case.body}
    if case.method == "GET":
        httpx_mock.add_response(method="GET", status_code=case.status, **body)
    else:
        httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
        httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=case.status, **body)
    encryptor, _ = make(tmp_path)

    with pytest.raises(MigrationError, match=re.escape(case.expected)):
        await run(encryptor)


async def test_the_server_text_of_a_refusal_is_part_of_the_message(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(method="GET", status_code=409, json={"detail": "No storage key is set"})

    with pytest.raises(MigrationError, match=r"Server answer: No storage key is set"):
        await run(make(tmp_path)[0])


# Connections


class _CountingServer(ThreadingHTTPServer):
    connections = 0


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        cast("_CountingServer", self.server).connections += 1

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        self._send(page(*[f"id{i:03d}" for i in range(40)]))

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._send(answer(*body["identifiers"]))


@pytest.fixture
def local_server() -> Iterator[_CountingServer]:
    server = _CountingServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
async def test_every_request_of_a_run_reuses_the_pooled_connection(
    local_server: _CountingServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    address = f"http://127.0.0.1:{local_server.server_address[1]}"
    original = httpx.AsyncClient

    def real_client(**kwargs: Any) -> httpx.AsyncClient:  # noqa: ANN401
        return original(transport=httpx.AsyncHTTPTransport(), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", real_client)
    encryptor, _ = make(tmp_path, address=address, concurrency=1, batch_size=4)

    async with httpx.AsyncClient(base_url=address) as http:
        await encryptor.run(http)

    assert encryptor.totals.encrypt_requests == 10
    assert encryptor.totals.requests == 11
    assert local_server.connections == 1


def test_the_batch_limit_matches_the_server() -> None:
    assert BATCH_MAX_SIZE == 500


async def test_an_answer_that_is_not_json_stops_the_run_with_a_message(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", text="<html>proxy page</html>")

    with pytest.raises(
        MigrationError, match=r"listing of the stored objects was answered with HTTP 200 and a body that is not JSON"
    ):
        await run(make(tmp_path)[0])


async def test_a_batch_answer_that_is_not_json_stops_the_run_with_a_message(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, text="not json")

    with pytest.raises(MigrationError, match=r"encrypt a batch was answered with HTTP 200 and a body that is not JSON"):
        await run(make(tmp_path)[0])


@pytest.mark.parametrize("body", [{"objects": []}, ["x"]])
async def test_a_listing_of_an_unexpected_shape_stops_the_run(
    httpx_mock: HTTPXMock, tmp_path: Path, body: object
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=body)

    with pytest.raises(MigrationError, match=r"listing of the stored objects has an unexpected shape"):
        await run(make(tmp_path)[0])


async def test_a_batch_answer_of_an_unexpected_shape_stops_the_run(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json={"unexpected": True})

    with pytest.raises(MigrationError, match=r"answer of an unexpected shape"):
        await run(make(tmp_path)[0])


# Count pass


def old_state(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """A state file as the version without the count pass wrote it."""
    state: dict[str, Any] = {
        "version": 1,
        "address": BASE,
        "start_after": "b",
        "completed": False,
        "totals": {
            "counts": {"encrypted": 2},
            "bytes_encrypted": 200,
            "bytes_listed": 200,
            "objects_listed": 2,
            "skipped_newer": 0,
            "requests": 3,
            "encrypt_requests": 1,
            "shed_429": 0,
            "shed_429_admission": 0,
            "retries": 0,
            "elapsed_seconds": 4.0,
            "limit_decreases": 0,
            "limit_increases": 0,
            "limit_final": 4,
        },
    }
    state.update(overrides)
    return state


def mock_count_and_run_of_three(httpx_mock: HTTPXMock) -> None:
    """Three objects of 100 bytes each, counted in two requests of 5000 and listed by the run in pages of 2."""
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=b", json=page("c"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        json=answer("a", "b"),
        match_json={"identifiers": ["a", "b"], "allow_unverified": False},
    )
    httpx_mock.add_response(
        method="POST", url=BATCH_URL, json=answer("c"), match_json={"identifiers": ["c"], "allow_unverified": False}
    )


async def test_the_count_pass_lists_with_the_largest_page_size_before_any_batch_is_sent(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    mock_count_and_run_of_three(httpx_mock)
    encryptor, _ = make(tmp_path, page_size=2, count=True)

    await run(encryptor)

    requests = httpx_mock.get_requests()
    assert (requests[0].method, dict(requests[0].url.params)) == ("GET", {"limit": "5000"})
    assert [r.method for r in requests].index("POST") > 1
    assert encryptor.remaining_objects == 3
    assert encryptor.remaining_bytes == 300


async def test_the_count_pass_follows_the_pages_and_adds_up_objects_and_bytes(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(
        url=f"{LIST_URL}?limit=5000&start_after=b",
        json={"objects": [stored("c", size=300)], "next_start_after": None},
    )
    encryptor, _ = make(tmp_path, count=True)

    async with httpx.AsyncClient(base_url=BASE) as http:
        await encryptor._count_pass(http)

    assert encryptor.remaining_objects == 3
    assert encryptor.remaining_bytes == 500
    assert sent_listing_params(httpx_mock) == [{"limit": "5000"}, {"limit": "5000", "start_after": "b"}]
    assert encryptor.total_objects == 3
    assert encryptor.total_bytes == 500


async def test_the_count_matches_the_objects_that_are_sent(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    mock_count_and_run_of_three(httpx_mock)
    encryptor, _ = make(tmp_path, page_size=2, count=True)

    await run(encryptor)

    assert sum(len(body["identifiers"]) for body in sent_bodies(httpx_mock)) == encryptor.total_objects == 3
    assert encryptor.done_objects == 3
    assert encryptor.done_bytes == encryptor.total_bytes == 300


async def test_the_count_pass_does_not_change_which_objects_are_sent(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    mock_count_and_run_of_three(httpx_mock)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    counted, _ = make(tmp_path / "a", page_size=2, count=True)
    await run(counted)
    with_count = sent_bodies(httpx_mock)
    uncounted, _ = make(tmp_path / "b", page_size=2, count=False)

    await run(uncounted)

    assert sent_bodies(httpx_mock)[len(with_count) :] == with_count


async def test_the_count_pass_leaves_out_objects_modified_after_before(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    objects = [stored("old", modified="2026-01-01T00:00:00Z"), stored("new", size=500, modified="2026-06-01T12:00:00Z")]
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json={"objects": objects, "next_start_after": None})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("old"))
    encryptor, _ = make(tmp_path, before=parse_timestamp("2026-03-01T00:00:00"), count=True)

    await run(encryptor)

    assert encryptor.remaining_objects == 1
    assert encryptor.remaining_bytes == 100
    assert encryptor.done_objects == 1


async def test_the_count_pass_stops_at_the_limit_and_requests_no_more_pages(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    encryptor, _ = make(tmp_path, limit=2, count=True)

    await run(encryptor)

    assert encryptor.remaining_objects == 2
    assert encryptor.total_objects == 2
    assert sent_listing_params(httpx_mock) == [{"limit": "5000"}, {"limit": "5000"}]


async def test_the_count_pass_cuts_the_last_page_at_the_limit(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", "d", next_start_after="d"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    encryptor, _ = make(tmp_path, limit=3, count=True)

    await run(encryptor)

    assert encryptor.remaining_objects == 3
    assert encryptor.remaining_bytes == 300
    assert encryptor.done_objects == 3


async def test_a_resumed_count_starts_at_the_saved_position_and_adds_the_objects_of_earlier_runs(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    (tmp_path / "state.json").write_text(json.dumps(old_state()))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=b", json=page("c"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    encryptor, _ = make(tmp_path, page_size=2, count=True)

    await run(encryptor)

    assert sent_listing_params(httpx_mock)[0] == {"limit": "5000", "start_after": "b"}
    assert encryptor.handled_before == 2
    assert encryptor.remaining_objects == 1
    assert encryptor.total_objects == 3
    assert encryptor.total_bytes == 300
    assert encryptor.done_objects == 3
    assert encryptor.done_bytes == 300


async def test_a_resumed_run_counts_again_and_does_not_trust_the_total_of_the_state_file(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    state = old_state(plan={"objects_total": 10, "bytes_total": 1000})
    (tmp_path / "state.json").write_text(json.dumps(state))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=b", json=page("c", "d"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c", "d"))
    encryptor, _ = make(tmp_path, count=True)

    await run(encryptor)

    assert encryptor.total_objects == 4
    assert encryptor.total_objects != 10
    plan = json.loads((tmp_path / "state.json").read_text())["plan"]
    assert plan == {"objects_total": 4, "bytes_total": 400}


async def test_a_state_file_of_the_version_without_the_count_pass_is_read_and_resumed(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    (tmp_path / "state.json").write_text(json.dumps(old_state()))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert encryptor.resumed is True
    assert encryptor.totals.counts == {"encrypted": 3}
    assert encryptor.handled_before == 2
    # The old file has no bytes of every outcome; the bytes of the encrypted objects are the nearest figure.
    assert encryptor.totals.bytes_handled == 300
    assert encryptor.total_objects is None


async def test_the_state_file_keeps_the_total_and_the_count_figures(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    mock_count_and_run_of_three(httpx_mock)
    encryptor, _ = make(tmp_path, page_size=2, count=True)

    await run(encryptor)

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["plan"] == {"objects_total": 3, "bytes_total": 300}
    assert state["totals"]["bytes_handled"] == 300
    assert state["totals"]["count_requests"] == 2
    assert state["totals"]["count_seconds"] == pytest.approx(0.0)
    assert state["version"] == 1


async def test_a_state_file_with_a_field_this_version_does_not_know_is_still_read(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    state = old_state()
    state["totals"]["field_of_a_later_version"] = 7
    (tmp_path / "state.json").write_text(json.dumps(state))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert encryptor.totals.counts == {"encrypted": 3}


async def test_without_the_count_pass_there_is_no_total_and_no_count_request(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, _ = make(tmp_path, count=False)

    await run(encryptor)

    assert sent_listing_params(httpx_mock) == [{"limit": "5000"}]
    assert encryptor.total_objects is None
    assert encryptor.total_bytes is None
    assert "plan" not in json.loads((tmp_path / "state.json").read_text())


async def test_a_dry_run_lists_once_and_totals_what_it_would_send(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    objects = [stored("old"), stored("new", size=500, modified="2026-06-01T12:00:00Z")]
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json={"objects": objects, "next_start_after": None})
    encryptor, _ = make(tmp_path, dry_run=True, count=True, before=parse_timestamp("2026-03-01T00:00:00"))

    await run(encryptor)

    assert sent_listing_params(httpx_mock) == [{"limit": "5000"}]
    assert encryptor.selected_objects == 1
    assert encryptor.selected_bytes == 100
    assert encryptor.totals.skipped_newer == 1


async def test_the_count_pass_is_kept_apart_from_the_requests_and_the_time_of_the_run(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    fake = FakeTime()

    def slow_count(request: httpx.Request) -> httpx.Response:
        fake.now += 10
        return httpx.Response(200, json=page("a", "b"))

    httpx_mock.add_callback(slow_count, url=f"{LIST_URL}?limit=5000")
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    encryptor, _ = make(tmp_path, fake=fake, page_size=2, count=True)

    await run(encryptor)

    assert encryptor.count_seconds_this_run == pytest.approx(10.0)
    assert encryptor.totals.count_seconds == pytest.approx(10.0)
    assert encryptor.totals.elapsed_seconds == pytest.approx(0.0)
    assert encryptor.totals.count_requests == 1
    assert encryptor.totals.requests == 2


async def test_more_objects_than_counted_are_still_sent_and_done_passes_the_total(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", "c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    encryptor, _ = make(tmp_path, page_size=2, count=True)

    await run(encryptor)

    assert encryptor.total_objects == 2
    assert encryptor.done_objects == 3
    assert encryptor.completed is True


async def test_the_callback_runs_once_after_the_count(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    mock_count_and_run_of_three(httpx_mock)
    seen: list[int | None] = []
    encryptor, _ = make(tmp_path, page_size=2, count=True)
    encryptor.on_counted = lambda: seen.append(encryptor.remaining_objects)

    await run(encryptor)

    assert seen == [3]


async def test_a_429_answer_during_the_count_is_waited_out_and_counted(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", status_code=429, headers={"Retry-After": "3"})
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path, page_size=5000, count=True)

    await run(encryptor)

    assert encryptor.totals.shed_429 >= 1
    assert max(fake.sleeps) >= 3.0
    assert encryptor.remaining_objects == 1


@dataclass
class CountRefusalCase:
    name: str
    status: int
    body: dict[str, Any]
    expected: str


COUNT_REFUSAL_CASES = [
    CountRefusalCase(
        name="token-rejected", status=401, body={"detail": "bad"}, expected="HTTP 401: the server does not accept"
    ),
    CountRefusalCase(
        name="no-super-admin", status=403, body={"detail": "no"}, expected="does not have the super admin permission"
    ),
    CountRefusalCase(
        name="no-routes",
        status=404,
        body={"detail": "Not Found"},
        expected="does not have the storage encryption routes",
    ),
    CountRefusalCase(
        name="not-enabled",
        status=409,
        body={"detail": "Storage encryption is not enabled"},
        expected="storage encryption is not enabled on the server",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in COUNT_REFUSAL_CASES])
async def test_a_refusal_during_the_count_stops_the_run_with_the_same_message_as_during_the_run(
    case: CountRefusalCase, httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(method="GET", status_code=case.status, json=case.body)
    encryptor, _ = make(tmp_path, count=True)

    with pytest.raises(MigrationError, match=re.escape(case.expected)) as raised:
        await run(encryptor)

    assert "The listing of the stored objects was refused" in str(raised.value)
    assert httpx_mock.get_requests(method="POST") == []
    assert len(httpx_mock.get_requests()) == 1
    assert not (tmp_path / "state.json").exists()
    assert encryptor.counting is False
    assert encryptor.total_objects is None


async def test_a_refusal_on_a_later_page_of_the_count_stops_the_run_before_any_batch(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", next_start_after="a"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=a", status_code=403, json={"detail": "no"})
    encryptor, _ = make(tmp_path, count=True)

    with pytest.raises(MigrationError, match="super admin"):
        await run(encryptor)

    assert httpx_mock.get_requests(method="POST") == []


async def test_a_server_that_cannot_be_reached_during_the_count_stops_the_run_with_the_cause(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"), is_reusable=True)
    encryptor, _ = make(tmp_path, count=True)

    with pytest.raises(MigrationError, match=r"cannot be reached \(ConnectError: connection refused\)"):
        await run(encryptor)

    assert len(httpx_mock.get_requests()) == UNANSWERED_MAX_RETRIES + 1
    assert encryptor.totals.requests == 0
    assert not (tmp_path / "state.json").exists()


@pytest.mark.parametrize("body", ["not json", '{"unexpected": 1}'], ids=["not-json", "unexpected-shape"])
async def test_an_unreadable_count_listing_stops_the_run_with_a_message(
    body: str, httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(method="GET", text=body)
    encryptor, _ = make(tmp_path, count=True)

    with pytest.raises(MigrationError, match="listing of the stored objects"):
        await run(encryptor)

    assert httpx_mock.get_requests(method="POST") == []


async def test_cancelling_the_run_during_the_count_saves_nothing_and_ends_the_count(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    async def never_answers(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)
        raise AssertionError("not reached")

    httpx_mock.add_callback(never_answers, url=f"{LIST_URL}?limit=5000")
    encryptor, _ = make(tmp_path, count=True)
    task = asyncio.create_task(run(encryptor))
    for _ in range(50):
        if encryptor.counting:
            break
        await asyncio.sleep(0.01)
    assert encryptor.counting is True

    task.cancel()
    with pytest.raises(asyncio.CancelledError, match=r"^$"):
        await task

    assert encryptor.counting is False
    assert not (tmp_path / "state.json").exists()
    assert encryptor.totals.requests == 0


# Retry-After and backoff limits


def test_the_backoff_does_not_overflow_for_a_very_high_attempt() -> None:
    delay = backoff_delay(attempt=5000, rng=random.Random(1))

    assert 30.0 <= delay <= 30.0 * 1.25


async def test_a_retry_after_beyond_the_maximum_pause_is_cut_and_said(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"Retry-After": "100000"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path)
    notices: list[str] = []
    encryptor.on_notice = notices.append

    await run(encryptor)

    assert fake.sleeps[0] == pytest.approx(RETRY_AFTER_MAX_SECONDS)
    assert len(notices) == 1
    assert "asked for a pause of 100000 seconds" in notices[0]


async def test_a_retry_after_that_is_not_finite_waits_the_backoff_only(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=429, headers={"Retry-After": "inf"})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path)

    await run(encryptor)

    assert fake.sleeps[0] < 1.0
    assert encryptor.totals.counts == {"encrypted": 1}


async def test_a_retry_after_given_as_a_date_is_honoured(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(
        method="POST",
        url=BATCH_URL,
        status_code=429,
        headers={"Retry-After": formatdate(time.time() + 60, usegmt=True)},
    )
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))
    encryptor, fake = make(tmp_path)

    await run(encryptor)

    assert 50.0 < fake.sleeps[0] <= 60.0


def test_a_first_latency_sample_of_zero_does_not_set_the_floor_to_zero() -> None:
    fake = FakeTime()
    limit = AdaptiveLimit(maximum=8, minimum=1, slow_factor=2.0, clock=fake.clock)

    limit.observe(0.0)
    limit.observe(0.01)
    limit.observe(0.01)

    assert limit.decreases == 0


# Expired login


EXPIRED = {"errors": [{"message": "Expired Signature", "extensions": {"code": 401}}]}


class Login:
    """Stands for the new login of the command: it sets a new token on the client of the run."""

    def __init__(self, delay: float = 0.0) -> None:
        self.calls = 0
        self.delay = delay

    async def __call__(self, http: httpx.AsyncClient) -> None:
        self.calls += 1
        await asyncio.sleep(self.delay)
        http.headers["Authorization"] = "Bearer new"


def reject_the_old_token(request: httpx.Request) -> httpx.Response:
    if request.headers.get("Authorization") == "Bearer old":
        return httpx.Response(401, json=EXPIRED)
    return httpx.Response(200, json=answer(*json.loads(request.content)["identifiers"]))


async def test_an_expired_token_is_renewed_and_the_request_is_sent_again(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_callback(reject_the_old_token, method="POST", url=BATCH_URL)
    encryptor, _ = make(tmp_path)
    login = Login()
    encryptor.refresh_login = login

    await run(encryptor, headers={"Authorization": "Bearer old"})

    assert login.calls == 1
    posts = httpx_mock.get_requests(method="POST")
    assert [r.headers["Authorization"] for r in posts] == ["Bearer old", "Bearer new"]
    assert encryptor.totals.counts == {"encrypted": 2}


async def test_a_token_that_cannot_be_renewed_stops_the_run_with_the_refusal(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=401, json=EXPIRED)
    encryptor, _ = make(tmp_path)

    with pytest.raises(MigrationError, match=r"HTTP 401: the server does not accept the token or credentials"):
        await run(encryptor, headers={"Authorization": "Bearer old"})

    assert len(httpx_mock.get_requests(method="POST")) == 1


async def test_a_401_that_does_not_say_the_token_expired_is_not_retried(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=401, json={"detail": "Not allowed"})
    encryptor, _ = make(tmp_path)
    login = Login()
    encryptor.refresh_login = login

    with pytest.raises(MigrationError, match=r"HTTP 401"):
        await run(encryptor)

    assert login.calls == 0


async def test_a_request_is_renewed_once_and_not_in_a_loop(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=401, json=EXPIRED)
    encryptor, _ = make(tmp_path)
    login = Login()
    encryptor.refresh_login = login

    with pytest.raises(MigrationError, match=r"HTTP 401"):
        await run(encryptor, headers={"Authorization": "Bearer old"})

    assert login.calls == 1
    assert len(httpx_mock.get_requests(method="POST")) == 2


async def test_two_requests_that_get_a_401_together_renew_the_login_once(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", "d"))
    httpx_mock.add_callback(reject_the_old_token, method="POST", url=BATCH_URL)
    encryptor, _ = make(tmp_path, concurrency=4)
    assert encryptor.limit.limit == 2
    login = Login(delay=0.05)
    encryptor.refresh_login = login

    await run(encryptor, headers={"Authorization": "Bearer old"})

    assert login.calls == 1
    assert encryptor.totals.counts == {"encrypted": 4}


async def test_a_login_that_fails_stops_the_run_with_a_message(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    async def failing(http: httpx.AsyncClient) -> None:
        raise httpx.ConnectError("connection refused")

    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=401, json=EXPIRED)
    encryptor, _ = make(tmp_path)
    encryptor.refresh_login = failing

    with pytest.raises(MigrationError, match=r"new login failed \(ConnectError: connection refused\)"):
        await run(encryptor)


# Files checked before the run


def files_at(option: str, path: Path) -> dict[str, Any]:
    return {option: path}


async def test_a_missing_directory_for_the_state_file_stops_the_run_before_any_request(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    encryptor, _ = make(tmp_path, state_file=tmp_path / "missing" / "state.json", count=True)

    with pytest.raises(MigrationError, match=r"directory of --state-file .* does not exist"):
        await run(encryptor)

    assert httpx_mock.get_requests() == []


async def test_a_missing_directory_for_the_report_stops_the_run_before_the_count(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    encryptor, _ = make(tmp_path, report=tmp_path / "missing" / "report.jsonl", count=True)

    with pytest.raises(MigrationError, match=r"directory of --report .* does not exist"):
        await run(encryptor)

    assert httpx_mock.get_requests() == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
@pytest.mark.parametrize("option", ["state_file", "report"])
async def test_a_directory_that_cannot_be_written_stops_the_run_before_any_request(
    httpx_mock: HTTPXMock, tmp_path: Path, option: str
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    encryptor, _ = make(tmp_path, **files_at(option, locked / "file"))

    try:
        with pytest.raises(MigrationError, match=r"is not writable"):
            await run(encryptor)
    finally:
        locked.chmod(0o700)

    assert httpx_mock.get_requests() == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
@pytest.mark.parametrize("option", ["state_file", "report"])
async def test_a_file_that_cannot_be_written_stops_the_run_before_any_request(
    httpx_mock: HTTPXMock, tmp_path: Path, option: str
) -> None:
    path = tmp_path / "readonly"
    path.write_text("{}")
    path.chmod(0o400)
    encryptor, _ = make(tmp_path, **files_at(option, path))

    with pytest.raises(MigrationError, match=r"cannot be written"):
        await run(encryptor)

    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("option", ["state_file", "report"])
async def test_a_directory_given_as_a_file_stops_the_run_before_any_request(
    httpx_mock: HTTPXMock, tmp_path: Path, option: str
) -> None:
    encryptor, _ = make(tmp_path, **files_at(option, tmp_path))

    with pytest.raises(MigrationError, match=r"cannot be written"):
        await run(encryptor)

    assert httpx_mock.get_requests() == []


async def test_a_dry_run_does_not_need_the_state_file_or_the_report(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    encryptor, _ = make(
        tmp_path, dry_run=True, state_file=tmp_path / "x" / "state.json", report=tmp_path / "y" / "report.jsonl"
    )

    await run(encryptor)

    assert encryptor.totals.objects_listed == 1


# Runs cut short by --limit and runs that add to the report


def serve_objects(httpx_mock: HTTPXMock, identifiers: list[str]) -> list[str]:
    """Serve the listing of `identifiers` after the `start_after` parameter, and record what is sent."""
    sent: list[str] = []

    def listing(request: httpx.Request) -> httpx.Response:
        after = request.url.params.get("start_after")
        rest = identifiers[identifiers.index(after) + 1 :] if after else identifiers
        return httpx.Response(200, json=page(*rest))

    def encrypt(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)["identifiers"]
        sent.extend(batch)
        return httpx.Response(200, json=answer(*batch))

    httpx_mock.add_callback(listing, method="GET", url=re.compile(rf"{re.escape(LIST_URL)}\?.*"))
    httpx_mock.add_callback(encrypt, method="POST", url=BATCH_URL)
    return sent


async def test_runs_cut_by_limit_send_every_object_once_and_leave_the_position_at_the_last_sent(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    identifiers = [f"o{n}" for n in range(10)]
    sent = serve_objects(httpx_mock, identifiers)
    positions: list[tuple[str | None, bool]] = []

    for _ in range(4):
        encryptor, _ = make(tmp_path, limit=3)
        await run(encryptor)
        state = json.loads((tmp_path / "state.json").read_text())
        positions.append((state["start_after"], state["completed"]))

    assert sent == identifiers
    assert positions == [("o2", False), ("o5", False), ("o8", False), ("o9", True)]


async def test_every_run_adds_to_the_report(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", outcome="skipped_unverified"))

    for _ in range(2):
        encryptor, _ = make(tmp_path)
        await run(encryptor)

    lines = (tmp_path / "report.jsonl").read_text().splitlines()
    assert [json.loads(line)["identifier"] for line in lines] == ["a", "a"]


# Listings whose next position is not the last listed object


LISTING_REQUEST_LIMIT = 20


def serve_pages(
    httpx_mock: HTTPXMock, pages: dict[str | None, dict[str, Any]], refuse_batches: bool = False
) -> tuple[list[str | None], list[str]]:
    """Serve each listing page by the `start_after` it is asked for, and record the positions asked and the objects sent.

    A server that is asked more than `LISTING_REQUEST_LIMIT` times answers 400, so a command that never advances
    ends with an error instead of running for ever.
    """
    asked: list[str | None] = []
    sent: list[str] = []

    def listing(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params.get("start_after"))
        if len(asked) > LISTING_REQUEST_LIMIT:
            return httpx.Response(400, json={"detail": "listing asked too often"})
        return httpx.Response(200, json=pages[asked[-1]])

    def encrypt(request: httpx.Request) -> httpx.Response:
        if refuse_batches:
            return httpx.Response(403, json={"detail": "no"})
        batch = json.loads(request.content)["identifiers"]
        sent.extend(batch)
        return httpx.Response(200, json=answer(*batch))

    httpx_mock.add_callback(listing, method="GET", url=re.compile(rf"{re.escape(LIST_URL)}\?.*"))
    httpx_mock.add_callback(encrypt, method="POST", url=BATCH_URL, is_optional=True)
    return asked, sent


async def test_an_empty_page_with_a_next_position_is_followed_and_never_listed_twice(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    asked, sent = serve_pages(httpx_mock, {None: page(next_start_after="b"), "b": page("c")})
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert asked == [None, "b"]
    assert sent == ["c"]
    assert encryptor.totals.objects_listed == 1
    assert encryptor.totals.counts == {"encrypted": 1}
    assert encryptor.completed is True
    state = json.loads((tmp_path / "state.json").read_text())
    assert (state["start_after"], state["completed"]) == ("c", True)


async def test_the_state_file_moves_to_the_next_position_of_an_empty_page(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    asked, _ = serve_pages(httpx_mock, {None: page(next_start_after="b"), "b": page("c")}, refuse_batches=True)
    encryptor, _ = make(tmp_path)

    with pytest.raises(MigrationError, match="HTTP 403"):
        await run(encryptor)

    assert asked == [None, "b"]
    state = json.loads((tmp_path / "state.json").read_text())
    assert (state["start_after"], state["completed"]) == ("b", False)
    assert encryptor.start_after == "b"


async def test_a_next_position_beyond_the_last_listed_object_is_the_new_position(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    asked, sent = serve_pages(httpx_mock, {None: page("a", "b", next_start_after="c"), "c": page("d")})
    encryptor, _ = make(tmp_path)

    await run(encryptor)

    assert asked == [None, "c"]
    assert sent == ["a", "b", "d"]
    assert encryptor.totals.objects_listed == 3
    assert json.loads((tmp_path / "state.json").read_text())["start_after"] == "d"


async def test_a_server_that_repeats_the_position_it_was_given_stops_the_run(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    asked, sent = serve_pages(httpx_mock, {None: page("a", next_start_after="a"), "a": page(next_start_after="a")})
    encryptor, _ = make(tmp_path)

    with pytest.raises(MigrationError, match="does not advance"):
        await run(encryptor)

    assert asked == [None, "a"]
    assert sent == ["a"]
    assert encryptor.completed is False
    assert json.loads((tmp_path / "state.json").read_text())["start_after"] == "a"


async def test_a_server_that_repeats_the_position_stops_the_count_before_any_batch(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    asked, sent = serve_pages(httpx_mock, {None: page("a", next_start_after="a"), "a": page(next_start_after="a")})
    encryptor, _ = make(tmp_path, count=True)

    with pytest.raises(MigrationError, match="does not advance"):
        await run(encryptor)

    assert asked == [None, "a"]
    assert sent == []


async def test_a_limit_that_cuts_a_page_keeps_the_last_sent_object_as_the_position(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    pages = {None: page("a", "b", "c", "d", next_start_after="e"), "b": page("c", "d", next_start_after="e")}
    asked, sent = serve_pages(httpx_mock, pages)
    encryptor, _ = make(tmp_path, limit=2)

    await run(encryptor)

    state = json.loads((tmp_path / "state.json").read_text())
    assert (state["start_after"], state["completed"]) == ("b", False)
    assert sent == ["a", "b"]

    pages["b"] = page("c", "d")
    again, _ = make(tmp_path, limit=2)
    await run(again)

    assert asked == [None, "b"]
    assert sent == ["a", "b", "c", "d"]
    assert json.loads((tmp_path / "state.json").read_text())["completed"] is True


async def test_the_count_and_the_run_agree_on_pages_that_are_empty_or_end_beyond_their_last_object(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    pages = {
        None: page(next_start_after="b"),
        "b": page("c", "d", next_start_after="e"),
        "e": page(next_start_after="f"),
        "f": page("g"),
    }
    asked, sent = serve_pages(httpx_mock, pages)
    encryptor, _ = make(tmp_path, count=True)

    await run(encryptor)

    assert sent == ["c", "d", "g"]
    assert asked == [None, "b", "e", "f"] * 2
    assert encryptor.remaining_objects == encryptor.total_objects == encryptor.done_objects == 3
    assert encryptor.done_bytes == encryptor.total_bytes == 300


class RecordingLimit(AdaptiveLimit):
    """An adaptive limit that keeps the latency samples it is given."""

    def __init__(self, maximum: int, minimum: int, slow_factor: float, clock: Callable[[], float]) -> None:
        super().__init__(maximum=maximum, minimum=minimum, slow_factor=slow_factor, clock=clock)
        self.observed: list[float] = []

    def observe(self, seconds: float) -> None:
        self.observed.append(seconds)
        super().observe(seconds)


async def test_the_pace_of_the_command_is_not_counted_as_the_latency_of_the_server(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    identifiers = ["a", "b", "c", "d", "e", "f"]
    encryptor, fake = make(tmp_path, concurrency=8, batch_size=1, rate=1.0)
    encryptor.limit = RecordingLimit(maximum=8, minimum=1, slow_factor=2.0, clock=fake.clock)

    def server_that_takes_a_tenth_of_a_second(request: httpx.Request) -> httpx.Response:
        fake.now += 0.1
        return httpx.Response(200, json=answer(*json.loads(request.content)["identifiers"]))

    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page(*identifiers))
    for _ in identifiers:
        httpx_mock.add_callback(server_that_takes_a_tenth_of_a_second, method="POST", url=BATCH_URL)

    await run(encryptor)

    assert encryptor.totals.counts == {"encrypted": 6}
    assert sum(fake.sleeps) > 4.0
    assert len(encryptor.limit.observed) == 6
    assert max(encryptor.limit.observed) < 0.11


@dataclass
class ServerTextCase:
    name: str
    response: httpx.Response
    expected: str


SERVER_TEXT_CASES = [
    ServerTextCase(
        name="plain_text",
        response=httpx.Response(500, text="boom \x1b[31mred\x07 end"),
        expected="boom  [31mred  end",
    ),
    ServerTextCase(
        name="detail",
        response=httpx.Response(409, json={"detail": "refused\x1b]0;title\x07"}),
        expected="refused ]0;title ",
    ),
    ServerTextCase(
        name="graphql_errors",
        response=httpx.Response(200, json={"errors": [{"message": "one\r\ntwo"}, {"message": "three\x9b"}]}),
        expected="one  two; three ",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in SERVER_TEXT_CASES])
def test_the_text_of_a_server_error_has_no_control_characters(case: ServerTextCase) -> None:
    assert server_detail(case.response) == case.expected
