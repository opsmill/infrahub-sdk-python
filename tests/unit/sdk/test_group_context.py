from __future__ import annotations

import inspect
import json
import pickle  # noqa: S403 - round-tripping our own exception, no untrusted data involved
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from infrahub_sdk import query_groups
from infrahub_sdk.exceptions import (
    BranchNotFoundError,
    GraphQLError,
    MergeInProgressError,
    NodeNotFoundError,
    RateLimitError,
    SchemaNotFoundError,
    ServerNotReachableError,
    ServerNotResponsiveError,
    TrackingGroupCleanupError,
    URLNotFoundError,
    graphql_error_from_response,
)
from infrahub_sdk.query_groups import (
    InfrahubGroupContext,
    InfrahubGroupContextBase,
    InfrahubGroupContextSync,
    ReapResult,
)
from tests.helpers.fixtures import read_fixture

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

async_methods = [method for method in dir(InfrahubGroupContext) if not method.startswith("_")]
sync_methods = [method for method in dir(InfrahubGroupContextSync) if not method.startswith("_")]

client_types = ["standard", "sync"]

GROUP_ID = "gggggggg-gggg-gggg-gggg-gggggggggggg"
TAG_ID = "tttttttt-tttt-tttt-tttt-tttttttttttt"
SECOND_TAG_ID = "uuuuuuuu-uuuu-uuuu-uuuu-uuuuuuuuuuuu"
THIRD_TAG_ID = "vvvvvvvv-vvvv-vvvv-vvvv-vvvvvvvvvvvv"
IDENTIFIER = "unit-tracking"

MANDATORY_RELATIONSHIP_ERROR = (
    "Cannot delete TestingPerson 'pppp'. It is linked to mandatory relationship owner on node TestingCat 'cccc'"
)
MISSING_NODE_ERROR = "Unable to find the node BuiltinTag/tttt in the database."
DELETE_QUERY = 'mutation BuiltinTagDelete { BuiltinTagDelete(data: {id: "tttt"}) { ok } }'


async def test_method_sanity() -> None:
    """Validate that there is at least one public method and that both clients look the same."""
    assert async_methods
    assert async_methods == sync_methods


@pytest.mark.parametrize("method", async_methods)
async def test_validate_method_signature(
    method: str,
    replace_sync_return_annotation: Callable[[str], str],
    replace_async_return_annotation: Callable[[str], str],
) -> None:
    async_method = getattr(InfrahubGroupContext, method)
    sync_method = getattr(InfrahubGroupContextSync, method)
    async_sig = inspect.signature(async_method)
    sync_sig = inspect.signature(sync_method)
    assert async_sig.parameters == sync_sig.parameters
    assert async_sig.return_annotation == replace_sync_return_annotation(sync_sig.return_annotation)
    assert replace_async_return_annotation(async_sig.return_annotation) == sync_sig.return_annotation


def test_set_properties() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert context.identifier == "MYID"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"}, delete_unused_nodes=True)
    assert context.identifier == "MYID"
    assert context.params == {"one": 1, "two": "two"}
    assert context.delete_unused_nodes is True


def test_get_params_as_str() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._get_params_as_str() == "one: 1, two: two"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert not context._get_params_as_str()


def test_generate_group_name() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert context._generate_group_name() == "MYID"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_name() == "MYID-11aaec5206c3dca37cbbcaaabf121550"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_name(suffix="xxx") == "MYID-xxx-11aaec5206c3dca37cbbcaaabf121550"


def test_generate_group_description(std_group_schema: NodeSchemaAPI) -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert not context._generate_group_description(schema=std_group_schema)

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_description(schema=std_group_schema) == "one: 1, two: two"

    assert std_group_schema.attributes[1].name == "description"
    std_group_schema.attributes[1].max_length = 20
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": "xxxxxxxxxxx", "two": "yyyyyyyyyyy"})
    assert context._generate_group_description(schema=std_group_schema) == "one: xxxxxxxxxx..."


def test_get_members_combines_groups_and_nodes() -> None:
    context = InfrahubGroupContextBase()
    context.related_group_ids = ["group1"]
    context.related_node_ids = ["node1", "node2"]
    assert context._get_members() == ["group1", "node1", "node2"]


def test_set_unused_member_ids_diffs_against_the_previous_run() -> None:
    context = InfrahubGroupContextBase()
    context._set_unused_member_ids(previous_member_ids=["kept", "dropped"], members=["kept", "added"])
    assert context.unused_member_ids == ["dropped"]

    context._set_unused_member_ids(previous_member_ids=["gone1", "gone2"], members=[])
    assert sorted(context.unused_member_ids or []) == ["gone1", "gone2"]


