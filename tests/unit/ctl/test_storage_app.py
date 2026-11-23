from __future__ import annotations

import asyncio
import json
import os
import signal
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl import config
from infrahub_sdk.ctl.storage import app
from infrahub_sdk.ctl.storage import encrypt as encrypt_module
from infrahub_sdk.ctl.storage import migration as migration_module
from infrahub_sdk.ctl.storage.migration import Options, StorageEncryptor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from click.testing import Result
    from pytest_httpx import HTTPXMock

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

runner = CliRunner()

BASE = "http://mock"
LIST_URL = f"{BASE}/api/storage/objects"
BATCH_URL = f"{BASE}/api/storage/objects/encrypt"
OLD = "2026-01-01T00:00:00Z"


def page(*identifiers: str, next_start_after: str | None = None) -> dict[str, Any]:
    objects = [{"identifier": i, "size": 100, "last_modified": OLD} for i in identifiers]
    return {"objects": objects, "next_start_after": next_start_after}


def answer(*identifiers: str, outcome: str = "encrypted", reason: str | None = None) -> dict[str, Any]:
    return {"results": [{"identifier": i, "outcome": outcome, "size": 100, "reason": reason} for i in identifiers]}


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(migration_module, "BACKOFF_BASE_SECONDS", 0.0)
    return ["--state-file", str(tmp_path / "state.json"), "--report", str(tmp_path / "report.jsonl")]


def invoke(files: list[str], *args: str) -> Result:
    return runner.invoke(app=app, args=["encrypt", "--no-count", *files, *args])


def invoke_counting(files: list[str], *args: str) -> Result:
    return runner.invoke(app=app, args=["encrypt", *files, *args])


def test_a_run_prints_a_summary_and_exits_0(httpx_mock: HTTPXMock, files: list[str], tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))

    result = invoke(files)

    assert result.exit_code == 0, result.stdout
    assert "Storage encryption" in result.stdout
    assert "Objects listed" in result.stdout
    assert "encrypted" in result.stdout
    assert "Answers 429" in result.stdout
    assert "In flight limit" in result.stdout
    assert "Pass finished" in result.stdout
    assert json.loads((tmp_path / "state.json").read_text())["completed"] is True


def test_objects_the_server_skips_do_not_fail_the_run_and_are_reported(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", outcome="skipped_unverified", reason="x"))

    result = invoke(files)

    assert result.exit_code == 0, result.stdout
    assert "skipped_unverified" in result.stdout
    assert json.loads((tmp_path / "report.jsonl").read_text())["identifier"] == "a"


def test_a_run_that_encrypts_every_object_does_not_point_to_the_report(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))

    result = invoke(files)

    assert result.exit_code == 0, result.stdout
    assert "were not encrypted" not in result.stdout
    assert (tmp_path / "report.jsonl").stat().st_size == 0


def test_a_run_that_leaves_an_object_unchanged_points_to_the_report(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b", outcome="already_encrypted"))

    result = invoke(files)

    assert result.exit_code == 0, result.stdout
    assert f"were not encrypted are listed in {tmp_path / 'report.jsonl'}" in result.stdout.replace("\n", " ")


def test_an_object_that_failed_makes_the_exit_code_1(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", outcome="failed", reason="disk full"))

    result = invoke(files)

    assert result.exit_code == 1, result.stdout
    assert "failed" in result.stdout


def test_the_requests_carry_the_token_and_the_priority(
    httpx_mock: HTTPXMock, files: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config.SETTINGS.active, "api_token", "secret-token")
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))

    result = invoke(files, "--priority", "medium")

    assert result.exit_code == 0, result.stdout
    for request in httpx_mock.get_requests():
        assert request.headers["X-INFRAHUB-KEY"] == "secret-token"
        assert request.headers["X-Priority"] == "medium"


def test_the_priority_is_read_in_any_case(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))

    result = invoke(files, "--priority", "HIGH")

    assert result.exit_code == 0, result.stdout
    assert {r.headers["X-Priority"] for r in httpx_mock.get_requests()} == {"high"}


def test_the_default_priority_is_low(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))

    invoke(files)

    assert {r.headers["X-Priority"] for r in httpx_mock.get_requests()} == {"low"}


