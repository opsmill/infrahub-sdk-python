from __future__ import annotations

import inspect
import pickle  # noqa: S403 - round-tripping our own exception, no untrusted data involved
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from infrahub_sdk.exceptions import GraphQLError, ServerNotResponsiveError, TrackingGroupCleanupError
from infrahub_sdk.query_groups import (
    InfrahubGroupContext,
    InfrahubGroupContextBase,
    InfrahubGroupContextSync,
    ReapResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

async_methods = [method for method in dir(InfrahubGroupContext) if not method.startswith("_")]
sync_methods = [method for method in dir(InfrahubGroupContextSync) if not method.startswith("_")]

client_types = ["standard", "sync"]

GROUP_ID = "gggggggg-gggg-gggg-gggg-gggggggggggg"
TAG_ID = "tttttttt-tttt-tttt-tttt-tttttttttttt"
IDENTIFIER = "unit-tracking"

MANDATORY_RELATIONSHIP_ERROR = (
    "Cannot delete TestingPerson 'pppp'. It is linked to mandatory relationship owner on node TestingCat 'cccc'"
)
MISSING_NODE_ERROR = "Unable to find the node BuiltinTag/tttt in the database."


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


@dataclass
class AlreadyDeletedCase:
    name: str
    errors: list[dict[str, Any]]
    expected: bool


ALREADY_DELETED_CASES = [
    AlreadyDeletedCase(name="missing-node", errors=[{"message": MISSING_NODE_ERROR}], expected=True),
    AlreadyDeletedCase(name="refusal", errors=[{"message": MANDATORY_RELATIONSHIP_ERROR}], expected=False),
    AlreadyDeletedCase(
        name="missing-node-and-refusal",
        errors=[{"message": MISSING_NODE_ERROR}, {"message": MANDATORY_RELATIONSHIP_ERROR}],
        expected=False,
    ),
    AlreadyDeletedCase(name="no-errors", errors=[], expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in ALREADY_DELETED_CASES])
def test_is_already_deleted(case: AlreadyDeletedCase) -> None:
    """A cascade-deleted member is tolerated, but a refusal alongside it must not be."""
    exc = GraphQLError(errors=case.errors, query="mutation BuiltinTagDelete { BuiltinTagDelete { ok } }")
    assert InfrahubGroupContextBase._is_already_deleted(exc) is case.expected


def test_failure_reason_omits_the_query() -> None:
    query = 'mutation TestingPersonDelete { TestingPersonDelete(data: {id: "pppp"}) { ok } }'
    exc = GraphQLError(errors=[{"message": MANDATORY_RELATIONSHIP_ERROR, "path": ["TestingPersonDelete"]}], query=query)

    reason = InfrahubGroupContextBase._failure_reason(exc)

    assert reason == MANDATORY_RELATIONSHIP_ERROR
    assert query not in reason


def test_failure_reason_of_a_non_graphql_error() -> None:
    assert InfrahubGroupContextBase._failure_reason(httpx.ReadTimeout("read timed out")) == "read timed out"


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
    """A transport failure mid-reap must not skip the upsert that keeps the member reachable."""
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", json=_group_query_response(member_ids=[TAG_ID])
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
    # The member the reap never got through stays in the group so a later run retries it.
    assert TAG_ID in requests[-1].read().decode()


def test_reap_result_retains_refused_and_unattempted_members() -> None:
    result = ReapResult(refused={"refused1": MANDATORY_RELATIONSHIP_ERROR}, unattempted=["unattempted1"])
    assert result.retained_member_ids == ["refused1", "unattempted1"]
    assert ReapResult().retained_member_ids == []