def catalogue_error(code: str) -> GraphQLError:
    """The exception the GraphQL path raises for a catalogue code's recorded server response."""
    envelope = json.loads(read_fixture(file_name=f"{code}.json", fixture_subdir="error_catalogue/codes"))
    return graphql_error_from_response(errors=envelope["errors"], query=DELETE_QUERY)


def uncoded_error(message: str) -> GraphQLError:
    """What a server older than the error catalogue reports: a message and no extensions."""
    return graphql_error_from_response(errors=[{"message": message}], query=DELETE_QUERY)


def test_a_coded_missing_node_is_raised_as_node_not_found() -> None:
    """The reap's `except NodeNotFoundError` clause is what tolerates a cascade-deleted member."""
    assert isinstance(catalogue_error("node_not_found"), NodeNotFoundError)


@dataclass
class ReapFailureCase:
    name: str
    build: Callable[[], GraphQLError]
    about_the_member: bool


REAP_FAILURE_CASES = [
    ReapFailureCase(
        name="uncoded-refusal", build=lambda: uncoded_error(MANDATORY_RELATIONSHIP_ERROR), about_the_member=True
    ),
    ReapFailureCase(name="undefined-error", build=lambda: catalogue_error("undefined_error"), about_the_member=True),
    ReapFailureCase(
        name="permission-denied", build=lambda: catalogue_error("permission_denied"), about_the_member=True
    ),
    ReapFailureCase(
        name="schema-gone-for-the-members-kind",
        build=lambda: SchemaNotFoundError(identifier="TestingCat"),
        about_the_member=True,
    ),
    ReapFailureCase(name="token-expired", build=lambda: catalogue_error("token_expired"), about_the_member=False),
    ReapFailureCase(
        name="authentication-required", build=lambda: catalogue_error("authentication_required"), about_the_member=False
    ),
    ReapFailureCase(
        name="merge-in-progress", build=lambda: catalogue_error("merge_in_progress"), about_the_member=False
    ),
    ReapFailureCase(
        name="branch-not-found-on-server", build=lambda: catalogue_error("branch_not_found"), about_the_member=False
    ),
    ReapFailureCase(
        name="branch-not-found-in-the-sdk", build=lambda: BranchNotFoundError(identifier="gone"), about_the_member=False
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in REAP_FAILURE_CASES])
def test_about_the_member(case: ReapFailureCase) -> None:
    """Only a failure about the member is recorded against it; one about the request stops the reap.

    The GraphQL path raises an expired token as a plain `GraphQLError`, so the class alone would file
    it as a refusal of every member in turn.
    """
    assert query_groups._about_the_member(case.build()) is case.about_the_member


@dataclass
class AlreadyDeletedCase:
    name: str
    build: Callable[[], GraphQLError]
    expected: bool


ALREADY_DELETED_CASES = [
    AlreadyDeletedCase(name="legacy-missing-node", build=lambda: uncoded_error(MISSING_NODE_ERROR), expected=True),
    AlreadyDeletedCase(
        name="legacy-refusal", build=lambda: uncoded_error(MANDATORY_RELATIONSHIP_ERROR), expected=False
    ),
    AlreadyDeletedCase(
        name="coded-failure-with-the-same-wording",
        build=lambda: graphql_error_from_response(
            errors=[{"message": MISSING_NODE_ERROR, "extensions": {"code": "UNDEFINED_ERROR"}}], query=DELETE_QUERY
        ),
        expected=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in ALREADY_DELETED_CASES])
def test_node_already_deleted(case: AlreadyDeletedCase) -> None:
    """The wording only stands in for the code on a server that predates the catalogue."""
    assert query_groups._node_already_deleted(case.build()) is case.expected


def test_failure_reason_of_a_described_code_names_it_without_the_query() -> None:
    reason = query_groups._failure_reason(catalogue_error("uniqueness_violation"))

    assert reason.startswith("UNIQUENESS_VIOLATION: ")
    assert DELETE_QUERY not in reason


def test_failure_reason_of_an_undescribed_failure_is_the_server_message_alone() -> None:
    assert query_groups._failure_reason(uncoded_error(MANDATORY_RELATIONSHIP_ERROR)) == MANDATORY_RELATIONSHIP_ERROR


def test_tracking_group_cleanup_error_survives_serialization() -> None:
    """The exception crosses a task-orchestrator boundary, which serializes failed runs."""
    failures = {TAG_ID: MANDATORY_RELATIONSHIP_ERROR}

    restored = pickle.loads(pickle.dumps(TrackingGroupCleanupError(failures=failures)))  # noqa: S301

    assert restored.failures == failures
    assert str(restored) == str(TrackingGroupCleanupError(failures=failures))