def test_the_options_reach_the_requests(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=3", json=page("a", "b", "c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))

    result = invoke(files, "--page-size", "3", "--batch-size", "2", "--allow-unverified", "--concurrency", "1")

    assert result.exit_code == 0, result.stdout
    bodies = [json.loads(r.content) for r in httpx_mock.get_requests(method="POST")]
    assert bodies == [
        {"identifiers": ["a", "b"], "allow_unverified": True},
        {"identifiers": ["c"], "allow_unverified": True},
    ]


def test_a_dry_run_only_lists(httpx_mock: HTTPXMock, files: list[str], tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))

    result = invoke(files, "--dry-run")

    assert result.exit_code == 0, result.stdout
    assert httpx_mock.get_requests(method="POST") == []
    assert "dry run" in result.stdout
    assert "Objects that would be sent" in result.stdout
    assert not (tmp_path / "state.json").exists()


def test_a_second_run_resumes_from_the_state_file(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    assert invoke(files, "--page-size", "2", "--limit", "2").exit_code == 0

    result = invoke(files, "--page-size", "2")

    assert result.exit_code == 0, result.stdout
    listings = [r.url.query for r in httpx_mock.get_requests(method="GET")]
    assert listings == [b"limit=2", b"limit=2&start_after=b"]
    assert "3" in result.stdout


@dataclass
class ErrorCase:
    name: str
    listing_status: int
    batch_status: int | None
    body: dict[str, Any]
    expected: str


ERROR_CASES = [
    ErrorCase(
        name="no-routes",
        listing_status=404,
        batch_status=None,
        body={"detail": "Not Found"},
        expected="does not have the storage encryption routes",
    ),
    ErrorCase(
        name="no-super-admin",
        listing_status=403,
        batch_status=None,
        body={"detail": "Forbidden"},
        expected="does not have the super admin permission",
    ),
    ErrorCase(
        name="token-rejected",
        listing_status=401,
        batch_status=None,
        body={"detail": "Unauthorized"},
        expected="does not accept the token",
    ),
    ErrorCase(
        name="encryption-disabled",
        listing_status=200,
        batch_status=409,
        body={"detail": "Storage encryption is not enabled."},
        expected="storage encryption is not enabled on the server",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in ERROR_CASES])
def test_a_refusal_prints_its_meaning_and_exits_2(
    case: ErrorCase, httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    if case.batch_status is None:
        httpx_mock.add_response(method="GET", status_code=case.listing_status, json=case.body)
    else:
        httpx_mock.add_response(method="GET", json=page("a"))
        httpx_mock.add_response(method="POST", status_code=case.batch_status, json=case.body)

    result = invoke(files)

    assert result.exit_code == 2, result.stdout
    assert case.expected in result.stdout.replace("\n", " ")
    assert "Traceback" not in result.stdout
    assert "Progress is saved" not in result.stdout
    assert not (tmp_path / "state.json").exists()


def test_an_error_after_a_complete_page_says_where_to_resume(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", status_code=403, json={"detail": "no"})

    result = invoke(files, "--page-size", "2")

    assert result.exit_code == 2, result.stdout
    assert "Progress is saved in" in result.stdout.replace("\n", " ")
    assert "run the same command again to resume" in result.stdout.replace("\n", " ")
    assert json.loads((tmp_path / "state.json").read_text())["start_after"] == "b"


def test_the_message_of_the_server_is_printed_without_markup_loss(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(method="GET", status_code=409, json={"detail": "No key [storage] is set"})

    result = invoke(files)

    assert result.exit_code == 2
    assert "No key [storage] is set" in result.stdout.replace("\n", " ")


def test_a_server_that_cannot_be_reached_exits_2_with_the_cause(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"), is_reusable=True)

    result = invoke(files)

    assert result.exit_code == 2, result.stdout
    text = result.stdout.replace("\n", " ")
    assert "cannot be reached" in text
    assert "ConnectError: connection refused" in text


def test_a_state_file_of_another_server_exits_2(httpx_mock: HTTPXMock, files: list[str], tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"address": "http://other", "start_after": None, "completed": False, "totals": {}})
    )

    result = invoke(files)

    assert result.exit_code == 2
    assert "belongs to http://other" in result.stdout.replace("\n", " ")


@dataclass
class OptionCase:
    name: str
    args: list[str]


OPTION_CASES = [
    OptionCase(name="priority", args=["--priority", "urgent"]),
    OptionCase(name="batch-size-too-large", args=["--batch-size", "501"]),
    OptionCase(name="page-size-too-large", args=["--page-size", "5001"]),
    OptionCase(name="concurrency-zero", args=["--concurrency", "0"]),
    OptionCase(name="concurrency-too-large", args=["--concurrency", "65"]),
    OptionCase(name="rate-zero", args=["--rate", "0"]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in OPTION_CASES])
def test_an_invalid_option_is_refused_before_any_request(
    case: OptionCase, httpx_mock: HTTPXMock, files: list[str]
) -> None:
    result = invoke(files, *case.args)

    assert result.exit_code == 2
    assert "Invalid value for" in result.output
    assert httpx_mock.get_requests() == []


def test_ctrl_c_stops_the_run_and_keeps_the_state(httpx_mock: HTTPXMock, files: list[str], tmp_path: Path) -> None:
    async def interrupt(request: httpx.Request) -> httpx.Response:
        os.kill(os.getpid(), signal.SIGINT)
        await asyncio.sleep(30)
        raise AssertionError("not reached")

    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_callback(interrupt, url=f"{LIST_URL}?limit=2&start_after=b")

    result = invoke(files, "--page-size", "2")

    assert result.exit_code == 130, result.stdout
    assert "Stopped" in result.stdout
    assert "Run the same command again" in result.stdout.replace("\n", " ")
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["start_after"] == "b"
    assert state["completed"] is False
    assert state["totals"]["counts"] == {"encrypted": 2}


def text_of(result: Result) -> str:
    return result.stdout.replace("\n", " ")


def squeezed(result: Result) -> str:
    return " ".join(result.stdout.split())


def test_a_server_that_repeats_the_position_it_was_given_exits_2_with_a_message(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    pages = {None: page("a", next_start_after="a"), "a": page(next_start_after="a")}
    asked: list[str | None] = []

    def listing(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params.get("start_after"))
        if len(asked) > 20:
            return httpx.Response(400, json={"detail": "listing asked too often"})
        return httpx.Response(200, json=pages[asked[-1]])

    httpx_mock.add_callback(listing, method="GET")
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a"))

    result = invoke(files)

    assert result.exit_code == 2, result.stdout
    assert "does not advance" in text_of(result)
    assert asked == [None, "a"]
    assert json.loads((tmp_path / "state.json").read_text())["start_after"] == "a"


def mock_three_objects(httpx_mock: HTTPXMock) -> None:
    """Three objects: counted with one request of 5000, listed by the run in pages of 2."""
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"), match_json=None)


def test_a_run_counts_first_prints_the_total_and_ends_with_done_over_total(
    httpx_mock: HTTPXMock, files: list[str]
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))

    result = invoke_counting(files)

    assert result.exit_code == 0, result.stdout
    assert "To process: 2 objects (200 B)" in result.stdout
    assert "Already handled in earlier runs" not in result.stdout
    assert "2 / 2 objects (100.0%)" in result.stdout
    assert "Bytes done in total" in result.stdout
    assert "Seconds counting" in result.stdout
    assert result.stdout.index("To process") < result.stdout.index("Storage encryption")


def test_the_count_pass_uses_the_largest_page_size_and_the_priority_and_token_of_the_run(
    httpx_mock: HTTPXMock, files: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config.SETTINGS.active, "api_token", "secret-token")
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))

    result = invoke_counting(files, "--page-size", "2", "--priority", "medium")

    assert result.exit_code == 0, result.stdout
    listings = httpx_mock.get_requests(method="GET")
    assert [r.url.query for r in listings] == [b"limit=5000", b"limit=2"]
    for request in listings:
        assert request.headers["X-Priority"] == "medium"
        assert request.headers["X-INFRAHUB-KEY"] == "secret-token"


def test_a_run_with_no_count_prints_no_total_and_lists_once(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))

    result = invoke(files)

    assert result.exit_code == 0, result.stdout
    assert "To process" not in result.stdout
    assert "Seconds counting" not in result.stdout
    assert "Done in total" not in result.stdout
    assert len(httpx_mock.get_requests(method="GET")) == 1


def test_a_resumed_run_prints_what_earlier_runs_handled_and_the_total_of_the_whole_pass(
    httpx_mock: HTTPXMock, files: list[str]
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    assert invoke(files, "--page-size", "2", "--limit", "2").exit_code == 0
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=b", json=page("c"))

    result = invoke_counting(files, "--page-size", "2")

    assert result.exit_code == 0, result.stdout
    assert "To process: 1 objects (100 B)" in result.stdout
    assert "Already handled in earlier runs: 2 objects" in result.stdout
    assert "3 / 3 objects (100.0%)" in result.stdout


def test_a_dry_run_prints_the_total_it_found_and_does_not_count_first(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))

    result = invoke_counting(files, "--dry-run")

    assert result.exit_code == 0, result.stdout
    assert "To process: 2 objects (200 B)" in result.stdout
    assert "Bytes that would be sent" in result.stdout
    assert len(httpx_mock.get_requests()) == 1


def test_a_dry_run_with_before_and_limit_totals_only_the_objects_it_would_send(
    httpx_mock: HTTPXMock, files: list[str]
) -> None:
    objects = [
        {"identifier": "old1", "size": 100, "last_modified": OLD},
        {"identifier": "new", "size": 900, "last_modified": "2026-06-01T00:00:00Z"},
        {"identifier": "old2", "size": 100, "last_modified": OLD},
        {"identifier": "old3", "size": 100, "last_modified": OLD},
    ]
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json={"objects": objects, "next_start_after": None})

    result = invoke(files, "--dry-run", "--before", "2026-03-01", "--limit", "2")

    assert result.exit_code == 0, result.stdout
    assert "To process: 2 objects (200 B)" in result.stdout