def _group_query_response(member_ids: list[str]) -> dict[str, Any]:
    return {
        "data": {
            "CoreStandardGroup": {
                "count": 1,
                "edges": [
                    {
                        "node": {
                            "id": GROUP_ID,
                            "display_label": IDENTIFIER,
                            "__typename": "CoreStandardGroup",
                            "name": {"value": IDENTIFIER, "is_default": False, "is_from_profile": False},
                            "description": {"value": None, "is_default": True, "is_from_profile": False},
                            "members": {
                                "count": len(member_ids),
                                "edges": [
                                    {"node": {"id": member_id, "display_label": member_id, "__typename": "BuiltinTag"}}
                                    for member_id in member_ids
                                ],
                            },
                        }
                    }
                ],
            }
        }
    }


NO_GROUP_RESPONSE: dict[str, Any] = {"data": {"CoreStandardGroup": {"count": 0, "edges": []}}}


async def _track_nothing(clients: BothClients, client_type: str, schema: dict) -> None:
    """Run a tracking block that saves no node, on whichever client is under test."""
    if client_type == "standard":
        clients.standard.schema.set_cache(schema=schema, branch="main")
        async with clients.standard.start_tracking(identifier=IDENTIFIER, delete_unused_nodes=True):
            pass
        return

    clients.sync.schema.set_cache(schema=schema, branch="main")
    with clients.sync.start_tracking(identifier=IDENTIFIER, delete_unused_nodes=True):
        pass


@pytest.mark.parametrize("client_type", client_types)
async def test_zero_member_run_without_group_issues_no_mutation(
    clients: BothClients, client_type: str, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """A run that tracked nothing and finds no group must not create an empty one."""
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=NO_GROUP_RESPONSE)

    await _track_nothing(clients=clients, client_type=client_type, schema=schema_query_05_data)

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize("client_type", client_types)
async def test_zero_member_run_with_empty_group_issues_no_mutation(
    clients: BothClients, client_type: str, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """Repeated zero-member runs settle on the lookup alone once the group is empty."""
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=_group_query_response(member_ids=[]))

    await _track_nothing(clients=clients, client_type=client_type, schema=schema_query_05_data)

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize("client_type", client_types)
async def test_failed_reap_still_records_the_membership(
    clients: BothClients, client_type: str, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """A transport failure mid-reap must not skip the upsert that keeps the unreached members."""
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", json=_group_query_response(member_ids=[TAG_ID, SECOND_TAG_ID])
    )
    httpx_mock.add_exception(httpx.ReadTimeout("read timed out"), method="POST", url="http://mock/graphql/main")
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {"CoreStandardGroupUpsert": {"ok": True, "object": {"id": GROUP_ID}}}},
    )

    # The failure is reported as itself, not blamed on the member it interrupted.
    with pytest.raises(ServerNotResponsiveError, match="Unable to read from"):
        await _track_nothing(clients=clients, client_type=client_type, schema=schema_query_05_data)

    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    upsert = requests[-1].read().decode()
    # The member never reached stays in the group so a later run retries it.
    assert SECOND_TAG_ID in upsert
    # Without an answer the interrupted delete may have gone through; naming a node that no
    # longer exists would make the server reject the whole write.
    assert TAG_ID not in upsert


@pytest.mark.parametrize("client_type", client_types)
async def test_interrupted_reap_keeps_only_the_members_it_never_reached(
    clients: BothClients, client_type: str, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """The deleted member and the interrupted one are dropped; the one never reached is kept."""
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_group_query_response(member_ids=[TAG_ID, SECOND_TAG_ID, THIRD_TAG_ID]),
    )
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", json={"data": {"BuiltinTagDelete": {"ok": True}}}
    )
    httpx_mock.add_exception(httpx.ReadTimeout("read timed out"), method="POST", url="http://mock/graphql/main")
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {"CoreStandardGroupUpsert": {"ok": True, "object": {"id": GROUP_ID}}}},
    )

    with pytest.raises(ServerNotResponsiveError, match="Unable to read from"):
        await _track_nothing(clients=clients, client_type=client_type, schema=schema_query_05_data)

    upsert = httpx_mock.get_requests()[-1].read().decode()
    assert THIRD_TAG_ID in upsert
    assert SECOND_TAG_ID not in upsert
    assert TAG_ID not in upsert


def code_response(code: str) -> dict[str, Any]:
    return json.loads(read_fixture(file_name=f"{code}.json", fixture_subdir="error_catalogue/codes"))


UPSERT_RESPONSE: dict[str, Any] = {"data": {"CoreStandardGroupUpsert": {"ok": True, "object": {"id": GROUP_ID}}}}


@pytest.mark.parametrize("client_type", client_types)
async def test_cascade_deleted_member_is_dropped_without_a_failure(
    clients: BothClients, client_type: str, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """A server-coded NODE_NOT_FOUND means another delete already took the member."""
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", json=_group_query_response(member_ids=[TAG_ID])
    )
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=code_response("node_not_found"))
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=UPSERT_RESPONSE)

    await _track_nothing(clients=clients, client_type=client_type, schema=schema_query_05_data)

    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    assert TAG_ID not in requests[-1].read().decode()