def test_the_total_follows_before_and_limit(httpx_mock: HTTPXMock, files: list[str]) -> None:
    objects = [
        {"identifier": "old1", "size": 100, "last_modified": OLD},
        {"identifier": "new", "size": 900, "last_modified": "2026-06-01T00:00:00Z"},
        {"identifier": "old2", "size": 100, "last_modified": OLD},
        {"identifier": "old3", "size": 100, "last_modified": OLD},
    ]
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json={"objects": objects, "next_start_after": None})
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("old1", "old2"))

    result = invoke_counting(files, "--before", "2026-03-01", "--limit", "2")

    assert result.exit_code == 0, result.stdout
    assert "To process: 2 objects (200 B)" in result.stdout
    assert "2 / 2 objects (100.0%)" in result.stdout


def test_an_error_during_the_run_prints_done_over_total(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", status_code=409, json={"detail": "Storage encryption is not enabled."})

    result = invoke_counting(files)

    assert result.exit_code == 2, result.stdout
    assert "Done before the error: 0 / 2 objects (0.0%)." in text_of(result)


def test_a_refusal_during_the_count_stops_the_run_with_a_clear_message_and_sends_nothing(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    httpx_mock.add_response(method="GET", status_code=403, json={"detail": "no"})

    result = invoke_counting(files)

    assert result.exit_code == 2, result.stdout
    assert "does not have the super admin permission" in text_of(result)
    assert "To process" not in result.stdout
    assert httpx_mock.get_requests(method="POST") == []
    assert not (tmp_path / "state.json").exists()


def test_a_server_that_cannot_be_reached_during_the_count_exits_2(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"), is_reusable=True)

    result = invoke_counting(files)

    assert result.exit_code == 2, result.stdout
    assert "ConnectError: connection refused" in text_of(result)
    assert httpx_mock.get_requests(method="POST") == []
    assert len(httpx_mock.get_requests()) == migration_module.UNANSWERED_MAX_RETRIES + 1


@dataclass
class StopCase:
    name: str
    signal_number: int
    exit_code: int
    stopped_by: str


STOP_CASES = [
    StopCase(name="ctrl-c", signal_number=signal.SIGINT, exit_code=130, stopped_by="Ctrl-C"),
    StopCase(name="sigterm", signal_number=signal.SIGTERM, exit_code=143, stopped_by="SIGTERM"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in STOP_CASES])
def test_a_stop_signal_cancels_the_work_saves_the_state_and_prints_done_over_total_then_resumes(
    case: StopCase, httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    async def stop(request: httpx.Request) -> httpx.Response:
        os.kill(os.getpid(), case.signal_number)
        await asyncio.sleep(30)
        raise AssertionError("not reached")

    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))
    httpx_mock.add_callback(stop, url=f"{LIST_URL}?limit=2&start_after=b")

    result = invoke_counting(files, "--page-size", "2")

    assert result.exit_code == case.exit_code, result.stdout
    assert f"Stopped by {case.stopped_by}. Done: 2 / 3 objects (66.6%)." in text_of(result)
    assert "Run the same command again to resume" in text_of(result)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["start_after"] == "b"
    assert state["completed"] is False
    assert state["totals"]["counts"] == {"encrypted": 2}

    httpx_mock.reset()
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000&start_after=b", json=page("c"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("c"))
    resumed = invoke_counting(files, "--page-size", "2")

    assert resumed.exit_code == 0, resumed.stdout
    assert "Already handled in earlier runs: 2 objects" in resumed.stdout
    assert "To process: 1 objects (100 B)" in resumed.stdout
    assert "3 / 3 objects (100.0%)" in resumed.stdout
    assert [json.loads(r.content)["identifiers"] for r in httpx_mock.get_requests(method="POST")] == [["c"]]


def encrypt_until(
    trouble_at: str, trouble: Callable[[], Awaitable[httpx.Response]]
) -> Callable[..., Awaitable[httpx.Response]]:
    """Answer every batch as encrypted, except the batch that holds `trouble_at`, which gets `trouble`."""

    async def handler(request: httpx.Request) -> httpx.Response:
        identifiers = json.loads(request.content)["identifiers"]
        if trouble_at in identifiers:
            return await trouble()
        return httpx.Response(200, json=answer(*identifiers))

    return handler


def stop_with(signal_number: int) -> Callable[[], Awaitable[httpx.Response]]:
    async def stop() -> httpx.Response:
        os.kill(os.getpid(), signal_number)
        await asyncio.sleep(30)
        raise AssertionError("not reached")

    return stop


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in STOP_CASES])
def test_a_stop_in_a_single_page_shows_what_the_server_confirmed_in_it_and_says_no_position_was_saved(
    case: StopCase, httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", "d"))
    httpx_mock.add_callback(encrypt_until("c", stop_with(case.signal_number)), method="POST", url=BATCH_URL)

    result = invoke(files, "--batch-size", "2", "--concurrency", "1")

    output = squeezed(result)
    assert result.exit_code == case.exit_code, result.stdout
    assert "encrypted (interrupted page, not saved) │ 2" in output
    assert "Bytes encrypted (interrupted page, not saved) │ 200" in output
    assert "Bytes encrypted │ 0" in output
    assert "Objects per second │ 0.0" not in output
    assert "the server reports the objects it already encrypted as already_encrypted" in output
    assert "No page was complete, so no position was saved" in output
    assert f"Stopped by {case.stopped_by}. Done: 2 objects." in output
    assert not (tmp_path / "state.json").exists()


def test_a_stop_in_a_later_page_keeps_the_saved_totals_and_shows_the_interrupted_page_apart(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2", json=page("a", "b", next_start_after="b"))
    httpx_mock.add_response(url=f"{LIST_URL}?limit=2&start_after=b", json=page("c", "d", next_start_after="d"))
    httpx_mock.add_callback(encrypt_until("d", stop_with(signal.SIGINT)), method="POST", url=BATCH_URL)

    result = invoke(files, "--page-size", "2", "--batch-size", "1", "--concurrency", "1")

    output = squeezed(result)
    assert result.exit_code == 130, result.stdout
    assert "│ encrypted │ 2 │" in output
    assert "encrypted (interrupted page, not saved) │ 1" in output
    assert "Bytes encrypted │ 200" in output
    assert "Bytes encrypted (interrupted page, not saved) │ 100" in output
    assert "No page was complete" not in output
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["start_after"] == "b"
    assert state["totals"]["counts"] == {"encrypted": 2}
    assert state["totals"]["bytes_encrypted"] == 200


def test_an_error_in_a_page_shows_what_the_server_confirmed_before_it_and_exits_2(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    async def refuse() -> httpx.Response:
        return httpx.Response(403, json={"detail": "no"})

    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b", "c", "d"))
    httpx_mock.add_callback(encrypt_until("c", refuse), method="POST", url=BATCH_URL)

    result = invoke(files, "--batch-size", "2", "--concurrency", "1")

    output = squeezed(result)
    assert result.exit_code == 2, result.stdout
    assert "encrypted (interrupted page, not saved) │ 2" in output
    assert "No page was complete, so no position was saved" in output
    assert not (tmp_path / "state.json").exists()


def test_a_complete_run_shows_no_interrupted_page_rows_and_no_note(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a", "b"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", "b"))

    result = invoke(files)

    assert result.exit_code == 0, result.stdout
    assert "interrupted page" not in result.stdout
    assert "No page was complete" not in result.stdout


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in STOP_CASES])
def test_a_stop_signal_during_the_count_saves_nothing_and_says_so(
    case: StopCase, httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    async def stop(request: httpx.Request) -> httpx.Response:
        os.kill(os.getpid(), case.signal_number)
        await asyncio.sleep(30)
        raise AssertionError("not reached")

    httpx_mock.add_callback(stop, url=f"{LIST_URL}?limit=5000")

    result = invoke_counting(files)

    assert result.exit_code == case.exit_code, result.stdout
    assert f"Stopped by {case.stopped_by}." in text_of(result)
    assert "Nothing was saved to resume from" in text_of(result)
    assert httpx_mock.get_requests(method="POST") == []
    assert not (tmp_path / "state.json").exists()


def test_a_failed_object_still_gives_exit_code_1_when_the_run_counted(httpx_mock: HTTPXMock, files: list[str]) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, json=answer("a", outcome="failed", reason="disk full"))

    assert invoke_counting(files).exit_code == 1


def make_encryptor(tmp_path: Path, *, dry_run: bool = False) -> StorageEncryptor:
    options = Options(state_file=tmp_path / "state.json", report=tmp_path / "report.jsonl", dry_run=dry_run)
    return StorageEncryptor(options=options, address=BASE)


async def test_the_progress_line_printed_when_the_output_is_not_a_terminal_shows_total_percent_and_remaining_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(encrypt_module, "PROGRESS_LINE_SECONDS", 0.3)
    monkeypatch.setattr(encrypt_module, "PROGRESS_LIVE_SECONDS", 0.02)
    clock = {"now": 0.0}

    class FakeClockModule:
        @staticmethod
        def monotonic() -> float:
            return clock["now"]

    monkeypatch.setattr(encrypt_module, "time", FakeClockModule)
    encryptor = make_encryptor(tmp_path)
    encryptor.remaining_objects = 1000
    encryptor.remaining_bytes = 100_000

    async def advance() -> None:
        # 100 objects/s: 0.1 s of the fake clock for each 10 objects.
        for _ in range(60):
            clock["now"] += 0.1
            encryptor.objects_confirmed += 10
            encryptor.bytes_confirmed += 1000
            await asyncio.sleep(0.01)

    with encrypt_module.console.capture() as capture:
        task = asyncio.create_task(encrypt_module._show_progress(encryptor))
        await advance()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    lines = [line for line in capture.get().splitlines() if "objects" in line]
    assert lines, capture.get()
    last = lines[-1]
    assert "/ 1,000 objects (" in last
    assert "estimating" not in last
    assert " objects/s | remaining " in last
    assert "%)" in last
    assert "remaining" in last
    assert " / 100.0 kB" in last
    assert "limit " in last
    assert "429: 0" in last
    assert "retries: 0" in last