@pytest.mark.parametrize("client_type", client_types)
async def test_locked_branch_stops_the_reap_instead_of_blaming_each_member(
    clients: BothClients, client_type: str, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """A coded failure about the request is not recorded against the member it interrupted.

    Both members stay in the group: the server answered, so the interrupted delete removed nothing,
    and the second was never attempted. The failure surfaces as itself rather than as a cleanup
    error listing every member.
    """
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", json=_group_query_response(member_ids=[TAG_ID, SECOND_TAG_ID])
    )
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=code_response("merge_in_progress"))
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=UPSERT_RESPONSE)

    with pytest.raises(MergeInProgressError, match=r"^MERGE_IN_PROGRESS: "):
        await _track_nothing(clients=clients, client_type=client_type, schema=schema_query_05_data)

    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    upsert = requests[-1].read().decode()
    assert TAG_ID in upsert
    assert SECOND_TAG_ID in upsert


@pytest.mark.parametrize("client_type", client_types)
async def test_failed_write_does_not_replace_the_error_that_stopped_the_reap(
    clients: BothClients, client_type: str, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """The write after an interrupted reap usually fails too; the reap's own error is still raised."""
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", json=_group_query_response(member_ids=[TAG_ID])
    )
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=code_response("merge_in_progress"))
    httpx_mock.add_exception(httpx.ReadTimeout("read timed out"), method="POST", url="http://mock/graphql/main")

    with pytest.raises(MergeInProgressError, match=r"^MERGE_IN_PROGRESS: ") as exc_info:
        await _track_nothing(clients=clients, client_type=client_type, schema=schema_query_05_data)

    assert isinstance(exc_info.value.__cause__, ServerNotResponsiveError)


@dataclass
class InterruptionCase:
    name: str
    build: Callable[[], Exception]
    interrupted_member_kept: bool


INTERRUPTION_CASES = [
    InterruptionCase(
        name="coded-request-failure", build=lambda: catalogue_error("merge_in_progress"), interrupted_member_kept=True
    ),
    InterruptionCase(
        name="rate-limited",
        build=lambda: RateLimitError(url="http://mock/graphql/main", attempts=3),
        interrupted_member_kept=True,
    ),
    InterruptionCase(
        name="endpoint-not-found",
        build=lambda: URLNotFoundError(url="http://mock/graphql/main"),
        interrupted_member_kept=True,
    ),
    InterruptionCase(
        name="timeout",
        build=lambda: ServerNotResponsiveError(url="http://mock/graphql/main"),
        interrupted_member_kept=False,
    ),
    InterruptionCase(
        name="connection-lost",
        build=lambda: ServerNotReachableError(address="http://mock"),
        interrupted_member_kept=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in INTERRUPTION_CASES])
def test_interrupted_member_is_kept_only_when_the_server_rejected_the_delete(case: InterruptionCase) -> None:
    """A rejected delete removed nothing; without an answer the delete may have gone through."""
    result = ReapResult()
    candidates = [("BuiltinTag", TAG_ID), ("BuiltinTag", SECOND_TAG_ID)]

    stopped = query_groups._record_failure(result=result, exc=case.build(), candidates=candidates, position=0)

    assert stopped is True
    expected = [TAG_ID, SECOND_TAG_ID] if case.interrupted_member_kept else [SECOND_TAG_ID]
    assert result.unattempted == expected


def test_no_existing_group_leaves_nothing_to_reap_on_a_reused_context() -> None:
    """A context reused after an earlier lookup must not reap that lookup's members against this run."""
    context = InfrahubGroupContextBase()
    context.unused_member_ids = [TAG_ID]

    assert context._reconcile_with(existing_group=None, members=[]) == []
    assert context.unused_member_ids is None
    assert context.previous_members is None
    assert context._reap_candidates() == []


def test_reap_result_failure_prefers_the_error_that_stopped_the_reap() -> None:
    """A reap that was stopped raises its own error, even when members were refused before that."""
    interruption = ServerNotResponsiveError(url="http://mock/graphql/main")
    refusals = {"refused1": MANDATORY_RELATIONSHIP_ERROR}

    assert ReapResult(refused=refusals, error=interruption).failure() is interruption

    failure = ReapResult(refused=refusals).failure()
    assert isinstance(failure, TrackingGroupCleanupError)
    assert failure.failures == refusals

    assert ReapResult().failure() is None


def test_reap_result_retains_refused_and_unattempted_members() -> None:
    result = ReapResult(refused={"refused1": MANDATORY_RELATIONSHIP_ERROR}, unattempted=["unattempted1"])
    assert result.retained_member_ids == ["refused1", "unattempted1"]
    assert ReapResult().retained_member_ids == []