@dataclass
class FreezeCase:
    name: str
    frozen_seconds: int


FREEZE_CASES = [
    FreezeCase(name="one-minute", frozen_seconds=60),
    FreezeCase(name="six-minutes", frozen_seconds=360),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in FREEZE_CASES])
async def test_the_remaining_time_after_the_process_was_frozen_is_estimating_and_then_right(
    case: FreezeCase, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = {"now": 1000.0}

    class FakeClockModule:
        @staticmethod
        def monotonic() -> float:
            return clock["now"]

    monkeypatch.setattr(encrypt_module, "time", FakeClockModule)
    encryptor = make_encryptor(tmp_path)
    encryptor.remaining_objects = 100_000
    encryptor.remaining_bytes = 10_000_000
    progress = encrypt_module._Progress(encryptor)

    def run(seconds: float) -> str:
        """Run at 100 objects/s, with a progress line every 0.5 s; return the last line."""
        line = ""
        for _ in range(int(seconds * 2)):
            clock["now"] += 0.5
            encryptor.objects_confirmed += 50
            line = progress.line()
        return line

    run(30)
    # The process is stopped: the clock moves and the count does not; a batch that was in flight completes on resume.
    clock["now"] += case.frozen_seconds
    encryptor.objects_confirmed += 50
    assert "remaining estimating" in progress.line()

    line = run(5)

    shown = line.split("remaining ")[1].split(" | ")[0]
    minutes, seconds = shown.rstrip("s").split("m ")
    expected = (100_000 - encryptor.objects_confirmed) / 100
    assert int(minutes) * 60 + int(seconds) == pytest.approx(expected, rel=0.05)


async def test_the_progress_line_while_counting_shows_the_objects_counted_so_far(tmp_path: Path) -> None:
    encryptor = make_encryptor(tmp_path)
    encryptor.counting = True
    encryptor.counted_objects = 12345

    line = encrypt_module._Progress(encryptor).line()

    assert line == "Counting the objects to process: 12,345 so far"


async def test_the_progress_line_without_a_total_shows_no_percent(tmp_path: Path) -> None:
    encryptor = make_encryptor(tmp_path)
    encryptor.objects_confirmed = 40

    line = encrypt_module._Progress(encryptor).line()

    assert line.startswith("40 objects | estimating | ")
    assert "%" not in line
    assert "remaining" not in line


async def test_the_progress_line_of_a_dry_run_counts_the_objects_listed(tmp_path: Path) -> None:
    encryptor = make_encryptor(tmp_path, dry_run=True)
    encryptor.totals.objects_listed = 7
    encryptor.totals.bytes_listed = 7000

    line = encrypt_module._Progress(encryptor).line()

    assert line.startswith("7 objects | estimating | 7.0 kB | ")


def test_a_missing_directory_for_the_state_file_exits_2_before_any_request(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    files = ["--state-file", str(tmp_path / "missing" / "state.json"), *files[2:]]

    result = invoke_counting(files)

    assert result.exit_code == 2
    assert "directory of --state-file" in result.stdout.replace("\n", " ")
    assert httpx_mock.get_requests() == []


def test_a_missing_directory_for_the_report_exits_2_before_the_count(
    httpx_mock: HTTPXMock, files: list[str], tmp_path: Path
) -> None:
    files = [*files[:2], "--report", str(tmp_path / "missing" / "report.jsonl")]

    result = invoke_counting(files)

    assert result.exit_code == 2
    assert "directory of --report" in result.stdout.replace("\n", " ")
    assert httpx_mock.get_requests() == []


def test_a_dry_run_needs_neither_directory(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    missing = ["--state-file", str(tmp_path / "x" / "s.json"), "--report", str(tmp_path / "y" / "r.jsonl")]

    result = invoke(missing, "--dry-run")

    assert result.exit_code == 0, result.stdout


def test_a_run_with_a_username_renews_an_expired_token_and_goes_on(
    httpx_mock: HTTPXMock, files: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INFRAHUB_USERNAME", "admin")
    monkeypatch.setenv("INFRAHUB_PASSWORD", "secret")
    expired = {"errors": [{"message": "Expired Signature", "extensions": {"code": 401}}]}
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/api/auth/login",
        json={"access_token": "old", "refresh_token": "refresh"},
    )
    httpx_mock.add_response(method="POST", url=f"{BASE}/api/auth/refresh", json={"access_token": "new"})
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(
        method="POST", url=BATCH_URL, status_code=401, json=expired, match_headers={"Authorization": "Bearer old"}
    )
    httpx_mock.add_response(
        method="POST", url=BATCH_URL, json=answer("a"), match_headers={"Authorization": "Bearer new"}
    )

    result = invoke(files)

    assert result.exit_code == 0, result.stdout
    assert len(httpx_mock.get_requests(url=f"{BASE}/api/auth/refresh")) == 1


def test_a_run_with_an_api_token_stops_on_a_401_with_the_clear_message(
    httpx_mock: HTTPXMock, files: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config.SETTINGS.active, "api_token", "secret-token")
    expired = {"errors": [{"message": "Expired Signature", "extensions": {"code": 401}}]}
    httpx_mock.add_response(url=f"{LIST_URL}?limit=5000", json=page("a"))
    httpx_mock.add_response(method="POST", url=BATCH_URL, status_code=401, json=expired)

    result = invoke(files)

    assert result.exit_code == 2
    assert "does not accept the token or credentials" in result.stdout.replace("\n", " ")
    assert len(httpx_mock.get_requests(method="POST", url=BATCH_URL)) == 1
